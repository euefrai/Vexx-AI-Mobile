"""Public allowlisted diagnostics; raw pages/model payloads remain local."""
import collections,hashlib,json
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
P=Path(__file__).resolve().parents[1]/'qa-artifacts/v5911'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def save(name,data):(P/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def public_url(url):
 p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))
cases=[]
for path in sorted(P.glob('holdout-qc-*.json')):
 d=read(path);cov=d.get('coverage',{});rs=cov.get('requirements',[])
 cases.append({'case':d['case'],'code_sha256':d['code_sha256'],
  'queries_sent':[{'provider':c['provider'],'query':c['query']} for c in d['provider_calls']],
  'retained_sources':[{**e,'url':public_url(e['url'])} for e in d['evidence']],
  'requirements':[{'entity':r['entity'],'attribute':r['attribute'],'type':r.get('type'),'state':r['state'],'passages':len(r.get('passage_ids',[]))} for r in rs],
  'fully_decomposed':cov.get('fully_decomposed'),'complete':cov.get('complete'),
  'provider_calls':len(d['provider_calls']),'inner_calls':len(read(P/'raw'/(path.stem+'-inner.json'))),
  'candidate_entries':sum(len(c['candidates']) for c in d['provider_calls']),
  'rejections':dict(collections.Counter(r for c in d['provider_calls'] for a in c['candidates'] for r in a.get('hard_rejections',[]))),
  'read_attempts':len(d['documents']),'extracted_documents':sum(bool(r.get('extracted_chars')) for r in d['documents']),
  'retained_entries':d['evidence_count'],'read_retained':sum(bool(e['read']) for e in d['evidence']),
  'linked_passage_ids':sum(len(e.get('passage_ids',[])) for e in d['evidence']),
  'links':len(cov.get('passages',[])),'seconds':d['seconds'],'error':d.get('error_code')})
save('holdout-summary.json',{'scope':'LIVE_EXTERNAL_NO_URL_SEEDS_NO_MODEL_NOT_HUMAN_GOLD','candidate':'71fab67',
 'later_correction':'Provider ad/snippet boundaries and synthesis-state propagation fixed later at 3de4932. This run is not a fresh evaluation of that later correction.',
 'cases':cases,'with_links':sum(bool(c['linked_passage_ids']) for c in cases),'with_entries':sum(bool(c['retained_entries']) for c in cases)})
contrast={};requests={}
for label,folder in [('A',P/'raw/contrast/A'),('B',P/'raw/contrast/B'),('C',P/'raw/C')]:
 rows=[]
 for f in sorted(folder.glob('http-*.json')):
  d=read(f);req=d['request'];response=d.get('response',{});requests.setdefault(label,req)
  rows.append({'requested_model':req.get('model'),'actual_model':response.get('model'),'http_status':d.get('http_status'),
   'elapsed_s':d['elapsed_s'],'finish':[c.get('finish_reason') for c in response.get('choices',[])],
   'answer_chars':[len(c['message'].get('content') or '') for c in response.get('choices',[])],
   'usage':{k:v for k,v in (response.get('usage') or {}).items() if k in ('prompt_tokens','completion_tokens','total_tokens')},'error':d.get('error_type')})
 contrast[label]=rows
b=json.loads(requests['B']['messages'][-1]['content']);c=json.loads(requests['C']['messages'][-1]['content'])
summary=read(P/'transport-C.json')['summary'];s=summary.get('sintese',{})
save('transport-summary.json',{'scope':'REAL_MODEL_KNOWN_PUBLIC_SOURCE_SEEDED_NOT_DISCOVERY','candidate':'71fab67',
 'A_B_requests_identical':requests['A']==requests['B'],'B_C_system_identical':requests['B']['messages'][0]==requests['C']['messages'][0],
 'B_C_quotes_identical':[x.get('quotes') for x in b['sources']]==[x.get('quotes') for x in c['sources']],
 'B_C_objective_identical':b['objective']==c['objective'],'outcomes':read(P/'raw/contrast/result.json'),
 'C':{'llm':s.get('llm'),'failure':s.get('fallback_detail'),'review':s.get('semantic_review'),'job_state':summary['status'],
      'chat_result_id':summary.get('chat_result_id'),'coverage':summary['usados'].get('answer_coverage')},
 'calls':contrast,'limit':'No success; one attempt per path. Later propagation fix tested separately and in unseeded QA, no contrast retried until green.'})
