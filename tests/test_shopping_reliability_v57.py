"""V5.7 — HOTFIX de confiabilidade comercial: regressões determinísticas.

Cenários cobertos (sem rede; fixtures locais, sem inventar evidência):

Links/páginas: 404 (reprovado), "produto removido/indisponível" em HTTP 200
(soft 404 — nunca vira oferta), esgotado ≠ removido, CAPTCHA/bot-wall
(não verificado — nunca "link quebrado"), redirect para a home/listagem,
403 (não verificado).

Preços/estoque: preço só em texto não vira preço confirmado; estoque
desconhecido não vira "em estoque"; "Preço não confirmado" declarado.

Cache/evidência: reuso declarado com data no grounding; cache expirado não
é reaproveitado; TTL configurável por `JULIA_SHOPPING_TTL`.

Roteamento: "me mostre tenis para jogar basquete" roteia para shopping
(antes respondia de memória); pedido explicativo não vira busca; verbos
fortes preservados.

Alegações: preço/produto sem busca verificada vira violação
`verificacao_alegada_sem_evidencia`; aviso explícito de não-verificação ou
oferta verificada não são marcados.

Imagens/JDUI: imagem reprovada zera a URL e o motivo chega ao card e ao
fence (backend e jdui.js); fence malformado não vira JSON bruto; fence de
produto emitido pelo MODELO é sempre removido (cards só da ferramenta).

Pipeline: página removida não gera card nem com JSON-LD residual; mistura
removida + válida deixa só a válida; falha parcial de provedor fica
registrada; service worker nunca intercepta /api (dados sempre vivos).
"""
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intent
import jdui
import pc_agent
import research
import shopping
import source_check


