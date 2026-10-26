"""Compact measured evidence; source captures and private runtime stay local."""
import json, pathlib, hashlib
P=pathlib.Path(__file__).resolve().parent

def read(name):return json.loads((P/name).read_text(encoding='utf-8-sig'))
def save(name,data):(P/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def states(d):return [{'attribute':r['attribute'],'state':r['state']} for r in (d.get('coverage') or {}).get('requirements',[])]
def browser(name):
 text=(P/name).read_text(encoding='utf-8-sig'); marker='### Result\n'
 if marker not in text:return {'error':'No browser result','log':name}
 return json.JSONDecoder().raw_decode(text.split(marker,1)[1])[0]
a=[]
for f in sorted(P.glob('A-*-after-verified.json')):
 d=read(f.name);before=read(f.name.replace('after','before'))
 a.append({'case':d['case'],'frozen_sha256':d.get('frozen_sha256'),'same_frozen_input':d.get('frozen_sha256')==before.get('frozen_sha256') if d.get('frozen_sha256') else None,'before':{'evidence':before.get('evidence_count',0),'states':states(before)},'after':{'evidence':d.get('evidence_count',0),'states':states(d),'error':d.get('error_code')},'documents':[{k:x.get(k) for k in ['url','extracted_chars','generated_passages','matched_passages','selected_passages','answerability_status']} for x in d['documents']]})
save('reading-summary.json',{'scope':'Seeded reading, agent annotation, not human gold','cases':a,'nikon_full_snapshot_diagnostic':{'default_chars':8000,'diagnostic_full_chars':12375,'battery_offset':11510,'weight_710_offset':12128,'production_limit_changed':False}})
h=[]
for f in sorted(P.glob('holdout-sq-*.json')):
 d=read(f.name);h.append({'case':d['case'],'seconds':d['seconds'],'provider_calls':len(d['provider_calls']),'document_attempts':len(d['documents']),'extracted_documents':sum(x.get('extracted_chars',0)>0 for x in d['documents']),'retained_evidence':d['evidence_count'],'read_evidence':sum(bool(e.get('read')) for e in d['evidence']),'states':states(d),'parsed_requirements':len(d['coverage'].get('requirements',[])),'complete':d['coverage'].get('complete',False)})
save('external-summary.json',{'freeze_commit':'8a6cfcc','cases':h,'read_evidence_total':sum(x['read_evidence'] for x in h),'precision':None,'recall':None,'reason':'No independent human gold; nine feed references are not read documents. No tuning after opening holdout.'})
r=[]
for n in ['replay-api-ff486ed.json','replay-api-cc60042.json','replay-api-candidate-verified.json']+[f'replay-dev-{c}-{s}.json' for c in ['api','company','history'] for s in ['before','after-verified']]:
 d=read(n);r.append({'artifact':n,**{k:d.get(k) for k in ['scope','baseline_ref','frozen_input_sha256','read_calls','evidence_count','elapsed_s','sqlite_bytes','document_cache_chars','process_rss_sample_bytes']},'states':states(d),'evidence':[ {k:e.get(k) for k in ['url','url_ref','excerpt_sha256','excerpt_chars','retained_requirement_ids','document_id','passage_ids']} for e in d.get('evidence',[])]})
save('replay-summary.json',{'runs':r,'limits':['Legacy pool is incomplete; frozen_missing is not a network error.','Navigation scheduling changes baseline cardinality; counts are not proof of semantic dedup.','Same HTML replay only improved API filtering, not company/history evidence.']})
b=[]
for n in ['browser-B.log','browser-full-new-resumed.log','browser-images.log','browser-cancel.log','browser-sources-A.log','browser-extra.log','browser-gallery.log','browser-visual-C.log']:
 d=browser(n);d.pop('public_answer',None);d.pop('source_text',None);d.pop('answer_coverage',None);b.append({'artifact':n,'result':d})
save('e2e-summary.json',{'scope':'Authenticated disposable local Chrome + real free PC Agent; not production','runs':b})
c=[]
for n in ['C-isolated.json','C-authenticated-delivery.json']:
 d=read(n);c.append(d)
save('synthesis-summary.json',{'runs':c,'checkpoint_correction':read('C-checkpoint-diagnostic.json'),'limits':['Original probe read compact job instead of terminal checkpoint: synthesis fields in first two files are not authoritative.','QA checkpoint confirms llm=false, quantity_mismatch. Isolated checkpoint already removed; review timeout proven by call and transport records.','Rejected writer text was not captured: cannot independently adjudicate numeric mismatch; no weakening of validator.']})
save('validation-summary.json',{'pytest':{'passed':1692,'skipped':4,'warnings':2,'seconds':150.86},'search':read('bench-search.log')['metricas'],'shopping':{k:read('bench-shopping.log')[k] for k in ['casos','aprovados']},'experience':{'passed':16,'total':16},'checks':['node --check both modified QA cjs','py_compile three diagnostic tools','git diff --check'],'decision':'NO_GO','production_touched':False})
files=[f for f in P.iterdir() if f.is_file() and f.name not in ['qa-runtime-private.json','qa-stop','manifest.json']]
save('manifest.json',{'files':[{ 'name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(files)],'raw_captures_not_committed':True})
print('Summaries written; holdout read evidence:',sum(x['read_evidence'] for x in h))
