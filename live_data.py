"""Dados atuais determinísticos. Fontes limitadas, sem chaves nem código do modelo."""
import copy
from decimal import InvalidOperation
import html
import json
import math
import os
import hashlib
import sqlite3
from pathlib import Path
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import xml.etree.ElementTree as ET

import research
import search_providers

UTC = timezone.utc
LOCATION_PROMPT = 'Para consultar o clima, em qual cidade você está? Informe cidade e estado/país (por exemplo, Salvador, Bahia).'
STATES = dict(zip('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(),
    ['Acre','Alagoas','Amapá','Amazonas','Bahia','Ceará','Distrito Federal','Espírito Santo','Goiás','Maranhão','Mato Grosso','Mato Grosso do Sul','Minas Gerais','Pará','Paraíba','Paraná','Pernambuco','Piauí','Rio de Janeiro','Rio Grande do Norte','Rio Grande do Sul','Rondônia','Roraima','Santa Catarina','São Paulo','Sergipe','Tocantins']))
_cache = {}
_lock = threading.Lock()


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def request(text):
    t = norm(text).strip().rstrip('.!?')
    t = re.sub(r'^(lucas|luccas)[, :]+', '', t)
    if greeting(text):return {'kind':'greeting','text':text}
    if re.search(r'\b(nao (pesquise|busque|consulte)|sem (internet|pesquisa|buscar))\b',t):return None
    if re.search(r'\b(traduza|traduzi[ra]|escreva|redija|codigo(?! ibge)|significa|defina|explique|o que e|diferenca|mudancas climaticas|clima organizacional|cpu|gpu|processador)\b', t):
        return None
    if re.search(r'\b(3d|maquete|modelo tridimensional)\b',t):return None
    import query_intelligence
    try:
        if query_intelligence.analyze(text)['domain'] == 'currency':
            return {'kind': 'currency', 'text': text}
    except ValueError:
        return None
    weather = re.search(r'\b(clima|previsao do tempo|meteorologia|temperatura|vai chover|esta chovendo|ta chovendo|chove agora)\b', t)
    weather = weather or re.search(r'\b(como (esta|ta) o tempo|tempo (agora|hoje|amanha|em))\b', t)
    weather = weather or re.search(r'\bprevisao (?:para )?(hoje|amanha|esta semana|os proximos)\b', t)
    if weather:
        return {'kind':'weather','text':text}
    if re.search(r'\b(onde fica|localize (?:a )?cidade|codigo ibge|(?:pesquise|busque|consulte|mostre|qual).*\b(?:cidade (?:de|chamada)|municipio de))\b',t):
        return {'kind':'location','text':text}
    if re.search(r'\b(noticias|manchetes)\b', t) and (len(t.split()) < 5 or re.search(r'\b(hoje|agora|ultimas|recentes|atualizadas|mostr\w*|quais|busque|pesquise|sobre|de)\b', t)):
        return {'kind':'news','text':text}
    if re.search(r'\b(que horas (sao|e)|qual (e )?a hora|horario atual|hora atual|qual (e )?a data|que dia e hoje|data (de hoje|atual))\b',t):
        return {'kind':'clock','text':text}
    return None


def greeting(text):
    words=re.findall(r'[a-z]+',norm(text))
    return bool(words and len(words)<=7 and words[0] in ('oi','ola','oie','bom','boa','hello','hey') and
                all(w in {'oi','ola','oie','bom','boa','dia','tarde','noite','tudo','bem','lucas','luccas','hello','hey','voce','e','com'} for w in words))


def cached(key, ttl, fetch):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now-hit[0]<ttl:
            return copy.deepcopy(hit[1])
    value = fetch()  # Errors are not cached or replaced with stale readings.
    with _lock:
        if len(_cache)>=128:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic(), copy.deepcopy(value))
    return value


def get_json(base, params):
    # Fixed hosts only; research.baixar rechecks SSRF and each redirect, with a byte cap.
    with _lock:
        blocked=_cache.get(('rate-limit',base))
    if blocked and time.monotonic()-blocked[0]<60:
        raise research.ResearchErro('Fonte temporariamente limitada.','rate_limited')
    try:
        options={}
        if urlsplit(base).hostname=='weather.visualcrossing.com':
            def same_host(url,timeout,user_agent=''):
                target=urlsplit(url)
                if target.scheme!='https' or target.hostname!='weather.visualcrossing.com' or not target.path.startswith('/VisualCrossingWebServices/rest/services/timeline/'):
                    raise ValueError('Redirecionamento meteorológico não autorizado')
                return research._abrir(url,timeout,user_agent)
            options['abrir']=same_host
        _, raw = research.baixar(base+'?'+urlencode(params), timeout=6, max_bytes=256*1024, aceitar='json',**options)
    except research.ResearchErro as exc:
        if getattr(exc,'http',None)==429 or exc.codigo=='rate_limited':
            with _lock:_cache[('rate-limit',base)]=(time.monotonic(),True)
        raise
    data = json.loads(raw)
    if not isinstance(data,dict) or data.get('error'):
        raise ValueError('Resposta inválida do serviço')
    return data


