"""V5.0.1 Research Recovery: fallback, bloqueios, digest sem LLM, E2E."""
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research
import research_agents


def _db(nome="rec501.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


class _Resp:
    def __init__(self, corpo=b"", status=200, ctype="text/html", length=None):
        self._corpo = corpo
        self.status = status
        self._ctype = ctype
        self._length = length
        self.headers = self

    def get_content_type(self):
        return self._ctype

    def get_content_charset(self):
        return "utf-8"

    def get(self, k, d=""):
        if k == "Content-Length":
            return self._length if self._length is not None else len(self._corpo)
        if k == "Content-Type":
            return self._ctype
        return d

    def read(self, n=-1):
        return self._corpo if n is None or n < 0 else self._corpo[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


DDG_BOTWALL = "<html><head></head><body><p>challenge</p></body></html>"
DDG_OK = ('<html><body><a class="result__a" href="https://exemplo.com/a">Artigo A</a>'
          '<div class="result__snippet">trecho sobre o tema</div></body></html>')
WIKI_JSON = json.dumps(["q", ["Python"], ["linguagem de programação"],
                        ["https://pt.wikipedia.org/wiki/Python"]])
PAG_WIKI = ("<html><head><title>Python</title></head><body><nav>menu</nav>"
            "<header>topo</header><p>Python é uma linguagem de programação.</p></body></html>")


def _abrir(url, timeout=10.0):
    if "bloqueio" in url:
        return _Resp(DDG_BOTWALL.encode())
    if "wikipedia.org/w/api" in url:
        return _Resp(WIKI_JSON.encode(), ctype="application/json")
    if "wikipedia.org/wiki" in url:
        return _Resp(PAG_WIKI.encode())
    if "duckduckgo" in url:
        return _Resp(DDG_OK.encode())
    if "403" in url:
        raise urllib.error.HTTPError(url, 403, "x", {}, None)
    if "429" in url:
        raise urllib.error.HTTPError(url, 429, "x", {}, None)
    if "lenta" in url:
        raise TimeoutError("tempo esgotado")
    raise AssertionError("url inesperada: " + url)


@pytest.fixture(autouse=True)
def _limpa_circuito():
    research._circuito.clear()
    yield
    research._circuito.clear()


# ── Bloqueios e fallback ──────────────────────────────────────────────

def test_ddg_botwall_vazio_sem_excecao(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)
    out = research.buscar_ddg("x", base="http://bloqueio/?q=",
                              abrir=lambda u, t=10: _abrir("http://bloqueio/?q="))
    assert out == []


def test_chain_alterna_no_vazio_e_registra_etapas(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)
    orig = research.buscar_ddg

    def _ddg(q, base=research.DDG_HTML, max_resultados=6, timeout=8.0, abrir=None):
        if base == research.DDG_HTML:
            return []
        return orig(q, base="http://duckduckgo-ok/?q=", max_resultados=max_resultados,
                    abrir=lambda u, t=10: _abrir("http://duckduckgo-ok/?q="))

    monkeypatch.setattr(research, "buscar_ddg", _ddg)
    monkeypatch.setattr(research, "_baixar_json",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede")))
    achados, info = research.buscar_com_fallback("tema")
    assert len(achados) == 1 and info["provedor"] == "ddg-lite"
    assert any("sem resultados" in e for e in info["etapas"])


def test_chain_cai_para_wikipedia(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)
    monkeypatch.setattr(research, "buscar_ddg", lambda *a, **k: [])
    monkeypatch.setattr(research, "_baixar_json",
                        lambda url, timeout=8.0, abrir=None: json.loads(WIKI_JSON))
    achados, info = research.buscar_com_fallback("Python")
    assert info["provedor"] == "wikipedia"
    assert achados[0]["tipo"] == "enciclopedia"
    assert achados[0]["url"].startswith("https://")


def test_chain_tudo_falha_honesto(monkeypatch):
    monkeypatch.setattr(research, "buscar_ddg",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(research, "_baixar_json",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede")))
    achados, info = research.buscar_com_fallback("tema")
    assert achados == [] and info["provedor"] == ""
    assert len(info["erros"]) == 3


def test_circuit_breaker_expira(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)
    research._circuito["ddg-lite"] = __import__("time").monotonic()
    monkeypatch.setattr(research, "buscar_ddg", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("ddg-lite não deveria ser chamado")))
    monkeypatch.setattr(research, "_baixar_json",
                        lambda url, timeout=8.0, abrir=None: json.loads(WIKI_JSON))
    achados, info = research.buscar_com_fallback("Python")
    assert info["provedor"] == "wikipedia"
    assert any("em espera" in e for e in info["etapas"])


def test_agents_fallback_continua_no_vazio():
    class _Vazio:
        nome = "vazio"

        def buscar(self, q, limite=6):
            return []

    class _Cheio:
        nome = "cheio"

        def buscar(self, q, limite=6):
            return [{"titulo": "T", "url": "https://x.com/a", "trecho": "t"}]

    achados, info = research_agents.buscar_com_fallback([_Vazio(), _Cheio()], "q")
    assert info["provedor"] == "cheio" and len(achados) == 1


def test_provedores_reais_incluem_wikipedia():
    nomes = [p.nome for p in research_agents.provedores_reais()]
    assert "wikipedia" in nomes and "ddg" in nomes


# ── Parser, digest e sem-LLM ──────────────────────────────────────────

def test_extracao_pula_navegacao():
    titulo, texto = research.extrair_texto_html(PAG_WIKI)
    assert titulo == "Python"
    assert "menu" not in texto and "linguagem de programação" in texto


def test_resumo_deterministico():
    fontes = [{"id": "S1", "titulo": "Python", "url": "https://pt.wikipedia.org/wiki/Python",
               "trecho": "linguagem de programação"}]
    txt = research.resumo_deterministico(fontes, "Python")
    assert "[Python](https://pt.wikipedia.org/wiki/Python)" in txt
    assert "Sem inferência" in txt
    vazio = research.resumo_deterministico([], "Python")
    assert "nenhum provedor" in vazio


def test_ai_completa_digest_sem_llm(monkeypatch):
    import hermes_bridge
    db = _db()
    pc_agent.persist_messages(db, [{
        "id": "rec-user-01", "conversation_id": "conv-r", "origin": "mobile",
        "role": "user", "text": "pesquise sobre Python e traga as fontes",
        "created_at": pc_agent.agora_iso()}], "ana")
    fontes = [{"id": "S1", "titulo": "Python", "url": "https://pt.wikipedia.org/wiki/Python",
               "trecho": "linguagem"}]
    monkeypatch.setattr(research, "pesquisa_rapida",
                        lambda *a, **k: {"fontes": fontes, "etapas": ["wiki: 1"],
                                        "divergencias": [], "de_cache": False})
    monkeypatch.setattr(hermes_bridge, "chat_complete",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("fora", "indisponivel")))
    monkeypatch.setattr(hermes_bridge, "chat_stream",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("fora", "indisponivel")))
    cfg = {"system": "sys", "model": "m", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": True, "proxy": "",
           "fallbacks": []}
    out = pc_agent.ai_completa(db, {"message_id": "rec-user-01",
                                    "conversation_id": "conv-r", "owner": "ana"}, cfg)
    assert "response_text" in out and "digest" in out
    assert "pt.wikipedia.org/wiki/Python" in out["response_text"]
    db.close()


def test_sem_fontes_continua_erro():
    import hermes_bridge
    db = _db()
    pc_agent.persist_messages(db, [{
        "id": "rec-user-02", "conversation_id": "conv-r", "origin": "mobile",
        "role": "user", "text": "qual a capital?", "created_at": pc_agent.agora_iso()}],
        "ana")
    cfg = {"system": "sys", "model": "m", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": False, "proxy": "",
           "fallbacks": []}
    import unittest.mock as _mock
    with _mock.patch.object(hermes_bridge, "chat_complete",
                            side_effect=hermes_bridge.BridgeErro("fora", "indisponivel")):
        out = pc_agent.ai_completa(db, {"message_id": "rec-user-02",
                                        "conversation_id": "conv-r", "owner": "ana"}, cfg)
    assert out.get("codigo") == "indisponivel"
    db.close()


# ── E2E local (HTTP real via loopback + baixar/parsing reais) ──────────

def test_e2e_local_pipeline(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/busca"):
                corpo = ('<html><body><a class="result__a" href="http://127.0.0.1:PORT/artigo">'
                         "Artigo Local</a>"
                         '<div class="result__snippet">trecho local</div></body></html>'
                         ).replace("PORT", str(srv.server_port)).encode()
            else:
                corpo = ("<html><head><title>Artigo Local</title></head><body>"
                         "<nav>menu</nav><p>Conteúdo real do artigo local.</p></body></html>"
                         ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import socket
        def local_connect(address, timeout, source_address=None):
            assert address == ("127.0.0.1", srv.server_port)
            return socket.create_connection(address, timeout, source_address)
        monkeypatch.setattr(research, "_conectar_publico", local_connect)
        base = f"http://127.0.0.1:{srv.server_port}/busca?q="
        db = _db()
        res = research.pesquisa_rapida(
            db, "ana", "artigo local",
            buscar_fn=lambda q: research.buscar_ddg(q, base=base, max_resultados=3),
            recuperar_fn=None, max_fontes=1)
        assert len(res["fontes"]) == 1
        assert "Conteúdo real do artigo local" in res["fontes"][0]["trecho"]
        assert "menu" not in res["fontes"][0]["trecho"]
        db.close()
    finally:
        srv.shutdown()


# ── E2E real (provedores externos acessíveis) ──────────────────────────

@pytest.mark.e2e_real
def test_e2e_wikipedia_live():
    try:
        achados = research.buscar_wikipedia("Python", max_resultados=2)
    except Exception as exc:
        pytest.skip(f"rede indisponível: {type(exc).__name__}")
    if not achados:
        pytest.skip("Wikipedia sem resultados")
    final, pagina = research.baixar(achados[0]["url"], timeout=15.0)
    titulo, texto = research.extrair_texto_html(pagina)
    assert titulo and len(texto) > 200


@pytest.mark.e2e_real
def test_e2e_openalex_live():
    import academic_research as _ac
    try:
        prov = _ac.AcademicResearchProvider()
        out = prov.buscar("machine learning", 2)
    except Exception as exc:
        pytest.skip(f"rede indisponível: {type(exc).__name__}")
    if not out:
        pytest.skip("OpenAlex sem resultados")
    assert out[0].get("title") or out[0].get("titulo")
