"""QA-only request/response capture. Never enabled by production imports."""
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request


def install(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    original=urllib.request.urlopen
    lock=threading.Lock();counter=0
    def observed(req,*args,**kwargs):
        nonlocal counter
        url=getattr(req,'full_url','')
        if '/chat/completions' not in url:return original(req,*args,**kwargs)
        with lock:counter+=1;index=counter
        payload=json.loads(req.data.decode('utf-8'))
        # Intentionally no endpoint, headers, auth or reasoning in the artifact.
        safe={k:payload[k] for k in ('model','messages','max_tokens','stream','temperature') if k in payload}
        row={'request':safe,'request_sha256':hashlib.sha256(json.dumps(safe,sort_keys=True).encode()).hexdigest(),
             'timeout_s':kwargs.get('timeout')}
        started=time.monotonic()
        def save():
            row['elapsed_s']=round(time.monotonic()-started,3)
            (directory/f'http-{index:03}.json').write_text(json.dumps(row,ensure_ascii=False),encoding='utf-8')
        try:
            response=original(req,*args,**kwargs)
            row['http_status']=getattr(response,'status',None)
        except Exception as exc:
            row['error_type']=type(exc).__name__;save();raise
        class Response:
            def __enter__(self):response.__enter__();return self
            def __exit__(self,*exc):return response.__exit__(*exc)
            def __getattr__(self,name):return getattr(response,name)
            def read(self,*a,**kw):
                data=response.read(*a,**kw)
                if len(data)<=256000:
                    try:
                        body=json.loads(data)
                        row['response']={'model':body.get('model'),'usage':body.get('usage'),
                          'choices':[{'finish_reason':c.get('finish_reason'),'message':{
                            k:v for k,v in (c.get('message') or {}).items() if k in ('role','content')},
                            'reasoning_present':bool((c.get('message') or {}).get('reasoning'))}
                            for c in (body.get('choices') or [])[:4]],
                          'error_present':bool(body.get('error'))}
                    except (ValueError,TypeError):row['unparsed_response_bytes']=len(data)
                else:row['oversized_response_bytes']=len(data)
                save();return data
        return Response()
    urllib.request.urlopen=observed
    return lambda:setattr(urllib.request,'urlopen',original)


def source_fixture():
    import research
    root=Path(__file__).resolve().parents[1]
    case=next(c for c in json.loads((root/'benchmarks/source_quality_v5998_dev.json').read_text(encoding='utf-8'))['queries'] if c['id']=='hypot')
    ref=hashlib.sha256(b'A|hypot').hexdigest()[:20]
    snap=json.loads((root/'qa-artifacts/v5998/raw'/ref/'known-source.json').read_text(encoding='utf-8'))
    record=research.extrair_artigo(snap['body'],snap['url'],consulta=case['query'])
    record.update(url=snap['url'],final=snap['url'],texto_lido=True)
    return case,record


def seed_research():
    """Explicit transport fixture only, not autonomous discovery."""
    import copy
    import research,research_agents as ra
    case,record=source_fixture()
    class Source:
        nome='verified-source-transport-fixture'
        def buscar(self,query,limite=6):return [{'titulo':record['titulo'],'url':record['url']}]
    def reader(url):
        if url!=record['url']:raise research.ResearchErro('Fixture missing','frozen_missing')
        return copy.deepcopy(record)
    ra.PROVS_FABRICA=lambda:[Source()]
    ra.RECUPERAR_FABRICA=lambda:reader
    return case,record
