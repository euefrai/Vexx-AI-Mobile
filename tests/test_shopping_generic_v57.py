"""V5.7 — Descoberta em consultas genéricas: referências não verificadas.

Cobre o incidente "me mostre tenis para jogar basquete" (0 resultados úteis):
consulta genérica não exige marca/modelo/tamanho/orçamento; páginas
específicas de produto que não puderam ser validadas (403/CAPTCHA sem
contorno, sem dados estruturados) viram REFERÊNCIAS não verificadas — só
nome+URL+motivo — nunca ofertas, nunca preço/foto/estoque inventados, nunca
"link quebrado". Página removida, home, busca/categoria, login e junk sem
identidade nunca viram referência.

Fixtures locais; sem rede (DNS mockado).
"""
import tempfile
from pathlib import Path

import pytest

import pc_agent
import research
import shopping


@pytest.fixture(autouse=True)
def _sem_dns(monkeypatch):
    # url_segura faz resolução real; nos testes o host é considerado público.
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "generic57.sqlite3")


_CONSULTA_GENERICA = "me mostre tenis para jogar basquete"


def _pagina_produto(nome="Tênis de Basquete Pro 2", com_preco=True,
                    url="https://lojax.com.br/produto/tenis-basquete-pro"):
    ofertas = ('"offers":{"@type":"Offer","price":"499.90",'
               '"priceCurrency":"BRL",'
               '"availability":"https://schema.org/InStock"},' if com_preco else "")
    return (
        f'<html><head><title>{nome} - Loja X</title>'
        '<meta property="og:type" content="product">'
        '<meta property="product:price:amount" content="499.90">'
        '<script type="application/ld+json">'
        f'{{"@context":"https://schema.org/","@type":"Product","name":"{nome}",'
        f'"image":"https://cdn.lojax.com.br/basquete.jpg",'
        f'"url":"{url}",{ofertas}"brand":"MarcaY"}}'
        '</script></head><body><h1>' + nome + '</h1>'
        '<button>Adicionar ao carrinho</button> R$ 499,90</body></html>')


def _bloqueada(url):
    raise research.ResearchErro("Provedor bloqueou (403).", "bloqueado")


_CAND_BLOQUEADO = {
    "titulo": "Tênis Nike Air Zoom Basquete — Esportes",
    "url": "https://esportes.com.br/produto/tenis-nike-air-zoom-basquete",
    "trecho": "Tênis para basquete com amortecimento",
}


# ── Filtros explícitos × atributos desejáveis ─────────────────────────

def test_generico_nao_gera_filtros_explicitos():
    crit = shopping.extrair_criterios(_CONSULTA_GENERICA)
    assert shopping.filtros_explicitos(crit) == {}
    assert shopping.atributos_desejaveis(crit).get("categoria") == "tenis"
    bloco = shopping.bloco_para_llm({"produtos": [], "criterios": crit})
    assert "FILTROS EXPLÍCITOS DO PEDIDO: nenhum" in bloco
    assert "NÃO exija do usuário" in bloco


def test_filtros_explicitos_separados_de_atributos():
    crit = shopping.extrair_criterios(
        "notebook gamer até R$ 4000 da samsung com 16gb ram")
    fx = shopping.filtros_explicitos(crit)
    assert fx.get("preco_max") == 4000
    assert "samsung" in fx.get("marcas", [])
    assert fx.get("specs", {}).get("ram_fisica_gb") == 16
    desej = shopping.atributos_desejaveis(crit)
    # "gamer" é atributo desejável (não vira exclusão dura).
    assert desej.get("specs", {}).get("flag_gamer") is True
    assert "flag_gamer" not in fx.get("specs", {})


# ── Referências não verificadas (bloqueio/sem-dados) ──────────────────

