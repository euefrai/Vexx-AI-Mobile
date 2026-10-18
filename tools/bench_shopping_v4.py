#!/usr/bin/env python3
"""Benchmark comercial V5.7 FASE 4 — identidade, orçamento e consultas.

Separado do benchmark congelado (`benchmarks/pesquisa_v57_v1.json`).
Fixtures locais e determinísticas; nenhuma loja real; sem rede.

Uso:
    python tools/bench_shopping_v4.py            # roda e mostra (NÃO grava)
    python tools/bench_shopping_v4.py --salvar   # grava artefato em qa-artifacts/
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import shopping  # noqa: E402

DADOS = RAIZ / "benchmarks" / "shopping_v4_v1.json"


def _produto(c: dict) -> dict:
    preco = c.get("preco", 1999.0)
    return {"nome": c["nome"], "marca": c.get("marca", ""),
            "modelo": c.get("modelo", ""), "preco": preco,
            "preco_texto": c.get("preco_texto", "R$ 1.999,00"),
            "preco_confirmado": preco is not None, "specs": {}}


def rodar() -> dict:
    dados = json.loads(DADOS.read_text(encoding="utf-8"))
    falhas: list = []
    total_ok = {"total": 0, "aprovados": 0}

    def caso(secao: str, nome: str, cond: bool, detalhe: str = ""):
        total_ok["total"] += 1
        if cond:
            total_ok["aprovados"] += 1
        else:
            falhas.append(f"[{secao}] {nome} {detalhe}")

    for c in dados.get("identidade", []):
        crit = shopping.extrair_criterios(c["texto"])
        p = _produto(c["produto"])
        dentro, fora = shopping.aplicar_filtros([p], crit)
        esperado = bool(c["dentro"])
        caso("identidade", c["caso"], bool(dentro) == esperado,
             f"(dentro={bool(dentro)}, esperado={esperado})")
        if not esperado and fora:
            codigos = set(fora[0].get("excluido_codigos") or [])
            esperados = set(c.get("codigos") or [])
            caso("identidade", c["caso"] + " — códigos", esperados <= codigos,
                 f"(códigos={sorted(codigos)}, esperados={sorted(esperados)})")
            alvo = c.get("alternativa_contem") or ""
            if alvo:
                alts = shopping.separar_alternativas(fora, crit)
                textos = " | ".join(a["diferencas"] for a in alts)
                caso("identidade", c["caso"] + " — alternativa",
                     alvo in textos, f"(diferenças={textos!r})")

    for c in dados.get("orcamento", []):
        got = shopping.extrair_criterios(c["texto"])["orcamento"] or {}

        def _igual(chave):
            esperado_v = c.get(chave)
            got_v = got.get(chave)
            if (got_v is None) != (esperado_v is None):
                return False
            return esperado_v is None or abs(got_v - esperado_v) < 0.01

        ok = _igual("max") and ("min" not in c or _igual("min"))
        caso("orcamento", c["texto"], ok,
             f"(orcamento={got}, esperado min={c.get('min')} max={c.get('max')})")

    for c in dados.get("consultas", []):
        qs = shopping._consultas_produto(
            shopping.extrair_criterios(c["texto"]), c["texto"])
        juntas = " | ".join(qs).lower()
        primeira = (qs[0] if qs else "").lower()
        caso("consultas", c["texto"],
             all(t.lower() in juntas for t in c.get("contem", [])),
             f"(consultas={qs})")
        ausentes = c.get("nao_primeira") or []
        if ausentes:
            caso("consultas", c["texto"] + " — 1ª limpa",
                 all(t.lower() not in primeira for t in ausentes),
                 f"(1ª={qs[0] if qs else ''!r})")

    return {"quando": datetime.now().isoformat(timespec="seconds"),
            "benchmark": dados.get("versao", "?"),
            "casos": total_ok["total"], "aprovados": total_ok["aprovados"],
            "taxa": round(total_ok["aprovados"] / total_ok["total"], 4)
            if total_ok["total"] else 0.0,
            "falhas": falhas}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salvar", action="store_true",
                    help="grava artefato em qa-artifacts/v57/ (padrão: não grava)")
    args = ap.parse_args()
    r = rodar()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if args.salvar:
        destino = RAIZ / "qa-artifacts" / "v57"
        destino.mkdir(parents=True, exist_ok=True)
        nome = f"bench-shopping-v4-{datetime.now().strftime('%Y-%m-%d')}.json"
        (destino / nome).write_text(
            json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"artefato: {destino / nome}")
    return 0 if not r["falhas"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
