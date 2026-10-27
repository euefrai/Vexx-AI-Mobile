"""Compare previous read records, same source text, with no external calls."""
import argparse,copy,hashlib,json,pathlib,subprocess,sys
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
import query_intelligence as qi,evidence_graph as eg
p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');args=p.parse_args()
if args.baseline:
 for m in (qi,eg):exec(compile(subprocess.check_output(['git','show','0959e8c:'+m.__name__+'.py']).decode(),'<baseline>','exec'),m.__dict__)
out=[]
for cid in ['ar-07','ar-08','ar-09']:
 d=json.loads((R/f'qa-artifacts/v5910/holdout-{cid}.json').read_text(encoding='utf-8'));records=[];digest=hashlib.sha256()
 folder=R/'qa-artifacts/v5910/raw'/hashlib.sha256(('B|'+cid).encode()).hexdigest()[:20]
 for f in sorted(folder.glob('*.json')):
  x=json.loads(f.read_text(encoding='utf-8'))
  if isinstance(x,dict) and isinstance(x.get('record'),dict):
   record=copy.deepcopy(x['record']);record.update(url=x['url'],texto_lido=True)
   records.append(record);digest.update(f.read_bytes())
 coverage=eg.requirement_coverage(d['case']['query'],records);ps=eg.select_answer_passages(coverage)
 out.append({'case':cid,'question':d['case']['query'],'input_sha256':digest.hexdigest(),
  'records':len(records),'requirements':[{'attribute':r['attribute'],'entity':r['entity'],'state':r['state']} for r in coverage['requirements']],
  'fully_decomposed':coverage.get('fully_decomposed'),'bindings':len(coverage['passages']),'selected':len(ps),'complete':coverage['complete'],
  'sources':[{'url':p.get('source_id'),'document_id':p.get('document_id'),'passage':p['id'],'support':p['support_label'],'text_span':p['text_span']} for p in ps],
  'limits':'Same previously extracted source records, no ranking, discovery or model claim; not human gold.'})
P=R/'qa-artifacts/v5911';P.mkdir(exist_ok=True,parents=True)
(P/('read-before-summary.json' if args.baseline else 'read-after-summary.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print([(d['case'],d['bindings'],d['complete']) for d in out])