def place_from(text):
    match = re.search(r'\b(?:em|na cidade de|para a cidade de|cidade (?:de|chamada)|onde fica|municipio de|c[oó]digo IBGE de|clima (?:de|do|da)|temperatura (?:de|do|da))\s+(.+)',text,re.I)
    if not match:
        return ''
    value = re.split(r'\s+(?:agora|hoje|amanhã|amanha|neste momento|por favor|nos próximos)\b',match[1],flags=re.I)[0]
    value=re.sub(r'\s+no\s+(Japão|Japao|Brasil|Portugal)$',r', \1',value,flags=re.I)
    return value.strip(' .?!')[:100]


def parse_place(city):
    value=re.sub(r'\s+',' ',str(city).strip(' .?!')).replace('/',',')[:100]
    country='';region=''
    for word,code in [('Brasil','BR'),('Brazil','BR'),('BR','BR'),('Japão','JP'),('Japao','JP'),('Japan','JP'),('Portugal','PT')]:
        m=re.search(r'(?:[, ]+)'+re.escape(norm(word))+r'$',norm(value))
        if m: country=code;value=value[:m.start()].strip(' ,');break
    for uf,name in sorted(STATES.items(),key=lambda x:len(x[1]),reverse=True):
        m=re.search(r'(?:[, ]+)(?:'+re.escape(norm(name))+'|'+uf.lower()+r')$',norm(value))
        if m:region=uf;country=country or 'BR';value=value[:m.start()].strip(' ,');break
    qualifier=''
    if ',' in value:
        value,qualifier=value.split(',',1)
        value=value.strip();qualifier=qualifier.strip()
    return {'city':value,'state':region,'country_code':country,'qualifier':qualifier}


def _ibge(path):
    if not re.fullmatch(r'(?:estados/[A-Z]{2}/municipios|municipios(?:/\d{7})?)',path):raise ValueError('Consulta geográfica inválida')
    def fetch():
        _,raw=research.baixar('https://servicodados.ibge.gov.br/api/v1/localidades/'+path,timeout=6,max_bytes=6*1024*1024,aceitar='json')
        data=json.loads(raw)
        if not isinstance(data,(dict,list)):raise ValueError('Cadastro geográfico inválido')
        return data
    return cached(('ibge',path),86400,fetch)


def _municipal_place(row, uf):
    code=str(row['id'])
    if not re.fullmatch(r'\d{7}',code):raise ValueError('Identificador oficial inválido')
    def fetch():
        _,raw=research.baixar('https://servicodados.ibge.gov.br/api/v3/malhas/municipios/'+code+'/metadados',timeout=6,max_bytes=65536,aceitar='json')
        record=next(v for v in json.loads(raw) if str(v.get('id'))==code)
        center=record['centroide']
        return number(center['latitude'],-90,90),number(center['longitude'],-180,180)
    lat,lon=cached(('ibge-center',code),86400,fetch)
    return dict(label=row['nome']+', '+STATES.get(uf,uf)+', Brasil (centroide municipal)',
        name=row['nome'],state=STATES.get(uf,uf),country='Brasil',ibge_id=int(code),
        latitude=lat,longitude=lon,timezone='',coordinate_scope='municipal_centroid',
        source_url='https://servicodados.ibge.gov.br/api/v1/localidades/municipios/'+code)


_geo_lock=threading.Lock()
_geo_last=0.0


def _photon(query):
    # Optional low-volume city lookup only. No autocomplete or address harvesting.
    if os.getenv('VEXX_PHOTON_ENABLED','1')!='1':return []
    global _geo_last
    with _geo_lock:
        time.sleep(max(0,1-(time.monotonic()-_geo_last)))
        _geo_last=time.monotonic()
        data=get_json('https://photon.komoot.io/api/',{'q':query,'limit':10,'lang':'en','layer':'city'})
    features=data.get('features',[])
    if not isinstance(features,list):raise ValueError('Localização inválida')
    rows=[]
    for feature in features:
        prop=feature['properties'];lon,lat=feature['geometry']['coordinates'][:2]
        rows.append(dict(name=prop.get('name',''),state=prop.get('state',''),country=prop.get('country',''),
            country_code=prop.get('countrycode','').upper(),latitude=number(lat,-90,90),longitude=number(lon,-180,180),
            timezone='',source_url='https://www.openstreetmap.org/copyright'))
    return rows


