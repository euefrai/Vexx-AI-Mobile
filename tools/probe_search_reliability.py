"""Public-network shopping check, using a disposable database and no model.

Run explicitly; this is a live probe, not an offline test or availability promise.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import shopping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    queries = [
        'Pesquise uma placa de vídeo RTX 3050 de 6 GB à venda no Brasil. Quero preço e link direto do produto.',
        'Pesquise placas de vídeo com 6 GB de VRAM para comprar no Brasil, com links diretos dos produtos e preços atuais.',
    ]
    rows = []
    with sqlite3.connect(':memory:') as db:
        research.criar_tabelas(db)
        shopping.criar_tabelas(db)
        for query in queries:
            started = time.monotonic()
            result = shopping.pesquisar(db, 'qa-public-search', query, usar_cache=False)
            products = result.get('produtos', [])
            rows.append({
                'query': query, 'elapsed_seconds': round(time.monotonic()-started, 3),
                'criteria': result.get('criterios'), 'discovery': result.get('descoberta'),
                'provider_steps': result.get('provedores'),
                'products': [{**{k:p.get(k) for k in ('nome','preco','preco_texto','url_final','url','preco_confirmado','link_veredito')},
                              'tier': shopping._tier(p)} for p in products],
                'checks': {
                    'has_products': bool(products),
                    'only_gpus': bool(products) and all(shopping._categoria_comercial(p.get('nome', '')) == 'gpu' for p in products),
                    'six_gb': bool(products) and all(re.search(r'6\s*gb', p.get('nome', ''), re.I) for p in products),
                    'has_confirmed_offer': any(shopping._tier(p) == 'confirmada' for p in products),
                },
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in rows:
        print(json.dumps({k:row[k] for k in ('query','elapsed_seconds','checks')}, ensure_ascii=False))
    return 0 if all(all(row['checks'].values()) for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
