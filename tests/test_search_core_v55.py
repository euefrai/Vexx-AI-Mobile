"""V5.5 Search core: provedores e orquestrador com fixtures CONGELADOS.

Sem rede: `_baixar`/`sp.buscar`/`pesquisar_com_recuperacao` são substituídos
por respostas fixas. Critérios objetivos, reprodutíveis em qualquer máquina:
estados honestos, números do pedido intactos, dedupe canônico, lacunas reais.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import search_orchestrator as orch
import search_providers as sp
import web_extract


def _sem_rede(url, timeout, *a, **k):
    raise AssertionError("fixture deveria evitar a rede: " + str(url))


# ── Fixtures congelados (RSS/HTML reais, sem rede) ───────────────────

RSS_BING = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Review Placa A: consumo medido</title>
<link>https://lab-a.example/review-placa-a</link>
<description>Medimos 65 W em jogos na Placa A em 2024.</description>
<pubDate>Mon, 03 Jun 2024 10:00:00 GMT</pubDate></item>
<item><title>Página do Bing (ruído interno)</title>
<link>https://www.bing.com/search?q=ruido</link>
<description>não é fonte</description></item>
<item><title>Blog B sobre a Placa A</title>
<link>https://blog-b.example/placa-a</link>
<description>Testes indicam 95 W.</description></item>
</channel></rss>
"""