def geocode(city):
    query=parse_place(city);name=query['city'];uf=query['state'];country=query['country_code']
    registry_error=False
    if country in ('','BR'):
        try:
            rows=_ibge('municipios/'+name) if re.fullmatch(r'\d{7}',name) else _ibge('estados/'+uf+'/municipios' if uf else 'municipios')
            if isinstance(rows,dict):
                if str(rows.get('id'))!=name:raise ValueError('Identificador oficial divergente')
                rows=[rows]
            matches=[r for r in rows if isinstance(r,dict) and (str(r.get('id'))==name or norm(r.get('nome',''))==norm(name))]
            def state(r):
                return ((r.get('microrregiao') or {}).get('mesorregiao',{}).get('UF',{}).get('sigla') or
                    (r.get('regiao-imediata') or {}).get('regiao-intermediaria',{}).get('UF',{}).get('sigla') or uf)
            if uf:matches=[r for r in matches if state(r)==uf]
            if len(matches)>1:
                return None,'Encontrei mais de uma localização. Qual delas?\n\n'+'\n'.join('- '+safe(r['nome']+', '+state(r)) for r in matches[:5])
            if matches:return _municipal_place(matches[0],state(matches[0])),None
        except (research.ResearchErro,ValueError,KeyError,TypeError,StopIteration):registry_error=True
    try:
        rows=cached(('photon',norm(city)),86400,lambda:_photon(city))
        rows=[r for r in rows if norm(r['name'])==norm(name)]
        if country:rows=[r for r in rows if r['country_code']==country]
        if uf:rows=[r for r in rows if norm(r['state'])==norm(STATES[uf])]
        if query['qualifier']:rows=[r for r in rows if norm(query['qualifier']) in (norm(r['country']),norm(r['state']),norm(r['country_code']))]
        for r in rows:r['label']=', '.join(dict.fromkeys(v for v in (r['name'],r['state'],r['country']) if v))
        if len({(r['label'],round(r['latitude'],3),round(r['longitude'],3)) for r in rows})>1:
            return None,'Encontrei mais de uma localização. Qual delas?\n\n'+'\n'.join('- '+safe(r['label']) for r in rows[:5])
        if rows:return rows[0],None
    except (research.ResearchErro,ValueError,KeyError,TypeError,IndexError):registry_error=True
    return None,f'Não consegui confirmar a localização de “{safe(city)}” nas fontes disponíveis'+(' porque um serviço está indisponível' if registry_error else '')+'. Isso não significa que o município não exista. Informe cidade e estado/país.'


def safe(value):
    text = html.unescape(re.sub(r'<[^>]*>', '', str(value)))
    return re.sub(r'([\\`*_{}\[\]()<>#!|])',r'\\\1',re.sub(r'\s+',' ',text)).strip()[:250]


def number(value, low=-200, high=10000):
    if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('Métrica inválida')
    return value


def condition(code):
    return ({0:'Céu limpo',1:'Predominantemente limpo',2:'Parcialmente nublado',3:'Nublado',45:'Nevoeiro',48:'Nevoeiro com geada',
             51:'Garoa leve',53:'Garoa',55:'Garoa intensa',56:'Garoa congelante',57:'Garoa congelante intensa',
             61:'Chuva leve',63:'Chuva',65:'Chuva intensa',66:'Chuva congelante',67:'Chuva congelante intensa',
             71:'Neve leve',73:'Neve',75:'Neve intensa',77:'Grãos de neve',80:'Pancadas leves',81:'Pancadas de chuva',82:'Pancadas fortes',
             85:'Pancadas de neve',86:'Pancadas fortes de neve',95:'Trovoadas',96:'Trovoadas com granizo',99:'Trovoadas fortes com granizo'}).get(code,'Condição não informada')


VC_BASE='https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/'
WEATHER_DISCLAIMER=('Dados sujeitos a erros, atrasos, estimativas e indisponibilidade, sem garantia de exatidão ou adequação. '
    'Previsões são incertas. Não substituem alertas oficiais ou aconselhamento meteorológico profissional '
    'e não devem ser a única base para decisões críticas.')


class WeatherError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)


def _weather_store():
    configured=os.getenv('VISUAL_CROSSING_USAGE_PATH','')
    if not configured:
        parent=Path(os.path.expandvars(os.getenv('JULIA_SQLITE_PATH',str(Path.home()/'.JULIA-mobile'/'memory.sqlite3')))).parent
        configured=str(parent/'weather-usage.sqlite3')
    path=Path(configured);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=1)
    db.executescript("""CREATE TABLE IF NOT EXISTS vc_calls(id INTEGER PRIMARY KEY,key_id TEXT,at REAL,cost INTEGER);
        CREATE TABLE IF NOT EXISTS vc_cache(key_id TEXT,lat REAL,lon REAL,at REAL,payload TEXT,PRIMARY KEY(key_id,lat,lon));
        CREATE TABLE IF NOT EXISTS vc_lease(id INTEGER PRIMARY KEY,until REAL);
        CREATE TABLE IF NOT EXISTS vc_circuit(key_id TEXT PRIMARY KEY,until REAL,reason TEXT);""")
    return db


