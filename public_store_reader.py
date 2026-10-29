"""Bounded anonymous rendering for the public stores requested by the user.

No cookies, API keys, user session, or model-provided actions are forwarded.
Anonymous quota/auth errors disable the fallback temporarily; direct reading stays available.
"""
import json
import http.client
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

STORES = ('kabum.com.br', 'mercadolivre.com.br', 'shopee.com.br')
ENDPOINT = 'https://api.firecrawl.dev/v2/scrape'
_slots = threading.BoundedSemaphore(2)
_cooldown_until = 0.0


class RenderedHTML(str):
    retrieval_method = 'firecrawl_public_render'


def eligible(url):
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or '').lower()
        if (p.scheme != 'https' or p.port not in (None, 443) or p.username or p.password
                or p.query or p.fragment):
            return False
        if not any(host == h or host.endswith('.'+h) for h in STORES):
            return False
        path = urllib.parse.unquote(p.path).lower()
        if re.search(r'/(?:login|auth|account|user|checkout|cart|purchase|orders|perfil|minha-conta)(?:/|$)', path):
            return False
        return path in ('','/') or bool(re.search(r'/produto/\d+|/p/mlb\d+|/mlb-\d+|-i\.\d+\.\d+',path))
    except (ValueError, TypeError):
        return False


def _open(request, timeout):
    import research
    opener = urllib.request.build_opener(research._SemRedirect, urllib.request.ProxyHandler({}),
                                        research._HTTPHandlerPublico, research._HTTPSHandlerPublico)
    return opener.open(request, timeout=timeout)


def render(url, timeout, max_bytes):
    global _cooldown_until
    import research
    if (not eligible(url) or timeout < 1 or time.monotonic() < _cooldown_until
            or not _slots.acquire(blocking=False)):
        return None
    try:
        research.url_segura(url)
        payload = {'url':url, 'formats':['rawHtml'], 'onlyMainContent':False,
                   'maxAge':0, 'timeout':max(500,int(timeout*1000)-300)}
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
            headers={'Content-Type':'application/json'}, method='POST')
        with _open(request, timeout) as response:
            if response.status != 200:
                return None
            limit = min(4*1024*1024, max_bytes*2+65536)
            raw = response.read(limit+1)
            if len(raw)>limit:
                return None
            result = json.loads(raw)
        if not isinstance(result,dict) or result.get('success') is not True:
            return None
        data = result.get('data')
        if not isinstance(data,dict): return None
        meta = data.get('metadata')
        if not isinstance(meta,dict): return None
        final = meta.get('url') or ''
        if meta.get('statusCode') != 200 or not eligible(final):
            return None
        research.url_segura(final)
        # A rendered redirect cannot silently change the destination store.
        if urllib.parse.urlsplit(final).hostname != urllib.parse.urlsplit(url).hostname:
            return None
        page = data.get('rawHtml')
        if not isinstance(page,str) or not page.strip() or len(page.encode('utf-8'))>max_bytes:
            return None
        if research.pagina_bloqueada(page): return None
        title,text = research.extrair_texto_html(page)
        if len(text.strip()) < 100: return None
        return final,RenderedHTML(page)
    except urllib.error.HTTPError as exc:
        if exc.code in (401,402,403,429):
            _cooldown_until=time.monotonic()+300
        return None
    except (OSError, ValueError, RecursionError, http.client.HTTPException, research.ResearchErro):
        return None
    finally:
        _slots.release()


def fetch(url, *, timeout=6.0, max_bytes=None):
    import research
    started = time.monotonic()
    enabled = os.environ.get('JULIA_PUBLIC_STORE_RENDER','0').lower() not in ('0','false','off')
    original_error = None
    options = {'timeout':timeout}
    if max_bytes is not None: options['max_bytes']=max_bytes
    try:
        original = research.baixar(url, **options)
    except research.ResearchErro as exc:
        if exc.codigo != 'bloqueado' or getattr(exc,'http',0) in (401,429): raise
        original_error = exc
        original = None
    if enabled and eligible(url):
        needs_render = original is None
        if original:
            _,text=research.extrair_texto_html(original[1])
            needs_render = len(text.strip()) < 100 or research.pagina_bloqueada(original[1])
        remaining = timeout-(time.monotonic()-started)
        if needs_render and remaining >= 1:
            rendered = render(url,remaining,max_bytes or research.MAX_PAGINA_BYTES)
            if rendered: return rendered
    if original_error: raise original_error
    return original
