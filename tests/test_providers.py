"""Multi-provedor LLM: roteamento, chaves, allowlist, adapters, sem vazamento."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hermes_bridge
import providers


class _Resp:
    def __init__(self, corpo: bytes):
        self._corpo = corpo

    def read(self, n=-1):
        return self._corpo if n is None or n < 0 else self._corpo[:n]

    def read1(self, n):
        out, self._corpo = self._corpo[:n], self._corpo[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _openai_ok():
    return _Resp(json.dumps(
        {"choices": [{"message": {"content": "olá"}}]}).encode())


def _openai_stream():
    return _Resp(b'data: {"choices": [{"delta": {"content": "oi"}}]}\n\ndata: [DONE]\n\n')


def _lista_openai():
    return _Resp(json.dumps({"data": [{"id": "gpt-4o-mini"}, {"id": "x"}]}).encode())


def _anthropic_ok():
    return _Resp(json.dumps(
        {"content": [{"type": "text", "text": "olá"}]}).encode())


def _anthropic_stream():
    return _Resp(b'event: content_block_delta\ndata: {"type": "content_block_delta", '
                 b'"delta": {"text": "oi"}}\n\n')


def test_dividir():
    assert providers.dividir("gemini/gemini-2.0-flash") == ("gemini", "gemini-2.0-flash")
    assert providers.dividir("openai/gpt-4o-mini") == ("openai", "gpt-4o-mini")
    assert providers.dividir("poolside/laguna-s-2.1:free") == ("hermes", "poolside/laguna-s-2.1:free")
    assert providers.dividir("desconhecido/x") == ("hermes", "desconhecido/x")
    assert providers.dividir("") == ("hermes", "")


def test_configurados_respeita_chave(monkeypatch):
    for env in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    assert providers.configurados() == ["hermes"]
    monkeypatch.setenv("GEMINI_API_KEY", "  AIzafake  ")
    assert providers.chave("gemini") == "AIzafake"
    assert "gemini" in providers.configurados()
    assert "openai" not in providers.configurados()


def test_base_publica_allowlist():
    assert hermes_bridge.base_publica("https://api.openai.com/v1",
                                      ("api.openai.com",))
    for ruim in ("http://api.openai.com/v1", "https://evil.com/v1",
                 "https://api.openai.com.evil.com/v1", "file:///x",
                 "https://user:pass@api.openai.com/v1",
                 "https://api.openai.com/v1?x=1", ""):
        with pytest.raises(hermes_bridge.BridgeErro):
            hermes_bridge.base_publica(ruim, ("api.openai.com",))


def test_req_auth_header():
    r1 = hermes_bridge._req("https://x/v1/chat", {}, 5)
    assert r1.get_header("Authorization") == "Bearer local"
    r2 = hermes_bridge._req("https://x/v1/chat", {}, 5, api_key="sk-secreta")
    assert r2.get_header("Authorization") == "Bearer sk-secreta"


def test_listar_sem_chaves_mostra_curadoria_sem_vazar(monkeypatch):
    for env in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(hermes_bridge, "listar_modelos",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("x", "indisponivel")))
    cat = providers.listar_tudo()
    assert cat["models"] == [] or all("/" in m for m in cat["models"])
    assert "sk-" not in json.dumps(cat)
    assert {p["id"] for p in cat["providers"]} >= {"hermes", "openai", "gemini"}
    assert all(p["configured"] is False for p in cat["providers"] if p["id"] != "hermes")


def test_listar_com_chave_usa_live_ou_curadoria(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    for env in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                "GROQ_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(hermes_bridge, "listar_modelos",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("x", "indisponivel")))
    cat = providers.listar_tudo()
    ids = [m for m in cat["models"] if m.startswith("openai/")]
    assert ids and "sk-fake" not in json.dumps(cat)


def test_chat_complete_openai_compat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    vistos = {}

    def _fake(req, timeout=None):
        vistos["url"] = req.full_url
        vistos["auth"] = req.get_header("Authorization")
        vistos["corpo"] = json.loads(req.data.decode())
        return _openai_ok()

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake)
    res = providers.chat_complete("openai", "gpt-4o-mini",
                                  [{"role": "user", "content": "oi"}])
    assert res["texto"] == "olá"
    assert vistos["url"] == "https://api.openai.com/v1/chat/completions"
    assert vistos["auth"] == "Bearer sk-fake"
    assert vistos["corpo"]["model"] == "gpt-4o-mini"


def test_chat_stream_openai_compat(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.urllib.request, "urlopen",
                        lambda req, timeout=None: _openai_stream())
    got = []
    res = providers.chat_stream("groq", "llama-3.3-70b-versatile",
                                [{"role": "user", "content": "oi"}],
                                lambda s, t: got.append(t))
    assert res["texto"] == "oi" and got == ["oi"]


def test_anthropic_complete_e_stream(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    vistos = {}

    def _fake(req, timeout=None):
        vistos["key"] = req.get_header("X-api-key")
        vistos["ver"] = req.get_header("Anthropic-version")
        vistos["auth"] = req.get_header("Authorization")
        vistos["corpo"] = json.loads(req.data.decode())
        return _anthropic_ok()

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake)
    res = providers.chat_complete("anthropic", "claude-3-5-sonnet-20241022",
                                  [{"role": "system", "content": "seja breve"},
                                   {"role": "user", "content": "oi"}])
    assert res["texto"] == "olá"
    assert vistos["key"] == "sk-ant-fake" and vistos["ver"] == providers.ANTHROPIC_VERSION
    assert vistos["auth"] is None  # Anthropic usa x-api-key, nunca Bearer
    assert vistos["corpo"]["system"] == "seja breve"
    monkeypatch.setattr(providers.urllib.request, "urlopen",
                        lambda req, timeout=None: _anthropic_stream())
    got = []
    res2 = providers.chat_stream("anthropic", "claude-3-5-sonnet-20241022",
                                 [{"role": "user", "content": "oi"}],
                                 lambda s, t: got.append(t))
    assert res2["texto"] == "oi" and got == ["oi"]


def test_sem_chave_e_desconhecido():
    import os as _os
    for env in ("OPENAI_API_KEY",):
        _os.environ.pop(env, None)
    with pytest.raises(hermes_bridge.BridgeErro) as e:
        providers.chat_complete("openai", "gpt-4o-mini", [{"role": "user", "content": "oi"}])
    assert e.value.codigo == "sem_chave"
    with pytest.raises(hermes_bridge.BridgeErro):
        providers.chat_complete("nope", "x", [])


def test_tentar_para_no_auth(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.urllib.request, "urlopen",
                        lambda req, timeout=None: (_ for _ in ()).throw(
                            urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b"{}"))))
    with pytest.raises(hermes_bridge.BridgeErro) as e:
        providers.tentar_modelos(["openai/gpt-4o-mini", "openai/gpt-4o"],
                                 [{"role": "user", "content": "oi"}])
    assert e.value.codigo == "auth"


def test_gerar_texto_roteia(monkeypatch):
    import pc_agent
    chamadas = {}
    monkeypatch.setattr(providers, "tentar_modelos",
                        lambda *a, **k: chamadas.setdefault("prov", True) or {"texto": "p"})
    monkeypatch.setattr(hermes_bridge, "tentar_modelos",
                        lambda *a, **k: chamadas.setdefault("hermes", True) or {"texto": "h"})
    cfg = {"proxy": "", "model": "openai/gpt-4o-mini", "fallbacks": [],
           "max_tokens": 50}
    pc_agent.gerar_texto(cfg, [], preferido="openai/gpt-4o-mini")
    assert chamadas == {"prov": True}
    chamadas.clear()
    pc_agent.gerar_texto({**cfg, "model": "laguna"}, [], preferido="laguna")
    assert chamadas == {"hermes": True}


def test_frontend_picker_com_busca():
    raiz = Path(__file__).resolve().parents[1]
    html = (raiz / "public" / "index.html").read_text(encoding="utf-8")
    js = (raiz / "public" / "app.js").read_text(encoding="utf-8")
    assert 'id="modelSearch"' in html
    assert "optgroup" in js and "modelSearch" in js
    assert "o.disabled = true" in js or "disabled = true" in js
    for segredo in ("OPENAI_API_KEY", "sk-", "api_key"):
        assert segredo not in js
