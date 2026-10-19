"""V5.7.2 — preços: separadores BR/US, moeda e orçamento verificável.

Defeitos reproduzíveis (2026-10-19):
- `normalizar_preco("$1,299.00")` → (1.3, "BRL") e `"R$ 1,299.00"` → (1.3, "BRL"):
  separador de milhar interpretado como decimal (e moeda errada sem "US$").
- Produto sem preço numérico entrava como "dentro" do orçamento (só ia para o
  fim da lista) — orçamento não verificável não pode virar correspondência.
- Produto em moeda diferente era comparado numericamente ao teto em BRL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import shopping


def _p(**kw):
    base = {"nome": "Notebook X 8GB", "marca": "X", "modelo": "", "variante": "",
            "imagem": "", "loja": "loja.test", "url": "https://loja.test/p",
            "url_final": "https://loja.test/p", "url_item": "https://loja.test/p",
            "preco": 1299.0, "moeda": "BRL", "preco_confirmado": True,
            "preco_texto": "R$ 1.299,00", "disponibilidade": "em_estoque",
            "avaliacao": None, "n_avaliacoes": None, "specs": {},
            "verificado_em": "2026-10-19T00:00:00+00:00", "ofertas": []}
    base.update(kw)
    return base


# ── Separadores e moeda ──────────────────────────────────────────────

def test_precos_brasileiros():
    assert shopping.normalizar_preco("R$ 2.974,15") == (2974.15, "BRL")
    assert shopping.normalizar_preco("R$ 499,90") == (499.9, "BRL")
    assert shopping.normalizar_preco("R$ 1.299,00") == (1299.0, "BRL")
    assert shopping.normalizar_preco("R$ 2 974,15") == (2974.15, "BRL")
    assert shopping.normalizar_preco("1299,99") == (1299.99, "BRL")
    assert shopping.normalizar_preco("1.299") == (1299.0, "BRL")


def test_precos_americanos():
    assert shopping.normalizar_preco("$1,299.00") == (1299.0, "USD")
    assert shopping.normalizar_preco("US$ 1,299.00") == (1299.0, "USD")
    assert shopping.normalizar_preco("USD 499.90") == (499.9, "USD")
    assert shopping.normalizar_preco("1,299", "USD") == (1299.0, "USD")
    # rótulo BR com formatação americana: o último separador é o decimal
    assert shopping.normalizar_preco("R$ 1,299.00") == (1299.0, "BRL")
    assert shopping.normalizar_preco("1299.99") == (1299.99, "BRL")


def test_preco_impossivel_nao_vira_numero():
    assert shopping.normalizar_preco("sem preço") is None
    assert shopping.normalizar_preco("R$ 0,00") is None
    assert shopping.normalizar_preco("1.2.3") is None


# ── Orçamento: dentro/fora verificável ───────────────────────────────

def test_orcamento_ate_500():
    p499 = _p(preco=499.0, preco_texto="R$ 499,00")
    p501 = _p(nome="Outro", preco=501.0, preco_texto="R$ 501,00")
    dentro, fora = shopping.aplicar_filtros(
        [p499, p501], {"orcamento": {"max": 500}})
    assert [x["preco"] for x in dentro] == [499.0]
    assert fora and fora[0]["excluido_codigos"] == ["preco_acima"]


def test_orcamento_entre_1000_e_2000():
    meio = _p(preco=1500.0, preco_texto="R$ 1.500,00")
    barato = _p(nome="B", preco=900.0, preco_texto="R$ 900,00")
    dentro, fora = shopping.aplicar_filtros(
        [meio, barato], {"orcamento": {"min": 1000, "max": 2000}})
    assert [x["preco"] for x in dentro] == [1500.0]
    assert fora[0]["excluido_codigos"] == ["preco_abaixo"]


def test_orcamento_acima_de_3000():
    caro = _p(preco=3500.0, preco_texto="R$ 3.500,00")
    barato = _p(nome="B", preco=2500.0, preco_texto="R$ 2.500,00")
    dentro, fora = shopping.aplicar_filtros(
        [caro, barato], {"orcamento": {"min": 3000}})
    assert [x["preco"] for x in dentro] == [3500.0]
    assert fora[0]["excluido_codigos"] == ["preco_abaixo"]


def test_sem_preco_nao_entra_no_orcamento_mas_fica_explicito():
    sem = _p(preco=None, preco_texto="Preço não confirmado",
             preco_confirmado=False)
    dentro, fora = shopping.aplicar_filtros([sem], {"orcamento": {"max": 500}})
    assert dentro == []
    assert fora and "preco_nao_confirmado" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, {"orcamento": {"max": 500}})
    assert alts and "preço não confirmado" in alts[0]["diferencas"]


def test_sem_orcamento_preco_desconhecido_continua_valido():
    sem = _p(preco=None, preco_texto="Preço não confirmado",
             preco_confirmado=False)
    dentro, fora = shopping.aplicar_filtros([sem], {"orcamento": {}})
    assert dentro == [sem] and fora == []


def test_moeda_diferente_nao_vira_orcamento_brl():
    usd = _p(preco=100.0, moeda="USD", preco_texto="USD 100.00")
    dentro, fora = shopping.aplicar_filtros([usd], {"orcamento": {"max": 500}})
    assert dentro == []
    assert "moeda_diferente" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, {"orcamento": {"max": 500}})
    assert alts and "USD" in alts[0]["diferencas"]


# ── Variantes e promoção: preço único nunca é inventado ─────────────

def test_variantes_marcam_a_partir_de():
    extraido = {"nome": "Fone X", "marca": "", "modelo": "", "variante": "",
                "imagem": "", "descricao": "", "avaliacao": None,
                "n_avaliacoes": None,
                "ofertas_ld": [
                    {"preco": 199.9, "moeda": "BRL", "preco_confirmado": True,
                     "disponibilidade": "em_estoque", "url_oferta": "",
                     "loja": "", "valido_ate": ""},
                    {"preco": 249.9, "moeda": "BRL", "preco_confirmado": True,
                     "disponibilidade": "em_estoque", "url_oferta": "",
                     "loja": "", "valido_ate": ""}]}
    p = shopping.montar_produto(extraido, "https://loja.test/f",
                                "https://loja.test/f", "t")
    assert p["preco"] == 199.9
    assert p["preco_a_partir_de"] is True
    assert p["preco_texto"].startswith("a partir de R$ 199,90")


def test_produto_sem_preco_confirmado_nao_inventa_valor():
    extraido = {"nome": "Fone Y", "marca": "", "modelo": "", "variante": "",
                "imagem": "", "descricao": "", "avaliacao": None,
                "n_avaliacoes": None,
                "ofertas_ld": [{"preco": None, "moeda": "BRL",
                                "preco_confirmado": False,
                                "disponibilidade": "desconhecida",
                                "url_oferta": "", "loja": "", "valido_ate": ""}]}
    p = shopping.montar_produto(extraido, "https://loja.test/y",
                                "https://loja.test/y", "t")
    assert p["preco"] is None
    assert p["preco_confirmado"] is False
    assert p["preco_texto"] == shopping.PRECO_NAO_CONFIRMADO


# ── JDUI: o card recebe o valor numérico ────────────────────────────

def test_card_e_fence_levam_preco_numerico():
    p = _p()
    card = shopping._jdui_produto(p)
    assert card["preco_valor"] == 1299.0
    assert card["preco"] == "R$ 1.299,00"
    fence = shopping.fence_resultado({"produtos": [p], "fontes": []})
    corpo = fence.split("```jdui", 1)[1].rsplit("```", 1)[0].strip()
    msg = json.loads(corpo)
    ok, norm, erros = jdui.validar_mensagem(msg)
    assert ok, erros
    assert norm["blocks"][0]["props"]["produto"]["preco_valor"] == 1299.0
