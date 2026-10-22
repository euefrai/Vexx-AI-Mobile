"""Opt-in real-model reviewer evaluation over frozen synthetic adversarial cases."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pc_agent
import research_synthesis as rs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', default='qa-artifacts/semantic-support-live.json')
    args = parser.parse_args()
    corpus = json.loads((ROOT/'benchmarks/semantic_support_v1.json').read_text(encoding='utf-8'))
    cfg = pc_agent.ai_config()
    writer = pc_agent._research_writer(cfg, threading.Event())
    out = ROOT/args.output
    results = {'scope': corpus['scope'], 'model': cfg['model'], 'real_model': True,
               'generation_tested': False, 'retrieval_tested': False, 'automatic_retries': 0, 'cases': []}
    started = time.monotonic()
    for case in corpus['cases']:
        if time.monotonic()-started > 180:
            results['stopped_reason'] = 'evaluation_time_budget'
            break
        points = [{'text': case['claim'], 'evidence': [{'id': 'E1', 'quote': case.get('quote', case['source'])}]}]
        sources = [{'id': 'E1', 'evidence_id': 'fixture', 'excerpt': case['source'],
                    'scope': case.get('scope', 'controlled_fixture')}]
        before = time.monotonic()
        record = {'id': case['id'], 'expected': case['state']}
        try:
            review = rs.check_support(points, sources, writer, timeout=12)[0]
            record.update(review=review, match=review['state'] == case['state'])
        except Exception as exc:
            record.update(match=False, error=rs.failure_detail(exc))
        record['elapsed_s'] = round(time.monotonic()-before, 3)
        results['cases'].append(record)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(case['id'], record.get('review', {}).get('state', record.get('error')), flush=True)
    results['completed'] = len(results['cases'])
    results['matches'] = sum(c['match'] for c in results['cases'])
    results['unsupported_classified_as_supported'] = sum(
        c['expected'] != 'SUPPORTED' and c.get('review', {}).get('state') == 'SUPPORTED' for c in results['cases'])
    results['elapsed_s'] = round(time.monotonic()-started, 3)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