for name in ['provider-replay-before-summary.json','provider-replay-after-summary.json']:
 d=read(P/name);d['read_urls']=[public_url(u) for u in d['read_urls']]
 for c in d['candidate_rejections']:c['url']=public_url(c['url'])
 save(name,d)
development=read(P/'provider-before.json')
save('provider-trace-summary.json',{'scope':'DEVELOPMENT_LIVE_BASELINE_0959e8c_NOT_FINAL_RANKING_PROOF',
 'query':development['case']['query'],
 'calls':[{'provider':c['provider'],'query':c['query'],
           'candidates':[{**a,'url':public_url(a['url'])} for a in c['candidates']]} for c in development['provider_calls']],
 'documents':[{'url':public_url(d['url']),'title':d['title'],'extracted_chars':d['extracted_chars'],
               'generated_passages':d['generated_passages'],'matched_passages':d['matched_passages'],
               'selected_passages':d['selected_passages']} for d in development['documents']],
 'controller_decisions':development['budget'].get('controller_decisions',[]),
 'limit':'Relevance of all discarded results was not independently annotated; no precision/recall claim.'})
ui=read(P/'authenticated-summary.json')
for name in ['ui-final-verified','ui-extra']:
 lines=(P/(name+'.log')).read_text(encoding='utf-8-sig').splitlines()
 assert lines[0]=='### Result',name
 ui[name]=json.loads(lines[1])
save('browser-summary.json',{'checks':{name:ui[name] for name in ['ui-final-verified','ui-extra']},
 'console_network_errors':'Expected anonymous /api/session 401 before QA login and fetch failures during explicit offline test; no captured pageerror.',
 'visual_inspection':['source-320.png','source-1280.png','gallery-390.png','gallery-modal.png'],
 'limits':['Desktop Chrome viewport emulation, no physical phone.',
           'First gallery image loaded; keyboard moved to second while screenshot still showed loading.',
           'First repeated UI probe toggled previously open metadata closed; harness made idempotent, then passed.',
           'Composer shortened again after visual inspection; 37 focused tests passed after final copy change.']})
writer=read(P/'raw/live/http-001.json');review=read(P/'raw/live/http-002.json')
payload=json.loads(writer['request']['messages'][-1]['content'])
answer=json.loads(writer['response']['choices'][0]['message']['content'])
review_input=json.loads(review['request']['messages'][-1]['content'])
catalog={(s['id'],q['id']):q['text'] for s in payload['sources'] for q in s['quotes']}
resolved=[]
for point,paragraph in zip(answer['points'],review_input['paragraphs'],strict=True):
 quotes=[catalog[(ref['id'],ref['quote_id'])] for ref in point['evidence']]
 assert quotes==[ref['quote'] for ref in paragraph['citations']]
 resolved.append({'source_quote_ids':point['evidence'],'literal_quotes_equal_review_input':True})
save('live-synthesis-summary.json',{'scope':'REAL_UNSEEDED_CHROME_AUTHENTICATED_FREE_MODEL_PARTIAL_RESEARCH',
 'candidate':'3de4932','case':'company','source_titles':[s['title'] for s in payload['sources']],
 'source_urls':[public_url(s['url']) for s in payload['sources']],
 'writer_input_chars':len(writer['request']['messages'][-1]['content']),
 'review_input_chars':len(review['request']['messages'][-1]['content']),
 'points':resolved,'review':json.loads(review['response']['choices'][0]['message']['content']),
 'calls':[{'model':d['response']['model'],'status':d['http_status'],'seconds':d['elapsed_s'],
           'finish':[c['finish_reason'] for c in d['response']['choices']],
           'usage':{k:v for k,v in d['response']['usage'].items() if k in ('prompt_tokens','completion_tokens','total_tokens')}} for d in (writer,review)],
 'persisted':next(c for c in ui['cases'] if c['name']=='company')['reload_preserved'],
 'limit':'Literal grounding and semantic review passed locally; products relation still not recognized by coverage matrix. One partial integration success, no complete research or universal reliability.'})
print({'holdout_cases':len(cases),'with_links':sum(bool(c['linked_passage_ids']) for c in cases),'with_entries':sum(bool(c['retained_entries']) for c in cases)})
