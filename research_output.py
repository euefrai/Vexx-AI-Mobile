"""Bounded output schemas for research; factual validation remains separate."""
import json
import threading
import time
import urllib.request

import hermes_bridge

_CAPABILITIES = {}
_LOCK = threading.Lock()


def supported(base, model, timeout=1):
    """Public local-proxy catalog only. Unknown capability keeps legacy calls."""
    with _LOCK:
        cached = _CAPABILITIES.get(base)
        if cached and cached[0] > time.monotonic():return model in cached[1]
    models = {}
    try:
        url = hermes_bridge._base(base, '', ()) + '/models'
        with urllib.request.urlopen(url, timeout=max(.1,min(1,timeout))) as response:
            raw = response.read(4*1024*1024+1)
        if len(raw) > 4*1024*1024:return False
        body = json.loads(raw)
        for item in body.get('data', [])[:2000]:
            if (isinstance(item,dict) and isinstance(item.get('id'),str)
                    and {'response_format','structured_outputs'} <= set(item.get('supported_parameters') or [])):
                reasoning = item.get('reasoning') or {}
                models[item['id']] = ('low' if isinstance(reasoning,dict) and reasoning.get('mandatory') is True
                    and 'low' in (reasoning.get('supported_efforts') or [])
                    and 'reasoning_effort' in item['supported_parameters'] else None)
    except (OSError, ValueError, TypeError, AttributeError, hermes_bridge.BridgeErro):
        pass
    with _LOCK:
        if len(_CAPABILITIES) >= 8:_CAPABILITIES.clear()
        _CAPABILITIES[base] = (time.monotonic()+(300 if models else 30), models)
    return model in models


def reasoning_effort(base, model):
    """Use a declared low effort only for mandatory reasoning within 1800 tokens."""
    with _LOCK:
        cached = _CAPABILITIES.get(base)
        return cached[1].get(model) if cached and cached[0] > time.monotonic() else None


def _object(properties):
    return {'type':'object', 'properties':properties,
            'required':list(properties), 'additionalProperties':False}


def _string(values=None):
    return {'type':'string', **({'enum':list(dict.fromkeys(values))} if values else {})}


def response_format(messages):
    try:
        payload = json.loads(messages[-1]['content'])
        sources = payload['sources']
        if not isinstance(sources, list) or not 1 <= len(sources) <= 6:
            return None
        ids = [s['id'] for s in sources]
        if payload.get('task') == 'verify_support':
            paragraphs = payload['paragraphs']
            if not 1 <= len(paragraphs) <= 5:return None
            positions = {'type':'integer','enum':[p['paragraph'] for p in paragraphs]}
            requirements = payload.get('requirements') or []
            options = [k for p in paragraphs for k in p.get('answer_options',{})]
            answers = _object({r['id']:{'anyOf':[_string(options), {'type':'null'}]}
                               for r in requirements}) if requirements and options else None
            supported = {'paragraph':positions,'state':_string(['SUPPORTED']), 'reason':_string(['none'])}
            if answers:supported['answers']=answers
            reasons = ['negation','entity','date','quantity','causality','scope','insufficient']
            uncertain = {'paragraph':positions,'state':_string(['PARTIAL','INCONCLUSIVE']), 'reason':_string(reasons)}
            contrary = {**uncertain,'state':_string(['CONTRADICTED']), 'counterevidence':_object({
                'source_id':_string(ids),'quote':_string(),'claim':_string()})}
            schema = _object({'reviews':{'type':'array','minItems':len(paragraphs),
                'maxItems':len(paragraphs),'items':{'anyOf':[_object(supported),_object(uncertain),_object(contrary)]}}})
            name = 'research_review'
        else:
            refs = [_object({'id':_string([s['id']]),'quote_id':_string([q['id'] for q in s['quotes']])})
                    for s in sources if s.get('quotes')]
            if not refs:return None
            schema = _object({'points':{'type':'array','maxItems':5,'items':_object({
                'text':{'type':'string','minLength':20,'maxLength':500},
                'evidence':{'type':'array','minItems':1,'maxItems':3,'items':{'anyOf':refs}}})}})
            name = 'research_draft'
        result = {'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}}
        return result if len(json.dumps(result)) <= 24000 else None
    except (ValueError, KeyError, TypeError, IndexError):
        return None
