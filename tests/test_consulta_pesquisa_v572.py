"""V5.7.2 — consulta de pesquisa: tira o PEDIDO e mantém o TEMA.

Defeito reproduzível (2026-10-19, rede real): "Explique a fotossíntese e
apresente fontes." ia crua para o buscador e voltava dicionário da palavra
"explique" (diciteca/dicio/escreva.ai) — o LLM respondia fielmente ao
material errado. A consulta limpa ("fotossíntese") devolve os artigos certos.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research


def test_remove_pedido_e_mantem_tema():
    limpa = research.consulta_de_pesquisa("Explique a fotossíntese e apresente fontes.")
    assert "fotoss" in limpa.lower()
    for palavra in ("explique", "apresente", "fontes"):
        assert palavra not in limpa.lower()


def test_variacoes_de_pedido():
    casos = {
        "Me fale sobre a Revolução Francesa.": "revolução francesa",
        "O que é computação quântica?": "computação quântica",
        "Por favor, pesquise sobre vacinas.": "vacinas",
        "Quero saber como funciona a energia solar.": "energia solar",
    }
    for frase, esperado in casos.items():
        limpa = research.consulta_de_pesquisa(frase).lower()
        for palavra in esperado.split():
            assert palavra in limpa, (frase, limpa)
    assert "explique" not in research.consulta_de_pesquisa(
        "Me explique o ciclo da água.").lower()


def test_frase_curta_ou_tema_puro_nao_muda():
    assert research.consulta_de_pesquisa("fotossíntese") == "fotossíntese"
    assert research.consulta_de_pesquisa("Explique.") == "Explique."
    assert research.consulta_de_pesquisa("") == ""


def test_pesquisa_rapida_envia_consulta_limpa():
    db = sqlite3.connect(":memory:")
    research.criar_tabelas(db)
    capturado = {}

    def buscar_fn(q, *a, **k):
        capturado["q"] = q
        return []

    research.pesquisa_rapida(db, "dono-teste", "Explique a fotossíntese e apresente fontes.",
                             buscar_fn=buscar_fn)
    assert "fotoss" in capturado["q"].lower()
    assert "explique" not in capturado["q"].lower()
    assert "fontes" not in capturado["q"].lower()
    db.close()
