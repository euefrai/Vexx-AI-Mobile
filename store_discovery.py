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
             'na', 'a', 'à', 'e', 'para', 'por', 'gpu', 'vram'}
    return ' '.join(word for word in words if word.casefold() not in noise)[:120]


def extract_kabum(page, limit=8):
    match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', page, re.S | re.I)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))['props']['pageProps']['data']['catalogServer']['data']
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
    if target.hostname != 'www.kabum.com.br' or not target.path.startswith('/busca/') or research.pagina_bloqueada(page):
        return []
    rows = extract_kabum(page, limit=12)
    if len(_CACHE) >= 32:
        _CACHE.pop(next(iter(_CACHE)))
    # A short discovery cache never constitutes a fresh offer verification.
    _CACHE[topic.casefold()] = (time.monotonic() + 180, rows)
    return [dict(row) for row in rows][:limit]
