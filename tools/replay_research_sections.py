"""Compare extraction of one saved development HTML; no network or inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--query', required=True)
    parser.add_argument('--baseline', required=True, help='Trusted local Git revision')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    capture = json.loads(args.capture.read_text(encoding='utf-8'))
    results = {'scope': 'Saved development HTML replay; no live discovery or model synthesis',
               'baseline': args.baseline, 'query': args.query,
               'html_sha256': hashlib.sha256(capture['body'].encode()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='vexx-section-replay-') as temporary:
        os.environ['JULIA_ENV_FILE'] = str(Path(temporary) / 'no-provider.env')
        import web_extract
        import evidence_graph
        import pc_agent
        import research
        import research_agents

        previous = []
        for filename in ('web_extract', 'evidence_graph'):
            module = types.ModuleType('baseline_' + filename)
            code = subprocess.check_output(['git', 'show', f'{args.baseline}:{filename}.py'], cwd=root)
            exec(compile(code, f'{args.baseline}:{filename}.py', 'exec'), module.__dict__)
            previous.append(module)
        for label, extractor, graph in [('before', *previous), ('after', web_extract, evidence_graph)]:
            rec = extractor.extrair_pagina(capture['body'], capture['url'], args.query, usar_trafilatura=False)
            rec['texto_lido'] = True
            coverage = graph.requirement_coverage(args.query, [rec])
            results[label] = {'extracted_chars': len(rec['texto']),
                'matched_passages': len(coverage['passages']), 'complete': coverage['complete'],
                'requirements': [{'attribute': r['attribute'], 'state': r['state']} for r in coverage['requirements']],
                'selected_sections': [{'section': p.get('section'), 'chars': len(p['text']),
                    'path': [h['text'] for h in p.get('section_path', [])]} for p in rec.get('answer_passages', [])]}

        db = pc_agent.open_db(Path(temporary) / 'reading.sqlite')
        try:
            job = research_agents.criar_job(db, 'qa-replay', args.query, manual='pro')
            hit = {'id': 'saved-development-source', 'url': capture['url'], 'titulo': rec.get('titulo', '')}
            def read_saved(url):
                if url != capture['url']:
                    raise research.ResearchErro('No saved capture for this URL', 'indisponivel')
                return {**rec, 'final': url, 'texto_lido': True}
            evidence = research_agents.agente_analista(db, job, {'alvo': args.query}, [hit],
                read_saved, teto_paginas=1)
            stored = research_agents.listar_evidencias(db, job['owner'], job['id'])
            assert all(e['url'] == capture['url'] for e in stored)
            coverage = evidence_graph.requirement_coverage(args.query, stored)
            results['persistence'] = {'retained_entries': len(evidence), 'reloaded_entries': len(stored),
                'matched_passages': len(coverage['passages']), 'complete': coverage['complete'],
                'graph_failures': sum(e['tipo'] == 'evidence_graph_failed' for e in
                    research_agents.eventos_desde(db, job['owner'], job['id']))}
        finally:
            db.close()
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