@pytest.fixture(autouse=True)
def _sem_ssrf(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


class _Resp:
    def __init__(self, corpo, status=200, ctype="text/html; charset=utf-8"):
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


def _db(nome="reliab.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


# ── Links: removido × esgotado × captcha × 404 × redirect ────────────

_PAG_PRODUTO_REMOVIDO = (
    '<html><head><title>Produto indisponível | Loja</title></head><body>'
    '<h1>Produto indisponível</h1>'
    '<p>Este produto não está mais disponível.</p></body></html>')

_PAG_PRODUTO_REMOVIDO_COM_JSONLD_RESIDUAL = (
    '<html><head><title>Produto indisponível | Loja</title>'
    '<script type="application/ld+json">'
    '{"@type":"Product","name":"Tênis de Basquete X",'
    '"offers":{"@type":"Offer","price":"499.00","priceCurrency":"BRL"}}'
    '</script></head><body><h1>Produto indisponível</h1>'
    '<p>O anúncio foi finalizado.</p></body></html>')

_PAG_ESGOTADO = (
    '<html><head><title>Tênis de Basquete X</title>'
    '<meta property="og:type" content="product">'
    '<script type="application/ld+json">'
    '{"@type":"Product","name":"Tênis de Basquete X",'
    '"offers":{"@type":"Offer","price":"499.00","priceCurrency":"BRL"}}'
    '</script></head><body><h1>Tênis de Basquete X</h1>'
    '<p>Produto esgotado</p><button>Adicionar ao carrinho</button></body></html>')

_PAG_CAPTCHA = (
    '<html><head><title>Verificação de segurança</title></head><body>'
    '<h1>Confirme que você é humano</h1>'
    '<p>Complete o captcha para continuar.</p></body></html>')


def _baixar_da(pagina):
    def _fn(url):
        return {"final": url, "texto": pagina}
    return _fn


def test_produto_removido_http200_reprovado_com_frase():
    r = source_check.avaliar_pagina(_PAG_PRODUTO_REMOVIDO,
                                    "https://loja.com/produto/x",
                                    esperado={"tipo": "produto"})
    assert r["veredito"] == "reprovado"
    assert r["codigo"] == "produto_removido"
    assert "produto indisponivel" in r["sinais"]["removido_frase"]


def test_produto_removido_com_jsonld_residual_ainda_reprova():
    r = source_check.avaliar_pagina(_PAG_PRODUTO_REMOVIDO_COM_JSONLD_RESIDUAL,
                                    "https://loja.com/produto/x",
                                    esperado={"tipo": "produto"})
    assert r["veredito"] == "reprovado"
    assert r["codigo"] == "produto_removido"


def test_esgotado_nao_e_removido():
    r = source_check.avaliar_pagina(_PAG_ESGOTADO, "https://loja.com/produto/x",
                                    esperado={"tipo": "produto"})
    assert r["codigo"] == "ok" and r["veredito"] == "verificado"
    assert r["sinais"]["removido"] is False


def test_frase_removida_em_script_de_template_nao_reprova():
    pagina = ('<html><head><title>Tênis Pro</title>'
              '<script>var t = {notFound: "Produto não encontrado"};</script>'
              '<script type="application/ld+json">'
              '{"@type":"Product","name":"Tênis Pro",'
              '"offers":{"@type":"Offer","price":"399.90","priceCurrency":"BRL"}}'
              '</script></head><body><h1>Tênis Pro</h1>'
              '<button>Adicionar ao carrinho</button>R$ 399,90</body></html>')
    r = source_check.avaliar_pagina(pagina, "https://loja.com/produto/tenis",
                                    esperado={"tipo": "produto"})
    assert r["veredito"] == "verificado"
    assert r["sinais"]["removido"] is False


def test_captcha_http200_vira_nao_verificado():
    def _abrir(url, timeout=8.0, ua=""):
        return _Resp(_PAG_CAPTCHA.encode())

    r = source_check.validar_link("https://loja.com/produto/x", abrir=_abrir,
                                  esperado={"tipo": "produto"})
    assert r["veredito"] == "nao_verificado"
    assert r["codigo"] == "bloqueio_pagina"
    assert "sem bypass" in r["motivo"]


def test_http_404_reprovado_pagina_nao_existe():
    def _abrir(url, timeout=8.0, ua=""):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    r = source_check.validar_link("https://loja.com/produto/nao-existe",
                                  abrir=_abrir, esperado={"tipo": "produto"})
    assert r["veredito"] == "reprovado"
    assert r["codigo"] == "http_404"
    assert "não existe" in r["motivo"]


def test_http_403_nao_e_link_quebrado():
    def _abrir(url, timeout=8.0, ua=""):
        raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)

    r = source_check.validar_link("https://loja.com/produto/x", abrir=_abrir,
                                  esperado={"tipo": "produto"})
    assert r["veredito"] == "nao_verificado"
    assert "CAPTCHA" in r["motivo"]


def test_redirect_para_home_nao_vira_produto():
    home = ('<html><head><title>Loja Certa — ofertas do dia</title></head><body>'
            + "".join(f"<div>Produto R$ 1.0{i:02d},00</div>" for i in range(7))
            + '</body></html>')

    def _abrir(url, timeout=8.0, ua=""):
        if url == "https://loja.com/r/123":
            err = urllib.error.HTTPError(url, 301, "moved", {}, None)
            err.headers = {"Location": "https://loja.com/"}
            raise err
        if url == "https://loja.com/":
            return _Resp(home.encode())
        raise AssertionError("url inesperada: " + url)

    r = source_check.validar_link("https://loja.com/r/123", abrir=_abrir,
                                  esperado={"tipo": "produto"})
    assert r["url_final"] == "https://loja.com/"
    assert r["veredito"] == "reprovado"
    assert r["codigo"] == "listagem_nao_produto"


def test_pagina_removida_nao_gera_card_mesmo_com_jsonld_residual():
    saidas = shopping._recuperar_ofertas(
        "https://loja.com/produto/x", "Tênis",
        baixar_fn=_baixar_da(_PAG_PRODUTO_REMOVIDO_COM_JSONLD_RESIDUAL),
        consulta="tenis")
    assert saidas == []


def test_esgotado_gera_card_com_link_verificado():
    saidas = shopping._recuperar_ofertas(
        "https://loja.com/produto/x", "Tênis",
        baixar_fn=_baixar_da(_PAG_ESGOTADO), consulta="tenis")
    assert len(saidas) == 1
    assert saidas[0]["link_veredito"] == "verificado"


def test_mistura_removida_e_valida_so_valida_vira_card():
    removida = shopping._recuperar_ofertas(
        "https://loja.com/produto/morto", "Morto",
        baixar_fn=_baixar_da(_PAG_PRODUTO_REMOVIDO), consulta="tenis")
    valida = shopping._recuperar_ofertas(
        "https://loja.com/produto/x", "Vivo",
        baixar_fn=_baixar_da(_PAG_ESGOTADO), consulta="tenis")
    assert removida == [] and len(valida) == 1


def test_item_de_categoria_com_url_da_oferta_nunca_herda_verificado():
    """Auditoria de descoberta 2026-10-18 (caso KaBuM): categoria/lista com
    HTTP 200, JSON-LD Products SEM url própria, mas com offers.url apontando
    para as páginas de produto (não abertas). O item não pode nascer
    "verificado" só porque a página ABERTA pareceu de produto — o link do
    card aponta para OUTRA página, nunca aberta."""
    itens = ",".join(
        '{"@type":"Product","name":"Notebook %d",'
        '"offers":{"@type":"Offer","price":"%d999.00","priceCurrency":"BRL",'
        '"url":"https://lojax.com.br/produto/notebook-%d"}}' % (i, i, i)
        for i in (1, 2, 3))
    precos = " ".join("R$ %d99,00" % (i + 10) for i in range(8))  # >6 preços
    pagina = ('<html><head><title>Notebooks — Loja X</title>'
              '<script type="application/ld+json">[' + itens + ']</script>'
              '</head><body><h1>Notebooks</h1>' + precos +
              '<button>Adicionar ao carrinho</button></body></html>')
    saidas = shopping._recuperar_ofertas(
        "https://lojax.com.br/esporte/notebooks", "Notebooks",
        baixar_fn=_baixar_da(pagina), consulta="notebook")
    assert len(saidas) == 3
    for p in saidas:
        assert p["link_veredito"] == "nao_verificado"
        assert p["link_codigo"] == "item_nao_aberto"
        assert p["url_item"].startswith("https://lojax.com.br/produto/notebook-")
        assert shopping._tier(p) == "parcial"
    # O preço real do dado estruturado continua (nem inventado, nem apagado).
    assert saidas[0]["preco"] is not None


# ── Preços e estoque ──────────────────────────────────────────────────

def test_preco_ausente_nao_vira_preco_confirmado():
    ex = {"nome": "Tênis X", "marca": "", "modelo": "", "variante": "",
          "imagem": "", "descricao": "", "avaliacao": None, "n_avaliacoes": None,
          "url_produto": "", "ofertas_ld": []}
    p = shopping.montar_produto(ex, "https://loja.com/produto/x",
                                "https://loja.com/produto/x", "Tênis")
    assert p["preco"] is None and p["preco_confirmado"] is False
    assert p["preco_texto"] == shopping.PRECO_NAO_CONFIRMADO


def test_preco_a_partir_de_em_texto_visivel_nao_confirma():
    pagina = ('<html><head><title>Tênis de Corrida Y</title>'
              '<meta property="og:type" content="product">'
              '<meta property="og:title" content="Tênis de Corrida Y"></head>'
              '<body><h1>Tênis de Corrida Y</h1>'
              '<p>a partir de R$ 199,00</p></body></html>')
    saidas = shopping._recuperar_ofertas(
        "https://loja.com/produto/y", "Tênis",
        baixar_fn=_baixar_da(pagina), consulta="tenis de corrida")
    assert len(saidas) == 1
    assert saidas[0]["preco"] is None
    assert saidas[0]["preco_texto"] == shopping.PRECO_NAO_CONFIRMADO
    fence = shopping.fence_resultado(
        {"produtos": saidas, "fontes": [], "criterios": {}})
    assert shopping.PRECO_NAO_CONFIRMADO in fence


def test_estoque_desconhecido_nao_vira_em_estoque():
    ex = {"nome": "Tênis Z", "marca": "", "modelo": "", "variante": "",
          "imagem": "", "descricao": "", "avaliacao": None, "n_avaliacoes": None,
          "url_produto": "",
          "ofertas_ld": [{"preco": 250.0, "moeda": "BRL", "preco_confirmado": True,
                          "disponibilidade": "", "url_oferta": "", "loja": "",
                          "valido_ate": ""}]}
    p = shopping.montar_produto(ex, "https://loja.com/produto/z",
                                "https://loja.com/produto/z", "Tênis")
    assert p["disponibilidade"] == "desconhecida"
    assert shopping._jdui_produto(p)["disponibilidade"] == "desconhecida"


# ── Cache e evidência ─────────────────────────────────────────────────

def _resultado_1produto(**kw):
    p = {"nome": "Tênis X", "preco_texto": "R$ 499,90", "preco": 499.9,
         "loja": "loja.com", "url": "https://loja.com/produto/x",
         "disponibilidade": "em_estoque"}
    r = {"produtos": [p], "fontes": [], "criterios": {},
         "total_bruto": 1, "excluidos": [], "de_cache": False,
         "verificado_em": "2026-10-17T10:00:00+00:00"}
    r.update(kw)
    return r


def test_bloco_declara_reuso_de_cache_com_data():
    bloco = shopping.bloco_para_llm(_resultado_1produto(de_cache=True))
    assert "cache local" in bloco
    assert "17/10/2026" in bloco
    assert "nunca como verificação de agora" in bloco


def test_bloco_fresco_nao_declara_reuso():
    bloco = shopping.bloco_para_llm(_resultado_1produto(de_cache=False))
    assert "dados coletados agora" in bloco
    assert "nível de verificação" in bloco
    assert "cache local" not in bloco


def test_bloco_fresco_nao_superestima_verificacao():
    # V5.7 (descoberta): produto sem link verificado/preço confirmado não pode
    # ser apresentado como "dados verificados" — o nível real é declarado.
    bloco = shopping.bloco_para_llm(_resultado_1produto(de_cache=False))
    assert "nível: oferta parcialmente verificada" in bloco
    assert "dados verificados agora" not in bloco


def test_resumo_texto_avisa_consulta_anterior():
    texto = shopping.resumo_texto(_resultado_1produto(de_cache=True))
    assert "consulta anterior" in texto and "17/10/2026" in texto


def test_cache_expirado_nao_e_reaproveitado():
    db = _db()
    shopping.salvar_consulta(db, "ana", "c", "tenis de basquete", {},
                             _resultado_1produto())
    hit = shopping.consulta_em_cache(db, "ana", "tenis de basquete")
    assert hit and hit["de_cache"] is True
    db.execute("UPDATE shopping_consultas SET expira_em = '2000-01-01T00:00:00+00:00'")
    db.commit()
    assert shopping.consulta_em_cache(db, "ana", "tenis de basquete") is None
    db.close()


def test_ttl_configuravel_por_env(monkeypatch):
    monkeypatch.delenv("JULIA_SHOPPING_TTL", raising=False)
    assert shopping._ttl_consulta() == 6 * 3600
    monkeypatch.setenv("JULIA_SHOPPING_TTL", "60")
    assert shopping._ttl_consulta() == 60
    monkeypatch.setenv("JULIA_SHOPPING_TTL", "abc")
    assert shopping._ttl_consulta() == 6 * 3600


# ── Roteamento do pedido de produto ───────────────────────────────────

def test_pedido_mostre_roteia_para_shopping():
    t = "me mostre tenis para jogar basquete"
    assert shopping.detectar_intencao(t) is True
    r = intent.analisar(t)
    assert r["intencao"] == "shopping"
    assert "shopping" in r["ferramentas"]
    assert r["evidencias"] == ["pedido_produto"]


def test_pedido_explicativo_nao_vira_busca():
    assert shopping.detectar_intencao(
        "me mostra como funciona o tenis de basquete") is False
    assert shopping.detectar_intencao("o que e um tenis de corrida?") is False


def test_verbos_fortes_preservados():
    assert shopping.detectar_intencao("pesquise tenis de basquete") is True
    assert shopping.detectar_intencao("qual a capital da Franca?") is False


# ── Alegações comerciais sem evidência ────────────────────────────────

_TABELA_INVENTADA = (
    "**Tênis para Basquete**\n\n"
    "| Marca | Preço Estimado (R$) |\n|---|---|\n"
    "| Nike LeBron 21 | 1.600-1.800 |\n| Adidas Harden | 900-1.100 |\n"
    "| Puma Tazon | 400-600 |")


def test_precos_sem_verificacao_viram_violacao():
    v = intent.validar(intent.analisar("me mostre tenis para jogar basquete"),
                       _TABELA_INVENTADA,
                       {"ferramentas_usadas": [], "produtos": []})
    assert any(x["codigo"] == "verificacao_alegada_sem_evidencia"
               for x in v["violacoes"])


def test_alegacao_com_busca_verificada_nao_e_violacao():
    v = intent.validar(intent.analisar("me mostre tenis para jogar basquete"),
                       "Achei: Tênis Nike Air — R$ 499,90 na loja X.",
                       {"ferramentas_usadas": ["shopping"],
                        "produtos": [{"nome": "Tênis Nike Air"}]})
    assert not any(x["codigo"] == "verificacao_alegada_sem_evidencia"
                   for x in v["violacoes"])


def test_resultado_vazio_sem_citacao_de_precos_e_honesto():
    v = intent.validar(intent.analisar("me mostre tenis para jogar basquete"),
                       "Não encontrei ofertas verificadas agora; me diga um "
                       "modelo específico que eu aprofundo a busca.",
                       {"ferramentas_usadas": ["shopping"], "produtos": []})
    assert v["violacoes"] == []


def test_aviso_explicito_de_nao_verificacao_nao_e_violacao():
    v = intent.validar(intent.analisar("oi"),
                       "Valores típicos: 1.600-1.800 reais. Não verifiquei em "
                       "lojas; podem ter mudado desde então.",
                       {"ferramentas_usadas": [], "produtos": []})
    assert not any(x["codigo"] == "verificacao_alegada_sem_evidencia"
                   for x in v["violacoes"])


# ── Imagens e JDUI ────────────────────────────────────────────────────

def test_imagem_reprovada_zera_url_e_motivo_vai_ao_fence():
    def _abrir(url, timeout=8.0, ua=""):
        if url.endswith("/ok.png"):
            return _Resp(_png(800, 600), ctype="image/png")
        return _Resp(b"<html>nao e imagem</html>")

    a = {"nome": "A", "imagem": "https://cdn.loja.com/ok.png"}
    b = {"nome": "B", "imagem": "https://cdn.loja.com/quebrada.jpg"}
    shopping.verificar_imagens([a, b], abrir=_abrir)
    assert b["imagem"] == "" and b["imagem_motivo"]
    fence = shopping.fence_resultado(
        {"produtos": [b], "fontes": [], "criterios": {}})
    corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    prod = corpo["blocks"][0]["props"]["produto"]
    assert prod["imagem"] == ""
    assert prod["imagem_veredito"] == "reprovado"
    assert prod["imagem_motivo"] == b["imagem_motivo"]


def test_jdui_valida_produto_com_imagem_motivo_preservado():
    ok, norm, errs = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "productcard", "props": {
                "produto": {"nome": "Tênis X", "imagem_veredito": "reprovado",
                            "imagem_motivo": "conteúdo text/html não é imagem"}}}]})
    assert ok, errs
    prod = norm["blocks"][0]["props"]["produto"]
    assert prod["imagem_motivo"] == "conteúdo text/html não é imagem"
    assert prod["imagem_veredito"] == "reprovado"


