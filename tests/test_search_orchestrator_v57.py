"""V5.7 — Search Orchestrator 4.0: reformulação de pergunta e correspondência.

Regressão real coberta (auditoria V5.7, 2026-10-17): a consulta
"como funciona o freio ABS" recebia dicionários da palavra "funciona"
(6/6 do Bing) e era declarada "ok" com correspondência 33%. Causa: o verbo
de pergunta contava como termo de correspondência e bloqueava a recuperação.
"""
import search_orchestrator as orch
import search_providers as sp

ORC = {"max_consultas": 1, "max_provedores": 2, "min_resultados": 1,
       "timeout_total": 5.0, "max_por_provedor": 4}


# ── Correspondência: verbo de pergunta não prova tema ────────────────

def test_termos_correspondencia_ignoram_verbo_de_pergunta():
    assert orch._termos_correspondencia("como funciona o freio ABS") == \
        ["freio", "abs"]
    assert orch._termos_correspondencia("o que faz um sensor de chuva") == \
        ["sensor", "chuva"]


# ── Reformulação conservadora ────────────────────────────────────────

def test_consulta_conteudo_tira_moldura_de_pergunta():
    assert orch.consulta_conteudo("como funciona o freio ABS") == "freio ABS"
    assert orch.consulta_conteudo("o que é fotossíntese") == "fotossíntese"
    assert orch.consulta_conteudo("quanto custa a placa a?") == "placa"
    assert orch.consulta_conteudo(
        "como funciona o motor 1.0 de 3 cilindros") == "motor 1.0 de 3 cilindros"


def test_consulta_conteudo_nunca_inventa():
    assert orch.consulta_conteudo("freio ABS") == ""
    assert orch.consulta_conteudo("qual o melhor preço?") == ""
    assert orch.consulta_conteudo("como funciona") == ""
    assert orch.consulta_conteudo("") == ""
    assert orch.consulta_conteudo("notebook lenovo ideapad 3i") == ""


# ── Junk do índice: reformula na MESMA fonte antes de trocar ─────────

def test_junk_com_verbo_de_pergunta_reformula_na_mesma_fonte(monkeypatch):
    chamadas = []

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append((nome, consulta))
        if "funciona" in consulta.lower():
            return [{"titulo": "Funciona - Dicionário", "url": "https://dicio.example/funciona",
                     "trecho": "conjugação do verbo funciona", "origem": nome, "tipo": "pagina"}]
        return [
            {"titulo": "Freio ABS: o que é e como funciona", "url": "https://auto.example/abs",
             "trecho": "sistema de freio ABS com sensor", "origem": nome, "tipo": "pagina"},
            {"titulo": "Freio ABS — Wikipédia", "url": "https://pt.wikipedia.org/wiki/Freio_ABS",
             "trecho": "freio antibloqueio", "origem": nome, "tipo": "enciclopedia"},
        ]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("como funciona o freio ABS", provedores=["bing"],
                         orcamento=ORC)
    assert ("bing", "freio ABS") in chamadas
    assert any("consulta reformulada" in e for e in res["etapas"])
    assert res["correspondencia"] >= 0.5
    assert res["estado"] in ("ok", "parcial")


# ── Provedor vazio: reformula antes de contar como vazio ─────────────

def test_provedor_vazio_reformula_antes_de_desistir(monkeypatch):
    chamadas = []

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append(consulta)
        if consulta.lower().startswith("o que"):
            raise sp.ErroProvedor("nada para essa consulta", "vazio")
        return [{"titulo": "Fotossíntese — Wikipédia",
                 "url": "https://pt.wikipedia.org/wiki/Fotossintese",
                 "trecho": "a fotossíntese é o processo de conversão", "origem": nome,
                 "tipo": "enciclopedia"}]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("o que é fotossíntese", provedores=["wikipedia"],
                         orcamento=ORC)
    assert any("fotoss" in c.lower() for c in chamadas)
    assert res["provedores"]["vazios"] == []
    assert res["correspondencia"] >= 0.5
    assert res["estado"] in ("ok", "parcial")


# ── Correspondência fraca: enxuta declarada para a recuperação ───────

def test_correspondencia_fraca_declara_enxuta_para_recuperacao(monkeypatch):
    monkeypatch.setattr(sp, "buscar", lambda nome, consulta, limite=6, timeout=10.0:
                        [{"titulo": "Freio motor: o que é", "url": f"https://a.example/{nome}",
                          "trecho": "freio motor ajuda na descida", "origem": nome,
                          "tipo": "pagina"}])
    res = orch.pesquisar("quanto custa o freio ABS hidráulico", provedores=["bing"],
                         orcamento=ORC)
    assert res["correspondencia"] < 0.5
    assert res["recuperacao"] and res["recuperacao"][0] == "freio abs hidráulico"


