"""Separate live diagnostics from frozen-body replay; never infer global recall."""
import json
from pathlib import Path
import statistics
import subprocess
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import research
import query_intelligence as qi

QA=ROOT/'qa-artifacts/v5995'


def rows(folder):
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((QA/folder).glob('rel-*.json'))]


def counters(items):
    return dict(cases=len(items),eligible_read_flags=sum(r.get('eligible_read',0) for r in items),
        questions_with_eligible_flags=sum(bool(r.get('eligible_read')) for r in items),
        opened=sum(r.get('opened',0) for r in items),calls=sum(len(r.get('calls',[])) for r in items),
        fetches=sum(len(r.get('fetches',[])) for r in items),
        median_seconds=round(statistics.median(r['seconds'] for r in items),3))


def main():
    output=QA/'external-comparison.json'
    if output.exists():raise SystemExit('Refusing to overwrite comparative evidence')
    before,after=rows('baseline-sealed'),rows('candidate-sealed')
    assert len(before)==len(after)==16
    assert [(r['id'],r['query'],r['dataset_sha256']) for r in before]==[(r['id'],r['query'],r['dataset_sha256']) for r in after]
    replay=[];analyze=qi.analyze
    for old in before:
        sources=[]
        anchor=(old.get('request') or {}).get('resolved_at');clock=datetime.fromisoformat(anchor) if anchor else None
        qi.analyze=lambda text,now=None,timezone_name='America/Bahia':analyze(text,now or clock,timezone_name)
        try:
            for source in old.get('sources',[]):
                extracted=[e['result'] for e in old.get('extractions',[]) if e['url']==source['url']]
                if source.get('status')!='aberta' or len(extracted)!=1 or not extracted[0]:continue
                new=research._fonte_de(extracted[0],source,old['query'])
                sources.append(dict(url=source['url'],before_flag=bool(source.get('relevante')),
                    after_flag=bool(new.get('relevante')),answerability=new.get('answerability')))
        finally:qi.analyze=analyze
        replay.append(dict(id=old['id'],sources=sources))
    result=dict(scope='SMALL_NONRANDOM_LIVE_COMPARISON_AND_FROZEN_RECLASSIFICATION_NOT_HUMAN_GOLD',
        retrieval_candidate_revision=after[0]['source_revision'],
        final_replay_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        live={'baseline':counters(before),'candidate':counters(after)},
        cases=[dict(id=a['id'],query=a['query'],before=a['eligible_read'],after=b['eligible_read']) for a,b in zip(before,after)],
        frozen_replay=dict(scope='ONLY_UNIQUE_RETURNED_BASELINE_READS_NO_NETWORK_NO_MODEL_NO_NEW_DISCOVERY',
            read_count=sum(len(r['sources']) for r in replay),
            before_flags=sum(s['before_flag'] for r in replay for s in r['sources']),
            after_flags=sum(s['after_flag'] for r in replay for s in r['sources']),cases=replay),
        limitations=['Engine relevance flags are not independent source quality or answer verification.',
            'Live network/index changes prevent attributing latency or discovery differences solely to code.',
            'One question can contribute multiple reads; no population precision/recall without gold.',
            'Final prompt and academic regression fixes occurred after retrieval freeze; sealed results apply to the recorded retrieval candidate.',
            'No sealed examples were used to tune rules. Original question files and captured baseline are preserved.'])
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'live':result['live'],'replay':{k:v for k,v in result['frozen_replay'].items() if k!='cases'}},ensure_ascii=False))


if __name__=='__main__':main()
