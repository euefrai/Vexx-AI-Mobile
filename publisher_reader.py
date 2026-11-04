"""Read published articles through a publisher's explicitly supported public API."""
import html
import json
import os
import re
from datetime import datetime
from urllib.parse import urlencode, urlsplit, unquote

HOST = 'ubatanoticias.com.br'
ENDPOINT = 'https://' + HOST + '/wp-json/wp/v2/posts'
FIELDS = 'id,link,date,date_gmt,modified_gmt,status,title,content'


def enabled():
    return os.getenv('JULIA_PUBLISHER_REST', '1').lower() not in ('0', 'false', 'off')


def eligible(url):
    try:
        p = urlsplit(url)
        parts = unquote(p.path).strip('/').split('/')
        return bool(p.scheme == 'https' and p.hostname in (HOST, 'www.' + HOST)
            and p.port in (None, 443) and not p.username and not p.password
            and not p.query and not p.fragment and 1 <= len(parts) <= 4
            and all(re.fullmatch(r'[\w-]+', part) for part in parts)
            and not any(part.lower() in ('wp-json', 'wp-admin', 'feed', 'category', 'categoria',
                'tag', 'author', 'autor', 'login', 'page') for part in parts)
            and len(parts[-1]) >= 3)
    except (ValueError, TypeError):
        return False


def _identity(url):
    p = urlsplit(url)
    return unquote(p.path).rstrip('/')


def _posts(params, timeout, cancelled=None):
    import research
    target = ENDPOINT + '?' + urlencode({**params, '_fields': FIELDS, 'context': 'view'})
    final, body = research.baixar(target, timeout=timeout, aceitar='json', cancelar=cancelled)
    actual = urlsplit(final)
    if (actual.scheme != 'https' or actual.hostname not in (HOST, 'www.' + HOST)
            or actual.path.rstrip('/') != urlsplit(ENDPOINT).path):
        raise research.ResearchErro('API mudou de publicador ou recurso.', 'redirect')
    try:
        rows = json.loads(body)
    except (ValueError, RecursionError):
        raise research.ResearchErro('API de notícias devolveu JSON inválido.', 'formato') from None
    if not isinstance(rows, list):
        raise research.ResearchErro('API de notícias fora do formato.', 'formato')
    return rows[:20], final


def _record(row):
    if (not isinstance(row, dict) or row.get('status') != 'publish'
            or type(row.get('id')) is not int or row['id'] <= 0):
        return None
    link = row.get('link')
    title = row.get('title')
    content = row.get('content')
    if (not eligible(link) or not isinstance(title, dict) or not isinstance(content, dict)
            or content.get('protected') is not False):
        return None
    markup = content.get('rendered')
    rendered_title = title.get('rendered')
    if not isinstance(markup, str) or not isinstance(rendered_title, str) or not markup.strip():
        return None
    try:
        published = str(row.get('date_gmt') or '')
        datetime.fromisoformat(published)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', published):
            return None
    except ValueError:
        return None
    title = html.unescape(re.sub('<[^>]*>', '', rendered_title))[:240]
    if not title.strip():
        return None
    # Publisher/photo credits identify authorship, not the story's location.
    def caption(match):
        plain = html.unescape(re.sub('<[^>]*>', '', match.group()))
        credit = re.fullmatch(r'\s*[—–-]?\s*(?:Cr[eé]dito|Foto|Fonte)\s*:\s*Ubat[aã]\s+Not[ií]cias\s*', plain, re.I)
        return '' if credit else match.group()
    markup = re.sub(r'<figcaption\b[^>]*>.*?</figcaption>', caption, markup, flags=re.I|re.S)
    markup = re.sub(r'\(\s*Ubat[aã]\s+Not[ií]cias\s*\)(?=\s*(?:</p>)?\s*$)', '', markup, flags=re.I)
    markup = re.sub(r'<p[^>]*>\s*(?:O post|The post)\b(?:(?!</p>).)*?'
                    r'(?:apareceu primeiro em|appeared first on)(?:(?!</p>).)*?</p>\s*$',
                    '', markup, flags=re.I|re.S)
    return {'url': link, 'titulo': title, 'markup': markup,
            'publicado_em': published + 'Z', 'publisher_post_id': row['id']}


def discover(query, limit=6, timeout=3):
    import query_intelligence as qi
    import search_verticals
    import research
    request = qi.analyze(query)
    if not enabled() or request['domain'] != 'news':
        return []
    params = request.get('parameters') or {}
    # Read a bounded recent page and apply the existing date/location/topic gates.
    # A region-wide request must not become an exact-city-only API search.
    args = {'per_page': 20, 'orderby': 'date', 'order': 'desc'}
    if params.get('start_date'):
        args['after'] = params['start_date'] + 'T00:00:00'
    if params.get('end_date'):
        args['before'] = params['end_date'] + 'T23:59:59'
    if params.get('topic'):
        args['search'] = str(params['topic'])[:160]
    posts, final = _posts(args, timeout)
    found = []
    for post in posts:
        record = _record(post)
        if not record:
            continue
        _, text = research.extrair_texto_html(record.pop('markup'))
        item = {**record, 'trecho': text[:1000], 'origem': 'publisher-rest',
                'tipo': 'noticia', 'publicador': HOST, 'content_scope': 'article_candidate',
                'source_recovery': {'method': 'publisher_rest', 'api_url': final,
                                    'state': 'original_candidate'}}
        if search_verticals.assess(request, item)['eligible']:
            found.append(item)
        if len(found) >= max(1, min(12, limit)):
            break
    return found


def read(url, query, timeout=3, cancelled=None):
    """Resolve an exact article slug; never substitute another article or homepage."""
    if not enabled() or not eligible(url):
        return None
    import research
    research.url_segura(url)
    try:
        posts, final = _posts({'slug': unquote(urlsplit(url).path).strip('/').split('/')[-1],
                               'per_page': 2}, timeout, cancelled)
    except research.ResearchErro as exc:
        if exc.codigo in ('ssrf', 'cancelada'):
            raise
        import retrieval_trace
        retrieval_trace.transport(url, 'PUBLISHER_API_UNAVAILABLE', status=getattr(exc, 'http', None),
                                  reason_code=getattr(exc, 'access_reason', exc.codigo).upper())
        return None  # HTML remains available within the caller's remaining budget.
    for post in posts:
        record = _record(post)
        if not record or _identity(record['url']) != _identity(url):
            continue
        page = ('<html><head><title>' + html.escape(record['titulo']) + '</title>'
                '<meta property="article:published_time" content="' + record['publicado_em'] + '">'
                '</head><body><main><h1>' + html.escape(record['titulo']) + '</h1>'
                + record['markup'] + '</main></body></html>')
        if research.pagina_bloqueada(page):
            continue
        article = research.extrair_artigo(page, record['url'], query)
        text = article.get('texto') or ''
        if len(text.strip()) < 100 or article.get('ilegivel'):
            continue
        metadata = {**(article.get('metadados') or {}), 'publicado_em': record['publicado_em'],
                    'canonica': record['url'], 'read_method': 'publisher_rest',
                    'publisher_api_url': final, 'publisher_post_id': record['publisher_post_id']}
        return {**article, 'metadados': metadata, 'final': record['url'],
                'lida': True, 'texto_lido': True, 'access_state': 'read', 'midia': [],
                'content_scope': 'publisher_article', 'extrator': 'publisher_rest',
                'fetched_at': research.agora_iso()}
    return None