def _normalize_weather(raw,lat,lon,now):
    if not isinstance(raw,dict) or raw.get('unitGroup','metric')!='metric':raise WeatherError('invalid_data')
    if abs(number(raw['latitude'],-90,90)-lat)>.05 or abs(number(raw['longitude'],-180,180)-lon)>.05:raise WeatherError('location_mismatch')
    zone=ZoneInfo(raw['timezone'])
    current=raw.get('currentConditions')
    if not isinstance(current,dict):raise WeatherError('missing_current')
    epoch=number(current['datetimeEpoch'],0,4102444800)
    instant=datetime.fromtimestamp(epoch,zone)
    if abs((now-instant).total_seconds())>7200 or (instant-now).total_seconds()>900:raise WeatherError('stale')
    # Only this section can supply current temperature. Never substitute daily mean/forecast.
    temp=number(current['temp'],-100,70)
    source=current.get('source','')
    nature={'obs':'Observação agregada; pode incluir interpolação',
            'fcst':'Estimativa por modelo; não é observação medida',
            'comb':'Condições combinadas de observações e modelos'}.get(source,'Estimativa atual; origem observacional não confirmada')
    result=dict(time=instant.replace(tzinfo=None).isoformat(),temperature_2m=temp,
        apparent_temperature=None if current.get('feelslike') is None else number(current['feelslike'],-120,90),
        relative_humidity_2m=None if current.get('humidity') is None else number(current['humidity'],0,100),
        wind_speed_10m=None if current.get('windspeed') is None else number(current['windspeed'],0,500),weather_code=None,condition=current.get('conditions') or 'Condição não informada')
    daily=dict(time=[],temperature_2m_min=[],temperature_2m_max=[],precipitation_probability_max=[],weather_code=[],conditions=[])
    days=raw.get('days',[])
    if not isinstance(days,list) or len(days)>16:raise WeatherError('invalid_data')
    for day in days:
        date=datetime.fromisoformat(day['datetime']).date()
        if day['datetime']!=date.isoformat() or (daily['time'] and day['datetime']<=daily['time'][-1]):raise WeatherError('invalid_data')
        if date<now.astimezone(zone).date() or date>now.astimezone(zone).date()+timedelta(days=14):raise WeatherError('invalid_data')
        lo=number(day['tempmin'],-100,70);hi=number(day['tempmax'],-100,70)
        if lo>hi:raise WeatherError('invalid_data')
        daily['time'].append(day['datetime']);daily['temperature_2m_min'].append(lo);daily['temperature_2m_max'].append(hi)
        probability=day.get('precipprob')
        daily['precipitation_probability_max'].append(None if probability is None else number(probability,0,100))
        daily['weather_code'].append(None);daily['conditions'].append(day.get('conditions') or 'Condição não informada')
    return dict(timezone=raw['timezone'],current=result,daily=daily,nature=nature,
        current_units={'temperature_2m':'°C','wind_speed_10m':'km/h'},_fetched_at=now.isoformat())


def _weather_data(lat,lon,now):
    lat,lon=round(number(lat,-90,90),2),round(number(lon,-180,180),2)
    key=os.getenv('VISUAL_CROSSING_API_KEY','').strip()
    if not key:raise WeatherError('missing_key')
    fingerprint=hashlib.sha256(key.encode()).hexdigest()[:24]
    try:limit=min(1000,max(1,int(os.getenv('VISUAL_CROSSING_DAILY_LIMIT','1000'))))
    except ValueError:raise WeatherError('configuration') from None
    db=_weather_store();lease=False
    try:
        now_s=time.time()
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM vc_cache WHERE at<?',(now_s-1800,))
        cached_row=db.execute('SELECT at,payload FROM vc_cache WHERE key_id=? AND lat=? AND lon=?',(fingerprint,lat,lon)).fetchone()
        if cached_row and 0<=now_s-cached_row[0]<300:
            db.commit();return json.loads(cached_row[1])
        circuit=db.execute('SELECT until,reason FROM vc_circuit WHERE key_id=?',(fingerprint,)).fetchone()
        if circuit and circuit[0]>now_s:raise WeatherError(circuit[1])
        row=db.execute('SELECT until FROM vc_lease WHERE id=1').fetchone()
        if row and row[0]>now_s:raise WeatherError('busy')
        db.execute('DELETE FROM vc_calls WHERE at<?',(now_s-86400,))
        used=db.execute('SELECT COALESCE(sum(cost),0) FROM vc_calls WHERE key_id=?',(fingerprint,)).fetchone()[0]
        # Reserve conservatively before I/O; crash/retry cannot erase usage.
        if used+32>limit:raise WeatherError('local_quota')
        cursor=db.execute('INSERT INTO vc_calls(key_id,at,cost) VALUES(?,?,32)',(fingerprint,now_s))
        call_id=cursor.lastrowid
        db.execute('INSERT OR REPLACE INTO vc_lease VALUES(1,?)',(now_s+120,));db.commit();lease=True
        params=dict(key=key,unitGroup='metric',include='current,days',contentType='json',lang='pt',
            elements='datetime,datetimeEpoch,temp,tempmax,tempmin,feelslike,humidity,windspeed,precipprob,conditions,source,stations')
        try:
            raw=get_json(VC_BASE+f'{lat},{lon}/next7days',params)
        except research.ResearchErro as exc:
            status=getattr(exc,'http',None)
            reason='invalid_key' if status in (401,403) else 'rate_limited' if status==429 or exc.codigo=='rate_limited' else 'unavailable'
            db.execute('INSERT OR REPLACE INTO vc_circuit VALUES(?,?,?)',(fingerprint,time.time()+(300 if reason=='invalid_key' else 60),reason));db.commit()
            raise WeatherError(reason) from None
        cost=raw.get('queryCost') if isinstance(raw,dict) else None
        if type(cost) is not int or not 0<=cost<=32:raise WeatherError('invalid_data')
        db.execute('UPDATE vc_calls SET cost=? WHERE id=?',(cost,call_id));db.commit()
        try:
            result=_normalize_weather(raw,lat,lon,now)
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            reason=exc.code if isinstance(exc,WeatherError) else 'invalid_data'
            db.execute('INSERT OR REPLACE INTO vc_circuit VALUES(?,?,?)',(fingerprint,time.time()+60,reason));db.commit()
            raise WeatherError(reason) from None
        db.execute('INSERT OR REPLACE INTO vc_cache VALUES(?,?,?,?,?)',(fingerprint,lat,lon,time.time(),json.dumps(result,ensure_ascii=False)));db.commit()
        return result
    except sqlite3.Error:
        raise WeatherError('busy') from None
    finally:
        if lease:
            db.execute('UPDATE vc_lease SET until=0 WHERE id=1');db.commit()
        db.close()


