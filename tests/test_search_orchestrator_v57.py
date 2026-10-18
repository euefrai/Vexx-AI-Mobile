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
