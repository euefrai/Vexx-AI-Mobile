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


def analyze(text, now=None, timezone_name='America/Bahia'):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Relógio precisa de timezone')
    local = now.astimezone(ZoneInfo(timezone_name))
    t = normalized(text)
    domain = 'general'
    if re.search(r'\b(voos?|passagens? aereas?|avioes?|aeroportos?)\b', t) or (re.search(r'\bpassagens? de .+? para ', t) and 'onibus' not in t):
        domain = 'air_travel'
    elif re.search(r'\b(onibus|rodoviari[ao]s?)\b', t):
        domain = 'bus_travel'
    elif re.search(r'\b(cotacao|cambio|dolar|dolares|usd|eur|jpy)\b', t) and not re.search(r'\b(codigo|programa|implemente)\b', t):
        domain = 'currency'
    elif re.search(r'\b(eventos?|shows?|concertos?|exposicoes)\b', t):
        domain = 'events'
    elif re.search(r'\b(noticias?|manchetes|aconteceu|acontecimentos?)\b', t):
        domain = 'news'
    elif re.search(r'\b(estudos?|cientific[oa]s?|papers?)\b', t) or re.search(r'\bartigo\b.*\b(doi|pesquisa)\b',t):
        domain = 'science'
    elif re.search(r'\b(documentacao|documentos?|arquivos?|pdf|asyncio)\b', t):
        domain = 'documents'
    params = {}
    resolved = str(text)
    relative = re.search(r'\b(daqui a|ultimos?|ultimas?|proximos?|proximas?)\s+(\d{1,3}|um|uma|dois|duas|sete|quinze|trinta)\s+(dias?|semanas?)\b', t)
    if relative:
        count = int(relative[2]) if relative[2].isdigit() else _NUMBERS[relative[2]]
        days = count * (7 if relative[3].startswith('semana') else 1)
        if not 1 <= days <= 366:
            raise ValueError('Janela temporal fora do limite de 366 dias')
        past = relative[1].startswith('ultim')
        start = local.date() - timedelta(days=days) if past else local.date()
        end = local.date() if past else local.date() + timedelta(days=days)
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
        route = re.search(r'\b(?:voos?|passagens?(?:\s+(?:aereas?|de onibus|rodoviarias?))?|onibus)\s+de\s+(.+?)\s+para\s+(.+?)(?=\s+(?:para\s+)?daqui|\s+em\s+20\d\d|,|[.!?]|$)', t)
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
        location = re.search(r'\b(?:em|noticias de)\s+(.+?)(?=\s+(?:nos|nas|ultimos|ultimas|proximos|proximas|recentemente)|[,.!?]|$)', t)
        if location:
            params['location'] = str(text)[location.start(1):location.end(1)].strip()
            region = re.match(r',\s*([a-z ]{2,30}?)(?=,|\s+(?:nos|nas|ultimos|ultimas)|[.!?]|$)', t[location.end():])
            if region:
                params['region'] = region[1].strip()
        if domain == 'news' and not params.get('start_date') and re.search(r'\b(ultimas?|recentemente|recentes?)\b', t):
            params.update(start_date=(local.date()-timedelta(days=7)).isoformat(),end_date=local.date().isoformat(),window_inferred=True)
    search_query = resolved
    if domain in ('air_travel', 'bus_travel') and params.get('origin') and params.get('destination'):
        mode = 'voos' if domain == 'air_travel' else 'passagens de ônibus'
        search_query = f'"{params["origin"]}" "{params["destination"]}" {mode}'
        if params.get('departure_date'):
            search_query += ' ' + params['departure_date']
        if params.get('adults'):
            search_query += ' ' + str(params['adults']) + ' adulto'
    if domain in ('news', 'events') and params.get('location'):
        search_query = '"' + params['location'] + '"' + (' "'+params['region']+'"' if params.get('region') else '') + (' notícias' if domain == 'news' else ' eventos programação')
        # News dates are a verification filter, not literal text that pages must repeat.
        if domain == 'events' and params.get('end_date'):
            search_query += ' ' + params['start_date'] + ' ' + params['end_date']
    return {'version': 1, 'search_query': search_query[:240], 'domain': domain, 'original_request': str(text)[:1000],
            'resolved_request': resolved[:1000], 'parameters': params,
            'temporal': bool(relative or explicit or re.search(r'\b(agora|atual|recentes?|hoje)\b', t)),
            'resolved_at': now.isoformat(), 'timezone': timezone_name,
            'requires_live_data': domain in ('air_travel', 'bus_travel', 'currency', 'news', 'events')}
