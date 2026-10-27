"""Summarize actual V5999 logs without promoting partial runs to success."""
from pathlib import Path
import json,re,hashlib
P=Path(__file__).resolve().parent

def load(n):return json.loads((P/n).read_text(encoding='utf-8-sig'))
def save(n,d):(P/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def browser(n):
 text=(P/n).read_text(encoding='utf-8-sig')
 if '### Result\n' not in text:return {'log':n,'error':text.splitlines()[:3]}
 d=json.JSONDecoder().raw_decode(text.split('### Result\n',1)[1])[0]
 for key in ['public_answer','source_text','text']:d.pop(key,None)
 if isinstance(d.get('answer_coverage'),dict):
  d['answer_coverage']={'complete_parsed_facets':d['answer_coverage'].get('complete'),'requirements':[{k:r.get(k) for k in ['id','entity','attribute','state']} for r in d['answer_coverage'].get('requirements',[])]}
 return d
files=['browser-B-verified.log','browser-multifacet.log','browser-table-numbers.log','browser-insufficient.log','browser-deep-flow.log','browser-images.log','browser-cancel.log','browser-A-visual-verified.log','browser-A-source.log','browser-source-visual-verified.log','browser-extra.log','browser-gallery.log','browser-gallery-focus.log']
save('e2e-summary.json',{'scope':'Authenticated disposable local FastAPI/PC Agent/SQLite/Chrome, not production','runs':[{'log':n,'result':browser(n)} for n in files], 'limits':['Bootstrap navigation race excluded.','First focus check false, later instrumented check true; unresolved intermittent issue.','Partial extractive results are not validated LLM answers.']})
models=[]
for n in ['C-real.json','C-authenticated.json']:
 d=load(n);models.append({k:d.get(k) for k in ['track','scope','model','source_url','source_sha256','input_coverage','calls','transport','first_token_s','job_state','outcome','synthesis_llm','fallback_detail','provider_code','synthesis_budget','semantic_review','elapsed_s','chat_result_id']})
for row in models:
 c=row.get('input_coverage') or {};row['input_coverage']={'complete_parsed_facets':c.get('complete'),'requirements':[{k:r.get(k) for k in ['id','entity','attribute','state']} for r in c.get('requirements',[])]}
save('synthesis-summary.json',{'runs':models,'scope':'Real free model; known evidence seeded, never autonomous discovery','limits':['HTTP 200 empty response is failure, not success.','No TTFT for this nonstreaming path; no queue/cold-start inference.','Captured first result replayed through current validator; second run remains blocked.']})
validation={}
for n in ['full-suite.log','full-suite-final.log','full-suite-release.log','full-suite-quiet.log','runtime-recheck.log','domain-focused.log','numeric-final.log']:
 f=P/n
 if f.exists():
  text=f.read_text(encoding='utf-8-sig');m=re.findall(r'(?:\d+ failed, )?\d+ passed[^\n]*',text)
  validation[n]=m[-1] if m else 'RUNNING_OR_NO_SUMMARY'
save('validation-summary.json',{'pytest_runs':validation,'search':load('bench-search.log')['metricas'],'shopping':{k:load('bench-shopping.log')[k] for k in ['casos','aprovados']},'experience':'16/16 checks','no_tests_removed':True,'numeric_original_v5998':'unresolved; old rejected output missing','publication':'NO_GO','limits':['Final full-suite release failed runtime reconnect 15s; isolated recheck passed; preserved regardless of later outcome.','Full suite before last three tests: 1731 passed. Last three focused passed; quiet full run is authoritative for full current count.']})
manifest=[]
for f in sorted(P.iterdir()):
 if not f.is_file() or f.name in ['qa-runtime-private.json','qa-stop','manifest.json']:continue
 manifest.append({'name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size})
save('manifest.json',{'files':manifest,'private_runtime_and_raw_captures_excluded':True,'not_all_local_artifacts_committed':True})
print('Summaries updated')
