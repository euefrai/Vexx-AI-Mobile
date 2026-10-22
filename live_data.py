"""Dados atuais determinísticos. Fontes limitadas, sem chaves nem código do modelo."""
import copy
from decimal import InvalidOperation
import html
import json
import math
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
_cache = {}
_lock = threading.Lock()


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def request(text):
    t = norm(text).strip().rstrip('.!?')
    t = re.sub(r'^(lucas|luccas)[, :]+', '', t)
    if re.search(r'\b(nao (pesquise|busque|consulte)|sem (internet|pesquisa|buscar))\b',t):return None
    if re.search(r'\b(traduza|traduzi[ra]|escreva|redija|codigo|significa|defina|explique|o que e|diferenca|mudancas climaticas|clima organizacional|cpu|gpu|processador)\b', t):
        return None
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
    if re.search(r'\b(noticias|manchetes)\b', t) and (len(t.split()) < 5 or re.search(r'\b(hoje|agora|ultimas|recentes|atualizadas|mostr\w*|quais|busque|pesquise|sobre|de)\b', t)):
        return {'kind':'news','text':text}
    if re.search(r'\b(que horas (sao|e)|qual (e )?a hora|horario atual|hora atual|qual (e )?a data|que dia e hoje|data (de hoje|atual))\b',t):
        return {'kind':'clock','text':text}
    return None


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
    _, raw = research.baixar(base+'?'+urlencode(params), timeout=6, max_bytes=256*1024, aceitar='json')
    data = json.loads(raw)
    if not isinstance(data,dict) or data.get('error'):
        raise ValueError('Resposta inválida do serviço')
    return data


def place_from(text):
    match = re.search(r'\b(?:em|na cidade de|para a cidade de|clima (?:de|do|da)|temperatura (?:de|do|da))\s+(.+)',text,re.I)
    if not match:
        return ''
    value = re.split(r'\s+(?:agora|hoje|amanhã|amanha|neste momento|por favor|nos próximos)\b',match[1],flags=re.I)[0]
    return value.strip(' .?!')[:100]


def geocode(city):
    data = cached(('geo',city.casefold()),3600,lambda:get_json('https://geocoding-api.open-meteo.com/v1/search',
                  {'name':city,'count':5,'language':'pt','format':'json'}))
    candidates = []
    rows=data.get('results',[])
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Localização inválida')
    exact=[r for r in rows if norm(r.get('name',''))==norm(city.split(',')[0].strip()) and str(r.get('feature_code','')).startswith('PPL')]
    if exact:rows=exact
    capitals=[r for r in rows if r.get('feature_code') in ('PPLA','PPLC')]
    if ',' in city and len(capitals)==1:rows=capitals
    for row in rows:
        lat,lon = row.get('latitude'),row.get('longitude')
        if type(lat) not in (int,float) or type(lon) not in (int,float) or not -90<=lat<=90 or not -180<=lon<=180:
            continue
        label = ', '.join(dict.fromkeys(str(row[k]) for k in ('name','admin1','country') if row.get(k)))
        candidates.append({'label':label,'latitude':lat,'longitude':lon,'timezone':row.get('timezone','UTC')})
    if not candidates:
        return None, f'Não localizei “{safe(city)}”. Informe cidade e estado/país.'
    # Never silently choose among homonymous cities in different regions.
    if len({r['label'] for r in candidates})>1:
        return None, 'Encontrei mais de uma localização. Qual delas?\n\n'+'\n'.join('- '+safe(r['label']) for r in candidates[:5])+'\n\nRepita o pedido incluindo a cidade e o estado/país.'
    return candidates[0], None


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
    def fetch():
        data=get_json('https://api.open-meteo.com/v1/forecast',{
            'latitude':lat,'longitude':lon,'timezone':'auto','forecast_days':7,
            'current':'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m',
            'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'})
        data['_fetched_at']=datetime.now(UTC).isoformat()
        return data
    data=cached(('weather',lat,lon),300,fetch)
    zone=ZoneInfo(data['timezone']);current=data['current'];units=data['current_units']
    observed=datetime.fromisoformat(current['time']).replace(tzinfo=zone)
    age=(now-observed).total_seconds()
    if age>7200 or age < -1800:
        return 'O serviço retornou uma leitura fora da janela atual. Não vou apresentá-la como clima de agora; tente novamente mais tarde.'
    if units.get('temperature_2m')!='°C' or units.get('wind_speed_10m')!='km/h':raise ValueError('Unidades inesperadas')
    temp=number(current['temperature_2m'],-100,70)
    apparent=number(current['apparent_temperature'],-120,90)
    humidity=number(current['relative_humidity_2m'],0,100)
    wind=number(current['wind_speed_10m'],0,500)
    lines=[f'**Clima em {safe(label)}**',f"{condition(current.get('weather_code'))} · **{temp:g} °C** · sensação de {apparent:g} °C.",
           f'Umidade: {humidity:g}% · vento: {wind:g} km/h.']
    t=norm(text);forecast=bool(re.search(r'amanha|previsao|proximos|semana|vai chover',t))
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
            prob=daily['precipitation_probability_max'][i]
            rain='não informada' if prob is None else f'{number(prob,0,100):g}%'
            rows.append(f"| {datetime.fromisoformat(date):%d/%m} | {lo:g}–{hi:g} °C | {rain} | {condition(daily['weather_code'][i])} |")
            if len(rows)>=count:break
        if rows:lines.extend(['**Previsão** (probabilidades, não garantia):','| Dia | Mín.–máx. | Chance de chuva | Condição |\n|---|---|---|---|\n'+'\n'.join(rows)])
        if len(rows)<count:lines.append('A fonte não disponibilizou todos os dias solicitados nesta consulta.')
    fetched=datetime.fromisoformat(data['_fetched_at']).astimezone(zone)
    lines.append(f'Dado válido para {observed:%d/%m/%Y às %H:%M} ({safe(data["timezone"])}); consultado às {fetched:%H:%M}.')
    lines.append('[Fonte: Open-Meteo](https://open-meteo.com/) · condições estimadas por modelos meteorológicos; cache de até 5 minutos.')
    return '\n\n'.join(lines)


def clock(text, context, now):
    city=place_from(text)
    if not city:return None  # Existing device-clock/calendar handler remains authoritative.
    place,error=geocode(city)
    if error:return error
    zone=ZoneInfo(place['timezone'])
    instant=context.get('current_at',now).astimezone(zone)
    return f'Em **{safe(place["label"])}**, são **{instant:%H:%M}**, dia **{instant:%d/%m/%Y}** ({safe(place["timezone"])}).\n\nHorário calculado pelo fuso IANA; localização: [Open-Meteo/GeoNames](https://open-meteo.com/en/docs/geocoding-api).'


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


def respond(text,context):
    req=request(text)
    if not req:return None
    try:
        return {'weather':weather,'clock':clock,'news':news,'currency':currency}[req['kind']](text,context,datetime.now(UTC))
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OSError,ZoneInfoNotFoundError,InvalidOperation):
        return 'Não consegui consultar os dados atuais agora: a fonte está indisponível ou retornou dados inválidos. Tente novamente em instantes. Não vou estimar valores sem uma fonte.'
