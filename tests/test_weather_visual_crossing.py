"""Provider migration: real adapter, isolated SQLite quota, deterministic HTTP."""
import copy,json,os,subprocess,sys,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
import live_data as live
import research
REAL_DOWNLOAD=research.baixar
import jdui
from weather_fixtures import timeline

NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)
LAT,LON=-14.10,-39.52


def raw():
    d={'timezone':'America/Bahia','current':{'time':'2026-10-22T09:00','temperature_2m':26,
        'apparent_temperature':28,'relative_humidity_2m':75,'wind_speed_10m':10,'weather_code':2},
        'daily':{'time':[(NOW.date()+timedelta(days=i)).isoformat() for i in range(7)],
        'temperature_2m_min':[20]*7,'temperature_2m_max':[30]*7,'precipitation_probability_max':[40]*7,'weather_code':[2]*7}}
    return timeline(d,LAT,LON)

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    live._cache.clear()
    monkeypatch.setattr(research,'baixar',lambda *a,**k:pytest.fail('Unmocked external HTTP'))
    yield
    live._cache.clear()


def test_current_tomorrow_seven_days_share_cache_and_attribution(monkeypatch):
    calls=[]
    monkeypatch.setattr(live,'get_json',lambda base,params:calls.append((base,params)) or raw())
    for text in ('clima agora','previsão amanhã','previsão próximos sete dias'):
        result=live.weather(text,{'coordinates':(LAT,LON)},NOW)
        assert '26 °C' in result and 'Visual Crossing' in result and 'não é observação medida' in result
        assert 'Não substituem alertas oficiais' in result
        assert r'\(' not in result
        fences=jdui.extrair_fences(result);assert len(fences)==1
        ok,msg,errors=jdui.validar_mensagem(json.loads(fences[0]));assert ok and not errors
        item=msg['blocks'][0]['props']['items'][0]
        assert item['url']=='https://www.visualcrossing.com/' and 'Dados meteorológicos: Visual Crossing' in item['desc']
    assert len(calls)==1 and calls[0][0].startswith(live.VC_BASE)
    assert calls[0][1]['unitGroup']=='metric' and calls[0][1]['include']=='current,days'
    assert len([line for line in result.splitlines() if __import__('re').match(r'\| \d{2}/\d{2} \|',line)])==7


def test_missing_key_does_not_call_http(monkeypatch):
    monkeypatch.delenv('VISUAL_CROSSING_API_KEY')
    with pytest.raises(live.WeatherError,match='missing_key'):live._weather_data(LAT,LON,NOW)

@pytest.mark.parametrize('status,code',[(401,'invalid_key'),(403,'invalid_key'),(429,'rate_limited'),(503,'unavailable')])
def test_provider_failures_cooldown_redacted(monkeypatch,status,code):
    calls=[]
    def fail(*args):
        calls.append(1)
        error=research.ResearchErro('URL with key='+os.environ['VISUAL_CROSSING_API_KEY'],'rede');error.http=status
        raise error
    monkeypatch.setattr(live,'get_json',fail)
    for _ in range(2):
        with pytest.raises(live.WeatherError,match=code) as caught:live._weather_data(LAT,LON,NOW)
        assert os.environ['VISUAL_CROSSING_API_KEY'] not in str(caught.value)
    assert len(calls)==1


def test_timeout_backoff(monkeypatch):
    calls=[]
    def timeout(*args):calls.append(1);raise research.ResearchErro('network timeout','rede')
    monkeypatch.setattr(live,'get_json',timeout)
    for _ in range(2):
        with pytest.raises(live.WeatherError,match='unavailable'):live._weather_data(LAT,LON,NOW)
    assert len(calls)==1


def test_quota_is_persistent_and_rolling(monkeypatch):
    calls=[];data=raw();data['queryCost']=32
    monkeypatch.setenv('VISUAL_CROSSING_DAILY_LIMIT','32')
    monkeypatch.setattr(live,'get_json',lambda *args:calls.append(1) or data)
    live._weather_data(LAT,LON,NOW)
    live._cache.clear()
    with pytest.raises(live.WeatherError,match='local_quota'):live._weather_data(LAT+.01,LON,NOW)
    assert len(calls)==1
    original=live.time.time()
    monkeypatch.setattr(live.time,'time',lambda:original+86401)
    live._weather_data(LAT,LON,NOW)
    assert len(calls)==2


