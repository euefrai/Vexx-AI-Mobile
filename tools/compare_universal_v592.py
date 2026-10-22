"""Summarize recorded probes, retaining originals and provenance; no network."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'qa-artifacts' / 'v592'


def main():
    read = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8-sig'))
    before = {r['case']: r for r in read('baseline-universal.json')}
    after = read('final-universal-validated.json')
    repaired = read('events-cache-repair.json')
    rows = []
    for original in after:
        row = repaired if original['case'] == 'events' else original
        rows.append({
            'case': row['case'], 'query': row['query'],
            'baseline_state': before[row['case']].get('state'),
            'baseline_seconds': before[row['case']]['seconds'],
            'final_state': row.get('state'), 'final_seconds': row['seconds'],
            'usable_sources': row.get('usable_sources'),
            'confirmed_offers': row.get('confirmed_offers'),
            'request': row.get('request'),
            'observations': len((row.get('currency_data') or {}).get('observations', [])),
            'provenance': 'events-cache-repair.json' if row is repaired else 'final-universal-validated.json',
            'earlier_error': original.get('error') if row is repaired else None,
        })
    report = {'kind': 'RECORDED_EXTERNAL_PROBES',
              'limitations': 'Different network snapshots, not controlled latency benchmark. Events rerun after cache defect fix. Context page does not verify an event. No model inference or verified travel inventory.',
              'cases': rows}
    (ROOT / 'universal-comparison.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in rows:
        print(r['case'], r['final_state'], r['baseline_seconds'], '->', r['final_seconds'])


if __name__ == '__main__':
    main()