def test_fence_de_produto_do_modelo_e_removido_sem_busca():
    texto = ("Segue a grade:\n\n```jdui\n"
             '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui",'
             '"component":"productgrid","props":{"items":[{"nome":"Inventado",'
             '"preco":"R$ 1"}]}}]}\n```\n')
    limpo = shopping.remover_fences_produto(texto)
    assert "Inventado" not in limpo and "```jdui" not in limpo
    aplicado = pc_agent._shopping_aplicar(texto, None)
    assert "Inventado" not in aplicado


def test_shopping_aplicar_anexa_card_da_ferramenta_na_frente():
    res = _resultado_1produto()
    texto = "Veja as opções verificadas:"
    out = pc_agent._shopping_aplicar(texto, res)
    assert out.lstrip().startswith("```jdui")   # imagens primeiro
    assert out.index("```jdui") < out.index(texto)
    assert "productcard" in out and texto in out


def test_shopping_aplicar_sem_produtos_anexa_nota_honesta():
    res = {"produtos": [], "fontes": [], "criterios": {}, "de_cache": False,
           "verificado_em": "2026-10-18T00:00:00"}
    out = pc_agent._shopping_aplicar("Não achei ofertas.", res)
    assert "Não achei ofertas." in out
    assert "nenhuma página trouxe dados estruturados" in out


