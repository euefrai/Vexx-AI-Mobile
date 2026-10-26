"""Existing full research pipeline on frozen live candidates and documents.

Replay deliberately returns one identical frozen candidate pool per request.
It isolates reading/retention, not the quality of new provider queries.
Raw captures stay local. No model, credentials, production DB, or network replay.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'v5997-isolated.env')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',action='store_true')
    p.add_argument('--case',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline',action='store_true')
    p.add_argument('--bundle',help='Separate frozen capture; never overwrite an earlier bundle')
    args=p.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite results')
    import pc_agent,research,research_agents as ra,search_orchestrator as orch,retrieval_trace,evidence_graph as eg
    if args.baseline:
        import query_intelligence,web_extract,search_providers
        for name,module in [('query_intelligence',query_intelligence),('web_extract',web_extract),('evidence_graph',eg),('search_providers',search_providers),('search_orchestrator',orch),('research',research),('retrieval_trace',retrieval_trace),('research_agents',ra)]:
            src=subprocess.check_output(['git','show','ff486ed:'+name+'.py'],cwd=ROOT).decode('utf-8')
            exec(compile(src,'<baseline:'+name+'>','exec'),module.__dict__)
    case=next(c for c in json.loads((ROOT/'benchmarks/retrieval_v5997_dev.json').read_text(encoding='utf-8'))['queries'] if c['id']==args.case)
    if args.bundle and (not args.bundle.replace('-','').isalnum()):raise SystemExit('Invalid bundle name')
    private=ROOT/'qa-artifacts/v5997/raw'/(args.bundle or args.case)
    queries=[];reads=[];lock=threading.Lock()
    if args.capture:
        private.mkdir(parents=True,exist_ok=False)
        providers=ra.provedores_reais(orquestrado=True)
        responses=[];documents={};raw_pages={}
        for provider in providers:
            original=provider.buscar
            def observed(query,limite=6,original=original,provider=provider):
                items=original(query,limite)
                responses.append({'provider':provider.nome,'query':query,'items':copy.deepcopy(items)})
                return items
            provider.buscar=observed
        baixar=research.baixar;extract=research.extrair_artigo
        aliases={}
        def fetch(url,*a,**kw):
            final,body=baixar(url,*a,**kw)
            with lock:
                aliases[orch.canonizar_url(url)]=orch.canonizar_url(final)
                if retrieval_trace._source.get() is not None and len(raw_pages)<20:
                    raw_pages[orch.canonizar_url(final)]={'final':final,'body':body}
            return final,body
        def extraction(body,url,*a,**kw):
            rec=extract(body,url,*a,**kw)
            with lock:documents[orch.canonizar_url(url)]={**copy.deepcopy(rec),'final':url,'texto_lido':bool(rec.get('texto')) and not rec.get('ilegivel',False)}
            return rec
        research.baixar=fetch;research.extrair_artigo=extraction
        recover=None
    else:
        frozen=json.loads((private/'capture.json').read_text(encoding='utf-8'))
        pool=[];seen=set()
        for row in frozen['responses']:
            for candidate in row['items']:
                key=orch.canonizar_url(candidate.get('url',''))
                if key and key not in seen:seen.add(key);pool.append(candidate)
        class Provider:
            nome='frozen-live-pool'
            def buscar(self,query,limite=6):
                queries.append(query)
                return copy.deepcopy(pool[:limite])
        providers=[Provider()]
        def recover(url):
            reads.append(url)
            key=orch.canonizar_url(url);key=frozen['aliases'].get(key,key)
            if key not in frozen['documents']:raise research.ResearchErro('Missing frozen document','frozen_missing')
            return copy.deepcopy(frozen['documents'][key])
        if frozen.get('raw_pages'):
            def frozen_fetch(url,*a,**kw):
                reads.append(url)
                key=orch.canonizar_url(url);key=frozen['aliases'].get(key,key)
                rec=frozen['raw_pages'].get(key)
                if rec is None:raise research.ResearchErro('Missing frozen HTML','frozen_missing')
                return rec['final'],rec['body']
            research.baixar=frozen_fetch
            recover=None
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='v5997-replay-') as directory:
        db=pc_agent.open_db(Path(directory)/'qa.sqlite3')
        try:
            job=ra.criar_job(db,'qa-replay',case['query'],conv='qa-context',manual='profunda')
            with retrieval_trace.observe(limit=1000) as trace:result=ra.executar(db,job['id'],job['owner'],providers,recover)
            stored=ra.carregar_job(db,job['owner'],job['id']);evidence=ra.listar_evidencias(db,job['owner'],job['id'])
            coverage=eg.requirement_coverage(case['query'],evidence)
            out={'scope':'LIVE_CAPTURE' if args.capture else 'CONTROLLED_REPLAY_IDENTICAL_CANDIDATE_POOL_AND_DOCUMENTS_NOT_QUERY_QUALITY',
                 'extraction_executed':bool(not args.capture and frozen.get('raw_pages')),
                 'frozen_input_sha256':None if args.capture else hashlib.sha256((private/'capture.json').read_bytes()).hexdigest(),
                 'baseline':args.baseline,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 'case':case,'queries':queries,'read_calls':len(reads),'distinct_urls':len(set(map(orch.canonizar_url,reads))),
                 'slots':stored['usados']['paginas'],'evidence_count':len(evidence),'coverage':eg.compact_coverage(coverage),
                 'query_registry':stored.get('ajustes',{}).get('queries',{}),
                 'evidence':[{'id':e['id'],'url_ref':hashlib.sha256(str(e.get('url','')).encode()).hexdigest(),
                              'document_id':e.get('document_id'),'provenance':e.get('retrieval_provenance'),
                              'passage_ids':[p['id'] for p in e.get('answer_passages',[])]} for e in evidence],
                 'sqlite_bytes':db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0],
                 'document_cache_chars':db.execute('SELECT COALESCE(SUM(LENGTH(resposta)),0) FROM research_cache WHERE owner_id=? AND provedor=?',
                                                   (job['owner'],'document:'+job['id'])).fetchone()[0],
                 'trace':trace,'elapsed_s':round(time.monotonic()-start,4),'status':result.get('status')}
            if args.capture:out.update(read_calls=None,distinct_urls=None)
            try:
                import psutil
                out['process_rss_sample_bytes']=psutil.Process().memory_info().rss
            except ImportError:out['process_rss_sample_bytes']=None
            if args.capture:
                capture={'case':case,'responses':responses,'documents':documents,'aliases':aliases,'raw_pages':raw_pages}
                (private/'capture.json').write_text(json.dumps(capture,ensure_ascii=False),encoding='utf-8')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({k:out[k] for k in ('scope','slots','read_calls','evidence_count','elapsed_s')}))
        finally:db.close()


if __name__=='__main__':main()
