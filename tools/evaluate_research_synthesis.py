"""Opt-in real model writing evaluation; no retrieval, daemon or production DB.

python tools/evaluate_research_synthesis.py --live
Records each attempt immediately. No automatic retries or provider switching.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pc_agent
import research_agents as ra


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--cases', default='')
    parser.add_argument('--output', default='qa-artifacts/research-synthesis-evaluation.json')
    args = parser.parse_args()
    corpus = json.loads((ROOT / 'benchmarks/research_synthesis_v1.json').read_text(encoding='utf-8'))
    out = ROOT / args.output
    import tempfile
    db = pc_agent.open_db(Path(tempfile.mkdtemp(prefix='vexx-synthesis-eval-')) / 'eval.sqlite3')
    result = {'scope': corpus['scope'], 'retrieval_tested': False, 'real_model': True,
              'model': pc_agent.ai_config()['model'], 'cases': []}
    started = time.monotonic()
    try:
        for case in corpus['cases']:
            if args.cases and case['id'] not in args.cases.split(','):
                continue
            if time.monotonic() - started > 240:
                result['stopped_reason'] = 'evaluation_time_budget'
                break
            job = ra.criar_job(db, 'evaluation-only', case['question'])
            evs = []
            for key in case['sources']:
                source = corpus['sources'][key]
                evs.append(dict(id=key, titulo=source['title'], url=source['url'],
                                dominio=urlsplit(source['url']).hostname, trecho=source['excerpt'],
                                texto_lido=True, access_state='read', score=1,
                                content_scope='manual_summary_of_official_documentation'))
            t = time.monotonic()
            before = ra.agente_sintetizador(db, job, evs, [])
            baseline_ms = round((time.monotonic()-t)*1000, 2)
            t = time.monotonic()
            candidates = []
            writer = pc_agent._research_writer(pc_agent.ai_config(), threading.Event())
            def capture(messages, timeout):
                candidate = writer(messages, timeout)
                candidates.append(candidate[:14000])
                return candidate
            after = ra.agente_sintetizador(db, job, evs, [], capture, timeout=20)
            result['cases'].append({'id': case['id'], 'question': case['question'],
                'baseline_ms': baseline_ms, 'assisted_ms': round((time.monotonic()-t)*1000, 2),
                'accepted': after['llm'], 'fallback_reason': after.get('fallback_reason'),
                'candidate': candidates[0] if candidates else '',
                'baseline': before, 'result': after})
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(case['id'], 'accepted' if after['llm'] else 'fallback', flush=True)
        result['accepted'] = sum(c['accepted'] for c in result['cases'])
        result['completed'] = len(result['cases'])
        result['elapsed_s'] = round(time.monotonic()-started, 2)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        db.close()


if __name__ == '__main__':
    main()
