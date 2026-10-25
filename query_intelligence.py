"""Request parameters for existing research routes; no fetching or model execution."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from zoneinfo import ZoneInfo


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold())
                   if not unicodedata.combining(c))


_NUMBERS = {'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'sete': 7,
            'quinze': 15, 'trinta': 30}
_CURRENCIES = {'USD': r'dolares?|dolar|usd', 'BRL': r'reais|real|brl',
               'EUR': r'euros?|eur', 'JPY': r'ienes?|jpy'}


def topic_profile(text):
    """Separate explicit operations from topics without claiming semantic NER.

    The original is authoritative. Unknown names remain unresolved candidates;
    dates, models, exclusions and comparisons are never inferred away.
    """
    original = str(text or '')
    value = re.sub(r'\s+', ' ', original).strip().rstrip('.!?')
    presentation = []
    tail = re.search(r'\s+e\s+(?:apresente|mostre|exiba|organize)\s+(?:(?:as?|os?)\s+)?'
                     r'(?:principais\s+)?(?:informa[cç][oõ]es|resultados|respostas?)\s+'
                     r'em\s+(?:cards|cart[oõ]es|tabelas?)(?:\s+com\s+imagens)?$', value, re.I)
    if tail:
        presentation.append(tail[0].strip())
        value = value[:tail.start()]
    value = re.sub(r'^(?:fa[cç]a\s+)?(?:uma\s+)?pesquisa\s+(?:profunda\s+)?(?:sobre\s+)?', '', value, flags=re.I)
    value = re.sub(r'^(?:pesquise|pesquisar|encontre|busque|procure)\s+(?:profundamente\s+|a fundo\s+)?', '', value, flags=re.I)
    value = re.sub(r'^(?:as?\s+)?(?:[uú]ltimas?\s+)?(?:novidades|informa[cç][oõ]es recentes)\s+sobre\s+', '', value, flags=re.I)
    value = re.sub(r'^(?:a|as|o|os)\s+(?=hist[oó]ria|documenta[cç][aã]o|especifica[cç][oõ]es|relat[oó]rio)', '', value, flags=re.I)
    operation = ''
    prefix = re.match(r'^(hist[oó]ria\s+(?:de|do|da|dos|das)\s+(?:empresa\s+)?|'
                      r'documenta[cç][aã]o\s+(?:oficia(?:l|is)\s+)?|'
                      r'especifica[cç][oõ]es\s+(?:oficia(?:l|is)\s+)?|'
                      r'relat[oó]rio\s+(?:p[uú]blico\s+)?(?:PDF\s+)?)', value, re.I)
    if prefix:
        operation = prefix[0].strip()
        value = value[prefix.end():].strip()
    source_preference = re.search(r'\s+(fontes?\s+(?:oficiais|prim[aá]rias|originais))$', value, re.I)
    preference = source_preference[1] if source_preference else ''
    if source_preference:
        value = value[:source_preference.start()].strip()
    required = ([re.sub(r'\s+(?:de|do|da|dos|das)\s*(?:empresa)?$', '', operation, flags=re.I)] if operation else [])
    required += [m[0] for m in re.finditer(r'\b(?:autonomia|limita[cç][oõ]es|processos|vantagens|custos|data de inaugura[cç][aã]o)\b', value, re.I)]
    entities = []
    for m in re.finditer(r'\b(?:[A-ZÀ-Ý][\w-]*)(?:(?:\s+(?:de|do|da|dos|das))?\s+[A-ZÀ-Ý][\w-]*)*', value):
        name = re.sub(r'^(?:Not[ií]cias|Compare|Pesquisa|Pesquise|Fontes|Documenta[cç][aã]o)\s+(?:(?:de|do|da|sobre|em)\s+)?', '', m[0])
        if normalized(name) in ('compare', 'noticias', 'pesquisa', 'pesquise', 'fontes', 'documentacao'):
            continue
        if name.upper() in ('PDF', 'API', 'GB', 'BRL', 'USD') or len(name) < 3:
            continue
        kind = ('product_model' if re.search(r'[A-Za-z]+-?\d', name) else
                'organization' if re.search(r'\bempresa\b', normalized(original)) else 'unresolved_named_entity')
        entities.append({'name': name, 'kind': kind, 'resolution': 'explicit_text_not_verified'})
    focused = ' '.join(x for x in (value, ' '.join(required[:1]), preference) if x).strip()
    # Discovery can reorder a noun phrase, but must not silently drop a
    # negative/budget/comparison suffix that this deterministic parser cannot model.
    guarded = bool(re.search(r'\b(?:nao|exceto|exclua|sem|ate|abaixo|acima|compare|versus)\b|r\$|\bvs\b', normalized(original)))
    if guarded:
        focused = original.strip()
    return {'original_request': original, 'primary_topic': value or original.strip(),
            'secondary_topics': [], 'entities': entities[:12], 'required_information': required,
            'intent': 'deep_research' if re.search(r'profund|a fundo', normalized(original)) else 'research',
            'hard_constraints': {'unparsed_original_guard': original if guarded else ''},
            'soft_preferences': [preference] if preference else [],
            'presentation_preferences': presentation, 'focused_query': focused,
            'scope': 'explicit syntax only; not universal entity disambiguation'}


def analyze(text, now=None, timezone_name='America/Bahia'):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Relógio precisa de timezone')
    local = now.astimezone(ZoneInfo(timezone_name))
    t = normalized(text)
    domain = 'general'
    if re.search(r'\b(voos?|passage(?:m|ns) aereas?|(?:aviao|avioes)|aeroportos?)\b', t) or (re.search(r'\bpassage(?:m|ns) de .+? para ', t) and 'onibus' not in t):
        domain = 'air_travel'
    elif re.search(r'\b(onibus|rodoviari[ao]s?)\b', t):
        domain = 'bus_travel'
    elif re.search(r'\b(cotacao|cambio|dolar|dolares|usd|eur|jpy)\b', t) and not re.search(r'\b(codigo|programa|implemente)\b', t):
        domain = 'currency'
    elif re.search(r'\b(eventos?|shows?|concertos?|exposicoes)\b', t):
        domain = 'events'
    elif re.search(r'\b(noticias?|manchetes|aconteceu|acontecimentos?|novidades)\b', t):
        domain = 'news'
    elif re.search(r'\b(estudos?|cientific[oa]s?|papers?)\b', t) or re.search(r'\bartigo\b.*\b(doi|pesquisa)\b',t):
        domain = 'science'
    elif re.search(r'\b(documentacao|documentos?|arquivos?|pdf|asyncio)\b', t):
        domain = 'documents'
    params = {}
    resolved = str(text)
    relative = re.search(r'\b(daqui a|ultimos?|ultimas?|proximos?|proximas?)\s+(\d{1,3}|um|uma|dois|duas|sete|quinze|trinta)\s+(dias?|semanas?|horas?)\b', t)
    if relative:
        count = int(relative[2]) if relative[2].isdigit() else _NUMBERS[relative[2]]
        days = count * (7 if relative[3].startswith('semana') else 1)
        if not 1 <= days <= 366:
            raise ValueError('Janela temporal fora do limite de 366 dias')
        past = relative[1].startswith('ultim')
        start = local.date() - timedelta(days=days) if past else local.date()
        end = local.date() if past else local.date() + timedelta(days=days)
        if relative[3].startswith('hora'):
            start_at = local - timedelta(hours=count) if past else local
            end_at = local if past else local + timedelta(hours=count)
            start, end = start_at.date(), end_at.date()
            params.update(start_at=start_at.isoformat(), end_at=end_at.isoformat())
        params.update(start_date=start.isoformat(), end_date=end.isoformat())
        if relative[1] == 'daqui a':
            params['departure_date'] = end.isoformat()
            replacement = 'em ' + end.isoformat()
        else:
            replacement = f'entre {start.isoformat()} e {end.isoformat()}'
        # Normalization preserves character count for ordinary Portuguese accents.
        prefix = re.sub(r'\b(?:nos|nas|para)\s+$', '', str(text)[:relative.start()], flags=re.I)
        resolved = prefix + replacement + str(text)[relative.end():]
    explicit = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', t)
    if explicit and domain in ('air_travel', 'bus_travel'):
        params['departure_date'] = datetime.strptime(explicit[1], '%Y-%m-%d').date().isoformat()
    if domain in ('air_travel', 'bus_travel'):
        relative_day = re.search(r'\b(depois de amanha|amanha|hoje)\b', t)
        if relative_day and not params.get('departure_date'):
            params['departure_date'] = (local.date() + timedelta(days={'hoje': 0, 'amanha': 1, 'depois de amanha': 2}[relative_day[1]])).isoformat()
        route = re.search(r'\b(?:voos?|passage(?:m|ns)(?:\s+(?:aereas?|de onibus|rodoviarias?))?|onibus)\s+de\s+(.+?)\s+para\s+(.+?)(?=\s+(?:para\s+)?(?:daqui|hoje|amanha|depois de amanha|\d+ adultos?|um adulto)|\s+em\s+20\d\d|,|[.!?]|$)', t)
        if route:
            params.update(origin=str(text)[route.start(1):route.end(1)].strip(),
                          destination=str(text)[route.start(2):route.end(2)].strip())
        passenger = re.search(r'\b(\d+|um|uma|dois|duas)\s+adultos?\b', t)
        if passenger:
            params['adults'] = int(passenger[1]) if passenger[1].isdigit() else _NUMBERS[passenger[1]]
        params['inventory_state'] = 'not_verified'
    if domain == 'currency':
        found = sorted((m.start(), code) for code, rx in _CURRENCIES.items()
                       for m in re.finditer(r'\b(?:' + rx + r')\b', t))
        pair = list(dict.fromkeys(code for _, code in found))
        if pair:
            params.update(base=pair[0], quote=pair[1] if len(pair) > 1 else 'BRL')
        value = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:dolares?|usd|euros?|eur|reais|brl|ienes?|jpy)\b', t)
        try:
            amount = Decimal(value[1].replace(',', '.')) if value else Decimal('1')
            if not amount.is_finite() or not 0 <= amount <= Decimal('1000000000000'):
                raise ValueError('Valor fora do limite')
            params['amount'] = str(amount)
        except InvalidOperation:
            raise ValueError('Valor inválido') from None
    if domain in ('news', 'events'):
        # Keep explicit calendar windows out of the entity, including follow-ups.
        if not params.get('start_date'):
            day = re.search(r'\b(anteontem|ontem|hoje)\b', t)
            week = re.search(r'\b(?:na|da|a)?\s*ultima semana\b', t)
            if day:
                chosen = local.date() - timedelta(days={'hoje':0,'ontem':1,'anteontem':2}[day[1]])
                params.update(start_date=chosen.isoformat(), end_date=chosen.isoformat())
            elif week:
                params.update(start_date=(local.date()-timedelta(days=7)).isoformat(), end_date=local.date().isoformat())
        # Only remove terminal presentation instructions with generic objects.
        # Comparisons naming entities, exclusions and budgets remain search text.
        presentation = r'\s+(?:e\s+)?(?:compare|resuma|destaque)\s+(?:os acontecimentos(?: mais relevantes)?|os resultados|as noticias|os destaques|os pontos principais)\s*(?=[.!?]|$)'
        boundary = r'(?=\s+(?:nos|nas|na ultima|ultimos|ultimas|proximos|proximas|recentemente|hoje|ontem|anteontem|sobre)\b|' + presentation + r'|[,.!?]|$)'
        location = re.search(r'\bem\s+(.+?)'+boundary, t)
        if not location:
            location = re.search(r'\bnoticias\s+(?:de|do|da|sobre)\s+(.+?)'+boundary, t)
        if location:
            params['location'] = str(text)[location.start(1):location.end(1)].strip()
            city_state = re.fullmatch(r'(.+?)/([A-Za-z]{2})', params['location'])
            if city_state:
                params.update(location=city_state[1].strip(), region=city_state[2].upper())
            region = re.match(r',\s*([a-z ]{2,30}?)(?=,|\s+(?:nos|nas|ultimos|ultimas)|[.!?]|$)', t[location.end():])
            if region:
                params['region'] = region[1].strip()
        if domain == 'news' and not params.get('start_date') and re.search(r'\b(ultimas?|recentemente|recentes?)\b', t):
            params.update(start_date=(local.date()-timedelta(days=7)).isoformat(),end_date=local.date().isoformat(),window_inferred=True)
        if domain == 'events' and not params.get('start_date') and re.search(r'\b(futuros?|proximos?)\b', t):
            params.update(start_date=local.date().isoformat(), end_date=(local.date()+timedelta(days=90)).isoformat(), window_inferred=True)
        topic = re.search(r'\b(?:sobre|acerca de)\s+(.+?)(?=\s+(?:em|(?:nos|nas)\s+(?:ultimos?|ultimas?|proximos?|proximas?)|na ultima|hoje|ontem|anteontem)\b|' + presentation + r'|[,.!?]|$)', t)
        if topic and (not params.get('location') or not topic[1].strip().startswith(normalized(params['location']))):
            params['topic'] = str(text)[topic.start(1):topic.end(1)].strip()
            params['topic'] = topic_profile(params['topic'])['primary_topic']
    search_query = resolved
    if domain in ('air_travel', 'bus_travel') and params.get('origin') and params.get('destination'):
        mode = 'voos' if domain == 'air_travel' else 'passagens de ônibus'
        search_query = f'"{params["origin"]}" "{params["destination"]}" {mode}'
        if params.get('departure_date'):
            search_query += ' ' + params['departure_date']
        if params.get('adults'):
            search_query += ' ' + str(params['adults']) + ' adulto'
    if domain in ('news', 'events') and (params.get('location') or params.get('topic')):
        search_query = ('"' + params['location'] + '"' if params.get('location') else '') + (' "'+params['region']+'"' if params.get('region') else '') + (' notícias' if domain == 'news' else ' eventos programação')
        # News dates are a verification filter, not literal text that pages must repeat.
        if domain == 'events' and params.get('end_date'):
            search_query += ' ' + params['start_date'] + ' ' + params['end_date']
        if params.get('topic'):
            search_query += ' ' + params['topic']
        # Do not shorten ambiguous restrictions that this parser does not model.
        if re.search(r'\b(?:nao|exceto|exclua|sem|ate|abaixo|acima|menos de|mais de)\b|r\$', t):
            search_query = resolved
        search_query = search_query.strip()
    required = {'air_travel': ['origin','destination','departure_date','adults','operator','departure_time','price','currency','inventory','source','observed_at'],
                'bus_travel': ['origin','destination','departure_date','operator','departure_time','price','currency','inventory','source','observed_at'],
                'news': ['article_url','article_text','published_at','location','source'],
                'events': ['name','location','event_date','organizer','source'],
                'science': ['title','doi','authors','publication_date','content_scope','source']}.get(domain, ['source','content_scope'])
    missing = [key for key in ('origin','destination','departure_date','adults') if domain in ('air_travel','bus_travel') and not params.get(key)]
    return {'version': 1, 'required_data': required, 'missing_parameters': missing, 'search_query': search_query[:240], 'domain': domain, 'original_request': str(text)[:1000],
            'resolved_request': resolved[:1000], 'parameters': params,
            'temporal': bool(params.get('start_date') or relative or explicit or re.search(r'\b(agora|atual|recentes?|hoje)\b', t)),
            'resolved_at': now.isoformat(), 'timezone': timezone_name,
            'requires_live_data': domain in ('air_travel', 'bus_travel', 'currency', 'news', 'events'),
            'constraints': {'hard': {k:v for k,v in params.items() if k in ('location','region','topic','start_date','end_date','start_at','end_at','origin','destination','departure_date','adults')},
                            'soft': {}, 'optional': {}}}


def constrain_discovery(query, request):
    """Reformulation may broaden vocabulary, never drop an explicit news place/topic."""
    if request.get('domain') != 'news': return query
    params=request.get('parameters') or {}
    missing=[]
    for field in ('location','region','topic'):
        value=str(params.get(field) or '').strip()
        if value and not re.search(r'(?<!\w)'+re.escape(normalized(value))+r'(?!\w)',normalized(query)):
            missing.append('"'+value.replace('"','')+'"')
    suffix=' '.join(missing)
    return (str(query)[:max(0,240-len(suffix)-1)]+' '+suffix).strip() if suffix else query
