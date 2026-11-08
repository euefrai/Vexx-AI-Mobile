"""Bounded, owner-scoped public bodies; evidence selection always runs again."""
import hashlib
import math
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.parse import parse_qs

_lock = threading.RLock()
_bodies = OrderedDict()
MAX_BODY = 512 * 1024
MAX_ENTRIES = 32
MAX_PER_OWNER = 8


class PublicBody(str):
    def __new__(cls, text, headers=None, status=200, fetched_at=None, checked_at=None, state='network'):
        obj = super().__new__(cls, text)
        obj.cache_headers = dict(headers or {})
        obj.http_status = status
        obj.fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        obj.checked_at = checked_at or obj.fetched_at
        obj.cache_state = state
        return obj


def response_body(text, headers, status=200):
    safe = {}
    if not hasattr(headers,'get_all') and hasattr(headers,'items'):
        headers = {str(k).lower():v for k,v in headers.items()}
    for key in ('cache-control','etag','last-modified','expires','date','age','vary','content-type'):
        values = headers.get_all(key) if hasattr(headers, 'get_all') else None
        value = ', '.join(values) if values else headers.get(key, headers.get(key.title(), ''))
        if value:
            if len(str(value))>4096:
                safe['cache-control']='no-store'
                break
            safe[key] = str(value)
    # Cookies are a storage exclusion, never copied into cache metadata.
    if headers.get('Set-Cookie') or headers.get('set-cookie'):
        safe['set-cookie'] = 'present'
    return PublicBody(text, safe, status)


def _date(value):
    try:
        stamp = parsedate_to_datetime(value)
        return stamp.timestamp() if stamp.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _validator(value):
    return value if isinstance(value, str) and len(value)<=1024 and not re.search(r'[\r\n\x00]',value) else ''


def _freshness(headers, now):
    control = headers.get('cache-control','').lower()
    if re.search(r'(?:^|,)\s*(?:no-store|private)\b',control) or headers.get('set-cookie'):
        return None
    vary = {v.strip().lower() for v in headers.get('vary','').split(',') if v.strip()}
    if not vary <= {'accept','accept-encoding','user-agent'}:
        return None
    ages = re.findall(r'(?:^|,)\s*max-age\s*=\s*"?(\d+)"?(?=\s*(?:,|$))', control)
    expires = _date(headers.get('expires'))
    lifetime = min(31_536_000,min(int(v) for v in ages)) if ages else max(0,expires-now) if expires is not None else 0
    age = headers.get('age','0')
    age = int(age) if str(age).isdigit() and len(str(age))<12 else 0
    date = _date(headers.get('date'))
    lifetime = max(0,lifetime-max(age,now-date if date is not None else 0))
    if re.search(r'(?:^|,)\s*no-cache\b',control):
        lifetime = 0
    validators = bool(_validator(headers.get('etag')) or _validator(headers.get('last-modified')))
    return lifetime if lifetime>0 or validators else None


def reader(owner, query):
    if not owner or os.getenv('JULIA_PUBLIC_DOCUMENT_CACHE','1').lower() in ('0','false','off'):
        return None
    import query_intelligence as qi
    request = qi.analyze(query)
    import search_orchestrator
    # Prices/inventory always require revalidation; current news has a short cap.
    cap = 0 if search_orchestrator.classificar(query).get('produto') else 30 if request.get('temporal') else 300
    return Reader(hashlib.sha256(str(owner).encode()).hexdigest(), cap)


