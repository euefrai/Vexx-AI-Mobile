"""Benchmark independente da pesquisa (V5.7) — fixtures congeladas, sem rede.

Uso:
    python tools/bench_pesquisa_v57.py            # offline (fixtures) + relatório
    python tools/bench_pesquisa_v57.py --real     # acrescenta sondas reais (rede)
    python tools/bench_pesquisa_v57.py --sem-salvar

Casos em `benchmarks/pesquisa_v57_v1.json`; roda contra as funções reais com
provedores injetados (determinístico). O baseline "antes" da auditoria está em
`docs/V5_7_PROGRESS.md` (fase 1) — este benchmark é o "depois" reproduzível.
"""
import argparse
import datetime
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import search_orchestrator as orch  # noqa: E402
import search_providers as sp  # noqa: E402
import shopping  # noqa: E402

FIX = RAIZ / "benchmarks" / "pesquisa_v57_v1.json"

ORCAMENTO = {"max_consultas": 1, "max_provedores": 1, "min_resultados": 1,
             "timeout_total": 5.0, "max_por_provedor": 4}


def _produto(base: dict) -> dict:
    return {"id": (base.get("nome") or "")[:40].lower().replace(" ", "-"),
            "nome": base.get("nome", ""), "marca": base.get("marca", ""),
            "modelo": "", "variante": "", "imagem": "", "descricao": "",
            "loja": "loja.example", "loja_dominio": "loja.example",
            "url": base.get("url", "https://loja.example/p"),
            "url_final": base.get("url", "https://loja.example/p"),
            "url_item": base.get("url_item", ""),
            "preco": base.get("preco"), "moeda": "BRL", "preco_confirmado": True,
            "preco_texto": base.get("preco_texto", ""), "preco_origem": "jsonld",
            "disponibilidade": "desconhecida", "avaliacao": None, "n_avaliacoes": 0,
            "specs": {}, "verificado_em": "2026-10-17T00:00:00+00:00",
            "item_de_listagem": base.get("item_de_listagem", False),
            "link_veredito": base.get("link_veredito", "")}