def test_pagina_bloqueada_vira_referencia_nao_verificada():
    db = _db()
    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c1",
                             buscar_fn=lambda q: [dict(_CAND_BLOQUEADO)],
                             baixar_fn=_bloqueada)
    assert res["produtos"] == []
    refs = res["encontrados"]
    assert len(refs) == 1
    r = refs[0]
    assert r["url"] == _CAND_BLOQUEADO["url"]
    assert r["origem_encontro"] == "busca"
    assert "403/CAPTCHA" in r["motivo"] and "não verificada" in r["motivo"]
    assert "quebrado" not in r["motivo"].lower()
    # Nunca ganha dado presumido de oferta.
    assert r.get("preco") is None and not r.get("imagem") and not r.get("preco_texto")
    # Sem produtos → sem cards; referência é texto (link com ressalva).
    assert shopping.fence_resultado(res) == ""
    texto = shopping.resumo_texto(res)
    assert "não verificadas" in texto and "referência" in texto.lower()
    assert _CAND_BLOQUEADO["url"] in texto
    assert "Nenhuma restrição do seu pedido limitou a busca" in texto
    assert "modelo específico" not in texto
    bloco = shopping.bloco_para_llm(res)
    assert "REFERÊNCIAS NÃO VERIFICADAS" in bloco
    assert "nunca afirme preço, foto ou estoque" in bloco


def test_pagina_sem_dados_estruturados_vira_referencia():
    db = _db()
    cand = {"titulo": "Tênis de Basquete Infantil — Mega Esportes",
            "url": "https://megaesportes.com.br/produto/tenis-basquete-infantil",
            "trecho": "linha de tênis de basquete"}
    res = shopping.pesquisar(
        db, "ana", _CONSULTA_GENERICA, "c2",
        buscar_fn=lambda q: [cand],
        baixar_fn=lambda url: {"final": url,
                               "texto": "<html><body>sem dados</body></html>"})
    assert res["produtos"] == []
    refs = res["encontrados"]
    assert len(refs) == 1
    assert refs[0]["motivo_codigo"] == "sem_dados"
    assert "não expôs dados estruturados" in refs[0]["motivo"]
    assert "não verificada" in refs[0]["motivo"]


def test_pagina_removida_nunca_vira_referencia():
    db = _db()
    pagina = ('<html><head><title>Produto indisponível | Loja</title></head>'
              '<body><h1>Produto indisponível</h1>'
              '<p>Este produto não está mais disponível.</p></body></html>')
    cand = {"titulo": "Tênis de Basquete Mágico Exclusivo",
            "url": "https://esportes.com.br/produto/tenis-basquete-magico"}
    res = shopping.pesquisar(
        db, "ana", _CONSULTA_GENERICA, "c3",
        buscar_fn=lambda q: [cand],
        baixar_fn=lambda url: {"final": url, "texto": pagina})
    assert res["produtos"] == []
    assert res["encontrados"] == []
    texto = shopping.resumo_texto(res)
    # A página removida não é apresentada nem como referência.
    assert cand["url"] not in texto


def test_home_busca_lista_login_nunca_viram_referencia():
    db = _db()
    cands = [
        {"titulo": "Loja Esportes — Tênis", "url": "https://lojaesportes.com.br/"},
        {"titulo": "Busca: tenis", "url": "https://lojaesportes.com.br/busca/tenis"},
        {"titulo": "Tenis - Mercado Livre", "url": "https://lista.mercadolivre.com.br/tenis"},
        {"titulo": "Entrar | Loja Esportes", "url": "https://lojaesportes.com.br/login"},
    ]
    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c4",
                             buscar_fn=lambda q: [dict(c) for c in cands],
                             baixar_fn=_bloqueada)
    assert res["produtos"] == []
    assert res["encontrados"] == []


def test_junk_sem_identidade_nao_vira_referencia():
    db = _db()
    cands = [
        {"titulo": "mike – Page 2 – Blog Pessoal",
         "url": "https://blog.exemplo.com/author/mike/page/2/"},
        {"titulo": "Panela Elétrica 5L — Panos & Cia",
         "url": "https://panosdecozinha.com.br/produto/panela-eletrica-5l"},
    ]
    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c5",
                             buscar_fn=lambda q: [dict(c) for c in cands],
                             baixar_fn=_bloqueada)
    assert res["encontrados"] == []