class Reader:
    def __init__(self, owner, max_age=300):
        self.owner = owner
        self.max_age = max_age

    def fetch(self, url, **options):
        import research
        import retrieval_trace
        timeout=options.get('timeout',10.0)
        if (not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0
                or not set(options)<={'timeout','aceitar','max_bytes','user_agent','cancelar'}):
            return research.baixar(url,**options)
        research.url_segura(url)  # Also revalidated for in-memory hits.
        cancelled = options.get('cancelar')
        if cancelled and cancelled():
            raise research.ResearchErro('Pesquisa cancelada.','cancelada')
        parsed = urlsplit(url)
        # Capability/auth/session queries and private paths are never retained.
        safe_fragment = not parsed.fragment or bool(re.fullmatch(r'[\w.-]{1,160}',parsed.fragment))
        safe_url = (not parsed.query and safe_fragment and not re.search(
            r'/(?:login|auth|account|checkout|cart|orders|perfil|minha-conta|wp-admin)(?:/|$)',parsed.path,re.I))
        if parsed.query and not parsed.fragment:
            import publisher_reader
            params = parse_qs(parsed.query,keep_blank_values=True)
            safe_url = (parsed.hostname==publisher_reader.HOST and parsed.path==urlsplit(publisher_reader.ENDPOINT).path
                and set(params)=={'slug','per_page','_fields','context'}
                and all(len(v)==1 for v in params.values()) and params['context']==['view']
                and params['per_page']==['2'] and params['_fields']==[publisher_reader.FIELDS]
                and bool(re.fullmatch(r'[\w-]{3,300}',params['slug'][0])))
        if not safe_url:
            return research.baixar(url,**options)
        signature = (options.get('aceitar','html'),options.get('max_bytes',research.MAX_PAGINA_BYTES),
                     options.get('user_agent',''))
        document_url = parsed._replace(fragment='').geturl()
        key = (self.owner,hashlib.sha256(document_url.encode()).hexdigest(),signature)
        with _lock:
            entry = _bodies.get(key)
            if entry:
                _bodies.move_to_end(key)
                body, stored_at, server_lifetime = entry
                if time.monotonic()-stored_at < min(server_lifetime,self.max_age):
                    retrieval_trace.transport(url,'PUBLIC_BODY_CACHE_HIT')
                    return url,PublicBody(body,body.cache_headers,fetched_at=body.fetched_at,
                                          checked_at=body.checked_at,state='fresh_cache')
        conditional = {}
        if entry:
            if _validator(body.cache_headers.get('etag')):
                conditional['If-None-Match'] = body.cache_headers['etag']
            elif _validator(body.cache_headers.get('last-modified')):
                conditional['If-Modified-Since'] = body.cache_headers['last-modified']
        request_options = {**options,**({'validadores':conditional} if conditional else {})}
        final,new_body = research.baixar(url,**request_options)
        if getattr(new_body,'http_status',200)==304:
            current_tag = new_body.cache_headers.get('etag')
            if (not entry or not conditional or final!=url or ('If-None-Match' in conditional and current_tag and
                    current_tag.removeprefix('W/') != body.cache_headers.get('etag','').removeprefix('W/'))):
                with _lock:_bodies.pop(key,None)
                raise research.ResearchErro('Resposta 304 sem documento correspondente.','http')
            headers = {**body.cache_headers,**new_body.cache_headers}
            # An old Date/Age must not make a validated body falsely fresh.
            headers['age'] = new_body.cache_headers.get('age','0')
            headers['date'] = new_body.cache_headers.get('date',datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT'))
            new_body = PublicBody(body,headers,fetched_at=body.fetched_at,
                                  checked_at=new_body.checked_at,state='revalidated')
            retrieval_trace.transport(url,'PUBLIC_BODY_REVALIDATED',status=304)
        with _lock:
            current = _bodies.get(key)
            headers = getattr(new_body,'cache_headers',{})
            freshness = _freshness(headers,time.time())
            cacheable = (final==url and freshness is not None and len(new_body.encode('utf-8'))<=MAX_BODY
                         and new_body.strip() and not research.pagina_bloqueada(new_body))
            if not cacheable:
                _bodies.pop(key,None)
            elif current is not None and current is not entry:
                # Another request updated this key while ours was in flight.
                # Never replace its newer body with an older 304/200 response.
                if current[0]!=new_body or current[0].cache_headers.get('etag')!=headers.get('etag'):
                    _bodies[key]=(current[0],current[1],0)
            else:
                _bodies[key] = (PublicBody(new_body,headers,fetched_at=new_body.fetched_at,
                                         checked_at=new_body.checked_at,state=new_body.cache_state),time.monotonic(),freshness)
                owned = [k for k in _bodies if k[0]==self.owner]
                for old in owned[:-MAX_PER_OWNER]:_bodies.pop(old,None)
                while len(_bodies)>MAX_ENTRIES:_bodies.popitem(last=False)
        return final,new_body
