"""Opt-in external retrieval probes. Isolated SQLite; no LLM, credentials or paid API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DATA=ROOT/'benchmarks/universal_search_v599.json'


def probe(case):
    import research,shopping,search_providers as sp
    calls=[];fetches=[]
    original=sp.buscar;download=research.baixar
    def search(name,query,*args,**kwargs):
        row={'provider':name,'query':query};calls.append(row)
        try:
            found=original(name,query,*args,**kwargs);row['candidates']=len(found);return found
        except Exception as exc:
            row['error']=getattr(exc,'codigo',type(exc).__name__);raise
    def fetch(url,*args,**kwargs):
        row={'url':url};fetches.append(row)
        try:
            final,body=download(url,*args,**kwargs);row.update(final=final,chars=len(body));return final,body
        except Exception as exc:
            row['error']=getattr(exc,'codigo',type(exc).__name__);raise
    sp.buscar=search;research.baixar=fetch
    db=sqlite3.connect(':memory:');research.criar_tabelas(db);shopping.criar_tabelas(db)
    start=time.monotonic();query=case['query']
    if case['category']=='products':
        result=shopping.pesquisar(db,'qa-v599',query,usar_cache=False,teto_paginas=3)
        media=[];sources=result.get('fontes') or []
    else:
        result=research.pesquisa_rapida(db,'qa-v599',query,timeout_busca=4,timeout_pagina=5,
               orcamento={'max_consultas':2,'max_provedores':3,'timeout_total':16})
        media=result.get('midia') or [];sources=result.get('fontes') or []
    row={'id':case['id'],'category':case['category'],'query':query,'scope':'LIVE_EXTERNAL',
         'real_model':False,'seconds':round(time.monotonic()-start,3),'state':result.get('estado'),
         'calls':calls,'fetches':fetches,'request':result.get('request'),
         'reservoir':result.get('candidate_reservoir'), 'media':media,
         'sources':[{k:s.get(k) for k in ('id','url','titulo','status','relevante','publicado_em','content_scope','vertical')} for s in sources],
         'opened':sum(s.get('status')=='aberta' for s in sources),
         'eligible_read':sum(s.get('status')=='aberta' and s.get('relevante') is not False for s in sources),
         'verified_offers':sum(bool(p.get('preco_confirmado')) for p in result.get('produtos') or []),
         'precision_and_recall':'not_measured_without_independent_judgments',
         'cards_rendered':None}
    db.close();return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--split',choices=('development','evaluation'),default='development')
    parser.add_argument('--case');parser.add_argument('--output',type=Path)
    args=parser.parse_args();cases=json.loads(DATA.read_text(encoding='utf-8'))[args.split]
    if args.case:
        print(json.dumps(probe(next(c for c in cases if c['id']==args.case)),ensure_ascii=False));return
    folder=args.output or ROOT/'qa-artifacts/v599'/args.split;folder.mkdir(parents=True,exist_ok=True)
    summary={'scope':'LIVE_EXTERNAL','dataset_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),'cases':[]}
    for case in cases:
        tick=time.monotonic()
        try:
            proc=subprocess.run([sys.executable,__file__,'--live','--split',args.split,'--case',case['id']],
                  capture_output=True,timeout=65,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
            row=json.loads(proc.stdout) if proc.returncode==0 else {'id':case['id'],'error':'process_failed','detail':proc.stderr[-1200:]}
        except subprocess.TimeoutExpired:row={'id':case['id'],'error':'process_ceiling_65s'}
        (folder/(case['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        brief={k:row.get(k) for k in ('id','state','opened','eligible_read','verified_offers','error')}
        brief['seconds']=round(time.monotonic()-tick,3);summary['cases'].append(brief)
        (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(brief),flush=True)


if __name__=='__main__':main()
