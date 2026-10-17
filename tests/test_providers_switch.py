"""V5.4.2 — provedores externos REAIS: erro honesto por provedor, fallback que
atravessa provedores, proxy respeitado, troca de modelo a qualquer momento."""
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


def _ok():
    return _Resp(json.dumps({"choices": [{"message": {"content": "olá"}}]}).encode())


def _stream_ok():
    return _Resp(b'data: {"choices": [{"delta": {"content": "oi"}}]}\n\ndata: [DONE]\n\n')


def _limpar_chaves(monkeypatch):
    for env in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)


def test_erro_direto_e_honesto_e_sem_fragmento_de_chave(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    corpo = json.dumps({"error": {
        "message": "Incorrect API key provided: sk-abcDEF123. Find yours at...",
        "code": "invalid_api_key", "type": "invalid_request_error"}}).encode()

    def _fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(corpo))

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake)
    with pytest.raises(hermes_bridge.BridgeErro) as e:
        providers.chat_complete("openai", "gpt-4o-mini",
                                [{"role": "user", "content": "oi"}])
    msg = str(e.value)
    assert e.value.codigo == "auth"
    assert "OpenAI recusou a chave" in msg and "OPENAI_API_KEY" in msg
    assert "hermes proxy" not in msg  # erro de provedor direto não fala de proxy
    assert "sk-abcDEF123" not in str(e.value.detalhe)
    assert "sk-" not in str(e.value.detalhe)


def test_fallback_atravessa_provedores_sem_chave(monkeypatch):
    _limpar_chaves(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.urllib.request, "urlopen",
                        lambda req, timeout=None: _ok())
    res = providers.tentar_modelos(
        ["gemini/gemini-2.0-flash", "openai/gpt-4o-mini"],
        [{"role": "user", "content": "oi"}])
    assert res["model_usado"] == "openai/gpt-4o-mini"
    assert res["tentativas"][0]["model"] == "gemini/gemini-2.0-flash"
    assert res["tentativas"][0]["codigo"] == "sem_chave"


def test_fallback_para_no_mesmo_provedor(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    chamadas = []

    def _fake(req, timeout=None):
        chamadas.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake)
    with pytest.raises(hermes_bridge.BridgeErro) as e:
        providers.tentar_modelos(["openai/gpt-4o-mini", "openai/gpt-4o"],
                                 [{"role": "user", "content": "oi"}])
    assert e.value.codigo == "auth"
    assert len(chamadas) == 1  # credencial ruim vale para o provedor todo


def test_stream_fallback_atravessa_provedores(monkeypatch):
    _limpar_chaves(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.urllib.request, "urlopen",
                        lambda req, timeout=None: _stream_ok())
    got = []
    res = providers.chat_stream_fb(
        ["deepseek/deepseek-chat", "groq/llama-3.3-70b-versatile"],
        [{"role": "user", "content": "oi"}], lambda s, t: got.append(t))
    assert res["model_usado"] == "groq/llama-3.3-70b-versatile"
    assert got == ["oi"]
    assert res["tentativas"][0]["codigo"] == "sem_chave"


def test_proxy_hermes_segue_o_configurado(monkeypatch):
    vistos = {}

    def _fake(req, timeout=None):
        vistos["url"] = req.full_url
        return _ok()

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake)
    providers.chat_complete("hermes", "poolside/x",
                            [{"role": "user", "content": "oi"}],
                            proxy="http://127.0.0.1:9999/v1")
    assert vistos["url"].startswith("http://127.0.0.1:9999/v1/")


def test_listar_marca_chave_recusada(monkeypatch):
    _limpar_chaves(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.hermes_bridge, "listar_modelos",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("x", "auth")))
    cat = providers.listar_tudo()
    prov = next(p for p in cat["providers"] if p["id"] == "openai")
    assert prov["configured"] is True and prov.get("auth_error") is True
    itens = [i for i in cat["items"] if i["provider"] == "openai"]
    assert itens and all(i.get("auth_error") for i in itens)
    assert "sk-fake" not in json.dumps(cat)


def test_listar_falha_de_rede_nao_marca_recusada(monkeypatch):
    _limpar_chaves(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(providers.hermes_bridge, "listar_modelos",
                        lambda *a, **k: (_ for _ in ()).throw(
                            hermes_bridge.BridgeErro("x", "indisponivel")))
    cat = providers.listar_tudo()
    prov = next(p for p in cat["providers"] if p["id"] == "openai")
    assert prov["configured"] is True and not prov.get("auth_error")


def test_gerar_texto_troca_de_modelo_por_mensagem_e_proxy(monkeypatch):
    import pc_agent
    chamadas = []

    def _fake(modelos, messages, **k):
        chamadas.append((list(modelos), k))
        return {"texto": "ok", "model_usado": modelos[0]}

    monkeypatch.setattr(providers, "tentar_modelos", _fake)
    cfg = {"proxy": "http://127.0.0.1:9999/v1", "model": "poolside/laguna",
           "fallbacks": [], "max_tokens": 40}
    pc_agent.gerar_texto(cfg, [], preferido="openai/gpt-4o-mini")
    pc_agent.gerar_texto(cfg, [], preferido="gemini/gemini-2.0-flash")
    (fila1, k1), (fila2, k2) = chamadas
    assert fila1[0] == "openai/gpt-4o-mini"
    assert fila2[0] == "gemini/gemini-2.0-flash"
    assert k1.get("proxy") == "http://127.0.0.1:9999/v1"


def test_env_local_carrega_sem_sobrescrever(tmp_path, monkeypatch):
    import env_local
    (tmp_path / ".env").write_text(
        "# comentário\nOPENAI_API_KEY=chave-do-arquivo\nJULIA_TESTE_ENV_LOCAL=1\n",
        encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "valor-do-sistema")
    monkeypatch.delenv("JULIA_TESTE_ENV_LOCAL", raising=False)
    n = env_local.carregar_env_local(tmp_path)
    import os
    assert n == 1
    assert os.environ["OPENAI_API_KEY"] == "valor-do-sistema"  # sistema manda
    assert os.environ["JULIA_TESTE_ENV_LOCAL"] == "1"


def test_frontend_troca_a_qualquer_momento():
    raiz = Path(__file__).resolve().parents[1]
    html = (raiz / "public" / "index.html").read_text(encoding="utf-8")
    js = (raiz / "public" / "app.js").read_text(encoding="utf-8")
    assert 'id="modelRefresh"' in html
    assert 'id="popModelRow"' in html and 'id="popModel"' in html
    assert "loadModels(true)" in js
    assert "abrirSeletorDeModelo" in js
    assert "auth_error" in js and "chave recusada" in js
    assert "itemProvider" in js
    assert "Não consegui responder" in js
    for segredo in ("OPENAI_API_KEY", "sk-", "api_key"):
        assert segredo not in js


def test_relay_repassa_metadados_de_provedor_para_o_app():
    """O /api/ai/models filtra campos do PC: auth_error e o mapa id->provedor
    PRECISAM passar (chaves, nunca)."""
    raiz = Path(__file__).resolve().parents[1]
    src = (raiz / "server.py").read_text(encoding="utf-8")
    i = src.find('"providers": [{k: p.get(k)')
    assert i > 0, "trecho do /api/ai/models não encontrado"
    trecho = src[max(0, i - 400):i + 200]
    for campo in ("id", "label", "configured", "auth_error"):
        assert f'"{campo}"' in trecho, f"campo {campo} não repassado pelo relay"
    assert '"items"' in trecho and '"provider"' in trecho, "mapa id->provedor não repassado"
    assert '"key"' not in trecho and '"api_key"' not in trecho