def weather(text, context, now):
    normalized=norm(text)
    if re.search(r'\b(ontem|passad[oa]|historico|daqui a|\d{1,2}/\d{1,2})\b',normalized):
        return 'Esta consulta oferece condições atuais e previsão de até 7 dias. Peça o clima agora, a previsão de amanhã ou dos próximos 7 dias, incluindo a cidade.'
    explicit = place_from(text)
    city = explicit or context.get('city','')
    coords = context.get('coordinates') if not explicit and not city else None
    if city:
        place,error = geocode(city)
        if error:return error
        lat,lon,label = place['latitude'],place['longitude'],place['label']
    elif coords:
        lat,lon = coords;number(lat,-90,90);number(lon,-180,180);label='Sua localização aproximada'
    else:
        return LOCATION_PROMPT
    lat,lon = round(lat,2),round(lon,2)
    data=_weather_data(lat,lon,now)
    zone=ZoneInfo(data['timezone']);current=data['current'];units=data['current_units']
    observed=datetime.fromisoformat(current['time']).replace(tzinfo=zone)
    age=(now-observed).total_seconds()
    if age>7200 or age < -1800:
        return 'O serviço retornou uma leitura fora da janela atual. Não vou apresentá-la como clima de agora; tente novamente mais tarde.'
    if units.get('temperature_2m')!='°C' or units.get('wind_speed_10m')!='km/h':raise ValueError('Unidades inesperadas')
    temp=number(current['temperature_2m'],-100,70)
    apparent=current['apparent_temperature'];humidity=current['relative_humidity_2m'];wind=current['wind_speed_10m']
    apparent_text='não informada' if apparent is None else f'{number(apparent,-120,90):g} °C'
    humidity_text='não informada' if humidity is None else f'{number(humidity,0,100):g}%'
    wind_text='não informado' if wind is None else f'{number(wind,0,500):g} km/h'
    display_label=label.removesuffix(' (centroide municipal)')
    geographic_note=' · centroide municipal' if display_label!=label else ''
    lines=[f'**Clima em {safe(display_label)}{geographic_note}**',f"{safe(current.get('condition') or condition(current.get('weather_code')))} · **{temp:g} °C** · sensação de {apparent_text}.",
           f'Umidade: {humidity_text} · vento: {wind_text}.']
    t=norm(text);forecast=bool(re.search(r'amanha|previsao|proximos|semana|vai chover',t))
    summary=None
    if forecast:
        local_day=now.astimezone(zone).date()
        offset=2 if 'depois de amanha' in t else 1 if 'amanha' in t else 0
        daily=data['daily'];target=local_day+timedelta(days=offset)
        count=7 if re.search(r'semana|proximos|7 dias',t) else 1
        if 'fim de semana' in t:
            target=local_day+timedelta(days=0 if local_day.weekday()==6 else (5-local_day.weekday())%7)
            count=1 if target.weekday()==6 else 2
        rows=[]
        for i,date in enumerate(daily['time']):
            if date<target.isoformat():continue
            lo=number(daily['temperature_2m_min'][i],-100,70);hi=number(daily['temperature_2m_max'][i],-100,70)
            if lo>hi:raise ValueError('Intervalo meteorológico inválido')
            prob=daily['precipitation_probability_max'][i]
            rain='não informada' if prob is None else f'{number(prob,0,100):g}%'
            description=safe(daily['conditions'][i]) if daily.get('conditions') else condition(daily['weather_code'][i])
            if summary is None:summary=(f'{lo:g}–{hi:g} °C',f'{date} · {description} · chance de chuva {rain}. Previsão por modelo.')
            rows.append(f"| {datetime.fromisoformat(date):%d/%m} | {lo:g}–{hi:g} °C | {rain} | {description} |")
            if len(rows)>=count:break
        if rows:lines.extend(['**Previsão** (probabilidades, não garantia):','| Dia | Mín.–máx. | Chance de chuva | Condição |\n|---|---|---|---|\n'+'\n'.join(rows)])
        if len(rows)<count:lines.append('A fonte não disponibilizou todos os dias solicitados nesta consulta.')
    fetched=datetime.fromisoformat(data['_fetched_at']).astimezone(zone)
    lines.append(f'Dado válido para {observed:%d/%m/%Y às %H:%M} ({safe(data["timezone"])}); consultado às {fetched:%H:%M}.')
    lines.append('[Dados meteorológicos: Visual Crossing](https://www.visualcrossing.com/) · '+data.get('nature','Natureza não confirmada')+'; cache de até 5 minutos.')
    if city and place.get('source_url')=='https://www.openstreetmap.org/copyright':
        lines.append('Localização: [© OpenStreetMap contributors · ODbL](https://www.openstreetmap.org/copyright), via Photon.')
    lines.append(WEATHER_DISCLAIMER)
    return card('\n\n'.join(lines),display_label,summary[0] if summary else f'{temp:g} °C',
                desc=(summary[1] if summary else f'{safe(current.get("condition") or condition(current.get("weather_code")))} · sensação {apparent_text} · {observed:%d/%m/%Y %H:%M} ({data["timezone"]}). {data.get("nature","Natureza não confirmada")}.')+(' Referência: centroide municipal.' if geographic_note else '')+' Dados meteorológicos: Visual Crossing.',
                url='https://www.visualcrossing.com/',badge='Visual Crossing · previsão' if summary else 'Visual Crossing · atual')