def test_referencia_nao_duplica_card_nem_a_si_mesma():
    db = _db()
    url_produto = "https://lojax.com.br/produto/tenis-basquete-pro"
    cands = [
        {"titulo": "Tênis de Basquete Pro 2 - Loja X",
         "url": url_produto, "trecho": "tenis basquete"},
        dict(_CAND_BLOQUEADO),
        # Mesmo recurso do bloqueado (www + barra final) — deve deduplicar.
        {"titulo": "Tênis Nike Air Zoom Basquete — Esportes",
         "url": "https://www.esportes.com.br/produto/tenis-nike-air-zoom-basquete/"},
    ]

    def _baixar(url):
        if url == url_produto:
            return {"final": url, "texto": _pagina_produto(url=url)}
        _bloqueada(url)

    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c6",
                             buscar_fn=lambda q: [dict(c) for c in cands],
                             baixar_fn=_baixar)
    assert len(res["produtos"]) == 1
    refs = res["encontrados"]
    assert len(refs) == 1
    assert "esportes.com.br" in refs[0]["url"]
    assert url_produto not in [r["url"] for r in refs]


# ── Níveis de evidência (confirmada × parcial × encontrada) ───────────

def test_tier_confirmada_usa_card_e_nao_superestima():
    db = _db()
    url = "https://lojax.com.br/produto/tenis-basquete-pro"
    res = shopping.pesquisar(
        db, "ana", _CONSULTA_GENERICA, "c7",
        buscar_fn=lambda q: [{"titulo": "Tênis de Basquete Pro 2 - Loja X",
                              "url": url, "trecho": "tenis basquete"}],
        baixar_fn=lambda u: {"final": u, "texto": _pagina_produto(url=url)})
    assert len(res["produtos"]) == 1
    p = res["produtos"][0]
    assert p["preco_confirmado"] is True
    assert shopping._tier(p) == "confirmada"
    assert "dados verificados" in shopping.resumo_texto(res)
    bloco = shopping.bloco_para_llm(res)
    assert "nível: oferta confirmada" in bloco
    assert "dados coletados agora" in bloco
    fence = shopping.fence_resultado(res)
    assert "```jdui" in fence and "productcard" in fence


def test_tier_parcial_declarada_no_texto_e_no_grounding():
    db = _db()
    url = "https://lojax.com.br/produto/tenis-basquete-pro"
    res = shopping.pesquisar(
        db, "ana", _CONSULTA_GENERICA, "c8",
        buscar_fn=lambda q: [{"titulo": "Tênis de Basquete Pro 2 - Loja X",
                              "url": url, "trecho": "tenis basquete"}],
        baixar_fn=lambda u: {"final": u,
                             "texto": _pagina_produto(com_preco=False, url=url)})
    assert len(res["produtos"]) == 1
    p = res["produtos"][0]
    assert p["preco"] is None and p["preco_confirmado"] is False
    assert shopping._tier(p) == "parcial"
    texto = shopping.resumo_texto(res)
    assert "dados estruturados reais" in texto
    assert shopping.PRECO_NAO_CONFIRMADO in texto
    assert "verificação parcial" in texto
    bloco = shopping.bloco_para_llm(res)
    assert "nível: oferta parcialmente verificada" in bloco
    assert "dados verificados agora" not in bloco


# ── Bloqueio de provedor: registrado, nunca contornado ────────────────

def test_provedor_bloqueado_registrado_sem_contorno(monkeypatch):
    db = _db()
    chamadas = []

    def _mlb(q, limite=10):
        raise research.ResearchErro("Provedor bloqueou (403).", "bloqueado")

    monkeypatch.setattr(shopping, "buscar_mlb", _mlb)
    monkeypatch.setattr(shopping, "buscar_ddg_chain",
                        lambda q, max_resultados=6: (
                            [], ["ddg: sem resultados (bloqueio?)",
                                 "ddg-lite: sem resultados (bloqueio?)"]))
    monkeypatch.setattr(shopping, "buscar_web_v55",
                        lambda q, max_resultados=10: (
                            [dict(_CAND_BLOQUEADO)],
                            ["web: 1 resultado (bing, ok)"]))

    def _baixar(url):
        chamadas.append(url)
        _bloqueada(url)

    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c9",
                             baixar_fn=_baixar)
    etapas = " | ".join(res.get("etapas_provedores", []))
    assert "mlb: falhou" in etapas
    assert "ddg: sem resultados (bloqueio?)" in etapas
    assert "web: 1 resultado (bing, ok)" in etapas
    # Nada de tentativa extra/paralela contra o site bloqueado.
    assert chamadas == [_CAND_BLOQUEADO["url"]]
    assert res["encontrados"][0]["motivo_codigo"] == "bloqueio"


