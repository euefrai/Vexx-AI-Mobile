"""Identical real provider pool/records/budget; no network or model calls."""
import argparse,copy,hashlib,json,os,pathlib,subprocess,sys,tempfile
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
os.environ['JULIA_ENV_FILE']=str(pathlib.Path(tempfile.gettempdir())/'v5911-none.env')
p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');a=p.parse_args()
import pc_agent,query_intelligence as qi,evidence_graph as eg,research_agents as ra,research,search_orchestrator as orch
if a.baseline:
 for mod in (qi,eg,orch,ra):exec(compile(subprocess.check_output(['git','show','0959e8c:'+mod.__name__+'.py']).decode(),'<baseline>','exec'),mod.__dict__)
P=R/'qa-artifacts/v5911';base=json.loads((P/'provider-before.json').read_text(encoding='utf-8'))
pool=[];seen=set()
for call in base['provider_calls']:
 for c in call['candidates']:
  if c['url'] not in seen:pool.append({'titulo':c['title'],'url':c['url'],'trecho':''});seen.add(c['url'])
records={};digest=hashlib.sha256()
folder=P/'raw'/hashlib.sha256(b'B|format-camera').hexdigest()[:20]
for path in sorted(folder.glob('*.json')):
 item=json.loads(path.read_text(encoding='utf-8'))
 if isinstance(item,dict) and isinstance(item.get('record'),dict):records[item['url']]=item['record'];digest.update(path.read_bytes())
reads=[]
class Frozen:
 nome='frozen-actual-provider-pool'
 def buscar(self,q,limite=6):return copy.deepcopy(pool[:limite])
def reader(url):
 reads.append(url)
 if url not in records:raise research.ResearchErro('Frozen missing','frozen_missing')
 return copy.deepcopy({**records[url],'texto_lido':True,'url':url,'final':url})
with tempfile.TemporaryDirectory(prefix='v5911-provider-') as d:
 db=pc_agent.open_db(pathlib.Path(d)/'qa.sqlite');job=ra.criar_job(db,'qa',base['case']['query'],conv='qa',manual='profunda')
 ra.executar(db,job['id'],'qa',[Frozen()],reader)
 stored=ra.carregar_job(db,'qa',job['id']);ev=ra.listar_evidencias(db,'qa',job['id']);coverage=eg.requirement_coverage(job['objetivo'],ev)
 out={'baseline':a.baseline,'scope':'SAME_REAL_POOL_FIXED_RECORDS_NOT_QUERY_QUALITY_OR_LIVE_DISCOVERY','pool':len(pool),
  'input_sha256':digest.hexdigest(),'records':len(records),'read_attempts':len(reads),'read_urls':reads,
  'retained_read':sum(bool(e.get('texto_lido')) for e in ev),'requirements':[{'attribute':r['attribute'],'state':r['state']} for r in coverage['requirements']],
  'candidate_rejections':[{'url':c['url'],'reasons':orch._context_mismatch(c,job['objetivo'])} for c in pool[:6]],
  'budget':{k:v for k,v in stored['usados'].items() if k in ('paginas','buscas','replans')}};db.close()
(P/('provider-replay-before-summary.json' if a.baseline else 'provider-replay-after-summary.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(out['retained_read'],out['requirements'])
