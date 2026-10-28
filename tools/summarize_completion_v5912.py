"""Allowlisted local evidence summaries, never raw pages/prompts/reasoning."""
import collections,json,re
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
P=Path(__file__).resolve().parents[1]/'qa-artifacts/v5912'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def save(name,data):
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return public_url(value) if isinstance(value,str) and value.startswith(('http://','https://')) else value
    (P/name).write_text(json.dumps(clean(data),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def public_url(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))


def case_summary(d):
    coverage=d.get('coverage') or {};requirements=coverage.get('requirements',[])
    return {'case':d['case'],'code_sha256':d['code_sha256'],'seconds':d['seconds'],
      'requirements':[{'entity':r['entity'],'attribute':r['attribute'],'type':r.get('type'),
                       'state':r['state'],'passage_ids':r.get('passage_ids',[])} for r in requirements],
      'fully_decomposed':coverage.get('fully_decomposed'),'retrieval_complete':coverage.get('complete'),
      'calls':len(d['provider_calls']),'queries':[{'provider':c['provider'],'query':c['query']} for c in d['provider_calls']],
      'read_observations':len(d['documents']),'nonempty_extractions':sum(bool(r.get('extracted_chars')) for r in d['documents']),
      'retained_entries':d['evidence_count'],'retained_read':sum(bool(e['read']) for e in d['evidence']),
      'retained_sources':[{**e,'url':public_url(e['url'])} for e in d['evidence']],
      'linked_passages':len({p['id'] for p in coverage.get('passages',[])}),
      'requirement_bindings':len(coverage.get('passages',[])),'error':d.get('error_code')}


def main():
    development={}
    for phase in ('before','after'):
        development[phase]=[case_summary(read(f)) for f in sorted(P.glob(phase+'-dev-*.json'))]
    save('development-summary.json',{'scope':'LIVE_DEVELOPMENT_DIFFERENT_NETWORK_RUNS_NOT_CAUSAL_RANKING_PROOF',
         'before':'40f9531','after':'ef97dfc','cases':development,
         'limit':'The before baseline reload replaced the inner-provider instrumentation; inner calls are not comparable.'})
    holdout=[case_summary(read(f)) for f in sorted(P.glob('holdout-rc-*.json'))]
    assert len(holdout)==16,'Incomplete holdout'
    save('holdout-summary.json',{'scope':'FROZEN_LIVE_EXTERNAL_NO_URL_SEEDS_NO_MODEL_NOT_HUMAN_GOLD',
        'candidate':'53d4154','later_changes':'1fee389 preserves short-field quotes and normalizes one isolated trailing delimiter; 3938bee binds semantic answer coverage. No later fresh discovery run.',
        'cases':holdout,'with_retained_read':sum(bool(c['retained_read']) for c in holdout),
        'with_linked_passages':sum(bool(c['linked_passages']) for c in holdout),
        'retrieval_complete':sum(bool(c['retrieval_complete']) for c in holdout),
        'limit':'Retrieval coverage is not a validated final answer; do not compare different holdouts causally or claim global precision.'})
    transport={}
    for stage,folder in [('ef97dfc','live'),('53d4154','final'),('1fee389','release'),('3938bee','verified')]:
        calls=[]
        for f in sorted((P/'raw'/folder).glob('http-*.json')):
            d=read(f);r=d.get('response') or {};messages=d['request']['messages']
            try:task=json.loads(messages[-1]['content']).get('task','write')
            except (ValueError,AttributeError):task='write'
            calls.append({'capture':f.name,'task':task,'requested_model':d['request']['model'],
                'effective_model':r.get('model'),'http_status':d.get('http_status'),'error_type':d.get('error_type'),
                'seconds':d['elapsed_s'],'usage':{k:v for k,v in (r.get('usage') or {}).items() if k in ('prompt_tokens','completion_tokens','total_tokens')},
                'choices':[{'finish':c.get('finish_reason'),'answer_chars':len((c.get('message') or {}).get('content') or ''),
                            'reasoning_present':c.get('reasoning_present',False)} for c in r.get('choices',[])]})
        transport[stage]=calls
    save('transport-summary.json',{'scope':'REAL_FREE_MODEL_QA_CALLS_NO_REASONING_CONTENT_PUBLISHED','stages':transport,
         'limit':'Different cases/code/payloads; not repeated identical requests until success. Reasoning was neither displayed nor used as an answer.'})
    tests={}
    for label in ('full-suite','full-final','full-release','full-verified'):
        text=(P/(label+'.log')).read_text(encoding='utf-8-sig');matches=re.findall(r'^.*\d+ passed.* in .+$',text,re.M)
        tests[label]={'result':matches[-1] if matches else 'NOT_FINISHED','exit':int((P/(label+'.exit')).read_text())}
    tests['full-release']['interruption']='Only the owned superseded pytest process was stopped after the semantic coverage defect was reproduced. This run is not a pass.'
    save('tests-summary.json',{'runs':tests,'focused':['165 passed in 31.87s after catalog fixes','142 passed in 20.73s after semantic coverage'],
         'limits':'Overlapping test runs must not be added together. First full failure had three real regressions, corrected before the next full pass.'})
    for name in ('ui-release','ui-extra-release'):
        lines=(P/(name+'.log')).read_text(encoding='utf-8-sig').splitlines();assert lines[0]=='### Result',name
        save(name+'-summary.json',json.loads(lines[1]))
    for name in ('reading-before-summary.json','reading-after-summary.json','reading-stage-one-summary.json'):
        save(name,read(P/name))
    print({'holdout':len(holdout),'with_links':sum(bool(c['linked_passages']) for c in holdout),
           'retrieval_complete':sum(bool(c['retrieval_complete']) for c in holdout),'tests':tests})


if __name__=='__main__':main()
