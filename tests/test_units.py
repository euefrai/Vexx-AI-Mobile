"""V4.6.1: normalização de unidades + suporte factual com contexto."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_graph as eg
import units


def test_conversoes_exatas():
    assert units.iguais({"valor": 65.0, "unidade": "W"}, {"valor": 0.065, "unidade": "kW"})
    assert units.iguais({"valor": 1.0, "unidade": "km"}, {"valor": 1000.0, "unidade": "m"})
    assert units.iguais({"valor": 0.0, "unidade": "C"}, {"valor": 32.0, "unidade": "F"})
    assert units.iguais({"valor": 50.0, "unidade": "%"}, {"valor": 50.0, "unidade": "por cento"})
    assert not units.iguais({"valor": 65.0, "unidade": "W"}, {"valor": 95.0, "unidade": "W"})
    assert not units.iguais({"valor": 65.0, "unidade": "W"}, {"valor": 65.0, "unidade": "Wh"})
    assert not units.iguais({"valor": 1.0, "unidade": "W"}, {"valor": 1.0, "unidade": "léguas"})
    assert not units.iguais({"valor": 1.0, "unidade": ""}, {"valor": 1.0, "unidade": "W"})


def test_dimensoes_e_ambiguidades():
    assert units.dimensao_de("kW") == "potencia"
    assert units.dimensao_de("GB") == "armazenamento"
    assert units.dimensao_de("min") == "tempo"
    assert units.dimensao_de("léguas") is None
    assert units.dimensao_de("") is None
    with pytest.raises(units.UnidadeErro):
        units.para_base(1.0, "palmos")
    # mesma dimensão, propriedades distintas: unidade compatível (contexto decide depois)
    assert units.compativeis({"unidade": "W"}, {"unidade": "kW"})
    assert not units.compativeis({"unidade": "W"}, {"unidade": "Wh"})
    assert not units.compativeis({"unidade": "W"}, {"unidade": "X9"})


def test_tdp_nao_confirma_consumo_maximo():
    claim = {"texto": "O Processador A tem consumo máximo de 65 W em jogos.",
             "condicoes": {"comparado_a": "", "metrica": "",
                           "quantidades": [{"valor": 65.0, "unidade": "W"}], "datas": []}}
    r = eg.verificar_claim(claim, [{"id": "e1", "trecho": "TDP de 65 W segundo a ficha técnica."}])
    assert r["estado"] != "SUPPORTED"  # entidade/propriedade distinta: TDP ≠ consumo máximo
    r2 = eg.verificar_claim(claim, [{"id": "e1",
                                     "trecho": "Medimos consumo máximo de 65 W no Processador A em jogos."}])
    assert r2["estado"] == "SUPPORTED" and r2["metodo"] == "quantidade+contexto"


def test_data_e_base_exigidas():
    claim = {"texto": "O fundo rendeu 30% em 2024 segundo o relatório.",
             "condicoes": {"comparado_a": "", "metrica": "",
                           "quantidades": [{"valor": 30.0, "unidade": "%"}], "datas": ["2024"]}}
    sem_data = eg.verificar_claim(claim, [{"id": "e1", "trecho": "O fundo rendeu 30% no período."}])
    assert sem_data["estado"] != "SUPPORTED"  # data ausente no trecho
    com_data = eg.verificar_claim(claim, [{"id": "e1",
                                           "trecho": "O fundo rendeu 30% em 2024, diz o relatório."}])
    assert com_data["estado"] == "SUPPORTED"
    comp = {"texto": "O modelo X é 40% mais rápido que o concorrente Z.",
            "condicoes": {"comparado_a": "o concorrente Z", "metrica": "mais rápido",
                          "quantidades": [{"valor": 40.0, "unidade": "%"}], "datas": []}}
    sem_base = eg.verificar_claim(comp, [{"id": "e1",
                                          "trecho": "O modelo X é 40% mais rápido nos testes."}])
    assert sem_base["estado"] != "SUPPORTED"  # comparado ausente no trecho
