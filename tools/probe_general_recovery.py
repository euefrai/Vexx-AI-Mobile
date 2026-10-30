"""Explicit public-network discovery/reading probe. No model, private data or fixtures."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research

CASES = [
    ('python-timeout', 'Pesquise na documentação oficial de Python o que faz asyncio.timeout e o que acontece quando o prazo expira.'),
    ('ram-ssd', 'Pesquise a diferença entre memória RAM e SSD e como cada um afeta o desempenho do computador.'),
    ('stoicism', 'Pesquise o que é estoicismo e explique a distinção entre o que depende de nós e o que não depende.'),
    ('sleep-memory', 'Pesquise estudos científicos sobre privação do sono, memória e aprendizagem.'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=[c[0] for c in CASES])
    args = parser.parse_args()
    rows = []
    with sqlite3.connect(':memory:') as db:
        research.criar_tabelas(db)
        for name, query in CASES:
            if args.case and args.case != name:
                continue
            start = time.monotonic()
            result = research.pesquisa_rapida(db, 'qa-general-recovery', query,
                max_fontes=4, timeout_pagina=4, timeout_busca=4,
                orcamento={'max_consultas':3, 'max_provedores':5, 'max_tentativas':7, 'timeout_total':14})
            row = {'case':name, 'query':query, 'seconds':round(time.monotonic()-start, 3),
                   **{k:result.get(k) for k in ('estado','erro','fontes_lidas','fontes_uteis',
                       'etapas','provedores','consultas','answer_coverage','read_recovery','candidate_reservoir')},
                   'sources':[{k:f.get(k) for k in ('id','url','url_final','titulo','status','relevante',
                       'content_scope','texto_lido','trecho','acessado_em')} for f in result.get('fontes', [])]}
            rows.append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k:row[k] for k in ('case','seconds','estado','fontes_lidas','fontes_uteis')}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
