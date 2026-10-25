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
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['JULIA_ENV_FILE'] = str(Path(tempfile.gettempdir()) / 'v5996-isolated.env')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'benchmarks/context_lock_v5996_external.json')
    parser.add_argument('--capture-private', action='store_true', help='Keep extracted public QA pages in ignored local files')
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
    dataset = args.dataset
    dataset_value = json.loads(dataset.read_text(encoding='utf-8'))
    rows = dataset_value if isinstance(dataset_value,list) else dataset_value['queries']
    case = dict(next(row for row in rows if row['id'] == args.case))
    case.setdefault('query',case.get('question'))
    captured = []
    capture_lock = threading.Lock()
    if args.capture_private:
        capture_dir = ROOT / 'qa-artifacts/v5996/dev-private' / args.output.stem
        capture_dir.mkdir(parents=True,exist_ok=False)
        extract = research.extrair_artigo
        def observed_extract(page, url, *a, **kw):
            result = extract(page,url,*a,**kw)
            with capture_lock:
                if len(captured) < 40:
                    ref = hashlib.sha256(str(url).encode()).hexdigest()
                    path = capture_dir / f'{len(captured):02}-{ref}.json'
                    path.write_text(json.dumps({'url':url,'result':result},ensure_ascii=False),encoding='utf-8')
                    captured.append(ref)
            return result
        research.extrair_artigo = observed_extract
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
                      'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                      'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                       for name in ('query_intelligence.py','research.py','research_agents.py','retrieval_trace.py')},
                      'private_extract_count':len(captured),
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