# ── Texto honesto quando não há nada útil ─────────────────────────────

def test_fluxo_vazio_explica_limitacao_sem_exigir_modelo():
    db = _db()
    cand = {"titulo": "Busca: tenis basquete",
            "url": "https://lojaesportes.com.br/busca/tenis-basquete"}
    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c10",
                             buscar_fn=lambda q: [cand],
                             baixar_fn=_bloqueada)
    assert res["produtos"] == [] and res["encontrados"] == []
    texto = shopping.resumo_texto(res)
    assert "Não consegui confirmar ofertas" in texto
    assert "Nenhuma restrição do seu pedido limitou a busca" in texto
    assert "modelo específico" not in texto
    bloco = shopping.bloco_para_llm(res)
    assert "peça um modelo" not in bloco
    assert "Explique a limitação de forma objetiva" in bloco
    assert "PROIBIDO inventar" in bloco


def test_referencias_persistem_na_consulta_salva():
    db = _db()
    shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c11",
                       buscar_fn=lambda q: [dict(_CAND_BLOQUEADO)],
                       baixar_fn=_bloqueada)
    salva = shopping.ultima_consulta(db, "ana", "c11")
    assert salva is not None
    assert len(salva["resultado"].get("encontrados", [])) == 1


def test_listagem_com_caminho_list_nao_vira_referencia():
    """Auditoria de descoberta 2026-10-18: `/list/` (Shopee) é listagem
    dinâmica — não é página específica de produto e nunca vira referência,
    mesmo com bloqueio/sem-dados na abertura."""
    db = _db()
    cand = {"titulo": "Tênis de Basquete em Oferta | Shopee 2026",
            "url": "https://shopee.com.br/list/T%C3%AAnis/Basquete"}
    res = shopping.pesquisar(db, "ana", _CONSULTA_GENERICA, "c12",
                             buscar_fn=lambda q: [dict(cand)],
                             baixar_fn=_bloqueada)
    assert res["produtos"] == [] and res["encontrados"] == []


def test_pagina_especifica_nao_fica_fora_do_teto_por_paginas_genericas():
    """Orçamento de páginas: seis homes/buscas à frente não podem consumir o
    teto inteiro quando há página específica de produto na fila — antes ela
    ficava sem tentativa E sem referência (descoberta perdida em silêncio).
    A ordenação só muda a ORDEM de download; nenhuma validação é afrouxada."""
    db = _db()
    genericas = (
        [{"titulo": f"Loja {i} — Tênis", "url": f"https://loja{i}.com.br/"}
         for i in (1, 3, 5)]
        + [{"titulo": f"Busca: tênis {i}", "url": f"https://loja{i}.com.br/busca/tenis"}
           for i in (2, 4, 6)])
    especifica = {"titulo": "Tênis de Basquete Pro X — Loja Sete",
                  "url": "https://loja7.com.br/produto/tenis-basquete-pro-x",
                  "trecho": "tênis de basquete com amortecimento"}
    tentadas = []

    def _baixar(url):
        tentadas.append(url)
        _bloqueada(url)

    res = shopping.pesquisar(
        db, "ana", _CONSULTA_GENERICA, "c13",
        buscar_fn=lambda q: [dict(c) for c in genericas + [especifica]],
        baixar_fn=_baixar)
    assert especifica["url"] in tentadas
    refs = res["encontrados"]
    assert len(refs) == 1 and refs[0]["url"] == especifica["url"]
    assert refs[0]["motivo_codigo"] == "bloqueio"