def test_cache_survives_new_process_without_secret_or_network(monkeypatch):
    monkeypatch.setattr(live,'get_json',lambda *args:raw())
    live._weather_data(LAT,LON,NOW)
    code="import live_data;from datetime import datetime;live_data.get_json=lambda *a:(_ for _ in ()).throw(AssertionError('HTTP not allowed'));print(live_data._weather_data(-14.10,-39.52,datetime.fromisoformat('2026-10-22T12:00:00+00:00'))['current']['temperature_2m'])"
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=15)
    assert r.returncode==0 and r.stdout.strip()=='26'


def test_one_concurrent_call_and_followup_reuses_result(monkeypatch):
    started=threading.Event();release=threading.Event();calls=[]
    def get(*args):calls.append(1);started.set();assert release.wait(5);return raw()
    monkeypatch.setattr(live,'get_json',get)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(live._weather_data,LAT,LON,NOW)
        assert started.wait(5)
        try:
            with pytest.raises(live.WeatherError,match='busy'):live._weather_data(LAT,LON,NOW)
        finally:release.set()
        assert first.result()['current']['temperature_2m']==26
    live._weather_data(LAT,LON,NOW)
    assert len(calls)==1


@pytest.mark.parametrize('defect',['empty','no_current','no_temp','stale','future','timezone','coordinates','units','nan','bad_days','daily_mean_only'])
def test_invalid_values_never_become_current_weather(defect):
    data=raw()
    if defect=='empty':data={}
    elif defect=='no_current':data['currentConditions']=None
    elif defect=='no_temp':data['currentConditions']['temp']=None
    elif defect=='stale':data['currentConditions']['datetimeEpoch']-=10800
    elif defect=='future':data['currentConditions']['datetimeEpoch']+=3600
    elif defect=='timezone':data['timezone']='Unknown/Fuse'
    elif defect=='coordinates':data['latitude']=10
    elif defect=='units':data['unitGroup']='us'
    elif defect=='nan':data['currentConditions']['temp']=float('nan')
    elif defect=='bad_days':data['days'][0]['tempmin']=50
    elif defect=='daily_mean_only':data.pop('currentConditions');data['days'][0]['temp']=24
    with pytest.raises((ValueError,KeyError)):live._normalize_weather(data,LAT,LON,NOW)


def test_missing_optional_values_are_not_zero(monkeypatch):
    data=raw();data['currentConditions'].update(feelslike=None,humidity=None,windspeed=None)
    monkeypatch.setattr(live,'get_json',lambda *args:data)
    result=live.weather('clima',{'coordinates':(LAT,LON)},NOW)
    assert 'sensação de não informada' in result and 'vento: não informado' in result
    assert '0 km/h' not in result and '0%' not in result


def test_current_source_and_cache_key_rotation(monkeypatch):
    data=raw();data['currentConditions']['source']='obs';calls=[]
    monkeypatch.setattr(live,'get_json',lambda *args:calls.append(1) or copy.deepcopy(data))
    assert 'Observação agregada' in live._weather_data(LAT,LON,NOW)['nature']
    monkeypatch.setenv('VISUAL_CROSSING_API_KEY','new-fixture-key')
    data['currentConditions']['temp']=27
    assert live._weather_data(LAT,LON,NOW)['current']['temperature_2m']==27 and len(calls)==2


def test_no_open_meteo_dependency_in_live_module():
    source=Path(live.__file__).read_text(encoding='utf-8').lower()
    assert 'open-meteo.com' not in source


def test_credentialed_redirect_never_reaches_another_host(monkeypatch):
    import urllib.error
    from email.message import Message
    monkeypatch.setattr(research,'baixar',REAL_DOWNLOAD)
    monkeypatch.setattr(research,'url_segura',lambda url:url)
    calls=[]
    def redirect(url,*args):
        calls.append(url.split('?')[0])
        headers=Message();headers['Location']='https://example.org/stolen?key=fixture-weather-key'
        raise urllib.error.HTTPError(url,302,'redirect',headers,None)
    monkeypatch.setattr(research,'_abrir',redirect)
    with pytest.raises(research.ResearchErro):live.get_json(live.VC_BASE+'-14.1,-39.52/next7days',{'key':'fixture-weather-key'})
    assert len(calls)==1 and calls[0].startswith(live.VC_BASE)
