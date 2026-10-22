"""V5.7.1 — Gate comercial da descoberta (reprodução do incidente 18/10).

Incidente: "me mostre um notebook" → mlb 403 → ddg bloqueado → ddg-lite
devolveu anúncio/blog/índice → o código antigo tratava QUALQUER resultado
como suficiente e encerrava a cadeia antes do provedor web → 0 ofertas.
Quando o fluxo chegava ao web, havia páginas comerciais válidas (4 KaBuM
confirmadas no diagnóstico anterior).

O gate classifica cada candidato por TIPO de página (PRODUCT_CANDIDATE,
COMMERCIAL_LISTING, EDITORIAL_REFERENCE, GENERIC_INDEX, IRRELEVANT,
UNKNOWN): só candidato comercial encerra a cascata; o restante continua
para o próximo provedor e é mesclado/deduplicado/ordenado. Uma 2ª onda de
consulta recupera candidatos quando a 1ª não rendeu NENHUMA oferta.

Fixtures congeladas do incidente (sem rede; DNS mockado).
"""
import tempfile
from pathlib import Path

import pytest

import pc_agent
import research
import shopping


@pytest.fixture(autouse=True)
def _sem_dns(monkeypatch):
    # url_segura faz resolução real; nos testes o host é público.
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "disc571.sqlite3")


def _mlb_falha(*a, **kw):
    raise research.ResearchErro("Provedor HTTP 403.", "http")


def _ddg_por_base(pool_html, pool_lite):
    def _fn(q, base=research.DDG_HTML, max_resultados=6, timeout=8.0):
        pool = pool_lite if base == research.DDG_LITE else pool_html
        return [dict(x) for x in pool]
    return _fn


def _web(pool, usados=None):
    def _fn(q, max_resultados=6, timeout=8.0, orcamento=None):
        return ([dict(x) for x in pool],
                {"estado": "ok", "provedores":
                 {"usados": usados or {"bing": len(pool)}}, "etapas": []})
    return _fn


def _nunca(*a, **kw):
    raise AssertionError("etapa não deveria rodar nesta condição")


# ── Congelados do incidente real (ddg-lite, 18/10 ~14:14) ─────────────
# Anúncio y.js, página do próprio DDG, blog com guia, blog de reviews e
# dois agregadores "melhores" — nenhuma página comercial de loja.
DDGLITE_LIXO = [
    {"titulo": "Fone Bluetooth Xiaomi — Oferta", "trecho": "",
     "url": "https://duckduckgo.com/y.js?ad_domain=mercadolivre.com.br"
            "&ad_provider=bingv7aa"},
    {"titulo": "Ads by Microsoft on DuckDuckGo Private Search", "trecho": "",
     "url": "https://duckduckgo.com/duckduckgo-help-pages/company/"
            "ads-by-microsoft-on-duckduckgo-private-search/"},
    {"titulo": "Notebook para estudar e trabalhar: guia 2026", "trecho": "",
     "url": "https://tecnoblog.net/guias/notebook-para-estudar-e-trabalhar/"},
    {"titulo": "Notebook para estudar e trabalhar", "trecho": "",
     "url": "https://techinter.com.br/notebooks/notebook-para-estudar-e-trabalhar/"},
    {"titulo": "Notebook bom e barato para estudar ou trabalhar", "trecho": "",
     "url": "https://leandroabreu.com.br/"
            "notebook-bom-e-barato-para-estudar-ou-trabalhar/"},
    {"titulo": "Qual o melhor notebook para trabalhar e estudar", "trecho": "",
     "url": "https://melhoresparacomprar.com.br/"
            "qual-o-melhor-notebook-para-trabalhar-e-estudar"},
]

