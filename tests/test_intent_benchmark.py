"""Benchmark de compreensão V5.1: 100+ casos PT-BR, gabarito objetivo."""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intent
import pc_agent
import shopping

RAIZ = Path(__file__).resolve().parents[1]
LIMIAR_GLOBAL = 0.90
LIMIAR_CATEGORIA = 0.75


def _sem(txt):
    return "".join(c for c in unicodedata.normalize("NFKD", (txt or "").lower())
                   if not unicodedata.combining(c))


def _legado(texto):
    t = (texto or "").lower()
    if shopping.detectar_intencao(texto):
        return ["shopping"]
    if pc_agent.intencao_pesquisa_aprofundada(texto):
        return ["research_deep"]
    if pc_agent.intencao_pesquisa(texto):
        return ["research"]
    if pc_agent.intencao_prova(texto) or pc_agent.intencao_aula(texto) \
            or pc_agent.intencao_reforco(texto):
        return ["learning"]
    if pc_agent.cmd_identidade(texto):
        return ["deterministico"]
    if re.search(r"lembre-se|o que voc|esque|pode guardar|meus eventos|anote", t):
        return ["memory"]
    if re.search(r"quanto |calcule|convert", t):
        return ["deterministico"]
    if "continuar" in t or "onde param" in t or "retome" in t:
        return ["deterministico"]
    return ["llm"]


def _confere(caso, r):
    erros = []
    if r["intencao"] != caso["int"]:
        erros.append(f"intencao {r['intencao']}")
    for f in caso.get("ferr", []):
        if f not in r["ferramentas"]:
            erros.append(f"ferramenta {f}")
    for p in caso.get("proib", []):
        if _sem(p) not in _sem(" ".join(r["restricoes"]["proibidas"])):
            erros.append(f"proibida {p}")
    for k, v in caso.get("formato", {}).items():
        if r["restricoes"]["formato"].get(k) != v:
            erros.append(f"formato {k}")
    if "ref" in caso and r["referencias"]["tipo"] != caso["ref"]:
        erros.append(f"ref {r['referencias']['tipo']}")
    if "corr" in caso and r["correcao"] != caso["corr"]:
        erros.append("correcao")
    ent = caso.get("ent", {})
    if ent.get("categoria") and r["entidades"].get("categoria") != ent["categoria"]:
        erros.append(f"categoria {r['entidades'].get('categoria')}")
    if "orcamento_max" in ent and (r["entidades"].get("orcamento", {}) or {}).get("max") != ent["orcamento_max"]:
        erros.append("orcamento_max")
    return erros


def test_benchmark_compreensao():
    dados = json.loads((RAIZ / "benchmarks" / "intent_v1.json").read_text(encoding="utf-8"))
    casos = dados["casos"]
    assert len(casos) >= 100, f"só {len(casos)} casos"
    por_cat = defaultdict(lambda: [0, 0])
    falhas, legado_hit, novo_hit, total_ferr = [], 0, 0, 0
    for i, caso in enumerate(casos):
        r = intent.analisar(caso["t"], caso.get("ctx"))
        erros = _confere(caso, r)
        cat = caso.get("cat", "?")
        por_cat[cat][1] += 1
        if erros:
            falhas.append(f"#{i} [{cat}] {caso['t'][:50]} -> {erros}")
        else:
            por_cat[cat][0] += 1
        if caso.get("ferr"):
            total_ferr += 1
            if caso["ferr"][0] in r["ferramentas"]:
                novo_hit += 1
            if caso["ferr"][0] in _legado(caso["t"]):
                legado_hit += 1
    total = len(casos)
    acc = (total - len(falhas)) / total
    print(f"\nINTENT-BENCH: {total - len(falhas)}/{total} = {acc:.3f}")
    for cat in sorted(por_cat):
        ok, n = por_cat[cat]
        print(f"  {cat}: {ok}/{n} = {ok / n:.3f}")
    print(f"  roteamento: novo {novo_hit}/{total_ferr} vs legado {legado_hit}/{total_ferr}")
    for f in falhas[:15]:
        print("  FALHA " + f)
    assert acc >= LIMIAR_GLOBAL, f"acurácia {acc:.3f} < {LIMIAR_GLOBAL}"
    for cat, (ok, n) in por_cat.items():
        assert ok / n >= LIMIAR_CATEGORIA, f"categoria {cat}: {ok / n:.3f}"
    assert novo_hit >= legado_hit, "regressão vs roteamento legado"
