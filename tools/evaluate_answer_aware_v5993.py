"""Offline counters after code freeze. Never a factual gold judge or optimizer."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import summarize_discovery_v5992 as counters


def main():
    qa=ROOT/'qa-artifacts/v5993'
    if not (qa/'code-freeze.json').exists():
        raise SystemExit('Freeze code before inspecting holdout results')
    counters.QA=qa
    result={'scope':'LIVE_EXTERNAL_ENGINE_COUNTERS_NOT_GOLD_PRECISION_OR_COMPLETENESS',
            'limits':['No real model or chat rendering in retrieval probes.',
                      'Eligibility and relation-pattern support are not independent factual judgments.',
                      'Missing parser coverage is unmeasured, not zero-error extraction.',
                      'Live network/index/load differences preclude causal latency attribution.'],
            'runs':{name:counters.summarize(name) for name in ('baseline-sealed','accepted-holdout')}}
    evaluations=[]
    for file in sorted((qa/'accepted-holdout').glob('aa-*.json')):
        row=json.loads(file.read_text(encoding='utf-8'))
        coverage=next((item.get('coverage') for item in row.get('answer_aware',[]) if item.get('coverage')), {})
        req=coverage.get('requirements',[])
        evaluations.append({'id':row.get('id'),'applicable':coverage.get('applicable',False),
            'parsed_aspects':[r['attribute'] for r in req],
            'states':[r['state'] for r in req],
            'supported_pattern_flags':sum(r['state']=='SUPPORTED' for r in req),
            'required_parsed_aspects':len(req),'engine_coverage_complete':coverage.get('complete',False),
            'source_urls':[s.get('url') for s in row.get('sources',[]) if s.get('status')=='aberta'],
            'error':row.get('error')})
    result['answer_aware_engine_diagnostics']=evaluations
    (qa/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({name:run['summary'] for name,run in result['runs'].items()},ensure_ascii=False))


if __name__=='__main__':main()