# Chegada do provedor web (Bing) no diagnóstico: listagem de categoria e
# páginas específicas de loja — é daqui que saíram as 4 ofertas KaBuM.
WEB_COMERCIAL = [
    {"titulo": "Notebooks | KaBuM!", "trecho": "", "origem": "bing",
     "url": "https://www.kabum.com.br/computadores/notebooks"},
    {"titulo": "Notebook - Magazine Luiza", "trecho": "", "origem": "bing",
     "url": "https://www.magazineluiza.com.br/notebook/informatica/s/in/note/"},
    {"titulo": "Notebook Asus Vivobook Go 15 — KaBuM!", "trecho": "",
     "origem": "bing",
     "url": "https://www.kabum.com.br/produto/649861/"
            "notebook-asus-vivobook-go-15"},
    {"titulo": "Notebook Lenovo IdeaPad 1i — Loja", "trecho": "",
     "origem": "bing",
     "url": "https://www.lojax.com.br/produto/notebook-lenovo-ideapad-1i"},
    # Duplicata do que o ddg-lite já tinha trazido: a mesclagem deduplica.
    {"titulo": "Notebook para estudar e trabalhar: guia 2026", "trecho": "",
     "origem": "bing",
     "url": "https://tecnoblog.net/guias/notebook-para-estudar-e-trabalhar/"},
]


def _pagina_produto(nome="Tênis de Basquete Pro 2", url=None):
    url = url or "https://lojax.com.br/produto/tenis-basquete-pro"
    return (
        f'<html><head><title>{nome} - Loja X</title>'
        '<meta property="og:type" content="product">'
        '<meta property="product:price:amount" content="499.90">'
        '<script type="application/ld+json">'
        f'{{"@context":"https://schema.org/","@type":"Product","name":"{nome}",'
        f'"image":"https://cdn.lojax.com.br/basquete.jpg",'
        f'"url":"{url}","offers":{{"@type":"Offer","price":"499.90",'
        f'"priceCurrency":"BRL",'
        f'"availability":"https://schema.org/InStock"}},"brand":"MarcaY"}}'
        '</script></head><body><h1>' + nome + '</h1>'
        '<button>Adicionar ao carrinho</button> R$ 499,90</body></html>')


def _produto(**kw):
    p = {"nome": "Notebook X 16GB", "marca": "MarcaX", "modelo": "",
         "variante": "", "imagem": "https://cdn.lojax.com.br/x.jpg",
         "loja": "lojax.com.br", "url": "https://lojax.com.br/produto/notebook-x",
         "url_final": "https://lojax.com.br/produto/notebook-x",
         "url_item": "https://lojax.com.br/produto/notebook-x",
         "preco": 4400.0, "moeda": "BRL", "preco_confirmado": True,
         "preco_texto": "R$ 4.400,00", "disponibilidade": "em_estoque",
         "specs": {}, "verificado_em": "x", "id": "p1",
         "link_veredito": "verificado", "link_codigo": "verificado",
         "link_motivo": ""}
    p.update(kw)
    return p


# ── Teste crítico 1: lixo do ddg-lite continua para o web ─────────────

def test_critico_1_ddglite_so_lixo_continua_para_web(monkeypatch):
    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(research, "buscar_ddg",
                        _ddg_por_base([], DDGLITE_LIXO))
    chamadas = []

    def _orch(q, max_resultados=6, timeout=8.0, orcamento=None):
        chamadas.append(q)
        return ([dict(x) for x in WEB_COMERCIAL],
                {"estado": "ok", "provedores": {"usados": {"bing": 5}},
                 "etapas": []})

    monkeypatch.setattr(research, "_buscar_orquestrado", _orch)

    achados, etapas = shopping.buscar_com_fallback(
        "notebook comprar oferta")

    assert chamadas, "cadeia deveria CONTINUAR até o provedor web"
    urls = [a["url"] for a in achados]
    # Candidatos comerciais na frente (potencial de validação).
    assert urls[:4] == [
        "https://www.kabum.com.br/produto/649861/notebook-asus-vivobook-go-15",
        "https://www.lojax.com.br/produto/notebook-lenovo-ideapad-1i",
        "https://www.kabum.com.br/computadores/notebooks",
        "https://www.magazineluiza.com.br/notebook/informatica/s/in/note/",
    ]
    # Anúncio nunca é baixado nem vira candidato/referência.
    assert not any("y.js" in u for u in urls)
    # Mesclagem deduplica o mesmo recurso (tecnoblog veio nas duas etapas).
    assert urls.count(
        "https://tecnoblog.net/guias/notebook-para-estudar-e-trabalhar/") == 1
    # Etapas registram a decisão real (lixo classificado, continuação).
    assert any(e.startswith("ddg-lite:") and "0 comerciais" in e
               for e in etapas)
    assert any(e.startswith("web:") for e in etapas)