def test_validar_resposta_anexa_nota_de_confiabilidade():
    out = pc_agent._validar_resposta(
        intent.analisar("me mostre tenis para jogar basquete"),
        _TABELA_INVENTADA, usadas=[], produtos=[], mid="m1")
    assert "Não verifiquei estes valores em lojas" in out
    out2 = pc_agent._validar_resposta(
        intent.analisar("me mostre tenis para jogar basquete"),
        _TABELA_INVENTADA, usadas=["shopping"],
        produtos=[{"nome": "Tênis real"}], mid="m2")
    assert "Não verifiquei estes valores em lojas" not in out2


def test_fence_malformado_nao_vira_json_bruto():
    texto = 'Antes.\n\n```jdui\n{"blocks": [QUEBRADO\n```\nDepois.'
    limpo, blocos, erros = jdui.normalizar(texto)
    assert "QUEBRADO" not in limpo
    assert blocos == [] and erros
    assert "Antes." in limpo and "Depois." in limpo


# ── Pipeline: provedor parcial + grounding do fallback ───────────────

def test_falha_parcial_de_provedor_fica_registrada(monkeypatch):
    def _mlb_falha(*a, **kw):
        raise research.ResearchErro("bloqueado", "bloqueado")

    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(shopping, "buscar_ddg_chain",
                        lambda q: ([{"url": "https://loja.com/p"}], ["ddg: 1 resultado"]))
    achados, etapas = shopping.buscar_com_fallback("tenis basquete")
    assert achados == [{"url": "https://loja.com/p"}]
    assert etapas[0].startswith("mlb: falhou")
    assert any(e.startswith("ddg:") for e in etapas)


