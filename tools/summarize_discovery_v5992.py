"""Offline comparable counters, explicitly not an independent relevance judge."""
from collections import Counter
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa-artifacts' / 'v5992'


def summarize(name):
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((QA / name).glob('*.json')) if p.name != 'summary.json']
    rows = [r for r in rows if isinstance(r, dict) and r.get('id')]
    cases = []
    for r in rows:
        items = (r.get('reservoir') or {}).get('items', [])
        cases.append({'id': r['id'], 'query': r.get('query'), 'eligible_read': r.get('eligible_read'),
            'opened_returned': r.get('opened'), 'pool_candidates': len(items),
            'provider_candidates': sum(len(p.get('items', [])) for p in r.get('provider_responses', [])),
            'pool_reads': sum(bool(i.get('read')) for i in items),
            'provider_calls': len(r.get('calls', [])), 'observed_fetch_calls': len(r.get('fetches', [])),
            'media_metadata': len(r.get('media', [])), 'seconds': r.get('seconds'), 'state': r.get('state'),
            'source_revision': r.get('source_revision'), 'request_clock_reference': r.get('request_clock_reference'),
            'recovered_original_candidates': sum(bool(i.get('recovery_method')) for i in items),
            'recovered_original_reads': sum(bool(i.get('recovery_method')) and bool(i.get('read')) for i in items),
            'dataset_sha256': r.get('dataset_sha256'), 'error': r.get('error')})
    summary = {key: sum(c[key] or 0 for c in cases) for key in (
        'eligible_read', 'opened_returned', 'pool_candidates', 'provider_candidates', 'pool_reads',
        'provider_calls', 'observed_fetch_calls', 'media_metadata', 'recovered_original_candidates', 'recovered_original_reads')}
    summary.update(cases=len(cases), cases_with_eligible_read=sum(bool(c['eligible_read']) for c in cases),
        median_seconds=round(median(c['seconds'] for c in cases if isinstance(c['seconds'], (int, float))), 3),
        states=dict(Counter(c['state'] or 'unreported' for c in cases)), errors=sum(bool(c['error']) for c in cases))
    return {'summary': summary, 'cases': cases}


if __name__ == '__main__':
    result = {'scope': 'LIVE_EXTERNAL_COUNTERS_NOT_INDEPENDENT_JUDGMENTS',
        'limits': ['Eligible is the engine flag, not factual precision or completed answers.',
                   'Observed fetch calls exclude lower-level redirects and binary downloader traffic.',
                   'Media metadata is not textual reading, image interpretation or watched video.',
                   'Network/index drift precludes causal attribution of aggregate differences.'],
        'runs': {name: summarize(name) for name in ('baseline-diagnostic', 'accepted-diagnostic',
            'baseline-historical', 'accepted-historical', 'baseline-sealed', 'accepted-holdout')}}
    (QA / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved comparison.json; inspect only after the code is frozen.')
