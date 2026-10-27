"""Same public snapshots, fixed extraction budget; no network/model calls."""
import argparse,hashlib,json,pathlib,sys,time,tracemalloc,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
if a.output.exists():raise SystemExit('Refusing to overwrite evidence')
import web_extract as w,query_intelligence as qi,evidence_graph as eg
if a.baseline:
 for m in [qi,w,eg]:exec(compile(subprocess.check_output(['git','show','8ccbbe0:'+m.__name__+'.py'],cwd=ROOT).decode('utf-8'),'<baseline>','exec'),m.__dict__)
rows=[]
cases=json.loads((ROOT/'benchmarks/source_quality_v5998_dev.json').read_text(encoding='utf-8'))['queries']
for case in cases:
 path=ROOT/'qa-artifacts/v5998/raw'/hashlib.sha256(('A|'+case['id']).encode()).hexdigest()[:20]/'known-source.json'
 if not path.exists():continue
 snap=json.loads(path.read_text(encoding='utf-8'))
 if 'body' not in snap:continue
 # Warm imports outside allocation/latency sample; all cases use same settings.
 w.extrair_pagina('<p>Warm up optional extractors before measurement.</p>')
 tracemalloc.start();start=time.perf_counter()
 rec=w.extrair_pagina(snap['body'],snap['url'],case['query'],teto=8000)
 elapsed=time.perf_counter()-start;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 rec['texto_lido']=True;start=time.perf_counter();cov=eg.requirement_coverage(case['query'],[rec]);chosen=eg.select_answer_passages(cov);selection=time.perf_counter()-start
 rows.append({'case':case['id'],'query':case['query'],'snapshot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'html_bytes':len(snap['body'].encode()),'retained_chars':len(rec['texto']),'scan':rec.get('document_scan'),'extraction_s':round(elapsed,6),'selection_s':round(selection,6),'python_allocation_peak_bytes':peak,'requirements':[{'attribute':r['attribute'],'entity':r['entity'],'state':r['state']} for r in cov['requirements']],'passages':[{'id':x['id'],'section':x.get('section'),'context_heading':x.get('context_heading'),'source_span':x.get('source_span'),'text_span':x['text_span'],'literal':x['text'] in rec['texto'],'characters':len(x['text']),'requirements':x.get('requirement_ids'),'support':x.get('requirement_support')} for x in chosen]})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'baseline':'8ccbbe0' if a.baseline else None,'scope':'PAIRED_PUBLIC_HTML_EXTRACTION_NOT_DISCOVERY_OR_LLM','output_budget':8000,'model_budget_unchanged':1800,'memory_scope':'tracemalloc Python allocations, not process RSS; timings include instrumentation','cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Cases:',len(rows),'with selected passages:',sum(bool(r['passages']) for r in rows))