def test_shopping_executar_grounding_no_fallback(monkeypatch):
    chamadas = []

    def _pesquisar_fake(db, owner, texto, conv, progresso=None):
        chamadas.append((owner, texto))
        return {"produtos": [{"nome": "Tênis X", "preco_texto": "R$ 499,90"}],
                "fontes": [{"id": "S1", "titulo": "Loja", "url": "https://loja.com"}],
                "criterios": {}, "de_cache": False}

    monkeypatch.setattr(shopping, "pesquisar", _pesquisar_fake)
    db = _db()
    extras = {"shop": True, "fontes": [], "ferramentas_usadas": [], "intent": {}}
    messages = [{"role": "system", "content": "base"}]
    res = pc_agent._shopping_executar(db, "ana", "conv", "me mostre tenis",
                                      extras, messages)
    assert res and chamadas == [("ana", "me mostre tenis")]
    assert "shopping" in extras["ferramentas_usadas"]
    assert extras["fontes"][0]["url"] == "https://loja.com"
    assert any("RESULTADO DE PESQUISA DE PRODUTOS" in m["content"]
               for m in messages if m["role"] == "system")
    db.close()


def test_shopping_executar_sem_pedido_nao_busca(monkeypatch):
    def _explode(*a, **kw):
        raise AssertionError("não deveria buscar")

    monkeypatch.setattr(shopping, "pesquisar", _explode)
    db = _db()
    extras = {"shop": False, "fontes": [], "ferramentas_usadas": []}
    assert pc_agent._shopping_executar(db, "ana", "c", "oi", extras, []) is None
    db.close()


