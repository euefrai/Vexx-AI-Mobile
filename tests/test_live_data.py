import copy
import gzip
from datetime import datetime, timezone
from email.message import Message
from email.utils import format_datetime
import io

import pytest
import live_data as live
import pc_agent
import research

NOW=datetime(2026,10,17,12,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_cache():
    live._cache.clear()
    yield
    live._cache.clear()


@pytest.mark.parametrize('text,kind',[
    ('qual o clima agora','weather'),('Vai chover amanhã em Recife?','weather'),
    ('Qual a previsão para amanhã em Salvador, Bahia?','weather'),('Como está o tempo hoje?','weather'),
    ('notícias','news'),('Últimas notícias sobre tecnologia','news'),('Que horas são em Tóquio?','clock'),
    ('Qual é a data?','clock'),('Explique a diferença entre tempo e clima',None),
    ('Qual a temperatura da CPU?',None),('Escreva uma notícia sobre o clima',None),('Quanto tempo de resposta?',None)])
def test_routing(text,kind):
    req=live.request(text)
    assert (req or {}).get('kind')==kind


def weather_data():
    return {'timezone':'America/Bahia','current':{'time':'2026-10-17T09:00','temperature_2m':26,
            'apparent_temperature':28,'relative_humidity_2m':80,'wind_speed_10m':12,'weather_code':2},
            'current_units':{'temperature_2m':'°C','wind_speed_10m':'km/h'},
            'daily':{'time':['2026-10-17','2026-10-18'],'temperature_2m_min':[24,25],
                     'temperature_2m_max':[29,30],'precipitation_probability_max':[15,65],'weather_code':[2,61]}}


def test_weather_cache_freshness_units_and_missing_values(monkeypatch):
    calls=[]
    def get(base,params):calls.append(params);return weather_data()
    monkeypatch.setattr(live,'get_json',get)
    ctx={'coordinates':(-12.97,-38.5)}
    result=live.weather('vai chover amanhã',ctx,NOW)
    assert '26 °C' in result and '18/10' in result and '65%' in result
    assert '17/10/2026 às 09:00' in result and 'Open-Meteo' in result
    live.weather('clima agora',ctx,NOW)
    assert len(calls)==1
    assert 'fora da janela' in live.weather('clima agora',ctx,NOW.replace(hour=16))
    live._cache.clear()
    def missing(*_):
        data=weather_data();data['current']['temperature_2m']=None;return data
    monkeypatch.setattr(live,'get_json',missing)
    with pytest.raises(ValueError):live.weather('clima',ctx,NOW)


def test_location_required_explicit_overrides_and_ambiguity(monkeypatch):
    monkeypatch.setattr(live,'get_json',lambda *_:pytest.fail('No network without location'))
    assert live.respond('qual o clima agora',{})==live.LOCATION_PROMPT
    rows=[dict(name='Springfield',admin1='A',country='US',feature_code='PPL',latitude=10,longitude=20),
          dict(name='Springfield',admin1='B',country='US',feature_code='PPL',latitude=11,longitude=21)]
    monkeypatch.setattr(live,'get_json',lambda *_:{'results':rows})
    assert 'mais de uma' in live.geocode('Springfield')[1]
    assert live.place_from('Como está o clima em Lisboa hoje?')=='Lisboa'
    seen=[]
    monkeypatch.setattr(live,'geocode',lambda city:(seen.append(city) or None,'cidade teste'))
    assert live.weather('clima em Lisboa',{'city':'Recife','coordinates':(0,0)},NOW)=='cidade teste'
    assert seen==['Lisboa']


def test_no_lookup_when_forbidden_or_historical(monkeypatch):
    monkeypatch.setattr(live,'get_json',lambda *_:pytest.fail('No unsupported lookup'))
    assert live.request('Não pesquise notícias agora') is None
    assert 'até 7 dias' in live.respond('Clima ontem em Recife',{})
    assert live.request('Data atual')['kind']=='clock'


def test_news_dates_links_topic_and_gzip_timezone(monkeypatch):
    def item(title,url,date):return {'titulo':title,'url':url,'meta':{'publicado_em':date}}
    date=format_datetime(NOW)
    rows=[item('Tecnologia <script>alert(1)</script>','https://example.org/news',date),
          item('Tecnologia antiga','https://example.org/old','Mon, 01 Jan 2024 00:00:00 GMT'),
          item('Tecnologia sem data','https://example.org/no',''),
          item('Tecnologia perigosa','javascript:alert(1)',date),
          item('Tecnologia anúncio','https://example.org/especial-publicitario/x',date)]
    monkeypatch.setattr(live.search_providers,'buscar_bing_news',lambda *a,**k:rows)
    result=live.news('notícias de tecnologia',{'timezone':'America/Bahia'},NOW)
    assert '— tecnologia' in result
    assert 'example.org/news' in result and '<script>' not in result
    assert '/old' not in result and 'perigosa' not in result and 'anúncio' not in result
    assert 'artigos completos não foram lidos' in result
    live._cache.clear()
    monkeypatch.setattr(live.search_providers,'buscar_bing_news',lambda *a,**k:[])
    xml='<rss><channel><item><title>Agora</title><link>https://example.org/new</link><pubDate>Sat, 17 Oct 2026 11:00:00 -0000</pubDate></item></channel></rss>'
    monkeypatch.setattr(research,'baixar',lambda *a,**k:('https://example.org',xml))
    assert 'Agora' in live.news('notícias de hoje',{'timezone':'America/Bahia'},NOW)


def test_unavailable_never_invents(monkeypatch):
    monkeypatch.setattr(live,'get_json',lambda *a:(_ for _ in ()).throw(research.ResearchErro('rede','rede')))
    assert 'indisponível' in live.respond('clima em Salvador',{})


def test_clock_remote(monkeypatch):
    monkeypatch.setattr(live,'geocode',lambda city:({'label':'Tóquio, Japão','timezone':'Asia/Tokyo'},None))
    assert '21:00' in live.clock('Que horas são em Tóquio?',{},NOW)


def test_gzip_reading_and_bomb_cap(monkeypatch):
    monkeypatch.setattr(research,'url_segura',lambda url:url)
    class Response(io.BytesIO):
        status=200
        def __init__(self,data):
            super().__init__(data);self.headers=Message()
            self.headers['Content-Type']='application/xml; charset=utf-8'
            self.headers['Content-Encoding']='gzip'
    def fetch(data,limit):
        return research.baixar('https://example.org/feed',max_bytes=limit,aceitar='feed',abrir=lambda *a:Response(data))
    assert fetch(gzip.compress(b'<rss/>'),100)[1]=='<rss/>'
    with pytest.raises(research.ResearchErro,match='descompactado'):
        fetch(gzip.compress(b'x'*10000),100)
    with pytest.raises(research.ResearchErro,match='gzip'):
        fetch(b'invalid gzip',100)


def test_durable_followup_owner_sse_and_cancel(tmp_path,monkeypatch):
    path=tmp_path/'live.sqlite3';db=pc_agent.open_db(path)
    payload=dict(message_id='live-user-001',conversation_id='live-conv',owner='u-alice',text='Vai chover amanhã?')
    monkeypatch.setattr(pc_agent,'gerar_texto',lambda *a,**k:pytest.fail('No LLM for live data'))
    first=pc_agent.ai_completa(db,payload,{'model':'test'})
    assert first['response_text']==live.LOCATION_PROMPT
    monkeypatch.setattr(live,'respond',lambda text,ctx:'Clima consultado: '+text)
    assert pc_agent.cmd_dados_atuais(db,'Salvador, Bahia','u-bob','live-conv',{}) is None
    assert pc_agent.cmd_dados_atuais(db,'Salvador, Bahia','u-alice','other-conv',{}) is None
    second=pc_agent.ai_completa(db,dict(payload,message_id='live-user-002',text='Salvador, Bahia'),{'model':'test'})
    assert 'Salvador, Bahia' in second['response_text']
    assert 'Vai chover amanhã' in second['response_text']
    assert pc_agent.ai_completa(db,payload,{'model':'test'})['replay']
    db.close();events=[]
    monkeypatch.setattr(pc_agent,'enviar_ws',lambda ws,e:events.append(e))
    pc_agent.ai_stream_worker(path,{'model':'test'},dict(payload,message_id='live-user-003'),'req-live',object(),pc_agent.SessaoStream(),{})
    assert events[-1]['type']=='ai_done'
    session=pc_agent.SessaoStream();session.parar.set()
    pc_agent.ai_stream_worker(path,{'model':'test'},dict(payload,message_id='live-user-004'),'req-cancel',object(),session,{})
    assert events[-1]['type']=='ai_cancelled'
    db=pc_agent.open_db(path)
    assert pc_agent.ai_estado(db,'live-user-003','u-alice')['state']=='completed'
    assert pc_agent.ai_estado(db,'live-user-004','u-alice')['state']=='cancelled'
    db.close()
