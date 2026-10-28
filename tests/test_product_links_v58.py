"""V5.8 — link do produto nunca é home/busca/categoria.

Regressões da auditoria de 2026-10-27: card apontava para a home da loja
quando o dado estruturado só declarava a home; resposta do modelo podia
trazer URL inventada ou de busca com rótulo de produto.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shopping
import source_check


def _extraido(**kw):
    ex = {"nome": "Placa de Vídeo 6GB", "marca": "", "modelo": "",
          "variante": "", "imagem": "", "descricao": "", "avaliacao": None,
          "n_avaliacoes": None, "url_produto": "", "ofertas_ld": []}
    ex.update(kw)
    return ex


# ── Gate de URL ──────────────────────────────────────────────────────────────

def test_url_de_listagem_e_url_de_item():
    assert source_check.url_de_listagem("https://loja.com/")
    assert source_check.url_de_listagem("https://loja.com/busca?q=placa")
    assert source_check.url_de_listagem("https://loja.com/categoria/gpu")
    assert not source_check.url_de_listagem("https://loja.com/produto/placa")
    assert source_check.url_parece_produto("https://loja.com/produto/placa")
    assert source_check.url_parece_produto("https://loja.com/dp/B0ABC123")
    assert not source_check.url_parece_produto("https://loja.com/")
    assert not source_check.url_parece_produto("https://loja.com/busca?q=placa")


def test_url_exibivel_rejeita_home_busca_e_credenciais():
    assert shopping.url_exibivel("https://loja.com/produto/x")
    assert not shopping.url_exibivel("https://loja.com/")
    assert not shopping.url_exibivel("https://loja.com/search?q=x")
    assert not shopping.url_exibivel("https://user:senha@loja.com/produto/x")
    assert not shopping.url_exibivel("javascript:alert(1)")
    assert not shopping.url_exibivel("/produto/x")


def test_verified_product_url_does_not_authorize_other_origins_or_credentials():
    result = {'produtos': [{'url_item': 'https://loja.com/produto/x'}]}
    for changed in ('http://loja.com/produto/x', 'https://loja.com:8443/produto/x',
                    'https://loja.com:0/produto/x',
                    'https://user:password@loja.com/produto/x'):
        answer = shopping.sanitizar_links_resposta('[Produto](' + changed + ')', result)
        assert '](' not in answer
        assert 'link não verificado' in answer
    assert shopping.sanitizar_links_resposta('[Produto](https://loja.com:443/produto/x)', result).startswith('[Produto](')


# ── Card: link do item ───────────────────────────────────────────────────────

def test_montar_produto_prefere_item_mesmo_com_home_declarada():
    ex = _extraido(
        url_produto="https://loja.com/",
        ofertas_ld=[{"preco": 100.0, "moeda": "BRL", "preco_confirmado": True,
                     "disponibilidade": "em_estoque",
                     "url_oferta": "https://loja.com/produto/x",
                     "loja": "", "valido_ate": ""}])
    p = shopping.montar_produto(ex, "https://loja.com/", "https://loja.com/", "t")
    assert p["url_item"] == "https://loja.com/produto/x"


def test_montar_produto_sem_item_nao_usa_home_como_link():
    p = shopping.montar_produto(
        _extraido(url_produto="https://loja.com/"),
        "https://loja.com/", "https://loja.com/", "t",
        validacao={"veredito": "verificado", "codigo": "ok"})
    assert p["url_item"] == ""
    assert p["link_codigo"] == "sem_link_item"
    assert p["link_veredito"] == "nao_verificado"


def test_montar_produto_pagina_de_item_sem_validacao_serve_de_link():
    p = shopping.montar_produto(
        _extraido(), "https://loja.com/produto/x",
        "https://loja.com/produto/x", "t")
    assert p["url_item"] == "https://loja.com/produto/x"


def test_montar_produto_pagina_de_busca_nunca_vira_link():
    p = shopping.montar_produto(
        _extraido(), "https://loja.com/categoria/gpu",
        "https://loja.com/categoria/gpu", "t")
    assert p["url_item"] == ""
    assert p["link_codigo"] == "sem_link_item"


def test_link_do_produto_nao_cai_para_listagem():
    p = {"url_item": "https://loja.com/busca?q=x",
         "url_final": "https://loja.com/",
         "url": "https://loja.com/produto/x"}
    assert shopping._link_do_produto(p) == "https://loja.com/produto/x"
    assert shopping._link_do_produto(
        {"url_item": "https://loja.com/", "url_final": "https://loja.com/"}) == ""


def test_deduplicar_oferta_sem_link_de_listagem():
    p = {"id": "gpu", "nome": "GPU", "loja": "Loja",
         "url_item": "https://loja.com/", "url_final": "https://loja.com/",
         "url": "https://loja.com/", "preco": 100.0}
    out = shopping.deduplicar([p])
    assert out[0]["ofertas"][0]["url"] == ""


def test_sources_de_ignora_home_busca_e_categoria():
    fontes = [
        {"id": "S1", "titulo": "home", "url": "https://loja.com/"},
        {"id": "S2", "titulo": "busca", "url": "https://loja.com/busca?q=x"},
        {"id": "S3", "titulo": "item", "url": "https://loja.com/produto/x"},
    ]
    assert shopping._sources_de(fontes) == [
        {"id": "S3", "title": "item", "url": "https://loja.com/produto/x"}]


# ── Sanitização da resposta do modelo ────────────────────────────────────────

def _sanitizar(texto, resultado=None, fontes=None):
    return shopping.sanitizar_links_resposta(texto, resultado, fontes)


def test_sanitizar_mantem_so_link_comprovado_e_rotula_os_demais():
    res = {"produtos": [{"url_item": "https://loja.com/produto/x"}],
           "fontes": [{"url": "https://loja.com/produto/y"}]}
    texto = ("confira [o X](https://loja.com/produto/x), "
             "[a busca](https://loja.com/busca?q=placa), "
             "https://loja.com/produto/y. e "
             "https://inventado.example/produto/z")
    saida = _sanitizar(texto, res)
    assert "[o X](https://loja.com/produto/x)" in saida
    assert "[a busca](" not in saida
    assert "a busca (página de busca/categoria — não é o produto)" in saida
    assert "https://loja.com/produto/y." in saida
    assert "inventado.example/produto/z (link não verificado" in saida
    assert "https://inventado.example/produto/z" not in saida


def test_sanitizar_protege_codigo_e_aceita_parametro_de_rastreio():
    res = {"produtos": [{"url_item": "https://loja.com/produto/x"}]}
    texto = ("https://loja.com/produto/x?utm_source=chat "
             "https://loja.com/produto/x?id=2 "
             "`https://loja.com/busca`\n"
             "```jdui\n[home](https://loja.com/)\n```")
    saida = _sanitizar(texto, res)
    assert "https://loja.com/produto/x?utm_source=chat" in saida
    assert "https://loja.com/produto/x?id=2" not in saida
    assert "`https://loja.com/busca`" in saida
    assert "```jdui\n[home](https://loja.com/)\n```" in saida


def test_sanitizar_sem_resultado_nao_inventa_allowlist():
    saida = _sanitizar("veja [aqui](https://loja.com/produto/x)")
    assert "[aqui](" not in saida
    assert "aqui (link não verificado" in saida