# ── Service worker: dados vivos, nunca cache de API ──────────────────

def test_service_worker_nao_intercepta_api_e_e_network_first():
    sw = (Path(__file__).resolve().parents[1] / "public" / "sw.js"
          ).read_text(encoding="utf-8")
    assert "url.pathname.startsWith('/api/')" in sw
    assert "fetch(evt.request).then" in sw
    assert ".catch(() => caches.match(cacheKey))" in sw


# ── Harness Node: jdui.js renderiza sem foto com motivo ──────────────

_HARNESS = r"""
const fs = require('fs');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this.dataset = {}; this._text = ''; this.className = ''; this.classList = { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false }; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(c => this.appendChild(c)); }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  addEventListener(name, fn) { this.events[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
}
global.document = { createElement: tag => new Element(tag),
  createElementNS: (ns, tag) => new Element(tag) };
global.location = { href: 'https://app.example.test/' };
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const JDUI = global.window.JDUI;
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
const V = 'JULIA-ui-message/v1';
const prod = { nome: 'Tênis X', imagem: '', imagem_veredito: 'reprovado',
  imagem_motivo: 'conteudo text/html nao e imagem' };
const v = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'productcard', props: { produto: prod } }] });
t('schema-imagem-motivo', v.ok === true &&
  v.msg.blocks[0].props.produto.imagem_motivo === 'conteudo text/html nao e imagem');
const root = new Element('main');
JDUI.mount(root, [{ blocks: [{ type: 'ui', component: 'productcard',
  props: { produto: prod } }] }], {});
t('card-sem-foto-confirmada', root.textContent.includes('Sem foto confirmada'));
const acharTitulo = (el) => {
  if (el.attrs && el.attrs.title && String(el.attrs.title).includes('nao e imagem')) return true;
  return (el.children || []).some(acharTitulo);
};
t('card-motivo-no-titulo', acharTitulo(root));
"""


def test_jdui_js_renderiza_motivo_da_imagem():
    import shutil as _sh
    import subprocess as _sp
    node = _sh.which("node")
    if node is None:
        pytest.skip("Node indisponível")
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_reliab_v57.cjs"
        harness.write_text(_HARNESS, encoding="utf-8")
        raiz = Path(__file__).resolve().parents[1]
        r = _sp.run([node, str(harness), str(raiz / "public" / "jdui.js")],
                    capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "FAIL" not in r.stdout
