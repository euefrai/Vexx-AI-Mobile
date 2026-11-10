import re
import pytest
import shopping
import store_discovery
from pc_modules.research_commands import _extrair_especificacoes_produto, _nome_amigavel

def test_limpeza_query_celulares_baratos():
    texto = "me mostra alguns celulares baratos nesse mes de novembro"
    crit = shopping.extrair_criterios(texto)
    assert crit.get("categoria") == "celular"

    ref = shopping._termo_referencia(texto)
    assert "alguns" not in ref.lower()
    assert "me" not in ref.lower().split()
    assert "novembro" not in ref.lower()
    assert "mes" not in ref.lower()

    cq = store_discovery.catalog_query(texto)
    assert "alguns" not in cq.lower()
    assert "novembro" not in cq.lower()
    assert "smartphone" in cq.lower() or "celular" in cq.lower()

    consultas = shopping._consultas_produto(crit, texto)
    for q in consultas:
        assert "alguns" not in q.lower()
        assert "novembro" not in q.lower()
        assert "smartphone" in q.lower() or "celular" in q.lower()


def test_bloqueio_dicionarios_em_referencias():
    cand_infopedia = {
        "url": "https://www.infopedia.pt/dicionarios/lingua-portuguesa/alguns",
        "titulo": "alguns | Dicionário Infopédia da Língua Portuguesa",
        "trecho": "Definição de alguns no Dicionário Infopédia"
    }
    motivo = {"codigo": "bloqueio"}
    ref = shopping._ref_de_busca(cand_infopedia, motivo, "smartphone", {"categoria": "celular"})
    assert ref is None

    cand_escreva = {
        "url": "https://escreva.ai/palavra/alguns/",
        "titulo": "Alguns - Significado e Sinônimo - escreva.ai",
        "trecho": "Sinônimos de alguns"
    }
    motivo_sem_dados = {"codigo": "sem_dados"}
    ref2 = shopping._ref_de_busca(cand_escreva, motivo_sem_dados, "smartphone", {"categoria": "celular"})
    assert ref2 is None


def test_extrair_especificacoes_celular():
    nome = 'Smartphone Samsung Galaxy A17, 128GB, RAM 4GB, Câmera Tripla 50MP + Selfie 13MP, Tela 6.7", Preto'
    specs = _extrair_especificacoes_produto(nome, "celular")
    assert "128GB" in specs
    assert "4GB RAM" in specs

    nome_amigavel = _nome_amigavel(nome)
    assert "Smartphone" not in nome_amigavel
    assert "Samsung Galaxy A17" in nome_amigavel