def clock(text, context, now):
    city=place_from(text)
    if not city:return None  # Existing device-clock/calendar handler remains authoritative.
    if '/' in city or city in ('UTC','GMT'):
        try:
            zone=ZoneInfo(city)
            instant=now.astimezone(zone)
            body=f'No fuso **{safe(city)}**, são **{instant:%H:%M}**, dia **{instant:%d/%m/%Y}**.'
            return card(body,city,instant.strftime('%H:%M'),desc=instant.strftime('%d/%m/%Y'),badge='Relógio do sistema')
        except (ValueError,ZoneInfoNotFoundError):pass
    place,error=geocode(city)
    if error:return error
    if not place.get('timezone'):
        place=dict(place,timezone=_weather_data(round(place['latitude'],2),round(place['longitude'],2),now)['timezone'])
    zone=ZoneInfo(place['timezone'])
    instant=now.astimezone(zone)
    geographic_source='IBGE' if place.get('ibge_id') else '© OpenStreetMap contributors · ODbL'
    geographic_url=place.get('source_url','https://www.openstreetmap.org/copyright')
    body=f'Em **{safe(place["label"])}**, são **{instant:%H:%M}**, dia **{instant:%d/%m/%Y}** ({safe(place["timezone"])}).\n\nHorário calculado pelo fuso IANA; localização: [{geographic_source}]({geographic_url}); fuso confirmado pela Visual Crossing.'
    return card(body,place['label'],instant.strftime('%H:%M'),desc=instant.strftime('%d/%m/%Y')+' · '+place['timezone'],badge='Relógio do sistema')


def news(text,context,now):
    deadline=time.monotonic()+14
    t=norm(text)
    match=re.search(r'\b(?:sobre|not[ií]cias (?:de|do|da|em|no|na))\s+(.+)',text,re.I)
    topic=re.sub(r'\b(hoje|agora|recentes|ultimas|últimas)\b','',match[1],flags=re.I).strip(' .?!') if match else ''
    query=(topic+' notícias').strip() if topic else 'notícias Brasil mundo'
    def fetch():
        try:items=search_providers.buscar_bing_news(query,limite=15,timeout=6)
        except (ValueError,OSError):items=[]
        return items
    items=cached(('news',query),180,fetch)
    zone=ZoneInfo(context.get('timezone','UTC'));cutoff=now-timedelta(hours=48)
    if 'hoje' in t:cutoff=now.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)
    def select(rows):
        selected=[];seen=set()
        for row in rows:
            try:
                published=row.get('meta',{}).get('publicado_em','')
                date=parsedate_to_datetime(published)
                # RFC 2822 -0000 represents UTC with an unknown original local zone.
                if date.tzinfo is None and published.strip().endswith('-0000'):date=date.replace(tzinfo=UTC)
                if date.tzinfo is None:continue
                if not cutoff<=date<=now+timedelta(minutes=5):continue
                url=row['url'];parsed=urlsplit(url)
                if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or any(c in url for c in '\r\n<>'):continue
                if 'especial-publicitario' in url or '/publicidade/' in url:continue
                if url in seen:continue
                if topic and not set(re.findall(r'\w{3,}',norm(topic))).intersection(re.findall(r'\w{3,}',norm(row['titulo']+' '+row.get('trecho','')))):continue
                seen.add(url);selected.append((date,row))
            except (ValueError,TypeError,KeyError):continue
        return sorted(selected,key=lambda x:x[0],reverse=True)[:5]
    selected=select(items)
    for feed in ('https://g1.globo.com/rss/g1/','https://feeds.bbci.co.uk/portuguese/rss.xml','https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml'):
        if selected or time.monotonic()>=deadline:break
        def rss():
            raw=research.baixar(feed,timeout=max(.1,min(5,deadline-time.monotonic())),max_bytes=768*1024,aceitar='feed')[1]
            if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():raise ValueError('XML inválido')
            root=ET.fromstring(raw)
            return [{'titulo':i.findtext('title',''),'url':i.findtext('link',''),'trecho':'','meta':{'publicado_em':i.findtext('pubDate','')}} for i in root.findall('.//item')[:60]]
        try:selected=select(cached(('rss',feed),180,rss))
        except (ValueError,OSError,ET.ParseError):pass
    if not selected:return 'Não consegui confirmar notícias recentes para esse pedido nas fontes disponíveis. Tente um assunto mais específico ou novamente mais tarde; não vou usar manchetes antigas como atuais.'
    lines=['**Notícias recentes'+(' — '+safe(topic) if topic else '')+'**']
    for date,row in selected:
        url=row['url'].replace('(','%28').replace(')','%29').replace(' ','%20')
        lines.append(f'- [{safe(row["titulo"])}]({url}) — {date.astimezone(zone):%d/%m às %H:%M} · {safe(urlsplit(url).hostname)}')
    lines.append(f'Consulta em {now.astimezone(zone):%d/%m/%Y às %H:%M} ({safe(str(zone))}). Manchetes e datas publicadas nos feeds; artigos completos não foram lidos. Cache de até 3 minutos.')
    return '\n\n'.join(lines)


