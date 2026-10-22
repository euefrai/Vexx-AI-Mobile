"""Bounded real before/after probes. No LLM, credentials or production DB.

Each case runs in its own process with a 75s ceiling. Raw public page bodies
stay out of reports; source excerpts, extraction counts and failures remain.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = [
    ('lenovo', 'Notebook Lenovo com 16 GB RAM até R$ 3.000.', 'shopping'),
    ('samsung', 'Celular Samsung Galaxy A56 256 GB, menor preço.', 'shopping'),
    ('basketball', 'Tênis de basquete até R$ 300.', 'shopping'),
    ('transformer', 'Como funciona a arquitetura Transformer? Fontes técnicas.', 'research'),
    ('frameworks', 'Compare FastAPI e Django usando documentação.', 'research'),
    ('batteries', 'Pesquise estudos científicos recentes sobre baterias de estado sólido.', 'research'),
    ('asyncio', 'Analise a documentação oficial do Python sobre asyncio.', 'research'),
]


def run_case(case):
    import research
    import shopping
    import search_orchestrator as orch
    import search_providers as sp
    name, query, mode = case
    requests, pages, calls = [], [], []
    download, json_download, search = research.baixar, research._baixar_json, sp.buscar
    started = time.monotonic()

    def observed_download(url, *args, **kwargs):
        entry = {'url': url, 'error': ''}
        requests.append(entry)
        try:
            final, body = download(url, *args, **kwargs)
            entry.update(final=final, chars=len(body))
            return final, body
        except Exception as exc:
            entry['error'] = getattr(exc, 'codigo', type(exc).__name__)
            raise

    def observed_json(url, *args, **kwargs):
        entry = {'url': url, 'error': ''}
        requests.append(entry)
        try:
            return json_download(url, *args, **kwargs)
        except Exception as exc:
            entry['error'] = getattr(exc, 'codigo', type(exc).__name__)
            raise

    def observed_search(provider, query, *args, **kwargs):
        calls.append({'provider': provider, 'query': query})
        return search(provider, query, *args, **kwargs)

    research.baixar, research._baixar_json, sp.buscar = observed_download, observed_json, observed_search
    db = sqlite3.connect(':memory:')
    research.criar_tabelas(db)
    shopping.criar_tabelas(db)
    if mode == 'shopping':
        result = shopping.pesquisar(db, 'v59-probe', query, usar_cache=False, teto_paginas=3)
        final = shopping.resumo_texto(result)
        sources = result.get('fontes', [])
        products = result.get('produtos', [])
    else:
        result = research.pesquisa_rapida(db, 'v59-probe', query, max_fontes=3,
            orcamento={'max_consultas': 2, 'max_provedores': 3, 'timeout_total': 16},
            timeout_busca=4, timeout_pagina=5)
        final = research.resumo_deterministico(result.get('fontes', []), query)
        sources, products = result.get('fontes', []), []
    for source in sources:
        pages.append({key: source.get(key) for key in (
            'url', 'titulo', 'status', 'origem', 'trecho', 'texto_lido', 'publicado_em')})
    return {'case': name, 'query': query, 'mode': mode,
            'seconds': round(time.monotonic()-started, 3), 'sources': pages,
            'opened_sources': sum(s.get('status') == 'aberta' for s in sources),
            'products': products, 'confirmed_offers': sum(
                p.get('verificacao', {}).get('estado') == 'confirmado' for p in products
                if isinstance(p.get('verificacao'), dict)),
            'criteria': result.get('criterios'), 'state': result.get('estado', result.get('erro', '')),
            'provider_decisions': result.get('descoberta', result.get('provedores')),
            'queries': result.get('consultas', []), 'search_calls': calls, 'requests': requests,
            'extraction': result.get('verificacao'), 'final': final,
            'limitations': 'Live network snapshot, no LLM. Opened/read is not an independently calibrated relevance score.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--case', choices=[c[0] for c in CASES])
    args = parser.parse_args()
    if args.case:
        case = next(c for c in CASES if c[0] == args.case)
        print(json.dumps(run_case(case), ensure_ascii=False, default=str))
        return
    rows = []
    for case in CASES:
        start = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, __file__, '--case', case[0]],
                cwd=ROOT, capture_output=True, timeout=75, encoding='utf-8', errors='replace',
                env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
            if proc.returncode:
                row = {'case': case[0], 'query': case[1], 'error': proc.stderr[-1600:]}
            else:
                row = json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            row = {'case': case[0], 'query': case[1], 'error': '75s process ceiling exceeded'}
        row.setdefault('seconds', round(time.monotonic()-start, 3))
        rows.append(row)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: row.get(k) for k in ('case', 'state', 'opened_sources', 'confirmed_offers', 'seconds', 'error')}), flush=True)


if __name__ == '__main__':
    main()
