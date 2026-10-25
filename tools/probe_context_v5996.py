"""Isolated autonomous retrieval diagnostic, no model/UI/production claims.

Baseline loads three historical modules in this subprocess only. Other code
stays current; this isolates planning changes, not a complete old release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['JULIA_ENV_FILE'] = str(Path(tempfile.gettempdir()) / 'v5996-isolated.env')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    import query_intelligence
    import research
    import research_agents as ra
    import pc_agent
    import retrieval_trace
    if args.baseline:
        for name, module in [('query_intelligence', query_intelligence), ('research', research), ('research_agents', ra)]:
            source = subprocess.check_output(['git', 'show', '39644ca:' + name + '.py'], cwd=ROOT).decode('utf-8')
            exec(compile(source, '<baseline:' + name + '>', 'exec'), module.__dict__)
    dataset = ROOT / 'benchmarks/context_lock_v5996_external.json'
    case = next(row for row in json.loads(dataset.read_text(encoding='utf-8'))['queries'] if row['id'] == args.case)
    calls = []
    providers = ra.provedores_reais(orquestrado=True)
    for provider in providers:
        original = provider.buscar
        def observed(query, limite=6, original=original, provider=provider):
            row = {'provider': provider.nome, 'query': query, 'candidates': 0}
            calls.append(row)
            result = original(query, limite)
            row['candidates'] = len(result)
            return result
        provider.buscar = observed
    with tempfile.TemporaryDirectory(prefix='v5996-context-') as directory:
        db = pc_agent.open_db(Path(directory) / 'qa.sqlite3')
        try:
            job = ra.criar_job(db, 'qa-context', case['query'], manual='profunda')
            with retrieval_trace.observe() as trace:
                result = ra.executar(db, job['id'], job['owner'], providers)
            stored = ra.carregar_job(db, job['owner'], job['id'])
            evidence = ra.listar_evidencias(db, job['owner'], job['id'])
            output = {'scope': 'LIVE_RETRIEVAL_NO_MODEL_NO_UI_NO_INDEPENDENT_GOLD',
                      'baseline_planner_modules': '39644ca' if args.baseline else None,
                      'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
                      'case': case, 'provider_calls': calls, 'trace': trace,
                      'budget_used': {k: stored['usados'].get(k) for k in ('buscas', 'paginas', 'replans')},
                      'read_evidence_count': sum(bool(e.get('texto_lido')) for e in evidence),
                      'evidence_count': len(evidence), 'status': result.get('status'),
                      'outcome': stored['usados'].get('research_outcome')}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k: output[k] for k in ('budget_used', 'read_evidence_count', 'status')}))
        finally:
            db.close()


if __name__ == '__main__':
    main()
