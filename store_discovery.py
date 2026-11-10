"""Discover public product URLs from the merchant's own search, not an index.

Catalog data is discovery only. Prices, identity and availability still pass
through the existing product-page reader and verification gates.
"""
import html
import json
import os
import re
import time
import urllib.parse

_CACHE = {}


def catalog_query(query):
    text = re.sub(r'\bsite:\S+', ' ', str(query), flags=re.I)
    text = re.sub(r'\b(\d+)\s+gb\b', r'\1GB', text, flags=re.I)
    words = re.findall(r'[\w-]+', text, re.UNICODE)
    noise = {'pesquise', 'pesquisa', 'pesquisar', 'procure', 'encontre', 'comprar', 'compra',
             'oferta', 'ofertas', 'melhor', 'menor', 'preço', 'preco', 'preços', 'precos',
             'atual', 'atuais', 'brasil', 'brasileiras', 'venda', 'vender', 'direto', 'diretos',
             'link', 'links', 'produto', 'produtos', 'quero', 'com', 'uma', 'um', 'de', 'no',
             'na', 'a', 'à', 'e', 'para', 'por', 'gpu', 'vram', 'compare', 'comparar',
             'comparativo', 'comparando', 'qual', 'versus', 'vs', 'diferença', 'diferenca',
             'recomende', 'indique', 'abaixo', 'menos', 'ate', 'até', 'top', 'barato',
             'barata', 'baratos', 'baratas', 'bom', 'bons', 'boa', 'boas', 'reais', 'r',
             'me', 'mim', 'eu', 'mostre', 'mostra', 'mostrar', 'diga', 'fale', 've', 'vê', 'ver',
             'traz', 'traga', 'ache', 'achar', 'algum', 'alguns', 'alguma', 'algumas',
             'uns', 'umas', 'outro', 'outros', 'outra', 'outras', 'qualquer',
             'nesse', 'neste', 'deste', 'desse', 'mes', 'mês', 'meses', 'ano', 'anos',
             'hoje', 'agora', 'atualmente', 'novembro', 'dezembro', 'janeiro'}
    cleaned_words = [word for word in words if word.casefold() not in noise]
    lower_words = [w.casefold() for w in cleaned_words]
    if any(w in ('fone', 'fones') for w in lower_words) and not any(w in ('ouvido', 'headphone', 'headset', 'earbuds', 'airpods') for w in lower_words):
        expanded = []
        for w in cleaned_words:
            if w.casefold() in ('fone', 'fones'):
                expanded.extend(['fone', 'de', 'ouvido'])
            else:
                expanded.append(w)
        cleaned_words = expanded
    elif any(w in ('celular', 'celulares') for w in lower_words) and not any(w in ('smartphone', 'smartphones') for w in lower_words):
        expanded = []
        for w in cleaned_words:
            if w.casefold() in ('celular', 'celulares'):
                expanded.append('smartphone')
            else:
                expanded.append(w)
        cleaned_words = expanded
    return ' '.join(cleaned_words)[:120]


def extract_kabum(page, limit=8):
    match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', page, re.S | re.I)
    if not match:
        return []
    try:
        raw_data = json.loads(match.group(1))['props']['pageProps']['data']
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        data = raw_data['catalogServer']['data']
    except (ValueError, KeyError, TypeError, RecursionError):
        return []
    if not isinstance(data, list):
        return []
    out, seen = [], set()
    for item in data[:100]:
        if not isinstance(item, dict):
            continue
        code, slug = str(item.get('code', '')), item.get('friendlyName', '')
        title = item.get('name')
        if not re.fullmatch(r'[1-9]\d{0,11}', code) or not isinstance(slug, str):
            continue
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,450}', slug) or not isinstance(title, str) or not title.strip():
            continue
        url = 'https://www.kabum.com.br/produto/' + code + '/' + slug
        if url in seen:
            continue
        seen.add(url)
        out.append({'titulo': html.unescape(title)[:200], 'url': url,
                    'trecho': html.unescape(re.sub(r'<[^>]+>', ' ', str(item.get('description') or '')))[:300],
                    'origem': 'kabum-search', 'tipo': 'produto', 'status': 'encontrada'})
        if len(out) >= min(12, max(1, limit)):
            break
    return out


def search_kabum(query, limit=8, timeout=5):
    if os.getenv('JULIA_NATIVE_STORE_SEARCH', '1') == '0':
        return []
    import research
    topic = catalog_query(query)
    if not topic:
        return []
    cached = _CACHE.get(topic.casefold())
    if cached and cached[0] > time.monotonic():
        return [dict(row) for row in cached[1]][:limit]
    url = 'https://www.kabum.com.br/busca/' + urllib.parse.quote(topic, safe='')
    final, page = research.baixar(url, timeout=min(6, timeout), max_bytes=2 * 1024 * 1024)
    target = urllib.parse.urlsplit(final)
    if target.hostname != 'www.kabum.com.br' or research.pagina_bloqueada(page):
        return []
    if target.path.startswith(('/atendimento', '/carrinho', '/login', '/cadastro', '/conta')):
        return []
    rows = extract_kabum(page, limit=12)
    topic_low = topic.casefold()
    if 'fone' in topic_low or 'headphone' in topic_low or 'headset' in topic_low or 'earbud' in topic_low:
        rows = [r for r in rows if not re.search(r'\b(?:fonte\s+carregador|fonte\s+para\s+notebook|carregador\s+para|fonte\s+chaveada|fonte\s+atx)\b', (r.get('titulo') or '').casefold())]
    if 'smartphone' in topic_low or 'celular' in topic_low:
        rows = [r for r in rows if not re.search(r'\b(?:carregador|power\s*bank|capa|pel[ií]cula|suporte|cabo|fone|buds|headset|adaptador)\b', (r.get('titulo') or '').casefold())]
    if len(_CACHE) >= 32:
        _CACHE.pop(next(iter(_CACHE)))
    # A short discovery cache never constitutes a fresh offer verification.
    _CACHE[topic.casefold()] = (time.monotonic() + 180, rows)
    return [dict(row) for row in rows][:limit]