def rodar(dados: dict = None, real: bool = False, salvar: bool = True) -> dict:
    dados = dados or json.loads(FIX.read_text(encoding="utf-8"))
    grupos, falhas = {}, []

    def caso(grupo, nome, ok):
        grupos.setdefault(grupo, {"aprovados": 0, "total": 0})
        grupos[grupo]["total"] += 1
        grupos[grupo]["aprovados"] += int(bool(ok))
        if not ok:
            falhas.append(f"{grupo}: {nome}")

    # reformulação conservadora de pergunta
    for c in dados.get("reformulacao", []):
        caso("reformulacao", c["entrada"],
             orch.consulta_conteudo(c["entrada"]) == c["esperado"])

    # termos de correspondência (verbo de pergunta não conta)
    for c in dados.get("correspondencia", []):
        caso("correspondencia", c["consulta"],
             orch._termos_correspondencia(c["consulta"]) == c["termos"])

    # fluxo real junk -> reformula na mesma fonte
    original = sp.buscar
    try:
        for c in dados.get("fluxo_junk", []):
            def fake(nome, consulta, limite=6, timeout=10.0, _c=c):
                if "funciona" in consulta.lower():
                    return [dict(_c["junk"], origem=nome, tipo="pagina")]
                return [dict(a, origem=nome, tipo="pagina") for a in _c["reais"]]
            sp.buscar = fake
            res = orch.pesquisar(c["consulta"], provedores=["bing"], orcamento=ORCAMENTO)
            e = c["esperado"]
            ok = (res["correspondencia"] >= e["correspondencia_min"]
                  and res["estado"] in e["estado_em"]
                  and any(a["url"] == e["url_real_presente"] for a in res["achados"])
                  and any(e["etapa_contem"] in x for x in res["etapas"]))
            caso("fluxo_junk", c["consulta"], ok)
    finally:
        sp.buscar = original

    # republicações entre domínios
    for c in dados.get("republicacao", []):
        itens = [dict(x) for x in c["itens"]]
        unicos, descartes = orch.deduplicar(itens)
        urls = [u["url"] for u in unicos]
        rep = []
        for u in unicos:
            rep.extend(u.get("republicacoes") or [])
        ok = (urls == c["esperado_unicos"] and rep == c["esperado_republicacoes"])
        alvo = c.get("esperado_descarte_contem") or ""
        motivos = " | ".join(d["motivo"] for d in descartes)
        ok = ok and ((alvo in motivos) if alvo else ("republicação de" not in motivos))
        caso("republicacao", "|".join(urls)[:60], ok)

    # produtos: marca obrigatória + specs
    for c in dados.get("produtos", []):
        p = _produto(c["produto"])
        criterios = dict(c["criterios"])
        criterios.setdefault("texto", c["caso"])
        dentro, fora = shopping.aplicar_filtros([p], criterios)
        ok = (bool(dentro) == bool(c["dentro"]))
        if not c["dentro"] and fora:
            ok = ok and set(fora[0].get("excluido_codigos") or []) == set(c["codigos"])
        alvo = c.get("alternativa_contem") or ""
        if alvo and fora:
            textos = " | ".join(a["diferencas"] for a in
                                shopping.separar_alternativas(fora, criterios))
            ok = ok and (alvo in textos)
        caso("produtos", c["caso"], ok)

    # specs pareadas
    for c in dados.get("specs", []):
        crit = shopping.extrair_criterios(c["texto"])
        ok = True
        if c.get("categoria") is not None:
            ok = ok and crit["categoria"] == c["categoria"]
        if c.get("ram") is not None:
            ok = ok and crit["specs"].get("ram_fisica_gb") == c["ram"]
        else:
            ok = ok and "ram_fisica_gb" not in crit["specs"]
        if c.get("armazenamento") is not None:
            ok = ok and crit["specs"].get("armazenamento_gb") == c["armazenamento"]
        else:
            ok = ok and "armazenamento_gb" not in crit["specs"]
        caso("specs", c["texto"], ok)

    # links: prioridade do card e selos honestos
    for c in dados.get("links", []):
        p = _produto(c["produto"])
        if "esperado" in c:
            caso("links", c["caso"], shopping._link_do_produto(p) == c["esperado"])
        else:
            selo = shopping._selo_verificacao(p)
            caso("links", c["caso"], c["selo_contem"] in selo)

    # conteúdo desatualizado em consulta temporal (sem data: nunca acusa)
    for c in dados.get("desatualizado", []):
        itens = [dict(x) for x in c["itens"]]
        info = {"temporal": c.get("temporal", False)}
        ranking = orch.ranquear(itens, c["consulta"], [], info)
        por_url = {a["url"]: a for a in ranking}
        ok = True
        for url, acao in c["esperado"].items():
            campo = por_url.get(url, {}).get("desatualizado", "ausente")
            if acao == "desatualizado":
                ok = ok and campo is True
            elif acao == "atual":
                ok = ok and campo is False
            else:  # neutro: sem flag alguma
                ok = ok and campo == "ausente"
        if c.get("primeiro"):
            ok = ok and bool(ranking) and ranking[0]["url"] == c["primeiro"]
        caso("desatualizado", c["consulta"], ok)

    # ganho real de informação: domínio/tema novo conta, repetição não
    for c in dados.get("ganho", []):
        itens = [dict(x) for x in c["itens"]]
        antes = {"dominios": set(c.get("antes_dominios", [])),
                 "temas": set(c.get("antes_temas", []))}
        g = orch._ganho_informacao(antes, itens, c["consulta"])
        caso("ganho", c["caso"],
             g["ganho_real"] == c["ganho_real"]
             and g["dominios_novos"] == c["dominios_novos"]
             and g["temas_novos"] == c["temas_novos"])

    # índice geral: detecção conservadora (sinaliza e demove, nunca apaga)
    for c in dados.get("indice", []):
        caso("indice", c["caso"],
             orch._pagina_de_indice(c["item"]) == c["esperado"])

    total = sum(g["total"] for g in grupos.values())
    aprovados = sum(g["aprovados"] for g in grupos.values())
    relatorio = {
        "versao": dados.get("versao", "v57-v1"),
        "gerado_em": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "grupos": grupos,
        "metricas": {"taxa_global": round(aprovados / total, 4) if total else 0.0,
                     "casos": total, "aprovados": aprovados},
        "falhas": falhas,
    }
    if real:
        relatorio["real"] = _sondas_reais()
    if salvar:
        destino = RAIZ / "qa-artifacts" / "v57"
        destino.mkdir(parents=True, exist_ok=True)
        data = datetime.date.today().isoformat()
        (destino / f"bench-pesquisa-v57-{data}.json").write_text(
            json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    return relatorio


def _sondas_reais() -> dict:
    """Sondas de rede (registro honesto; sem assert)."""
    out = {}
    try:
        r = orch.pesquisar_com_recuperacao("como funciona o freio ABS",
                                           max_resultados=6, timeout=6.0)
        out["freio_abs"] = {
            "estado": r.get("estado"),
            "correspondencia": r.get("correspondencia"),
            "top3": [a.get("url") for a in (r.get("achados") or [])[:3]],
            "etapas": (r.get("etapas") or [])[:4],
        }
    except Exception as exc:  # registro, nunca esconder
        out["freio_abs"] = {"erro": repr(exc)[:200]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark V5.7 da pesquisa")
    ap.add_argument("--real", action="store_true", help="acrescenta sondas reais (rede)")
    ap.add_argument("--sem-salvar", action="store_true", help="não grava o JSON em qa-artifacts")
    args = ap.parse_args()
    rel = rodar(real=args.real, salvar=not args.sem_salvar)
    print(json.dumps(rel, ensure_ascii=True, indent=1)[:4000])
    return 1 if rel["falhas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
