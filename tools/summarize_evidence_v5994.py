"""Counters and explicitly limited manual metadata judgments after code freeze."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa-artifacts/v5994'


def rows(name):
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((QA/name).glob('*.json')) if p.name!='summary.json']


def counters(items):
    return dict(cases=len(items),eligible_reads=sum(r.get('eligible_read',0) for r in items),
        cases_with_eligible_read=sum(bool(r.get('eligible_read')) for r in items),
        opened=sum(r.get('opened',0) for r in items),calls=sum(len(r.get('calls',[])) for r in items),
        fetches=sum(len(r.get('fetches',[])) for r in items),errors=sum(bool(r.get('error')) for r in items),
        median_seconds=statistics.median(r['seconds'] for r in items if isinstance(r.get('seconds'),(int,float))),
        supported_requirement_flags=sum(req['state']=='SUPPORTED' for r in items for a in r.get('answer_aware',[]) for req in (a.get('coverage') or {}).get('requirements',[])),
        partial_requirement_flags=sum(req['state']=='PARTIALLY_SUPPORTED' for r in items for a in r.get('answer_aware',[]) for req in (a.get('coverage') or {}).get('requirements',[])))


def main():
    freeze=json.loads((QA/'code-freeze.json').read_text(encoding='utf-8'))
    if any(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=sha for f,sha in freeze['files'].items()):
        raise SystemExit('Candidate changed after freeze; do not reuse held-out acceptance')
    names=['baseline-live-sealed','after-live','historical','old-twelve','old-fifteen','previous-twenty']
    runs={name:counters(rows(name)) for name in names}
    observed=Counter(a['classification'] for r in rows('after-live') for a in r.get('provider_audit',[]))
    judgments=[]
    # These 24 titles/URLs were reviewed by the agent after freeze. This is
    # topical metadata relevance, not passage gold or independently human review.
    relevant={'ei-01','ei-04','ei-05'}
    generic={'ei-02','ei-09'}
    for row in rows('after-live'):
        sample=next((a for a in row.get('provider_audit',[]) if a['provider']=='bing' and a.get('results')),None)
        if not sample:continue
        for i,item in enumerate(sample['results'][:2]):
            good=row['id'] in relevant
            judgments.append(dict(case=row['id'],query=sample['adapter_query'],provider='bing',rank=i+1,
                **item,metadata_topic_relevant=good,generic=row['id'] in generic,
                classification='RESULT_RELEVANT_BUT_UNREAD' if good else 'QUERY_CORRECT_PROVIDER_IRRELEVANT',
                criterion='Named subject present and pertinent in title/URL; no assertion of body reading or answer sufficiency.',
                annotator='agent_manual_not_independent_human',query_judgment='Original entity retained; broad wording is not itself proof of an invalid query.'))
    fidelity=dict(scope='JUDGED_METADATA_SAMPLE_NOT_PASSAGE_OR_POPULATION_PRECISION',sample_size=len(judgments),
        relevant=sum(j['metadata_topic_relevant'] for j in judgments),
        generic=sum(j['generic'] for j in judgments),
        relevant_fraction=sum(j['metadata_topic_relevant'] for j in judgments)/len(judgments),
        unique_urls=len({j['url'] for j in judgments}),
        original_source_verification='not_assessed',
        provider_events=dict(observed),judgments=judgments,
        limitations=['Top two results of first successful Bing call per case; nonrandom sample.',
                    'Query correctness reviewed from text, not an independent intent gold.',
                    'No inference of full-body eligibility, locality/time compliance or verified original ownership.',
                    'HTTP success status unavailable in legacy downloader; null never becomes 200.',
                    'DDG/Wikipedia use legacy helpers not observed by adapter request diagnostics.'])
    result=dict(scope='LIVE_EXTERNAL_ENGINE_COUNTERS_NOT_GOLD_PRECISION_OR_COMPLETE_ANSWERS',runs=runs,
        limits=['No model/chat in these retrieval probes.',
                'Live network/index/load differ; no causal latency or recall claim.',
                'One new eligible read is not consistent external improvement.',
                'Previously opened sets are diagnostics; no post-holdout algorithm tuning.'])
    (QA/'external-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (QA/'provider-fidelity.json').write_text(json.dumps(fidelity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(runs,ensure_ascii=False))


def direction(kind='direction'):
    freeze=json.loads((QA/('code-freeze-'+kind+'.json')).read_text(encoding='utf-8'))
    checks={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==sha for f,sha in freeze['files'].items()}
    if not all(checks.values()):raise SystemExit('Candidate changed after causal freeze')
    result=dict(scope='LIVE_EXTERNAL_FRESH_'+kind.upper()+'_ENGINE_COUNTERS_NOT_FACTUAL_GOLD',
        runs={name:counters(rows(name)) for name in [kind+'-baseline-sealed',kind+'-after']},
        limits=['No model/chat or independent human judgments in retrieval probes.',
                'Earlier 12-question set and 17-example sealed set are now diagnostics.',
                'Do not tune from this new held-out output.'])
    (QA/(kind+'-comparison.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (QA/('post-'+kind+'-guard.json')).write_text(json.dumps(dict(algorithm_unchanged=True,files=checks),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['runs']))


if __name__=='__main__':
    import sys
    direction('order') if '--order' in sys.argv else direction() if '--direction' in sys.argv else main()
