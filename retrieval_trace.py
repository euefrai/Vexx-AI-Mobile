"""Opt-in, bounded QA observations. No URLs, queries, page text or credentials.

Observers are context-local; callers explicitly export their own observations.
Unknown transport details remain null rather than inferring HTTP 200 from text.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib

_active = ContextVar('retrieval_trace', default=None)


@contextmanager
def observe(limit=400):
    rows = []
    token = _active.set((rows, max(1, min(int(limit), 1000))))
    try:
        yield rows
    finally:
        _active.reset(token)


def record(job_id, step_id, source, state, *, charged=False, rec=None):
    sink = _active.get()
    if sink is None or len(sink[0]) >= sink[1]:
        return
    rec = rec or {}
    # Even path segments can contain credentials or private search terms.
    # A protected reference is sufficient for joining selection/read events.
    reference = hashlib.sha256(str(source.get('url') or '').encode()).hexdigest()
    sink[0].append({'candidate_ref': reference,
                    'job_ref': hashlib.sha256(str(job_id).encode()).hexdigest(),
                    'step_ref': hashlib.sha256(str(step_id).encode()).hexdigest(),
                    'state': state, 'slot_charged': bool(charged),
                    'read': bool(rec.get('texto_lido')),
                    'extracted_chars': len(rec.get('texto') or ''),
                    'http_status': None, 'response_bytes': None})