def exchange_data(text, context, now):
    """Daily ECB reference observations; no banking spread or live inventory."""
    from decimal import Decimal
    import query_intelligence
    info = query_intelligence.analyze(text, now, context.get('timezone') or 'America/Bahia')
    params = info['parameters']
    base, quote = params.get('base'), params.get('quote')
    if not base or not quote or base == quote:
        raise ValueError('Informe duas moedas diferentes')
    query = {'base': base, 'quotes': quote}
    historical = bool(params.get('start_date'))
    if historical:
        query.update({'from': params['start_date'], 'to': params['end_date']})
    endpoint = 'https://api.frankfurter.dev/v2/providers/ecb/rates'
    url = endpoint + '?' + urlencode(query)
    if research._circuito_fechado('fx-ecb'):
        raise ValueError('Fonte de câmbio em espera após bloqueio')
    def fetch():
        try:
            _, raw = research.baixar(url, timeout=6, max_bytes=128*1024, aceitar='json')
        except research.ResearchErro as exc:
            if exc.codigo == 'bloqueado':
                research._circuito_falha('fx-ecb')
            raise
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 367:
            raise ValueError('Formato de cotações inválido')
        return rows
    rows = cached(('fx-ecb', url), 300, fetch)
    observations = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get('base', '')).upper() != base or str(row.get('quote', '')).upper() != quote:
            raise ValueError('Par de moedas divergente')
        date = datetime.strptime(str(row.get('date')), '%Y-%m-%d').date()
        value = Decimal(str(row.get('rate')))
        if not value.is_finite() or not 0 < value < Decimal('1000000000') or date > now.date():
            raise ValueError('Taxa ou data inválida')
        if historical and not params['start_date'] <= date.isoformat() <= params['end_date']:
            continue
        observations[date.isoformat()] = value
    if not observations:
        raise ValueError('Nenhuma observação disponível')
    ordered = sorted(observations.items())
    if not historical and (now.date() - datetime.fromisoformat(ordered[-1][0]).date()).days > 7:
        raise ValueError('Cotação antiga demais para consulta atual')
    amount = Decimal(params['amount'])
    return {'base': base, 'quote': quote, 'amount': str(amount),
            'rate': str(ordered[-1][1]), 'converted': str((amount * ordered[-1][1]).quantize(Decimal('0.01'))),
            'rate_date': ordered[-1][0], 'rate_time': None, 'rate_timezone': 'UTC',
            'queried_at': now.isoformat(), 'query_timezone': info['timezone'],
            'rate_type': 'daily_reference', 'provider': 'ECB via Frankfurter',
            'source_url': url, 'historical': historical,
            'observations': [{'date': d, 'rate': str(v)} for d, v in ordered],
            'request': info}


def currency(text, context, now):
    import jdui
    data = exchange_data(text, context, now)
    source = data['source_url']
    body = (f"**{data['amount']} {data['base']} ≈ {data['converted']} {data['quote']}**\n\n"
            f"Taxa de referência diária: 1 {data['base']} = {data['rate']} {data['quote']}. "
            f"Data da taxa: {data['rate_date']} (UTC); horário de publicação não informado. "
            f"Consulta: {data['queried_at']}. Não é uma oferta bancária nem cotação intradiária. "
            f"[Fonte: ECB via Frankfurter]({source}). Cache de até 5 minutos.")
    blocks = [{'type': 'ui', 'component': 'cards', 'props': {'title': 'Câmbio de referência', 'items': [{
        'title': data['base'] + ' → ' + data['quote'], 'value': data['converted'] + ' ' + data['quote'],
        'desc': 'Referência diária de ' + data['rate_date'] + '; sem impostos ou spread de instituição.',
        'badge': 'Referência diária', 'url': source}]}}]
    series = data['observations']
    if data['historical'] and len(series) >= 2:
        count = min(24, len(series))
        sample = [series[round(i * (len(series)-1) / (count-1))] for i in range(count)]
        blocks.append({'type': 'ui', 'component': 'chart', 'props': {
            'type': 'line', 'title': 'Observações reais — ' + data['base'] + '/' + data['quote'],
            'labels': [p['date'] for p in sample],
            'series': [{'label': data['quote'] + ' por ' + data['base'], 'values': [float(p['rate']) for p in sample]}],
            'source': source}})
        first, last = series[0], series[-1]
        body += f"\n\nSérie disponível: {first['date']} a {last['date']}, {len(series)} observações. "
        from decimal import Decimal
        variation = ((Decimal(last['rate']) / Decimal(first['rate']) - 1) * 100).quantize(Decimal('0.01'))
        body += f"Primeira taxa: {first['rate']}; última: {last['rate']}; variação observada: {variation}%. O gráfico seleciona até 24 observações existentes; não preenche dias sem publicação."
    ok, msg, errors = jdui.validar_mensagem({'version': jdui.VERSION, 'blocks': blocks})
    if not ok:
        raise ValueError('Não foi possível validar apresentação da cotação')
    return body + '\n\n```jdui\n' + json.dumps(msg, ensure_ascii=False) + '\n```'


