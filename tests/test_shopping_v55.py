"""V5.5 Shopping: cadeia web por último, verificação de link/imagem, alternativas.

Offline: tudo com injeção/monkeypatch; rede só em testes e2e_real.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research
import shopping


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "shop55.sqlite3")


def _baixar_fixture(mapa):
    def _fn(url):
        if url in mapa:
            return {"final": url, "texto": mapa[url]}
        return {"final": url, "texto": "<html></html>"}
    return _fn


PAGINA_PRODUTO = (
    '<html><head><title>Notebook Gamer X 16GB RAM - Loja Certa</title>'
    '<meta property="og:type" content="product">'
    '<meta property="product:price:amount" content="4299.00">'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org/","@type":"Product",'
    '"name":"Notebook Gamer X 16GB RAM",'
    '"image":"https://cdn.loja.com/x.jpg",'
    '"url":"https://loja.com/produto/x",'
    '"offers":{"@type":"Offer","price":"4299.00","priceCurrency":"BRL",'
    '"availability":"https://schema.org/InStock"}}'
    '</script></head><body><h1>Notebook Gamer X 16GB RAM</h1>'
    '<button>Adicionar ao carrinho</button></body></html>')

PAGINA_LISTA_PRODUTOS = (
    '<html><head><title>Resultados para notebook 16gb ram</title></head>'
    '<body><h1>Resultados para notebook</h1><p>Ordenar por: relevância</p>'
    '<div>Notebook A R$ 3.299,00</div><div>Notebook B R$ 3.499,00</div>'
    '<div>Notebook C R$ 3.599,00</div><div>Notebook D R$ 3.699,00</div>'
    '<div>Notebook E R$ 3.799,00</div><div>Notebook F R$ 3.899,00</div>'
    '<div>Notebook G R$ 3.999,00</div>'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org/","@graph":['
    '{"@type":"Product","name":"Notebook A 16GB RAM",'
    '"url":"https://loja.com/produto/a",'
    '"offers":{"@type":"Offer","price":"3299.00","priceCurrency":"BRL"}},'
    '{"@type":"Product","name":"Notebook B 16GB RAM",'
    '"offers":{"@type":"Offer","price":"3499.00","priceCurrency":"BRL"}}'
    ']}</script></body></html>')

PAGINA_OG_PRODUTO = (
    '<html><head><title>Fone Bluetooth Y</title>'
    '<meta property="og:type" content="product">'
    '<meta property="og:title" content="Fone Bluetooth Y">'
    '<meta property="og:image" content="https://cdn.loja.com/y.jpg">'
    '<meta property="product:price:amount" content="199.90">'
    '<meta property="product:price:currency" content="BRL">'
    '</head><body><h1>Fone Bluetooth Y</h1>'
    '<button>Adicionar ao carrinho</button></body></html>')

PAGINA_BLOG = (
    '<html><head><title>Blog do Zé</title>'
    '<meta property="og:title" content="Post do blog">'
    '<meta property="og:image" content="https://cdn.blog.com/p.jpg">'
    '</head><body><p>texto corrido sem dados de produto</p></body></html>')


def _prod(**kw):
    p = {"nome": "Notebook X 16GB RAM 512GB", "marca": "MarcaX", "modelo": "",
         "variante": "", "imagem": "", "loja": "loja.com",
         "url": "https://loja.com/produto/x", "url_final": "https://loja.com/produto/x",
         "url_item": "https://loja.com/produto/x",
         "preco": 4400.0, "moeda": "BRL", "preco_confirmado": True,
         "preco_texto": "R$ 4.400,00", "disponibilidade": "em_estoque",
         "specs": {}, "verificado_em": "x", "id": "p1",
         "link_veredito": "verificado"}
    p.update(kw)
    return p


# ── Cadeia de busca: web (orquestrador) por último, sem quebrar legado ──

def test_chain_web_entra_por_ultimo(monkeypatch):
    def _mlb_falha(q, limite=10, timeout=8.0):
        raise research.ResearchErro("Provedor HTTP 403.", "http")

    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(
        research, "buscar_ddg",
        lambda q, base=research.DDG_HTML, max_resultados=6, timeout=8.0: [])
    chamadas = []

    def _orch(q, max_resultados=6, timeout=8.0, orcamento=None):
        chamadas.append(q)
        return ([{"titulo": "T", "url": "https://loja.com/produto/x",
                  "trecho": "x", "origem": "bing"}],
                {"estado": "ok", "provedores": {"usados": {"bing": 1}},
                 "etapas": []})

    monkeypatch.setattr(research, "_buscar_orquestrado", _orch)
    achados, etapas = shopping.buscar_com_fallback("notebook 16gb")
    assert chamadas and [a["url"] for a in achados] == ["https://loja.com/produto/x"]
    assert any(e.startswith("web: 1 resultados") for e in etapas)
    # A ordem legada dos diagnósticos continua: mlb falhou antes do web.
    assert etapas[0].startswith("mlb: falhou")


def test_chain_web_nao_roda_se_ddg_achou(monkeypatch):
    def _mlb_falha(q, limite=10, timeout=8.0):
        raise research.ResearchErro("Provedor HTTP 403.", "http")

    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(
        research, "buscar_ddg",
        lambda q, base=research.DDG_HTML, max_resultados=6, timeout=8.0:
        [{"titulo": "T", "url": "https://loja.com/p", "trecho": "x"}])

    def _nunca(*a, **k):
        raise AssertionError("web não deve rodar quando ddg achou")

    monkeypatch.setattr(shopping, "buscar_web_v55", _nunca)
    achados, etapas = shopping.buscar_com_fallback("celular")
    assert [a["url"] for a in achados] == ["https://loja.com/p"]
    assert not any(e.startswith("web:") for e in etapas)


# ── Extração com verificação: listagem × produto × OG ─────────────────

def test_listagem_so_vira_produto_com_url_do_item():
    fn = _baixar_fixture({"https://loja.com/busca": PAGINA_LISTA_PRODUTOS})
    saidas = shopping._recuperar_ofertas(
        "https://loja.com/busca", "Resultados", baixar_fn=fn, consulta="notebook")
    assert [p["nome"] for p in saidas] == ["Notebook A 16GB RAM"]
    p = saidas[0]
    assert p["item_de_listagem"] is True
    assert p["link_veredito"] == "nao_verificado"
    assert p["url_item"] == "https://loja.com/produto/a"
    assert "listagem" in p["link_motivo"]


def test_pagina_produto_marca_link_verificado():
    fn = _baixar_fixture({"https://loja.com/produto/x": PAGINA_PRODUTO})
    saidas = shopping._recuperar_ofertas(
        "https://loja.com/produto/x", "Notebook", baixar_fn=fn,
        consulta="notebook 16gb")
    assert len(saidas) == 1
    p = saidas[0]
    assert p["link_veredito"] == "verificado"
    assert p["item_de_listagem"] is False
    assert p["url_item"] == "https://loja.com/produto/x"
    assert p["preco_origem"] == "jsonld"


def test_og_com_sinais_de_produto_vira_produto():
    fn = _baixar_fixture({"https://loja.com/produto/y": PAGINA_OG_PRODUTO})
    saidas = shopping._recuperar_ofertas("https://loja.com/produto/y", "Fone",
                                         baixar_fn=fn)
    assert len(saidas) == 1
    assert saidas[0]["preco"] == 199.9
    assert saidas[0]["preco_origem"] == "opengraph"


def test_og_sem_sinais_nao_vira_produto():
    fn = _baixar_fixture({"https://blog.exemplo.com/post": PAGINA_BLOG})
    assert shopping._recuperar_ofertas("https://blog.exemplo.com/post", "Post",
                                       baixar_fn=fn) == []


# ── Alternativas próximas com diferenças explícitas ───────────────────

def test_alternativa_ate_25_por_cento_acima():
    criterios = {"orcamento": {"max": 4000.0}, "specs": {}}
    perto = _prod(id="a", preco=4400.0, preco_texto="R$ 4.400,00")
    longe = _prod(id="b", nome="Notebook Caro", preco=6000.0,
                  preco_texto="R$ 6.000,00")
    dentro, fora = shopping.aplicar_filtros([perto, longe], criterios)
    assert dentro == [] and len(fora) == 2
    alts = shopping.separar_alternativas(fora, criterios)
    assert [a["id"] for a in alts] == ["a"]
    assert "acima do teto" in alts[0]["diferencas"]
    assert alts[0]["diferencas_lista"]


def test_alternativa_usado_e_ram_abaixo_com_diferencas():
    criterios = {"orcamento": {}, "specs": {"flag_novo": True, "ram_fisica_gb": 16}}
    usado = _prod(id="u", nome="Notebook Y 8GB RAM", specs={"Condicao": "Usado"})
    dentro, fora = shopping.aplicar_filtros([usado], criterios)
    alts = shopping.separar_alternativas(fora, criterios)
    assert len(alts) == 1
    assert "usado (pedido: somente novos)" in alts[0]["diferencas"]
    assert "RAM 8GB (pedido: 16GB)" in alts[0]["diferencas"]


def test_abaixo_da_faixa_e_descarte_nao_alternativa():
    criterios = {"orcamento": {"min": 2000.0, "max": 4000.0}, "specs": {}}
    fraco = _prod(id="f", preco=900.0, preco_texto="R$ 900,00")
    _, fora = shopping.aplicar_filtros([fraco], criterios)
    assert fora and fora[0]["excluido_codigos"] == ["preco_abaixo"]
    assert shopping.separar_alternativas(fora, criterios) == []


# ── URL do item: precedência e fence ──────────────────────────────────

def test_url_item_precedencia():
    ex = {"nome": "N", "marca": "", "modelo": "", "variante": "", "imagem": "",
          "descricao": "", "avaliacao": None, "n_avaliacoes": None,
          "url_produto": "https://loja.com/produto/n",
          "ofertas_ld": [{"preco": 10.0, "moeda": "BRL", "preco_confirmado": True,
                          "disponibilidade": "em_estoque", "url_oferta": "https://loja.com/o",
                          "loja": "", "valido_ate": ""}]}
    p = shopping.montar_produto(ex, "https://loja.com/busca",
                                "https://loja.com/busca", "t")
    assert p["url_item"] == "https://loja.com/produto/n"
    p2 = shopping.montar_produto({**ex, "url_produto": ""}, "https://loja.com/busca",
                                 "https://loja.com/busca", "t")
    assert p2["url_item"] == "https://loja.com/o"
    p3 = shopping.montar_produto(
        {"nome": "N", "imagem": "", "descricao": "", "avaliacao": None,
         "n_avaliacoes": None, "ofertas_ld": []},
        "https://loja.com/p", "https://loja.com/p", "t")
    assert p3["url_item"] == "https://loja.com/p"


def test_fence_usa_url_item_nao_link_de_busca():
    p = _prod()
    p["url_final"] = "https://loja.com/busca?q=notebook"
    fence = shopping.fence_resultado({"produtos": [p], "fontes": []})
    corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    assert corpo["blocks"][0]["props"]["produto"]["url"] == "https://loja.com/produto/x"


# ── Verificação de imagens (injetável, sem rede) ──────────────────────

class _Resp:
    def __init__(self, corpo, status=200, ctype="image/png"):
        self._corpo = corpo
        self.status = status
        self.headers = {"Content-Type": ctype}

    def read(self, n=-1):
        return self._corpo[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _png(largura, altura):
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + largura.to_bytes(4, "big") + altura.to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00" + b"\x00" * 16)


def test_verificar_imagens_injetavel(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)

    def _abrir(url, timeout=8.0, ua=""):
        if url.endswith("/ok.png"):
            return _Resp(_png(800, 600), ctype="image/png")
        if url.endswith("/pixel.gif"):
            return _Resp(b"GIF89a" + bytes([1, 0, 1, 0]) + b"\x00" * 10,
                         ctype="image/gif")
        return _Resp(b"<html>nao e imagem</html>", ctype="text/html")

    a = {"nome": "A", "imagem": "https://cdn.loja.com/ok.png"}
    b = {"nome": "B", "imagem": "https://cdn.loja.com/pixel.gif"}
    c = {"nome": "C", "imagem": "https://cdn.loja.com/oops.jpg"}
    shopping.verificar_imagens([a, b, c], abrir=_abrir)
    assert a["imagem"] == "https://cdn.loja.com/ok.png"
    assert a["imagem_veredito"] == "verificado"
    assert b["imagem"] == "" and b["imagem_veredito"] == "reprovado"
    assert b["imagem_motivo"]
    assert c["imagem"] == "" and c["imagem_veredito"] == "reprovado"


# ── Pipeline completo com mocks: alternativas + verificação ───────────

def _busca_uma(consulta):
    return [{"titulo": "Notebook", "url": "https://loja.com/produto/x",
             "trecho": "x"}]


def test_pesquisar_produto_verificado_e_verificacao():
    db = _db()
    res = shopping.pesquisar(
        db, "ana", "notebook gamer 16gb até R$ 5000", "c1",
        buscar_fn=_busca_uma,
        baixar_fn=_baixar_fixture({"https://loja.com/produto/x": PAGINA_PRODUTO}))
    assert len(res["produtos"]) == 1
    p = res["produtos"][0]
    assert p["url_item"] == "https://loja.com/produto/x"
    assert res["alternativas"] == []
    assert res["verificacao"]["links"]["verificado"] == 1
    assert res["verificacao"]["links"]["total"] == 1
    assert "dados verificados" in shopping.resumo_texto(res)


def test_pesquisar_alternativas_quando_nada_atende():
    db = _db()
    res = shopping.pesquisar(
        db, "ana", "notebook gamer até R$ 4000", "c2",
        buscar_fn=_busca_uma,
        baixar_fn=_baixar_fixture({"https://loja.com/produto/x": PAGINA_PRODUTO}))
    assert res["produtos"] == []
    assert len(res["alternativas"]) == 1
    alt = res["alternativas"][0]
    assert alt["link_veredito"] == "verificado"
    assert "acima do teto" in alt["diferencas"]
    assert res["excluidos"] == []
    assert res["verificacao"]["links"]["total"] == 1
    assert res["verificacao"]["links"]["verificado"] == 1
    texto = shopping.resumo_texto(res)
    assert "diferenças" in texto and "nenhuma atende" in texto
    bloco = shopping.bloco_para_llm(res)
    assert "OPÇÕES PRÓXIMAS" in bloco and "diferenças" in bloco


def test_bloco_llm_sem_produtos_com_alternativas():
    res = {"produtos": [], "alternativas": [_prod(diferencas="preço 10% acima do teto",
                                                  diferencas_lista=["x"])]}
    bloco = shopping.bloco_para_llm(res)
    assert "OPÇÕES PRÓXIMAS" in bloco
    assert "10% acima do teto" in bloco
    assert "PROIBIDO inventar" in bloco