# ── Teste crítico 2: ddg-lite comercial mantém o caminho rápido ───────

def test_critico_2_ddglite_comercial_mantem_caminho_rapido(monkeypatch):
    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    quatro = [{"titulo": f"Notebook Bom {i}", "trecho": "",
               "url": f"https://lojaboa.com.br/produto/notebook-bom-{i}"}
              for i in range(1, 5)]
    monkeypatch.setattr(research, "buscar_ddg", _ddg_por_base([], quatro))
    monkeypatch.setattr(shopping, "buscar_web_v55", _nunca)

    achados, etapas = shopping.buscar_com_fallback("notebook")

    assert [a["url"] for a in achados] == [c["url"] for c in quatro]
    assert not any(e.startswith("web:") for e in etapas)


# ── Teste crítico 3: mistura de produtos e blogs ──────────────────────

def test_critico_3_mistura_preserva_produtos(monkeypatch):
    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    p1 = {"titulo": "Fone Bluetooth JBL Tune 510BT — KaBuM!", "trecho": "",
          "url": "https://www.kabum.com.br/produto/123456/"
                 "fone-jbl-tune-510bt"}
    p2 = {"titulo": "Fone de Ouvido Bluetooth Sony — Loja X", "trecho": "",
          "url": "https://www.lojax.com.br/produto/fone-sony-wf-c500"}
    blogs = DDGLITE_LIXO[2:]  # 4 blogs/agregadores congelados
    monkeypatch.setattr(research, "buscar_ddg",
                        _ddg_por_base([], [p1, p2] + blogs))
    monkeypatch.setattr(shopping, "buscar_web_v55", _nunca)

    achados, etapas = shopping.buscar_com_fallback("fone bluetooth")

    urls = [a["url"] for a in achados]
    assert p1["url"] in urls and p2["url"] in urls
    assert urls[0] == p1["url"] and urls[1] == p2["url"]
    # Cobertura comercial suficiente → caminho rápido preservado.
    assert not any(e.startswith("web:") for e in etapas)


# ── Teste crítico 4: todos editoriais → zero confirmadas, motivo ──────

def test_critico_4_todos_editoriais_zero_confirmadas(monkeypatch):
    db = _db()
    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(research, "buscar_ddg", _ddg_por_base([], DDGLITE_LIXO))
    editoriais = [
        {"titulo": "Os melhores notebooks de 2026", "trecho": "",
         "origem": "bing",
         "url": "https://olhardigital.com.br/2026/10/17/reviews/"
                "melhores-notebooks-para-trabalhar/"},
        {"titulo": "Melhor notebook", "trecho": "", "origem": "bing",
         "url": "https://dicio.com.br/melhor"},
        {"titulo": "notebook — Busca", "trecho": "", "origem": "bing",
         "url": "https://www.google.com/search?q=notebook"},
    ]
    monkeypatch.setattr(research, "_buscar_orquestrado",
                        _web(editoriais))

    fases = []
    res = shopping.pesquisar(
        db, "ana", "me mostre um notebook", "c4",
        baixar_fn=lambda url: {"final": url,
                               "texto": "<html><head><title>Guia</title>"
                                        "</head><body><p>artigo</p></body>"
                                        "</html>"},
        progresso=lambda fase, detalhe="": fases.append(fase))

    assert res["produtos"] == [] and res["alternativas"] == []
    # O web foi realmente consultado (continuação registrada nas etapas).
    assert any("web:" in e for e in res["etapas_provedores"])
    dec = res.get("descoberta") or {}
    motivos = {d.get("motivo") for d in dec.get("decisoes", [])}
    assert "irrelevant_results" in motivos
    assert dec.get("motivo_final") == "no_confirmed_offers"
    # 1ª onda não rendeu nada → 2ª onda real (recuperação) foi disparada.
    assert dec.get("ondas") == 2 and "recuperando" in fases


