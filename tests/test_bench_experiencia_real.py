"""Wrapper pytest da bateria de experiência real (V5.7 FINAL).

A bateria em `tools/bench_experiencia_real.py` roda o pipeline verdadeiro
com fixtures locais (sem rede) e mede o resultado do ponto de vista do
usuário. Aqui ela é exigida 100% verde para não regredir; o registro
antes/depois fica nos artefatos `qa-artifacts/v57/`.
"""
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _carregar():
    spec = importlib.util.spec_from_file_location(
        "bench_exp_real", RAIZ / "tools" / "bench_experiencia_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bateria_experiencia_real_completa():
    mod = _carregar()
    resultados = mod.executar()
    falhas = [r for r in resultados if not r["ok"]]
    detalhe = "\n".join(f"{r['id']}: {r['detalhe']}" for r in falhas)
    assert not falhas, detalhe
