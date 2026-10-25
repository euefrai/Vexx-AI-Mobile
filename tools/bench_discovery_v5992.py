"""Bounded live diagnostics using the existing retrieval engine, never an oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def probe(case):
    import research
    import search_providers as sp
    import search_orchestrator as orch
    from tools.bench_universal_v599 import probe as existing_probe
    responses, extracts, orchestration = [], [], []
    search, extract, orchestrate = sp.buscar, research._recuperar_um, orch.pesquisar_com_recuperacao

    def observe_search(name, query, *args, **kwargs):
        items = search(name, query, *args, **kwargs)
        responses.append({'provider': name, 'query': query, 'items': items})
        return items

    def observe_extract(candidate, *args, **kwargs):
        result = extract(candidate, *args, **kwargs)
        extracts.append({'url': candidate.get('url'), 'result': result})
        return result

    def observe_orchestration(*args, **kwargs):
        result = orchestrate(*args, **kwargs)
        orchestration.append({k: result.get(k) for k in ('candidate_reservoir', 'etapas', 'query_plan', 'ganho_informacao', 'lacunas')})
        return result

    sp.buscar, research._recuperar_um, orch.pesquisar_com_recuperacao = observe_search, observe_extract, observe_orchestration
    try:
        row = existing_probe(case)
        row.update(provider_responses=responses, extractions=extracts, orchestration=orchestration)
        return row
    finally:
        sp.buscar, research._recuperar_um, orch.pesquisar_com_recuperacao = search, extract, orchestrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--key', default='queries')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case')
    parser.add_argument('--sealed', action='store_true', help='Do not print individual results')
    args = parser.parse_args()
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))[args.key]
    if args.case:
        row = probe(next(c for c in cases if c['id'] == args.case))
        row['source_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=ROOT).strip()
        row['dataset_sha256'] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        print(json.dumps(row, ensure_ascii=False))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for case in cases:
        command = [sys.executable, __file__, '--live', '--dataset', str(args.dataset), '--key', args.key,
                   '--output', str(args.output), '--case', case['id']]
        try:
            child = subprocess.run(command, capture_output=True, timeout=65, encoding='utf-8', cwd=ROOT,
                                   env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            row = json.loads(child.stdout) if child.returncode == 0 else {'id': case['id'], 'error': 'process_failed', 'detail': child.stderr[-1800:]}
        except subprocess.TimeoutExpired:
            row = {'id': case['id'], 'error': 'process_ceiling_65s'}
        (args.output / (case['id'] + '.json')).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        brief = {key: row.get(key) for key in ('id', 'state', 'eligible_read', 'seconds', 'error')}
        summary.append(brief)
        if not args.sealed:
            print(json.dumps(brief), flush=True)
        (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('Completed', len(summary), 'cases', flush=True)


if __name__ == '__main__':
    main()