# ── Teste crítico 5: produto aparente que cai em home não confirma ────

def test_critico_5_produto_aparente_que_redireciona_home(monkeypatch):
    db = _db()
    cand = {"titulo": "Notebook Asus Vivobook Go 15 — Loja X", "trecho": "",
            "url": "https://lojax.com.br/produto/"
                   "notebook-asus-vivobook-go-15"}
    home = ("<html><head><title>Loja X — Página inicial</title></head>"
            "<body><h1>Bem-vindo à Loja X</h1></body></html>")
    res = shopping.pesquisar(
        db, "ana", "notebook asus vivobook", "c5",
        buscar_fn=lambda q: [dict(cand)],
        baixar_fn=lambda url: {"final": "https://lojax.com.br/",
                               "texto": home})
    assert res["produtos"] == []
    assert shopping.fence_resultado(res) == ""


# ── Teste crítico 6: marca/orçamento não são correspondência exata ────

def test_critico_6_marca_orcamento_nao_e_correspondencia(monkeypatch):
    crit = shopping.extrair_criterios("notebook samsung até R$ 3000")
    p1 = _produto(id="s1", nome="Notebook Samsung Galaxy Book4",
                  marca="Samsung", preco=4500.0,
                  preco_texto="R$ 4.500,00")
    p2 = _produto(id="s2", nome="Notebook Positivo Vision 15",
                  marca="Positivo", preco=2500.0,
                  preco_texto="R$ 2.500,00")
    dentro, fora = shopping.aplicar_filtros([p1, p2], crit)
    assert dentro == []
    assert len(fora) == 2
    por_id = {p["id"]: p for p in fora}
    assert "preco_acima" in por_id["s1"]["excluido_codigos"]
    assert any(c.startswith("marca")
               for c in por_id["s2"]["excluido_codigos"])
    alt = shopping.separar_alternativas(fora, crit)
    assert not any(a.get("id") == "s1" for a in alt)


# ── Teste crítico 7: 2ª onda recupera candidatos válidos ──────────────

def test_critico_7_segunda_onda_recupera_candidatos(monkeypatch):
    db = _db()
    letras = "abcdefgh"
    cands = [{"titulo": f"Tênis de Basquete Modelo {c.upper()} — Loja Y",
              "trecho": "tenis basquete",
              "url": f"https://lojay.com.br/produto/tenis-basquete-{c}"}
             for c in letras]
    bloqueadas = {c["url"] for c in cands[:6]}

    def _baixar(url):
        if url in bloqueadas:
            raise research.ResearchErro("Provedor bloqueou (403).",
                                        "bloqueado")
        nome = f"Tênis de Basquete {url[-1].upper()} Pro"
        return {"final": url, "texto": _pagina_produto(nome, url=url)}

    fases = []
    res = shopping.pesquisar(
        db, "ana", "me mostre tenis para jogar basquete", "c7",
        buscar_fn=lambda q: [dict(c) for c in cands],
        baixar_fn=_baixar,
        progresso=lambda fase, detalhe="": fases.append(fase))

    assert len(res["produtos"]) == 2, "2ª onda deveria achar g/h"
    assert "recuperando" in fases
    assert (res["descoberta"] or {}).get("ondas") == 2


