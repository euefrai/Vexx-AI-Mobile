"""Opt-in, bounded QA observations. No URLs, queries, page text or credentials.

Observers are context-local; callers explicitly export their own observations.
Unknown transport details remain null rather than inferring HTTP 200 from text.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import re
import threading

_active = ContextVar('retrieval_trace', default=None)
_source = ContextVar('retrieval_trace_source', default=None)


@contextmanager
def observe(limit=400):
    rows = []
    scope = (rows, max(1, min(int(limit), 1000)), threading.Lock(), [False])
    token = _active.set(scope)
    try:
        yield rows
    finally:
        with scope[2]:
            scope[3][0] = True
        _active.reset(token)


def record(job_id, step_id, source, state, *, charged=False, rec=None,
           http_status=None, response_bytes=None, content_type='', request_url='', coverage=None, reason_code=''):
    sink = _active.get()
    if sink is None or len(sink[0]) >= sink[1]:
        return
    rec = rec or {}
    # Even path segments can contain credentials or private search terms.
    # A protected reference is sufficient for joining selection/read events.
    reference = hashlib.sha256(str(source.get('url') or '').encode()).hexdigest()
    row = {'candidate_ref': reference,
                    'job_ref': hashlib.sha256(str(job_id).encode()).hexdigest(),
                    'step_ref': hashlib.sha256(str(step_id).encode()).hexdigest(),
                    'state': state, 'slot_charged': bool(charged),
                    'reason_code': reason_code if re.fullmatch(r'[A-Z0-9_,]{1,120}',reason_code) else '',
                    'read': bool(rec.get('texto_lido')),
                    'extracted_chars': len(rec.get('texto') or ''),
                    'http_status': http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
                    'response_bytes': response_bytes if type(response_bytes) is int and response_bytes >= 0 else None,
                    'content_type': content_type if re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+',content_type) else '',
                    'request_ref': hashlib.sha256(request_url.encode()).hexdigest() if request_url else '',
                    'useful_passages': len((coverage or {}).get('passages', [])),
                    'requirement_ids': [r['id'] for r in (coverage or {}).get('requirements', [])
                                        if re.fullmatch(r'R-[a-f0-9]{12}', str(r.get('id', '')))]}
    with sink[2]:
        if not sink[3][0] and len(sink[0]) < sink[1]:
            sink[0].append(row)


@contextmanager
def source_scope(job_id, step_id, source):
    token = _source.set((job_id, step_id, source))
    try:
        yield
    finally:
        _source.reset(token)


def transport(url, state, *, status=None, byte_count=None, content_type=''):
    source = _source.get()
    if source is not None:
        record(*source, state, http_status=status, response_bytes=byte_count,
               content_type=content_type, request_url=str(url))