RSS_BING_VAZIO = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Página do Bing</title>
<link>https://www.bing.com/search?q=x</link><description>ruído</description></item>
</channel></rss>
"""

PAGINA_BLOQUEIO = ("<html><body><h1>Please complete the following challenge "
                   "to continue</h1></body></html>")

PAGINA_MARGINALIA = """<html><body><main>
<a href="https://old-search.marginalia.nu/about">About Marginalia</a>
<a href="https://indice.example/tema">https://indice.example/tema</a>
<a href="https://bom.example/artigo">Artigo útil sobre o tema pesquisado</a>
<a href="https://bom.example/artigo">Artigo útil sobre o tema pesquisado</a>
<a href="https://curto.example/x">abc</a>
<a href="https://outro.example/nota">Nota técnica do laboratório</a>
</main></body></html>"""

PAGINA_ARTIGO = """<html lang="pt-BR"><head>
<title>Review Placa A — Lab A</title>
<meta property="og:title" content="Review Placa A">
<meta property="og:site_name" content="Lab A">
<script type="application/ld+json">{"@context":"https://schema.org",
"@type":"Article","headline":"Review Placa A","datePublished":"2024-06-03",
"author":{"@type":"Person","name":"Ana Testes"}}</script>
</head><body><nav>menu</nav>
<article><h1>Review da Placa A</h1>
<p>A Placa A é uma GPU lançada em 2024.</p>
<p>Medimos o consumo: 65 W em jogos e 20 W em idle.</p>
<table><tr><th>Métrica</th><th>Valor</th></tr>
<tr><td>Consumo</td><td>65 W</td></tr></table>
<p><a href="/fonte">Fonte dos testes</a></p></article>
<footer>rodapé</footer></body></html>"""


# ── Provedores: parsers com fixtures congelados ──────────────────────

def test_buscar_bing_rss_congelado(monkeypatch):
    chamadas = []

    def _baixar(url, timeout, aceitar="texto", max_bytes=sp.MAX_BYTES):
        chamadas.append((url, aceitar))
        return ("https://www.bing.com/search", RSS_BING)

    monkeypatch.setattr(sp, "_baixar", _baixar)
    achados = sp.buscar_bing("consumo placa a", limite=5)
    assert [a["url"] for a in achados] == ["https://lab-a.example/review-placa-a",
                                           "https://blog-b.example/placa-a"]
    assert achados[0]["origem"] == "bing" and achados[0]["tipo"] == "pagina"
    assert "65 W" in achados[0]["trecho"]
    assert achados[0]["meta"]["publicado_em"].startswith("Mon, 03 Jun 2024")
    assert chamadas and chamadas[0][1] == "feed"  # aceita feed oficial, não HTML


def test_buscar_bing_news_marca_noticia(monkeypatch):
    urls = []

    def _baixar(url, timeout, aceitar="texto", max_bytes=sp.MAX_BYTES):
        urls.append(url)
        return (url, RSS_BING)

    monkeypatch.setattr(sp, "_baixar", _baixar)
    achados = sp.buscar_bing_news("placa a", limite=3)
    assert "/news/search?" in urls[0]
    assert achados[0]["origem"] == "bing-news" and achados[0]["tipo"] == "noticia"


def test_buscar_bing_bloqueio_sem_bypass(monkeypatch):
    monkeypatch.setattr(sp, "_baixar",
                        lambda url, timeout, *a, **k: (url, PAGINA_BLOQUEIO))
    with pytest.raises(sp.ErroProvedor) as exc:
        sp.buscar_bing("qualquer")
    assert exc.value.codigo == "bloqueado"


def test_buscar_bing_vazio_declarado(monkeypatch):
    monkeypatch.setattr(sp, "_baixar",
                        lambda url, timeout, *a, **k: (url, RSS_BING_VAZIO))
    with pytest.raises(sp.ErroProvedor) as exc:
        sp.buscar_bing("sem fontes")
    assert exc.value.codigo == "vazio"


def test_buscar_marginalia_filtra_ruido_e_duplicata(monkeypatch):
    monkeypatch.setattr(sp, "_baixar",
                        lambda url, timeout, *a, **k: (url, PAGINA_MARGINALIA))
    achados = sp.buscar_marginalia("tema pesquisado", limite=5)
    assert [a["url"] for a in achados] == ["https://bom.example/artigo",
                                           "https://outro.example/nota"]
    assert all(a["origem"] == "marginalia" and a["trecho"] == "" for a in achados)


# ── Orquestrador: variantes nunca mudam o pedido ─────────────────────

def test_variantes_preservam_numeros_e_orcamento():
    consulta = "notebook gamer até R$ 3000 com 16gb de ram"
    vs = orch.variantes(consulta, [sp.CLASSE_GERAL], teto=3)
    assert vs and all("3000" in v for v in vs) and all("16gb" in v.lower() for v in vs)
    assert vs[0] == consulta


def test_variantes_produto_sem_expansao_por_classe():
    vs = orch.variantes("notebook gamer até R$ 3000", [sp.CLASSE_TECNICA],
                        teto=3, produto=True)
    assert vs[0] == "notebook gamer até R$ 3000"
    assert all("documentação" not in v for v in vs)


def test_termos_para_provedor_tecnico_em_ingles():
    assert orch.termos_para_provedor("memória ram e erro de rede",
                                     sp.CLASSE_TECNICA) == "memory ram e error de network"
    assert orch.termos_para_provedor("qualquer", sp.CLASSE_GERAL) == "qualquer"


# ── Dedupe canônico e ranking ────────────────────────────────────────

def test_deduplicar_tracking_www_e_mescla_de_trecho():
    a1 = {"titulo": "A", "url": "https://www.exemplo.com/p/1?utm_source=x&gclid=1",
          "trecho": "curto"}
    a2 = {"titulo": "A", "url": "https://exemplo.com/p/1",
          "trecho": "trecho bem mais longo e aproveitável"}
    a3 = {"titulo": "B", "url": "https://exemplo.com/p/2", "trecho": "ok"}
    ruim = {"titulo": "C", "url": "sem-esquema"}
    unicos, descartes = orch.deduplicar([a1, a2, a3, ruim])
    assert [a["url"] for a in unicos] == [
        "https://www.exemplo.com/p/1?utm_source=x&gclid=1", "https://exemplo.com/p/2"]
    assert unicos[0]["trecho"] == "trecho bem mais longo e aproveitável"
    motivos = [d["motivo"] for d in descartes]
    assert any("duplicada de" in m for m in motivos)
    assert "url inválida" in motivos
    rank = orch.ranquear([{"titulo": "Placa A em jogos: 65 W", "trecho": "",
                           "url": "https://lab-a.example/x", "origem": "bing"}],
                         "consumo placa a em jogos", [sp.CLASSE_TECNICA],
                         {"temporal": False})
    assert rank and rank[0]["relevancia"] > 0


# ── Lacunas do pedido e consultas de recuperação ─────────────────────

def test_lacunas_numeros_e_recuperacao_sem_mexer_no_pedido():
    consulta = "quanto custa o notebook gamer até R$ 3000?"
    info = orch.classificar(consulta)
    assert info["produto"] is True
    achados = [{"titulo": "Notebook gamer barato", "trecho": "sem valores na fonte",
                "url": "https://loja.example/n", "tipo": "pagina", "origem": "bing"}]
    lacunas = orch.detectar_lacunas(consulta, achados, info["classes"], info)
    assert any("números" in l for l in lacunas)
    recs = orch._consultas_recuperacao(consulta, info["classes"], info, lacunas)
    assert recs and all("valor preço número" in r for r in recs)
    assert all("3000" in r for r in recs)  # orçamento do pedido intacto


def test_lacunas_com_achados_de_noticia_seguem_honestas():
    info = orch.classificar("últimas notícias sobre vacinas")
    assert sp.CLASSE_NOTICIA in info["classes"] or sp.CLASSE_SAUDE in info["classes"]
    lacunas = orch.detectar_lacunas("últimas notícias sobre vacinas",
                                    [{"titulo": "Portal", "trecho": "texto",
                                      "url": "https://p.example/x", "tipo": "academico"}],
                                    info["classes"], info)
    assert any("notícia" in l for l in lacunas)


# ── Escolha de provedores e estados honestos ─────────────────────────

def test_escolher_provedores_por_classe():
    disponiveis = ["bing", "marginalia", "wikipedia", "pubmed", "stackexchange",
                   "hn", "openlibrary", "worldbank", "bcb", "commons", "bing-news"]
    prod = orch._escolher_provedores([sp.CLASSE_GERAL], {"produto": True},
                                     disponiveis=disponiveis)
    assert prod[:2] == ["bing", "marginalia"]
    acad = orch._escolher_provedores([sp.CLASSE_ACADEMICA], {"produto": False},
                                     disponiveis=disponiveis)
    assert acad[:3] == ["pubmed", "openlibrary", "wikipedia"]
    tec = orch._escolher_provedores([sp.CLASSE_TECNICA], {"produto": False},
                                    disponiveis=disponiveis)
    assert tec[:2] == ["stackexchange", "hn"]


ACHADOS_OK = [
    {"titulo": "Review Placa A: consumo em jogos", "url": "https://lab-a.example/r",
     "trecho": "Medimos 65 W em jogos na Placa A.", "origem": "bing", "tipo": "tecnico"},
    {"titulo": "Placa A: testes de consumo", "url": "https://lab-b.example/t",
     "trecho": "Consumo de 95 W na Placa A em jogos.", "origem": "marginalia",
     "tipo": "pagina"},
]


def _orcamento_1():
    return {"max_consultas": 1, "max_provedores": 2, "min_resultados": 3,
            "timeout_total": 10.0}


def test_pesquisar_estado_ok_com_fixture(monkeypatch):
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0:
                        [dict(a) for a in ACHADOS_OK])
    res = orch.pesquisar("consumo da placa a em jogos", provedores=["bing", "marginalia"],
                         orcamento=_orcamento_1())
    assert res["estado"] == "ok" and res["correspondencia"] >= 0.5
    assert [a["url"] for a in res["achados"]] == [a["url"] for a in ACHADOS_OK]
    assert res["provedores"]["usados"] == {"bing": 1}
    assert res["consultas"] == ["consumo da placa a em jogos"]
    assert any(e.startswith("bing: 2 resultados") for e in res["etapas"])


def test_pesquisar_estado_bloqueado(monkeypatch):
    def _falha(nome, consulta, limite=6, timeout=10.0):
        raise sp.ErroProvedor("bot-wall", "bloqueado")

    monkeypatch.setattr(sp, "buscar", _falha)
    res = orch.pesquisar("qualquer tema", provedores=["bing", "marginalia"],
                         orcamento=_orcamento_1())
    assert res["estado"] == "bloqueado" and res["achados"] == []
    assert {f["codigo"] for f in res["provedores"]["falhas"]} == {"bloqueado"}
    assert res["estado_texto"] == research.ESTADO_TEXTO["bloqueado"]


def test_pesquisar_estado_rede_e_sem_resultados(monkeypatch):
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0:
                        (_ for _ in ()).throw(sp.ErroProvedor("caiu", "rede")))
    res = orch.pesquisar("tema", provedores=["bing"], orcamento=_orcamento_1())
    assert res["estado"] == "rede"
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0: [])
    res2 = orch.pesquisar("tema", provedores=["bing"], orcamento=_orcamento_1())
    assert res2["estado"] == "sem_resultados" and res2["provedores"]["vazios"] == []


def test_pesquisar_sem_correspondencia_nao_finge(monkeypatch):
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0:
                        [{"titulo": "Receita de bolo", "url": "https://cozinha.example/b",
                          "trecho": "modo de preparo", "origem": "bing", "tipo": "pagina"}])
    res = orch.pesquisar("consumo da placa a em jogos", provedores=["bing"],
                         orcamento=_orcamento_1())
    assert res["achados"] and res["correspondencia"] <= 0.15
    assert res["estado"] == "sem_correspondencia"


# ── Correspondência sem genéricos + resgate de provedor (junk do índice) ──

JUNK_BING = {"titulo": "Receita de bolo", "url": "https://cozinha.example/b",
             "trecho": "modo de preparo", "origem": "bing", "tipo": "pagina"}


def test_termos_correspondencia_ignoram_genericos_de_loja():
    # genéricos ("preço", "até", "R$") não provam correspondência
    assert orch._termos_correspondencia("preço fone bluetooth até R$ 500") == \
        ["fone", "bluetooth", "500"]
    assert orch._termos_correspondencia("qual o melhor preço?") == []
    termos = orch._termos_correspondencia("preço fone bluetooth até R$ 500")
    generico = {"titulo": "Entrega em até 2h — compare preços, ganhe cashback",
                "trecho": "Melhor preço, ofertas e promoções em São Paulo"}
    real = {"titulo": "Fone Bluetooth JBL por R$ 500",
            "trecho": "Fone de ouvido bluetooth com preço verificado"}
    assert orch._util_para_pedido(generico, termos) is False
    assert orch._util_para_pedido(real, termos) is True
    assert orch._util_para_pedido(generico, []) is True  # sem termos: indefinível


def test_pesquisar_junk_nao_encerra_e_tenta_proximo_provedor(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        if nome == "bing":
            return [dict(JUNK_BING)]
        return [dict(a) for a in ACHADOS_OK]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("consumo da placa a em jogos",
                         provedores=["bing", "marginalia"], orcamento=_orcamento_1())
    assert res["estado"] == "ok" and res["correspondencia"] >= 0.5
    assert res["provedores"]["usados"] == {"bing": 1, "marginalia": 1}
    assert any("sem correspondência com o pedido" in e for e in res["etapas"])
    urls = [a["url"] for a in res["achados"]]
    assert "https://cozinha.example/b" in urls  # lixo registrado, nunca apagado
    assert all(a["url"] in urls for a in ACHADOS_OK)


def test_pesquisar_junk_em_todos_os_provedores_vira_sem_correspondencia(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [dict(JUNK_BING, origem=nome, url=f"https://cozinha.example/{nome}")]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("consumo da placa a em jogos",
                         provedores=["bing", "marginalia"], orcamento=_orcamento_1())
    assert res["estado"] == "sem_correspondencia"
    assert res["provedores"]["usados"] == {"bing": 1, "marginalia": 1}
    assert res["achados"]  # nada é apagado; só não se finge correspondência


def test_recuperacao_tambem_junk_nao_vira_ok(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [dict(JUNK_BING)]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("quanto custa a placa a?",
                                         max_resultados=4, orcamento=_orcamento_1())
    assert res["recuperou"] is True
    assert res["estado"] == "sem_correspondencia"  # recuperação não "conserta"


def test_sem_correspondencia_declara_consulta_enxuta(monkeypatch):
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0:
                        [dict(JUNK_BING, origem=nome)])
    res = orch.pesquisar("preço fone bluetooth até R$ 500", provedores=["bing"],
                         orcamento=_orcamento_1())
    assert res["estado"] == "sem_correspondencia"
    # enxuta = só os termos distintivos do pedido, sem genéricos; número intacto
    assert res["recuperacao"][0] == "fone bluetooth 500"


def test_recuperacao_enxuta_acha_o_que_o_indice_devolveu_como_lixo(monkeypatch):
    chamadas = []
    REAIS = [
        {"titulo": "Fones de Ouvido KaBuM!: Ofertas de até 15% OFF",
         "url": "https://kabum.example/fones",
         "trecho": "fone de ouvido bluetooth por R$ 500", "tipo": "pagina"},
        {"titulo": "Fone Bluetooth JBL por R$ 500",
         "url": "https://loja.example/fone",
         "trecho": "fone bluetooth 500 reais com garantia", "tipo": "pagina"},
    ]

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append(consulta)
        if "preço" in consulta.lower():
            return [dict(JUNK_BING, origem=nome, url=f"https://cozinha.example/{nome}")]
        return [dict(a, origem=nome) for a in REAIS]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("preço fone bluetooth até R$ 500",
                                         max_resultados=6, orcamento=_orcamento_1())
    assert "fone bluetooth 500" in chamadas  # rodada de recuperação usou a enxuta
    assert res["recuperou"] is True and res["estado"] == "ok"
    assert res["correspondencia"] >= 0.5
    urls = [a["url"] for a in res["achados"]]
    assert all(a["url"] in urls for a in REAIS)  # resultado real entra
    assert "https://cozinha.example/bing" in urls  # e o lixo segue registrado


# ── Recuperação por lacuna (uma rodada, honesta) ─────────────────────

R1 = {"titulo": "Fonte um sobre a placa a", "url": "https://f1.example/a",
      "trecho": "sem números ainda", "origem": "bing", "tipo": "pagina"}
R2 = {"titulo": "Fonte dois com valores", "url": "https://f2.example/b",
      "trecho": "valor de R$ 1.200 em 2026", "origem": "bing", "tipo": "dados"}
R3 = {"titulo": "Fonte três complementar", "url": "https://f3.example/c",
      "trecho": "dados oficiais de 2026", "origem": "bing", "tipo": "dados"}


def test_recuperacao_roda_uma_rodada_por_lacuna(monkeypatch):
    chamadas = []

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append(consulta)
        if "valor preço número" in consulta:
            return [dict(R1), dict(R2), dict(R3)]
        return [dict(R1)]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("quanto custa a placa a?", max_resultados=4,
                                         orcamento=_orcamento_1())
    assert res["recuperou"] is True
    assert "— recuperação por lacuna —" in res["etapas"]
    assert len(res["achados"]) == 3
    assert res["estado"] == "ok"
    assert any("valor preço número" in c for c in chamadas)
    assert all("quanto custa a placa a?" in c for c in chamadas)


def test_recuperacao_adiada_quando_tempo_curto(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [dict(R1)]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("quanto custa a placa a?", max_resultados=4,
                                         orcamento=_orcamento_1(), limite_primeira=-1.0)
    assert res["recuperou"] is False
    assert "recuperacao_adiada" in res and res["lacunas"]


def test_recuperacao_nao_roda_sem_lacunas(monkeypatch):
    chamadas = []

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append(consulta)
        return [dict(a) for a in ACHADOS_OK]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("consumo da placa a em jogos", max_resultados=4,
                                         orcamento=_orcamento_1())
    assert res["recuperou"] is False and "recuperação_adicional" not in res
    assert chamadas == ["consumo da placa a em jogos"]  # sem rodada extra


# ── research._buscar_orquestrado: info real e status por provedor ────

def test_buscar_orquestrado_info_e_status(monkeypatch):
    capturado = {}

    def _fake(consulta, *, max_resultados=6, timeout=8.0, orcamento=None,
              limite_primeira=None):
        capturado.update({"consulta": consulta, "max_resultados": max_resultados,
                          "timeout": timeout, "orcamento": dict(orcamento or {}),
                          "limite_primeira": limite_primeira})
        return {"achados": [dict(ACHADOS_OK[0]),
                            {**ACHADOS_OK[1], "origem": "bing"}],
                "estado": "parcial", "estado_texto": "poucas fontes",
                "provedores": {"usados": {"bing": 2},
                               "falhas": [{"provedor": "marginalia", "codigo": "bloqueado"}],
                               "vazios": []},
                "lacunas": ["sem fonte acadêmica"], "recuperacao": ["estudo artigo"],
                "consultas": ["q"], "descartes": [], "correspondencia": 0.5,
                "etapas": ["bing: 2 resultados"]}

    monkeypatch.setattr(orch, "pesquisar_com_recuperacao", _fake)
    achados, info = research._buscar_orquestrado("q de teste", max_resultados=4,
                                                 orcamento={"max_consultas": 1})
    assert [a["url"] for a in achados] == [a["url"] for a in ACHADOS_OK]
    assert info["estado"] == "parcial" and info["recuperacao"] == ["estudo artigo"]
    assert info["lacunas"] == ["sem fonte acadêmica"]
    assert capturado["orcamento"]["max_consultas"] == 1
    assert capturado["orcamento"]["timeout_total"] == research.ORCAMENTO_RAPIDA["timeout_total"]
    assert capturado["limite_primeira"] == research.LIMITE_RECUPERACAO_S
    assert research.status_provedor("bing")["resultados"] == 2
    assert research.status_provedor("marginalia")["bloqueado"] is True


# ── Extração de página: fixture de artigo congelado ──────────────────

def test_extrair_pagina_artigo_congelado():
    ext = web_extract.extrair_pagina(PAGINA_ARTIGO, "https://lab-a.example/review",
                                     consulta="consumo da placa a")
    assert "Review Placa A" in ext["titulo"]
    assert "65 W" in ext["texto"] and ext["tamanho_html"] > 100
    assert ext["metadados"]["publicado_em"].startswith("2024-06-03")
    assert ext["metadados"]["autor"] == "Ana Testes"
    assert ext["metadados"]["idioma"].startswith("pt")
    assert ["Métrica", "Valor"] in ext["tabelas"][0]
    assert any(l["url"] == "https://lab-a.example/fonte" and l["interno"]
               for l in ext["links"])
    assert "65 W" in ext["trecho_usado"]
    assert ext["ilegivel"] is False


def test_extrair_pagina_ilegivel_e_sem_metadados():
    ext = web_extract.extrair_pagina("<html><body>\x00\x01\x02 binário</body></html>")
    assert ext["ilegivel"] is True
    assert ext["metadados"]["publicado_em"] == ""