# ── Teste crítico 8: falhas de provedor, estados honestos ─────────────

def test_critico_8_falhas_provedores_estados_honestos(monkeypatch):
    db = _db()

    def _ddg(q, base=research.DDG_HTML, max_resultados=6, timeout=8.0):
        if base == research.DDG_HTML:
            raise research.ResearchErro("Provedor bloqueou (429).",
                                        "bloqueado")
        raise TimeoutError("tempo esgotado")

    def _web(q, max_resultados=6, timeout=8.0, orcamento=None):
        raise ValueError("erro interno de programação")

    monkeypatch.setattr(shopping, "buscar_mlb", _mlb_falha)
    monkeypatch.setattr(research, "buscar_ddg", _ddg)
    monkeypatch.setattr(research, "_buscar_orquestrado", _web)

    achados, etapas = shopping.buscar_com_fallback("notebook")
    assert achados == []
    assert etapas[0] == "mlb: falhou (ResearchErro)"
    assert any(e.startswith("ddg: falhou (ResearchErro)") for e in etapas)
    # V5.9.1: a blocked DDG host must not be retried via its Lite surface.
    assert not any(e.startswith("ddg-lite:") for e in etapas)
    # Erro interno do web aparece pelo tipo — nunca rotulado como bloqueio.
    assert any(e.startswith("web: falhou (ValueError)") for e in etapas)

    res = shopping.pesquisar(db, "ana", "notebook de teste", "c8")
    assert res["produtos"] == [] and res["erro"] == "provedor_indisponivel"
    assert (res.get("descoberta") or {}).get("motivo_final") \
        == "provider_unavailable"


# ── Classificação de candidatos (unidade) ─────────────────────────────

def test_classificacao_de_candidatos():
    tabela = [
        ("https://duckduckgo.com/y.js?ad_domain=x", "IRRELEVANT"),
        ("javascript:alert(1)", "IRRELEVANT"),
        ("ftp://loja.com/x", "IRRELEVANT"),
        ("", "IRRELEVANT"),
        ("https://duckduckgo.com/duckduckgo-help-pages/company/ads/",
         "GENERIC_INDEX"),
        ("https://www.google.com/search?q=x", "GENERIC_INDEX"),
        ("https://lojax.com.br/", "GENERIC_INDEX"),
        ("https://tecnoblog.net/guias/notebook-para-estudar/",
         "EDITORIAL_REFERENCE"),
        ("https://www.techtudo.com.br/reviews/notebook-barato/",
         "EDITORIAL_REFERENCE"),
        ("https://techinter.com.br/notebooks/notebook-para-estudar/",
         "EDITORIAL_REFERENCE"),
        ("https://melhoresparacomprar.com.br/qual-o-melhor-notebook",
         "EDITORIAL_REFERENCE"),
        ("https://www.kabum.com.br/produto/649861/notebook-asus",
         "PRODUCT_CANDIDATE"),
        ("https://lojax.com.br/produto/notebook-x", "PRODUCT_CANDIDATE"),
        ("https://www.kabum.com.br/computadores/notebooks",
         "COMMERCIAL_LISTING"),
        ("https://lista.mercadolivre.com.br/fone-bluetooth",
         "COMMERCIAL_LISTING"),
        ("https://shopee.com.br/list/Fone-Bluetooth", "COMMERCIAL_LISTING"),
        ("https://loja.claro.com.br/acessorios/fone-de-ouvido",
         "COMMERCIAL_LISTING"),
        ("https://loja.com/p", "COMMERCIAL_LISTING"),
        ("https://megaesportes.com.br/tenis-infantil/junior-2026",
         "UNKNOWN"),
        ("https://dicio.com.br/melhor", "UNKNOWN"),
    ]
    for url, esperado in tabela:
        obtido = shopping.classificar_candidato({"url": url})
        assert obtido == esperado, (url, obtido, esperado)