def card(body, title, value, desc='', url='', badge=''):
    """Use the existing Python/JS cards schema; text remains a safe fallback."""
    import jdui
    ok,msg,_=jdui.validar_mensagem({'version':jdui.VERSION,'blocks':[{'type':'ui','component':'cards','props':{'items':[dict(title=title,value=value,desc=desc,url=url,badge=badge)]}}]})
    return body+'\n\n```jdui\n'+json.dumps(msg,ensure_ascii=False)+'\n```' if ok else body


def location(text,context,now):
    city=place_from(text)
    if 'codigo ibge' in norm(text):
        match=re.search(r'\b\d{7}\b',text)
        if match:city=match[0]
    if not city:
        match=re.search(r'\b\d{7}\b',text)
        city=match[0] if match else ''
    if not city:return 'Qual cidade e estado/país você quer localizar?'
    place,error=geocode(city)
    if error:return error
    code=place.get('ibge_id')
    source='https://servicodados.ibge.gov.br/api/v1/localidades/municipios/'+str(code) if code else 'https://www.openstreetmap.org/copyright'
    # Official identifiers, not an invented precise address.
    body='**'+safe(place['label'])+'**'+('\n\nCódigo IBGE: '+str(code)+'.' if code else '')
    body+='\n\nLocalização confirmada no cadastro consultado. [Fonte geográfica]('+source+').'
    return card(body,place['label'],str(code) if code else 'Localidade',url=source,badge='IBGE' if code else '© OpenStreetMap · ODbL')


def respond(text,context):
    req=request(text)
    if not req:return None
    try:
        if req['kind']=='greeting':return 'Oi! Tudo bem? Como posso ajudar?'
        result={'weather':weather,'clock':clock,'news':news,'currency':currency,'location':location}[req['kind']](text,context,datetime.now(UTC))
        for phrase,status in [('mais de uma localização','ambiguous'),('fora da janela atual','stale'),('Não consegui confirmar a localização','unconfirmed')]:
            if result and phrase in result:return card(result,'Não foi possível concluir',{'ambiguous':'Qual localidade?','stale':'Dado desatualizado','unconfirmed':'Local não confirmado'}[status],badge=status)
        return result
    except WeatherError as exc:
        messages={'missing_key':'A chave do serviço meteorológico não está configurada no servidor.',
            'invalid_key':'O serviço meteorológico recusou a chave configurada. Verifique a configuração no servidor.',
            'local_quota':'O limite local de consultas meteorológicas das últimas 24 horas foi atingido.',
            'rate_limited':'A fonte limitou as consultas ou esgotou a quota. Aguarde pelo menos um minuto.',
            'stale':'O serviço retornou dados fora da janela atual. Não vou apresentá-los como clima de agora.',
            'busy':'Há outra consulta meteorológica em andamento. Tente novamente em instantes.',
            'location_mismatch':'A fonte retornou coordenadas divergentes; não vou substituir a localidade.',
            'missing_current':'A fonte não disponibilizou condições atuais válidas.',
            'configuration':'A configuração do serviço meteorológico precisa ser revisada.',
            'invalid_data':'A fonte retornou dados meteorológicos vazios ou inválidos.',
            'unavailable':'O serviço meteorológico está indisponível agora. Tente novamente mais tarde.'}
        body=messages.get(exc.code,messages['unavailable'])+' Não vou estimar valores sem uma fonte.'
        return card(body,'Consulta meteorológica indisponível','Verifique a configuração' if exc.code in ('missing_key','invalid_key','configuration') else 'Consulta não concluída',badge='Clima')
    except research.ResearchErro as exc:
        limited=getattr(exc,'http',None)==429 or exc.codigo=='rate_limited'
        body=('A fonte limitou temporariamente as consultas. Aguarde um minuto antes de tentar novamente.' if limited else 'O serviço de dados está indisponível agora. Tente novamente mais tarde.')+' Não vou estimar valores sem uma fonte.'
        return card(body,'Consulta indisponível','Limite de consultas' if limited else 'Serviço indisponível',badge='rate_limit' if limited else 'unavailable')
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OSError,ZoneInfoNotFoundError,InvalidOperation):
        return 'Não consegui consultar os dados atuais agora: a fonte está indisponível ou retornou dados inválidos. Tente novamente em instantes. Não vou estimar valores sem uma fonte.'
