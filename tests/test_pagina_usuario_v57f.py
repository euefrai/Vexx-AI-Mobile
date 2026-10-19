"""V5.7 FINAL — página específica pedida pelo usuário (URL na mensagem).

"Analise esta página/resuma este link: URL" passa a ler UMA página com o
mesmo `baixar` de qualquer recuperação (SSRF/redirect/tamanho/tipo) e a
colocar o conteúdo real no prompt; bloqueio/ilegível vira aviso honesto,
sem fonte e sem conteúdo inventado. Link citado de passagem não abre, e um
pedido de pesquisa explícito continua como pesquisa.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research


@pytest.fixture(autouse=True)
def _sem_dns(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "pu57f.sqlite3")


def _cfg():
    return {"proxy": "http://127.0.0.1:9/v1", "model": "m", "system": "BASE",
            "context": 12, "max_tokens": 500, "memoria_global": True,
            "pesquisa_web": True}


_MARCADOR = "MARCADOR-PAGINA-V57F"
_URL = "https://exemplo.com/relatorio"


def _html():
    return ('<html><head><title>Relatório de campo</title></head><body><article><p>'
            + "Texto introdutório do relatório com informações úteis para a análise. " * 10
            + f"{_MARCADOR} aparece no corpo do documento e resume o resultado. "
            + "Conteúdo adicional com detalhes medidos em campo, tabelas e conclusões. " * 20
            + "</p></article></body></html>")


class _Spy:
    def __init__(self):
        self.chamadas = []

    def __call__(self, *a, **k):
        self.chamadas.append((a, k))
        return {"fontes": [], "etapas": ["(spy)"], "divergencias": [],
                "de_cache": False, "estado": "sem_resultados"}


# ── detecção ─────────────────────────────────────────────────────────

def test_url_pedida_conservadora():
    assert research.url_pedida("analise esta página: " + _URL) == _URL
    assert research.url_pedida("resuma este link: " + _URL) == _URL
    assert research.url_pedida(_URL) == _URL
    assert research.url_pedida("veja: " + _URL + ".") == _URL  # pontuação final sai
    # menção de passagem / pedido de pesquisa não abrem a página
    assert research.url_pedida(
        "achei essa referência em " + _URL + " ontem, o que acha de energia solar?") == ""
    assert research.url_pedida("pesquise sobre energia solar e veja " + _URL) == ""
    assert research.url_pedida("bom dia, tudo bem por aí?") == ""


def test_consulta_limpa_tira_pedido_e_abre_a_url():
    limpa = research._consulta_limpa(
        "analise esta página para mim: https://pt.wikipedia.org/wiki/Fotoss%C3%ADntese")
    assert "fotossíntese" in limpa
    assert "página" not in limpa and "analise" not in limpa


def test_analisar_url_lida_e_falhas(monkeypatch):
    monkeypatch.setattr(research, "baixar",
                        lambda u, timeout=10.0, **k: (u, _html()))
    fonte, erro = research.analisar_url(_URL, consulta="relatório")
    assert erro == "" and fonte and fonte["status"] == "aberta"
    assert _MARCADOR in fonte["texto_lido"]
    assert fonte["url"] == _URL

    def bloqueia(u, timeout=10.0, **k):
        raise research.ResearchErro("Proibido (403).", "bloqueado")

    monkeypatch.setattr(research, "baixar", bloqueia)
    fonte2, erro2 = research.analisar_url(_URL)
    assert fonte2 is None and erro2 == "bloqueado"

    monkeypatch.setattr(
        research, "baixar",
        lambda u, timeout=10.0, **k: (u, "<html><body><script>x()</script></body></html>"))
    fonte3, erro3 = research.analisar_url(_URL)
    assert fonte3 is None and erro3 == "ilegivel"


def test_bloco_pagina_usuario_honesto():
    b = research.bloco_pagina_usuario(_URL, "bloqueado")
    assert _URL in b and "não são contornados" in b and "sem inventar" in b
    b2 = research.bloco_pagina_usuario(_URL, "rede")
    assert _URL in b2 and "rede" in b2


# ── integração com a montagem do prompt ──────────────────────────────

def test_prompt_traz_pagina_lida(monkeypatch):
    db = _db()
    spy = _Spy()
    monkeypatch.setattr(research, "baixar", lambda u, timeout=10.0, **k: (u, _html()))
    monkeypatch.setattr(research, "pesquisa_rapida", spy)
    monkeypatch.setattr(research, "pesquisa_aprofundada", spy)
    msgs, extras = pc_agent.ai_montar_mensagens(
        db, "conv-p1", _cfg(), "analise esta página para mim: " + _URL)
    sistema = msgs[0]["content"]
    assert extras.get("pagina_usuario") == _URL
    assert extras.get("fontes") and extras["fontes"][0]["url"] == _URL
    assert _MARCADOR in sistema and _URL in sistema
    assert spy.chamadas == []  # não dispara busca genérica por cima
    db.close()


def test_prompt_bloqueio_honesto(monkeypatch):
    db = _db()

    def bloqueia(u, timeout=10.0, **k):
        raise research.ResearchErro("Proibido (403).", "bloqueado")

    spy = _Spy()
    monkeypatch.setattr(research, "baixar", bloqueia)
    monkeypatch.setattr(research, "pesquisa_rapida", spy)
    monkeypatch.setattr(research, "pesquisa_aprofundada", spy)
    msgs, extras = pc_agent.ai_montar_mensagens(
        db, "conv-p2", _cfg(), "resuma esta página: " + _URL)
    sistema = msgs[0]["content"]
    assert extras.get("pagina_usuario") == _URL
    assert not extras.get("fontes")
    assert _URL in sistema and "não são contornados" in sistema
    assert spy.chamadas == []
    db.close()