def test_recuperacao_com_enxuta_melhora_correspondencia_fraca(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        if consulta.lower().startswith("freio abs"):
            return [{"titulo": "Freio ABS hidráulico azul: manual",
                     "url": "https://m.example/abs",
                     "trecho": "freio ABS hidráulico azul automotivo",
                     "origem": nome, "tipo": "pagina"}]
        return [{"titulo": "Freio motor", "url": f"https://a.example/{nome}",
                 "trecho": "freio motor ajuda na descida", "origem": nome,
                 "tipo": "pagina"}]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar_com_recuperacao("preço do freio ABS hidráulico azul",
                                         max_resultados=4, orcamento=ORC)
    assert res["recuperou"] is True
    assert res["correspondencia"] >= 0.5
    urls = [a["url"] for a in res["achados"]]
    assert "https://m.example/abs" in urls


# ── Republicações: mesmo título em domínios distintos ────────────────

def test_republicacao_mesmo_titulo_entre_dominios_e_registrada():
    titulo = "Governo anuncia novo pacote de incentivos para carros elétricos no país"
    a = {"titulo": titulo, "url": "https://portal-a.example/n/pacote",
         "trecho": "primeira versão do texto"}
    b = {"titulo": titulo, "url": "https://portal-b.example/2026/pacote",
         "trecho": "replica"}
    c = {"titulo": "Análise: carros elétricos mudam o mercado em 2026",
         "url": "https://portal-c.example/analise", "trecho": "análise"}
    unicos, descartes = orch.deduplicar([a, b, c])
    assert [u["url"] for u in unicos] == [a["url"], c["url"]]
    assert unicos[0]["republicacoes"] == [b["url"]]
    assert any("republicação de" in d["motivo"] for d in descartes)


def test_titulos_curtos_nao_sao_tratados_como_republicacao():
    a = {"titulo": "Freio ABS", "url": "https://x.example/a", "trecho": ""}
    b = {"titulo": "Freio ABS", "url": "https://y.example/b", "trecho": ""}
    unicos, _ = orch.deduplicar([a, b])
    assert len(unicos) == 2


# ── Conteúdo desatualizado em consultas temporais (V5.7) ─────────────

def test_conteudo_desatualizado_e_sinalizado_nao_apagado(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [
            {"titulo": "Eleições 2026: calendário oficial",
             "url": "https://t.example/novo", "trecho": "calendário do pleito",
             "data": "Fri, 10 Jan 2026 00:00:00 GMT", "origem": "bing",
             "tipo": "noticia"},
            {"titulo": "Eleições 2018: como foi o pleito",
             "url": "https://t.example/velho", "trecho": "retrospecto do pleito",
             "data": "Mon, 01 Jan 2018 00:00:00 GMT", "origem": "bing",
             "tipo": "noticia"},
        ]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("eleições 2026", provedores=["bing"], orcamento=ORC)
    por_url = {a["url"]: a for a in res["achados"]}
    assert por_url["https://t.example/velho"].get("desatualizado") is True
    assert por_url["https://t.example/velho"].get("ano") == 2018
    assert por_url["https://t.example/novo"].get("desatualizado") is False
    assert "https://t.example/velho" in res["desatualizados"]
    assert len(res["achados"]) == 2  # rebaixado, nunca apagado
    assert res["achados"][0]["url"] == "https://t.example/novo"


def test_sem_data_conhecida_nao_acusa_desatualizado(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [{"titulo": "Como votar nas eleições", "url": "https://s.example/a",
                 "trecho": "passo a passo", "origem": "bing", "tipo": "pagina"}]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("eleições 2026", provedores=["bing"], orcamento=ORC)
    assert res["achados"][0].get("desatualizado") is None
    assert res["desatualizados"] == []


def test_consulta_sem_recorte_temporal_nao_marca_nada(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [{"titulo": "Freio ABS: o que é", "url": "https://f.example/a",
                 "trecho": "sistema de freios", "origem": "bing", "tipo": "pagina",
                 "data": "Mon, 01 Jan 2015 00:00:00 GMT"}]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("freio ABS", provedores=["bing"], orcamento=ORC)
    assert res["achados"][0].get("desatualizado") is None
    assert res["desatualizados"] == []


# ── Ganho real de informação (parada honesta, não por quantidade) ────

def test_ganho_informacao_conta_dominio_e_tema_novos():
    itens = [{"titulo": "Freio ABS: como funciona", "url": "https://a.example/x",
              "trecho": "sistema de freios", "origem": "bing", "tipo": "pagina"}]
    g = orch._ganho_informacao({"dominios": set(), "temas": set()},
                               itens, "freio ABS")
    assert g["ganho_real"] is True
    assert g["dominios_novos"] == ["a.example"]
    assert g["temas_novos"] == ["abs", "freio"]
    repetido = orch._ganho_informacao(orch._retrato(itens, "freio ABS"),
                                      itens, "freio ABS")
    assert repetido["ganho_real"] is False
    assert repetido["dominios_novos"] == [] and repetido["temas_novos"] == []


def test_parada_por_ganho_zero_evita_consulta_redundante(monkeypatch):
    chamadas = []

    def _buscar(nome, consulta, limite=6, timeout=10.0):
        chamadas.append((nome, consulta))
        return [{"titulo": "Freio ABS: explicação",
                 "url": f"https://m.example/{len(chamadas)}",
                 "trecho": "sistema de freios abs", "origem": nome,
                 "tipo": "pagina"}]

    monkeypatch.setattr(sp, "buscar", _buscar)
    orc = {"max_consultas": 4, "max_provedores": 3, "min_resultados": 3,
           "timeout_total": 5.0, "max_por_provedor": 4}
    res = orch.pesquisar("freio ABS", provedores=["bing", "marginalia", "wikipedia"],
                         orcamento=orc,
                         extra_queries=["freio ABS sistema", "freio ABS valores"])
    # a 2ª consulta repetiu domínio e tema: a 3ª nem roda
    assert len(chamadas) == 2
    assert len(res["consultas"]) == 2
    assert any("parada por ganho zero" in e for e in res["etapas"])
    assert len(res["achados"]) == 2  # nada é apagado, só se para de insistir


def _recuperacao_falsa(base_achado, extra_achado):
    base = {"achados": [dict(base_achado)], "etapas": ["bing: 1 resultados"],
            "estado": "parcial", "estado_texto": "parcial", "provedores": {},
            "classes": [], "temporal": False, "desatualizados": [],
            "lacunas": ["valores"], "consultas": ["freio ABS"],
            "recuperacao": ["freio ABS valores"], "descartes": [],
            "correspondencia": 0.4, "segundos": 0.1}
    extra = {"achados": [dict(extra_achado)], "etapas": ["bing: 1 resultados"],
             "descartes": [], "lacunas": [], "segundos": 0.1}
    chamadas = []

    def falso(consulta, **kw):
        chamadas.append(consulta)
        return dict(base) if len(chamadas) == 1 else dict(extra)

    return falso


def test_recuperacao_sem_ganho_novo_e_declarada(monkeypatch):
    item = {"titulo": "Freio ABS funciona", "url": "https://m.example/a",
            "trecho": "freio abs", "origem": "bing", "tipo": "pagina"}
    monkeypatch.setattr(orch, "pesquisar",
                        _recuperacao_falsa(item, dict(item, url="https://m.example/b")))
    res = orch.pesquisar_com_recuperacao("freio ABS")
    assert res["recuperou"] is True
    assert res["ganho_informacao"]["ganho_real"] is False
    assert res["ganho_informacao"]["dominios_novos"] == []
    assert any("recuperação sem ganho novo" in e for e in res["etapas"])


def test_recuperacao_com_ganho_novo_e_declarada(monkeypatch):
    item = {"titulo": "Freio ABS funciona", "url": "https://m.example/a",
            "trecho": "freio abs", "origem": "bing", "tipo": "pagina"}
    novo = {"titulo": "Freio ABS: guia novo", "url": "https://n.example/c",
            "trecho": "freio abs", "origem": "bing", "tipo": "pagina"}
    monkeypatch.setattr(orch, "pesquisar", _recuperacao_falsa(item, novo))
    res = orch.pesquisar_com_recuperacao("freio ABS")
    assert res["recuperou"] is True
    assert res["ganho_informacao"]["ganho_real"] is True
    assert res["ganho_informacao"]["dominios_novos"] == ["n.example"]
    assert any("recuperação com ganho novo" in e for e in res["etapas"])


# ── Índice geral: reclassificação e recuperação dirigida ─────────────

def test_paginas_de_indice_sao_sinalizadas_e_demovidas(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [
            {"titulo": "Resultados para freio ABS",
             "url": "https://m.example/search?q=freio+abs",
             "trecho": "freio abs resultados", "origem": "bing",
             "tipo": "pagina"},
            {"titulo": "Freio ABS: como funciona",
             "url": "https://n.example/guia",
             "trecho": "freio abs sistema", "origem": "bing",
             "tipo": "pagina"},
        ]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("freio ABS", provedores=["bing"], orcamento=ORC)
    por_url = {a["url"]: a for a in res["achados"]}
    assert por_url["https://m.example/search?q=freio+abs"].get("pagina_de_indice") is True
    assert por_url["https://n.example/guia"].get("pagina_de_indice") is None
    assert res["achados"][0]["url"] == "https://n.example/guia"  # conteúdo vence
    assert res["indice_geral"] == ["https://m.example/search?q=freio+abs"]
    assert len(res["achados"]) == 2  # demovida, nunca apagada


def test_rodada_so_com_indices_gera_lacuna_e_consulta_de_recuperacao(monkeypatch):
    def _buscar(nome, consulta, limite=6, timeout=10.0):
        return [
            {"titulo": "Resultados para freio ABS",
             "url": "https://m.example/search?q=freio",
             "trecho": "freio abs resultados", "origem": "bing",
             "tipo": "pagina"},
            {"titulo": "Índice de conteúdos de freios",
             "url": "https://m.example/indice",
             "trecho": "freio abs índice", "origem": "bing",
             "tipo": "pagina"},
        ]

    monkeypatch.setattr(sp, "buscar", _buscar)
    res = orch.pesquisar("como funciona o freio ABS",
                         provedores=["bing"], orcamento=ORC)
    assert any("índice geral" in lac for lac in res["lacunas"])
    assert any("freio abs" in q for q in res["recuperacao"])
    assert any("só com páginas de índice" in e for e in res["etapas"])
