"""Opt-in, bounded QA observations. No URLs, queries, page text or credentials.

Observers are context-local; callers explicitly export their own observations.
Unknown transport details remain null rather than inferring HTTP 200 from text.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import re
import threading
from datetime import datetime, timezone
import math

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
           http_status=None, response_bytes=None, content_type='', request_url='', coverage=None, reason_code='',
           duration_s=None,budget=None):
    sink = _active.get()
    if sink is None or len(sink[0]) >= sink[1]:
        return
    rec = rec or {}
    provenance=source.get('retrieval_provenance') or {}
    requested=[r for r in provenance.get('requirement_ids',[])[:16] if re.fullmatch(r'R-[a-f0-9]{12}',str(r))]
    support={}
    for passage in (coverage or {}).get('passages',[]):
        bindings=passage.get('requirement_support') or {passage.get('requirement_id'):passage.get('support_label')}
        for rid,label in bindings.items():
            if re.fullmatch(r'R-[a-f0-9]{12}',str(rid)) and label in ('DIRECT_SUPPORT','PARTIAL_SUPPORT'):
                if support.get(rid)!='DIRECT_SUPPORT':support[rid]=label
    events={'SELECTED':'READ_SLOT_CHARGED' if charged else 'CANDIDATE_SELECTED',
            'HTTP_RESPONSE':'HTTP_RESPONSE','BODY_RECEIVED':'FETCH_COMPLETED','REDIRECT_VALIDATED':'REDIRECT_RESOLVED',
            'CONTENT_EXTRACTED':'EXTRACTION_COMPLETED','CONTENT_EMPTY':'EXTRACTION_FAILED',
            'CACHE_REUSE':'CACHE_REUSED','SKIPPED_DUPLICATE':'DOCUMENT_DEDUPLICATED',
            'SKIPPED_LOW_PRIORITY':'CANDIDATE_SKIPPED','BUDGET_EXHAUSTED':'CANDIDATE_SKIPPED',
            'RELEVANCE_REJECTED':'EVIDENCE_REJECTED','PASSAGE_NOT_FOUND':'PASSAGE_REJECTED'}
    # Even path segments can contain credentials or private search terms.
    # A protected reference is sufficient for joining selection/read events.
    reference = hashlib.sha256(str(source.get('url') or '').encode()).hexdigest()
    row = {'candidate_ref': reference if source.get('url') else '',
                    'candidate_id':provenance.get('candidate_id','') if re.fullmatch(r'C-[a-f0-9]{20}',str(provenance.get('candidate_id',''))) else '',
                    'source_ref':reference if source.get('url') else '',
                    'timestamp':datetime.now(timezone.utc).isoformat(), 'event':events.get(state,state),
                    'duration_s':duration_s if type(duration_s) in (float,int) and math.isfinite(duration_s) and duration_s>=0 else None,
                    'budget_consumed':{k:v for k,v in (budget or {}).items() if k in ('paginas','buscas','replans') and type(v) is int and v>=0},
                    'query_ids':[q for q in provenance.get('query_ids',[])[:16] if re.fullmatch(r'Q-[a-f0-9]{20}',str(q))],
                    'provider':provenance.get('provider','') if re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',str(provenance.get('provider',''))) else '',
                    'rank':provenance.get('rank') if type(provenance.get('rank')) is int and provenance['rank']>0 else None,
                    'document_id':rec.get('document_id','') if re.fullmatch(r'D-[a-f0-9]{24}',str(rec.get('document_id',''))) else '',
                    'job_ref': hashlib.sha256(str(job_id).encode()).hexdigest() if job_id else '',
                    'step_ref': hashlib.sha256(str(step_id).encode()).hexdigest() if step_id else '',
                    'duplicate_of':rec.get('duplicate_of','') if re.fullmatch(r'[a-f0-9]{64}',str(rec.get('duplicate_of',''))) else '',
                    'state': state, 'slot_charged': bool(charged),
                    'reason_code': reason_code if re.fullmatch(r'[A-Z0-9_,]{1,120}',reason_code) else '',
                    'read': bool(rec.get('texto_lido')),
                    'extracted_chars': len(rec.get('texto') or ''),
                    'document_scan':{k:v for k,v in (rec.get('document_scan') or {}).items()
                                     if k in ('available_chars','scanned_elements','retained_chars','selected_passages','late_passages','output_budget')
                                     and type(v) is int and 0<=v<=2*1024*1024},
                    'http_status': http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
                    'response_bytes': response_bytes if type(response_bytes) is int and response_bytes >= 0 else None,
                    'content_type': content_type if re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+',content_type) else '',
                    'request_ref': hashlib.sha256(request_url.encode()).hexdigest() if request_url else '',
                    'useful_passages': len((coverage or {}).get('passages', [])),
                    'passage_yield':{k:v for k,v in ((coverage or {}).get('diagnostics') or {}).items()
                                     if k in ('read_documents','generated_passages','matched_bindings','retained_bindings')
                                     and type(v) is int and 0<=v<=100000},
                    'requested_requirement_ids':requested,
                    'requirement_ids':list(support) if coverage is not None else requested,
                    'requirement_support':support,
                    'passage_ids':list(dict.fromkeys(p['id'] for p in (coverage or {}).get('passages',[])
                                                    if re.fullmatch(r'P-[a-f0-9]{16}',str(p.get('id','')))))[:40]}
    with sink[2]:
        if not sink[3][0] and len(sink[0]) < sink[1]:
            sink[0].append(row)


def summarize(rows):
    """Only observations: no final-answer correctness or independent gold claim."""
    def candidates(states):return {r['candidate_ref'] for r in rows if r.get('candidate_ref') and r['state'] in states}
    reasons={}
    for row in rows:
        if row['event'] in ('EVIDENCE_REJECTED','PASSAGE_REJECTED','CANDIDATE_SKIPPED','FETCH_BLOCKED','EXTRACTION_FAILED'):
            key=row.get('reason_code') or row['state'];reasons[key]=reasons.get(key,0)+1
    return {'discovered':len(candidates({'CANDIDATE_DISCOVERED'})),
            'selected':len(candidates({'SELECTED'})), 'slots_charged':sum(bool(r['slot_charged']) for r in rows),
            'read':len({r['candidate_ref'] for r in rows if r.get('candidate_ref') and r.get('read')}),
            'cache_reused':len(candidates({'CACHE_REUSE'})), 'blocked':len(candidates({'FETCH_BLOCKED'})),
            'cache_reuse_events':sum(r['state']=='CACHE_REUSE' for r in rows),
            'duplicates':len(candidates({'SKIPPED_DUPLICATE','DOCUMENT_DEDUPLICATED'})),
            'partial':len(candidates({'EVIDENCE_PARTIAL'})), 'direct':len(candidates({'EVIDENCE_SUPPORTED'})),
            'chat_messages_persisted':sum(r['state']=='JDUI_DELIVERED' for r in rows),
            'loss_reasons':reasons,'scope':'OBSERVED_RETRIEVAL_NOT_FACTUAL_GOLD'}


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
