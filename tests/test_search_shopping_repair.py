import pytest
from store_discovery import catalog_query
from shopping import (
    extrair_criterios,
    _consultas_produto,
    _termo_referencia,
    aplicar_filtros,
    _categoria_comercial,
)
from pc_modules.research_commands import _shopping_aplicar

def test_catalog_query_remove_palavras_de_comando_e_expande_fone():
    q = catalog_query("compare fones até R$ 300")
    assert "compare" not in q.lower()
    assert "até" not in q.lower()
    assert "r$" not in q.lower()
    assert "fone de ouvido" in q.lower()

def test_termo_referencia_remove_compare():
    ref = _termo_referencia("compare fones até R$ 300")
    assert "compare" not in ref.lower()
    assert "fones" in ref.lower()

def test_consultas_produto_expande_fone_para_evitar_colisao_com_fontes():
    crit = extrair_criterios("compare fones até R$ 300")
    consultas = _consultas_produto(crit, "compare fones até R$ 300")
    assert any("fone de ouvido" in c.lower() for c in consultas)
    assert not any("compare" in c.lower() for c in consultas)

def test_categoria_comercial_distingue_fonte_carregador_de_fone():
    cat_fonte = _categoria_comercial("Fonte Carregador Para All In One Hp Compac Cq1-1325br 19v 3.42a 65w")
    cat_fone = _categoria_comercial("Fone de Ouvido Sem Fio JBL Tune 520BT Bluetooth")
    assert cat_fonte == "fonte_carregador"
    assert cat_fone == "fone"

def test_aplicar_filtros_rejeita_fonte_carregador_quando_pedido_e_fone():
    crit = extrair_criterios("fones até R$ 300")
    produtos = [
        {
            "nome": "Fonte Carregador Para All In One Hp Compac Cq1-1325br 19v 3.42a 65w",
            "preco": 47.63,
            "preco_texto": "R$ 47,63",
            "moeda": "BRL",
            "url": "https://kabum.com.br/produto/123",
        },
        {
            "nome": "Fone de Ouvido Bluetooth JBL Wave Buds 2",
            "preco": 249.90,
            "preco_texto": "R$ 249,90",
            "moeda": "BRL",
            "url": "https://kabum.com.br/produto/456",
        },
        {
            "nome": "Suporte Fone De Ouvido Gamer Headset RGB",
            "preco": 89.90,
            "preco_texto": "R$ 89,90",
            "moeda": "BRL",
            "url": "https://kabum.com.br/produto/789",
        }
    ]
    dentro, fora = aplicar_filtros(produtos, crit)
    # Apenas o fone real deve passar no filtro
    assert len(dentro) == 1
    assert "JBL Wave Buds" in dentro[0]["nome"]
    # A fonte carregador deve ser rejeitada como tipo_produto_diferente
    rejeitados = {p["nome"]: p.get("excluido_codigos", []) for p in fora}
    assert "tipo_produto_diferente" in rejeitados["Fonte Carregador Para All In One Hp Compac Cq1-1325br 19v 3.42a 65w"]
    assert "acessorio" in rejeitados["Suporte Fone De Ouvido Gamer Headset RGB"]

def test_shopping_aplicar_nao_injeta_tabela_se_produtos_forem_mismatched():
    shop_res = {
        "criterios": {"comparacao": True},
        "produtos": [
            {
                "nome": "Fonte Carregador HP Compaq",
                "preco": 47.63,
                "preco_texto": "R$ 47,63",
                "excluido_codigos": ["tipo_produto_diferente"]
            }
        ],
        "fontes": []
    }
    texto = "A busca não encontrou fones de ouvido."
    out = _shopping_aplicar(texto, shop_res)
    # Não deve colocar fence de productcompare para itens excluídos por tipo diferente
    assert "productcompare" not in out
