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
    ('samsung', 'Samsung Galaxy A56 256 GB, menor preço.', 'shopping'),
    ('basketball', 'Tênis de basquete até R$ 300.', 'shopping'),
    ('transformer', 'Como funciona a arquitetura Transformer? Fontes técnicas.', 'research'),
    ('semiconductors', 'Pesquise estudos científicos recentes sobre avanços em materiais semicondutores.', 'research'),
    ('scientific-transformer', 'Pesquise estudos científicos sobre a arquitetura Transformer.', 'research'),
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
    requests, pages, calls, discovered, item_pages = [], [], [], [], []
    download, json_download, search = research.baixar, research._baixar_json, sp.buscar
    discovery, item_reader, market_json = research._buscar_orquestrado, shopping._recuperar_ofertas, shopping._get_json
    started = time.monotonic()

    def observed_download(url, *args, **kwargs):
        tick = time.monotonic()
        entry = {'url': url, 'error': ''}
        requests.append(entry)
        try:
            final, body = download(url, *args, **kwargs)
            entry.update(final=final, chars=len(body), ms=round((time.monotonic()-tick)*1000, 2))
            return final, body
        except Exception as exc:
            entry.update(error=getattr(exc, 'codigo', type(exc).__name__), ms=round((time.monotonic()-tick)*1000, 2), http=getattr(exc, 'http', None))
            raise

    def observed_json(url, *args, **kwargs):
        tick = time.monotonic()
        entry = {'url': url, 'error': ''}
        requests.append(entry)
        try:
            value = json_download(url, *args, **kwargs)
            entry['ms'] = round((time.monotonic()-tick)*1000, 2)
            return value
        except Exception as exc:
            entry.update(error=getattr(exc, 'codigo', type(exc).__name__), ms=round((time.monotonic()-tick)*1000, 2), http=getattr(exc, 'http', None))
            raise

    def observed_search(provider, query, *args, **kwargs):
        call = {'provider': provider, 'query': query}
        calls.append(call)
        tick = time.monotonic()
        try:
            return search(provider, query, *args, **kwargs)
        finally:
            call['ms'] = round((time.monotonic()-tick)*1000, 2)

    def observed_discovery(*args, **kwargs):
        hits, info = discovery(*args, **kwargs)
        discovered.extend({k: h.get(k) for k in ('titulo', 'url', 'origem')} for h in hits)
        return hits, info

    def observed_item(url, *args, **kwargs):
        products = item_reader(url, *args, **kwargs)
        diagnostic = args[3] if len(args) > 3 else kwargs.get('relatorio', [])
        item_pages.append({'url': url, 'offers': len(products),
                           'extracted': products, 'diagnostic': [d for d in (diagnostic or []) if d.get('url') == url]})
        return products

    def observed_market(url, *args, **kwargs):
        tick = time.monotonic()
        entry = {'url': url, 'error': ''}
        requests.append(entry)
        try:
            value = market_json(url, *args, **kwargs)
            entry['ms'] = round((time.monotonic()-tick)*1000, 2)
            return value
        except Exception as exc:
            entry.update(error=getattr(exc, 'codigo', type(exc).__name__), ms=round((time.monotonic()-tick)*1000, 2), http=getattr(exc, 'http', None))
            raise

    research.baixar, research._baixar_json, sp.buscar = observed_download, observed_json, observed_search
    research._buscar_orquestrado, shopping._recuperar_ofertas, shopping._get_json = observed_discovery, observed_item, observed_market
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
            'url', 'titulo', 'status', 'origem', 'trecho', 'texto_lido', 'publicado_em',
            'relevante', 'content_scope', 'full_text_fetched', 'autor', 'publicador',
            'doi', 'authors', 'year', 'publication_type', 'review_status', 'abstract', 'provider_url')})
    return {'case': name, 'query': query, 'mode': mode,
            'seconds': round(time.monotonic()-started, 3), 'sources': pages,
            'opened_sources': sum(s.get('status') == 'aberta' and s.get('metadata_source') != 'academic_provider' for s in sources) if mode == 'research' else None,
            'usable_sources': result.get('fontes_uteis'), 'discovered': discovered,
            'item_pages': item_pages,
            'products': products, 'confirmed_offers': sum(shopping._tier(p) == 'confirmada' for p in products),
            'intent': orch.classificar(query), 'criteria': result.get('criterios'), 'state': result.get('estado', result.get('erro') or result.get('descoberta', {}).get('motivo_final', '')),
            'provider_decisions': result.get('descoberta', result.get('provedores')),
            'page_diagnostics': result.get('diagnostico_paginas'),
            'bibliographic_reads': sum(s.get('access_state') == 'abstract_metadata' for s in sources),
            'queries': result.get('consultas', []), 'search_calls': calls, 'requests': requests,
            'extraction': result.get('verificacao'), 'excluded': result.get('excluidos'),
            'jdui': shopping.fence_resultado(result) if mode == 'shopping' else None,
            'alternatives': result.get('alternativas'), 'final': final,
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
