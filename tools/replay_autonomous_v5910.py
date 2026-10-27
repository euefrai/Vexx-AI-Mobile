"""Frozen provider pool + frozen extracted public records; no network/LLM."""
import argparse,copy,json,pathlib,sys,tempfile,subprocess,hashlib,os
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));os.environ['JULIA_ENV_FILE']=str(pathlib.Path(tempfile.gettempdir())/'v5910-none.env')
p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
if a.output.exists():raise SystemExit('Refusing overwrite')
import query_intelligence as qi,evidence_graph as eg,research_agents as ra,pc_agent,research,retrieval_trace as rt
if a.baseline:
 for mod in (qi,eg,ra):exec(compile(subprocess.check_output(['git','show','6d73e48:'+mod.__name__+'.py'],cwd=R).decode('utf-8'),'<baseline>','exec'),mod.__dict__)
base=json.loads((R/'qa-artifacts/v5910/baseline-company.json').read_text(encoding='utf-8'));folder=R/'qa-artifacts/v5910/raw/c7e6e05a091feb2f5cc6';records={};h=hashlib.sha256()
for f in sorted(folder.glob('*.json')):
 d=json.loads(f.read_text(encoding='utf-8'))
 if isinstance(d,dict) and isinstance(d.get('record'),dict):records[d['url']]=d['record'];h.update(f.read_bytes())
pool=[];seen=set()
for call in base['provider_calls']:
 for c in call['candidates']:
  if c['url'] not in seen:pool.append({'titulo':c['title'],'url':c['url'],'trecho':''});seen.add(c['url'])
class Frozen:
 nome='frozen-recorded-provider-pool'
 def buscar(self,query,limite=6):return copy.deepcopy(pool[:limite])
reads=[]
def reader(url):
 reads.append(url)
 if url not in records:raise research.ResearchErro('Frozen document absent','frozen_missing')
 return copy.deepcopy({**records[url],'texto_lido':True,'final':url})
with tempfile.TemporaryDirectory(prefix='v5910-replay-') as folder:
 db=pc_agent.open_db(pathlib.Path(folder)/'qa.sqlite');job=ra.criar_job(db,'qa-replay',base['case']['query'],conv='qa',manual='profunda')
 with rt.observe() as trace:ra.executar(db,job['id'],job['owner'],[Frozen()],reader)
 ev=ra.listar_evidencias(db,job['owner'],job['id']);cov=eg.requirement_coverage(job['objetivo'],ev)
 out={'base':'6d73e48','baseline':a.baseline,'scope':'FROZEN_POOL_NEUTRALIZES_QUERY_NOT_AUTONOMOUS','extraction_reexecuted':False,'input_sha256':h.hexdigest(),'pool_urls':len(pool),'available_records':len(records),'read_attempts':len(reads),'retained_read_evidence':len([e for e in ev if e.get('texto_lido')]),'requirements':[{'attribute':r['attribute'],'state':r['state']} for r in cov['requirements']],'evidence':[{'url':e['url'],'passages':len(e.get('answer_passages',[]))} for e in ev],'errors':list({t['reason_code'] for t in trace if t.get('reason_code')})};db.close()
a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(out['retained_read_evidence'],out['requirements'])
