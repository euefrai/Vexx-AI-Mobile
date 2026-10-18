"""V5.7 — Benchmark independente da pesquisa com fixtures congeladas.

Executa `tools/bench_pesquisa_v57.py` em modo offline (sem rede): os casos de
`benchmarks/pesquisa_v57_v1.json` rodam contra as funções reais com provedores
injetados. Exige aprovação total — falha aqui significa regressão de qualidade
da pesquisa (reformulação, junk, republicações, marca/specs, links).
"""
import importlib.util
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _carregar():
    caminho = RAIZ / "tools" / "bench_pesquisa_v57.py"
    spec = importlib.util.spec_from_file_location("bench_pesquisa_v57", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bench_pesquisa_v57_offline_tudo_aprovado():
    rel = _carregar().rodar(salvar=False)
    assert rel["falhas"] == []
    assert rel["metricas"]["taxa_global"] == 1.0
    for grupo in ("reformulacao", "correspondencia", "fluxo_junk",
                  "republicacao", "produtos", "specs", "links", "desatualizado",
                  "ganho", "indice"):
        assert rel["grupos"][grupo]["aprovados"] == rel["grupos"][grupo]["total"], grupo
