"""Bounded real adapter comparison. No inference, credentials or full-page dumps."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    if not os.getenv('JULIA_ENV_FILE'):raise SystemExit('Use an isolated environment')
    import research as core,search_providers as sp
    out=ROOT/'qa-artifacts/v5995/provider-audit.json'
    if out.exists():raise SystemExit('Refusing to overwrite provider evidence')
    out.parent.mkdir(parents=True,exist_ok=True)
    queries=['Natura fundadores produtos','Object.assign JavaScript reference','notícias Guanambi Bahia saúde']
    tasks=[(p,q) for q in queries for p in ['ddg','bing','marginalia','wikipedia']]
    tasks += [('bing-news',queries[-1]),('google-news',queries[-1]),('stackexchange',queries[1]),
              ('hn',queries[1]),('crossref','photovoltaic energy'),('pubmed','influenza vaccine'),
              ('openlibrary','Carolina Maria de Jesus'),('worldbank','Brazil population'),
              ('bcb','cotação dólar real'),('commons','Jardim Botânico Curitiba')]
    rows=[];opened=core._abrir;download=core.baixar
    transport=[];bodies=[]
    def observe_open(url,timeout,*args):
        parts=urllib.parse.urlsplit(url)
        params={k:sp._audit_text(v) for k,v in urllib.parse.parse_qsl(parts.query)
                if k in {'q','query','search','term','srsearch','action','format','count','setlang','cc','hl','gl','ceid','language','lang','sort','filter','date_restrict'}}
        row=dict(url=sp._audit_url(url),parameters=params);transport.append(row)
        try:
            result=opened(url,timeout,*args);row['http_status']=getattr(result,'status',None);return result
        except Exception as exc:
            row['http_status']=getattr(exc,'code',getattr(exc,'http',None));raise
    def observe_body(*args,**kwargs):
        final,body=download(*args,**kwargs)
        bodies.append(dict(url=sp._audit_url(final),chars=len(body),sha256=hashlib.sha256(body.encode()).hexdigest()))
        return final,body
    core._abrir=observe_open;core.baixar=observe_body
    try:
        for provider,query in tasks:
            transport=[];bodies=[];events=[];start=time.monotonic()
            row=dict(provider=provider,query=query,scope='LIVE_EXTERNAL_ADAPTER_DISCOVERY_NOT_READ_EVIDENCE')
            try:
                with sp.observe_searches(events.append,query):items=sp.buscar(provider,query,limite=4,timeout=5)
                row['results']=[dict(rank=i+1,title=sp._audit_text(item.get('titulo'),160),
                     url=sp._audit_url(item.get('url')),snippet=sp._audit_text(item.get('trecho'),280),
                     kind=item.get('tipo'),published_at=(item.get('meta') or {}).get('publicado_em'))
                    for i,item in enumerate(items)]
                row['state']='UNJUDGED_DISCOVERY' if items else 'PROVIDER_EMPTY'
            except Exception as exc:
                row.update(state='PROVIDER_ERROR',error_code=getattr(exc,'codigo',type(exc).__name__))
            row.update(seconds=round(time.monotonic()-start,3),transport=transport,body_hashes=bodies,audit=events)
            rows.append(row)
            out.write_text(json.dumps(dict(scope='NONRANDOM_BOUNDED_COMPARISON_NOT_GLOBAL_PROVIDER_ACCURACY',rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:core._abrir=opened;core.baixar=download
    print('Adapter calls recorded:',len(rows))


if __name__=='__main__':main()
