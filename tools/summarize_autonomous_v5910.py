"""Compact public metrics; raw corpus, HTTP payloads and accounts stay ignored."""
import collections,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'qa-artifacts/v5910'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def save(name,value):(P/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
rows=[]
for path in sorted(P.glob('holdout-ar-*.json')):
    d=read(path);inner=read(P/'raw'/(path.stem+'-inner.json'))
    requirements=d['coverage'].get('requirements',[])
    rows.append({'case':d['case'],'outer_provider_calls':len(d['provider_calls']),'inner_provider_calls':len(inner),
      'provider_result_entries':sum(len(c['candidates']) for c in d['provider_calls']),
      'candidate_rejections':dict(collections.Counter(r for c in d['provider_calls'] for v in c['candidates'] for r in v.get('hard_rejections',[]))),
      'read_attempts':len(d['documents']),'extracted_documents':sum(bool(v.get('extracted_chars')) for v in d['documents']),
      'selected_document_passages':sum(v.get('selected_passages',0) for v in d['documents']),
      'retained_entries':d['evidence_count'],'retained_read_sources':sum(bool(e.get('read')) for e in d['evidence']),
      'retained_answer_passage_ids':sum(len(e.get('passage_ids',[])) for e in d['evidence']),
      'requirements':[{'attribute':r['attribute'],'state':r['state']} for r in requirements],
      'schema_applicable':d['coverage']['applicable'],'complete':d['coverage']['complete'],
      'trace_reasons':dict(collections.Counter(t['reason_code'] for t in d['trace'] if t.get('reason_code'))),
      'seconds':d['seconds'],'budget':{k:v for k,v in d.get('budget',{}).items() if k in ('buscas','paginas','replans')},
      'sources':[{'url':e['url'],'read':e.get('read'),'passages':e.get('passage_ids',[])} for e in d['evidence']]})
save('holdout-summary.json',{'annotation':'AGENT_OBSERVED_NOT_HUMAN_GOLD','retrieval_tuned_after_open':False,
 'scope':'NEW_FROZEN_FULL_DISCOVERY_NO_URL_SEEDS_NO_MODEL','count':len(rows),
 'with_retained_entries':sum(bool(r['retained_entries']) for r in rows),
 'with_retained_answer_passages':sum(bool(r['retained_answer_passage_ids']) for r in rows),
 'warning':'Entries can be snippets/context. No parsed schema is not complete coverage. Different holdouts are not a causal comparison.',
 'cases':rows})
contrast={}
for label,folder in [('A',P/'raw/contrast/A'),('B',P/'raw/contrast/B'),('C',P/'raw/C')]:
    calls=[]
    for f in sorted(folder.glob('http-*.json')):
        d=read(f);response=d.get('response',{});req=d['request']
        calls.append({'requested_model':req.get('model'),'actual_model':response.get('model'),'max_tokens':req.get('max_tokens'),
          'stream':req.get('stream',False),'request_sha256':d['request_sha256'],'http_status':d.get('http_status'),
          'elapsed_s':d['elapsed_s'],'error_type':d.get('error_type'),
          'finish_reasons':[c.get('finish_reason') for c in response.get('choices',[])],
          'answer_characters':[len(c['message'].get('content') or '') for c in response.get('choices',[])],
          'usage':{k:v for k,v in (response.get('usage') or {}).items() if k in ('prompt_tokens','completion_tokens','total_tokens')},
          'reasoning_present':any(c.get('reasoning_present') for c in response.get('choices',[]))})
    contrast[label]=calls
b=read(P/'raw/contrast/B/http-001.json')['request'];a=read(P/'raw/contrast/A/http-001.json')['request'];c=read(P/'raw/C/http-001.json')['request']
bp=json.loads(b['messages'][-1]['content']);cp=json.loads(c['messages'][-1]['content'])
save('transport-summary.json',{'scope':'KNOWN_PUBLIC_SOURCE_TRANSPORT_NOT_DISCOVERY',
 'A_B_exact_request_equal':a==b,'B_C_system_equal':b['messages'][0]==c['messages'][0],
 'B_C_objective_equal':bp['objective']==cp['objective'],'B_C_verification_equal':bp['verification']==cp['verification'],
 'B_C_excerpts_equal':[x['excerpt'] for x in bp['sources']]==[x['excerpt'] for x in cp['sources']],
 'B_C_source_fields_differ':sorted({k for bs,cs in zip(bp['sources'],cp['sources']) for k in bs.keys()|cs.keys() if bs.get(k)!=cs.get(k)}),
 'B_C_passage_ranges_equal':[s.get('passage_ranges') for s in bp['sources']]==[s.get('passage_ranges') for s in cp['sources']],
 'outcomes':read(P/'raw/contrast/result.json'),'calls':contrast,
 'C':'Real login + CSRF + /api/research/start + relay + development PC Agent + temporary SQLite; timeout; evidence preserved.',
 'historical_empty_root_cause':'NOT_REPRODUCED; old raw body absent. Controlled text-part parsing and metadata loss fixed; no claim that old model cause is solved.',
 'probe_limit':'First C polling harness used wrong terminal spelling and observed for 210s; this is not model or job latency. Poll spelling fixed.'})
known=read(P/'known-source-regression.json')
save('known-source-summary.json',{k:v for k,v in known.items() if k!='cases'}|{'cases':[{
 'case':r['case'],'snapshot_sha256':r['snapshot_sha256'],'retained_chars':r['retained_chars'],'requirements':r['requirements'],
 'selected_passages':len(r['passages']),'literal_passages':all(p['literal'] for p in r['passages']),
 'source_spans':sum(bool(p.get('source_span')) for p in r['passages']),
 'scan':r['scan']} for r in known['cases']]})
print('Saved holdout, transport and known-source compact summaries')
save('controlled-summary.json',{'scope':'FROZEN_PROVIDER_POOL_AND_READ_RECORDS_NOT_LIVE_DISCOVERY',
 'before':read(P/'company-replay-before.json'),'after':read(P/'company-replay-after.json')})
ui={}
for label,name in [('live','ui.log'),('exports','ui-extra.log'),('focus_before','gallery-before.log'),('focus_after','gallery-after.log'),('focus_final','gallery-final.log')]:
    lines=(P/name).read_text(encoding='utf-8-sig').splitlines()
    if lines and lines[0]=='### Result':ui[label]=json.loads(lines[1])
    else:ui[label]={'instrument_failed':True}
save('ui-summary.json',ui)
