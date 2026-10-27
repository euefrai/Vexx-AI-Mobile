"""Separate known-source reading from URL-free discovery; isolated SQLite only.

Captured public documents remain local. Baseline and candidate A use identical
HTML; B uses live providers and is not a paired network quality comparison.
Agent annotations are not human gold. No model or success fabrication here.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'v5998-isolated.env')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track',choices=['A','B'],required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--dataset',type=Path,default=ROOT/'benchmarks/source_quality_v5998_dev.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--baseline-ref',choices=['cc60042','8ccbbe0'],default='cc60042')
    parser.add_argument('--artifact-version',choices=['v5998','v5999'],default='v5998')
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite evidence')
    import research,research_agents as ra,pc_agent,web_extract as we,evidence_graph as eg
    import query_intelligence as qi,search_orchestrator as orch,retrieval_trace as trace,search_providers
    loaded_sha={}
    if args.baseline:
        for mod in (qi,we,eg,search_providers,orch,research,trace,ra):
            src=subprocess.check_output(['git','show',args.baseline_ref+':'+mod.__name__+'.py'],cwd=ROOT).decode('utf-8')
            loaded_sha[mod.__name__]=hashlib.sha256(src.encode()).hexdigest()
            exec(compile(src,'<v5997:'+mod.__name__+'>','exec'),mod.__dict__)
    case=next(x for x in json.loads(args.dataset.read_text(encoding='utf-8'))['queries'] if x['id']==args.case)
    safe=hashlib.sha256((args.track+'|'+case['id']).encode()).hexdigest()[:20]
    raw=ROOT/'qa-artifacts'/args.artifact_version/'raw'/safe
    raw.mkdir(parents=True,exist_ok=True)
    out={'track':args.track,'case':{k:v for k,v in case.items() if k!='url'},'baseline':args.baseline_ref if args.baseline else None,
         'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         'code_sha256':{m.__name__:loaded_sha.get(m.__name__) or hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (we,eg,qi,orch,ra)},
         'annotation':'AGENT_OBSERVED_NOT_HUMAN_GOLD','provider_calls':[],'documents':[]}
    started=time.monotonic()
    original_extract=research.extrair_artigo
    def extraction(body,url,*a,**kw):
        rec=original_extract(body,url,*a,**kw)
        ref=hashlib.sha256(url.encode()).hexdigest()
        (raw/(ref+'.json')).write_text(json.dumps({'url':url,'body':body,'record':rec},ensure_ascii=False),encoding='utf-8')
        inspect(rec,url)
        return rec
    def inspect(rec,url):
        doc={**rec,'url':url,'texto_lido':bool(rec.get('texto')) and not rec.get('ilegivel')}
        coverage=eg.requirement_coverage(case['query'],[doc])
        candidates=rec.get('answer_passages') or we.passage_candidates(rec.get('texto',''),url,rec.get('secoes'))
        selected=eg.select_answer_passages(coverage)
        out['documents'].append({'source_ref':hashlib.sha256(url.encode()).hexdigest(),'url':url,'title':rec.get('titulo'),
            'extractor':rec.get('extrator'),'content_scope':rec.get('content_scope'),'extracted_chars':len(rec.get('texto','')),
            'document_scan':rec.get('document_scan'),
            'sections':[{ 'heading':s['titulo'],'chars':len(s['texto'])} for s in rec.get('secoes',[])],
            'generated_passages':len(candidates),'matched_passages':len(coverage['passages']),'selected_passages':len(selected),
            'requirements':[{'id':r['id'],'entity':r['entity'],'attribute':r['attribute'],'state':r['state']} for r in coverage['requirements']],
            'passages':[{'id':p['id'],'requirements':p.get('requirement_ids',[]),'support':p.get('requirement_support',{}),
                         'span':p.get('text_span'),'source_span':p.get('source_span'),'section':p.get('section'),
                         'literal':p['text'] in rec.get('texto',''),'excerpt':p['text'][:220]}
                        for p in selected],
            'answerability_status':'PARSED_FACETS_OBSERVED' if coverage['applicable'] else 'UNSUPPORTED_REQUIREMENT_SCHEMA'})
        return doc
    with tempfile.TemporaryDirectory(prefix='v5998-track-') as folder:
        db=pc_agent.open_db(Path(folder)/'qa.sqlite')
        try:
            job=ra.criar_job(db,'qa-v5998',case['query'],conv='qa-only',manual='profunda')
            with trace.observe(limit=1000) as events:
                if args.track=='A':
                    frozen=raw/'known-source.json'
                    if frozen.exists():
                        snap=json.loads(frozen.read_text(encoding='utf-8'))
                    elif case['url'].lower().endswith('.pdf'):
                        rec=research._recuperar_um({'url':case['url'],'titulo':''},None,8,case['query'])
                        snap={'url':case['url'],'record':rec,'scope':'PDF_EXTRACTION_SNAPSHOT_NOT_HTML_REEXTRACTION'}
                        frozen.write_text(json.dumps(snap,ensure_ascii=False),encoding='utf-8')
                    else:
                        final,body=research.baixar(case['url'],timeout=8)
                        snap={'url':final,'body':body}
                        frozen.write_text(json.dumps(snap,ensure_ascii=False),encoding='utf-8')
                    out['frozen_sha256']=hashlib.sha256(frozen.read_bytes()).hexdigest()
                    rec=(original_extract(snap['body'],snap['url'],consulta=case['query']) if 'body' in snap else snap['record'])
                    doc=inspect(rec,snap['url'])
                    def reader(url):
                        if orch.canonizar_url(url)!=orch.canonizar_url(snap['url']):
                            raise research.ResearchErro('Document absent from single-source snapshot','frozen_missing')
                        return copy.deepcopy(doc)
                    ra.agente_analista(db,job,{'id':'known-source','alvo':case['query']},
                                      [{'url':snap['url'],'titulo':rec.get('titulo','')}],reader,teto_paginas=1)
                else:
                    providers=ra.provedores_reais(orquestrado=True)
                    for provider in providers:
                        original=provider.buscar
                        def observed(query,limite=6,original=original,provider=provider):
                            row={'provider':provider.nome,'query':query,'candidates':[]};out['provider_calls'].append(row)
                            result=original(query,limite)
                            row['candidates']=[{'rank':n+1,'title':r.get('titulo'),'url':r.get('url'),
                                'type':r.get('tipo'),'hard_rejections':orch._context_mismatch(r,case['query'])} for n,r in enumerate(result)]
                            return result
                        provider.buscar=observed
                    research.extrair_artigo=extraction
                    ra.executar(db,job['id'],job['owner'],providers)
                    job=ra.carregar_job(db,job['owner'],job['id'])
                evidence=ra.listar_evidencias(db,job['owner'],job['id'])
                (raw/(args.output.stem+'-evidence.json')).write_text(json.dumps(evidence,ensure_ascii=False),encoding='utf-8')
                out.update(trace=events,budget=job['usados'],evidence_count=len(evidence),
                    evidence=[{'id':e['id'],'url':e.get('url'),'read':bool(e.get('texto_lido')),
                               'document_id':e.get('document_id'),'provenance':e.get('retrieval_provenance'),
                               'passage_ids':[p['id'] for p in e.get('answer_passages',[])]} for e in evidence],
                    coverage=eg.compact_coverage(eg.requirement_coverage(case['query'],evidence)))
        except Exception as exc:
            out['error_code']=getattr(exc,'codigo',type(exc).__name__)
        finally:db.close()
    out['seconds']=round(time.monotonic()-started,3)
    out['limits']=['A is seeded reading, never discovery.','B live internet is not a paired causal comparison.',
                   'No model or chat delivery in this diagnostic.','Facet states are not independent factual gold.']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:out.get(k) for k in ('track','case','evidence_count','error_code','seconds')},ensure_ascii=False))


if __name__=='__main__':main()
