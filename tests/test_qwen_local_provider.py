"""Testes do Provedor Qwen 2.5 1.5B Local (Principal)."""
import json
import io
import sys
import urllib.error
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hermes_bridge
import providers
import server


def test_qwen_local_configuracao_e_divisao():
    assert "qwen_local" in providers.PROVIDERS
    assert "qwen_local" in providers.configurados()
    assert providers.chave("qwen_local") == "sk-local"
    assert providers.chave_origem("qwen_local") == "local_pc"

    prov, mid = providers.dividir("qwen2.5-1.5b-instruct")
    assert prov == "qwen_local"
    assert mid == "qwen2.5-1.5b-instruct"

    prov, mid = providers.dividir("qwen_local/qwen2.5-1.5b-instruct")
    assert prov == "qwen_local"
    assert mid == "qwen2.5-1.5b-instruct"

    prov, mid = providers.dividir("local/qwen2.5-1.5b-instruct")
    assert prov == "qwen_local"
    assert mid == "qwen2.5-1.5b-instruct"

    assert providers.supports_chat("qwen2.5-1.5b-instruct") is True
    assert providers.selection_error("qwen2.5-1.5b-instruct") is None


def test_qwen_local_listar_tudo_prioridade():
    cat = providers.listar_tudo()
    assert cat["default"] == "vexx-qwen-2.5-3b"
    assert "vexx-qwen-2.5-3b" in cat["models"]
    assert "qwen2.5-1.5b-instruct" in cat["models"]
    assert any(it["id"] == "qwen2.5-1.5b-instruct" and it["provider"] == "qwen_local" for it in cat["items"])
    assert any(p["id"] == "qwen_local" and p["configured"] is True for p in cat["providers"])


def test_qwen_local_podar_contexto():
    mensagens = [
        {"role": "system", "content": "Instrução inicial"},
        {"role": "user", "content": "M1 " * 500},
        {"role": "assistant", "content": "R1 " * 500},
        {"role": "user", "content": "M2 recente"}
    ]
    podado = providers._podar_contexto_local(mensagens, max_chars=100)
    assert len(podado) == 2
    assert podado[0]["role"] == "system"
    assert podado[1]["content"] == "M2 recente"


def test_qwen_local_chat_complete_mock(monkeypatch):
    chamadas = []

    class _Resp:
        def __init__(self):
            self.corpo = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "Olá do Qwen local!"}}]
            }).encode("utf-8")

        def read(self, n=-1):
            return self.corpo if n is None or n < 0 else self.corpo[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        chamadas.append(req)
        return _Resp()

    monkeypatch.setattr(providers.urllib.request, "urlopen", _fake_urlopen)
    res = providers.chat_complete("qwen_local", "qwen2.5-1.5b-instruct", [{"role": "user", "content": "olá"}])
    assert res["texto"] == "Olá do Qwen local!"
    assert len(chamadas) == 1
    assert chamadas[0].full_url == "http://127.0.0.1:8008/v1/chat/completions"
    assert chamadas[0].headers.get("Authorization") == "Bearer sk-local"


def test_qwen_local_endpoint_latencia(monkeypatch):
    import routers.ai_routes as air
    async def fake_rev(req):
        return "user_test"
    monkeypatch.setattr(air, "revogacao_ok", fake_rev)
    monkeypatch.setattr(air, "require_csrf", lambda req: None)

    fake_res = {
        "status": "sucesso",
        "local_online": True,
        "modelo": "qwen2.5-1.5b-instruct",
        "ttft_ms": 235.0,
        "duracao_ms": 650.0,
        "tokens_per_sec": 14.5
    }
    monkeypatch.setattr(providers, "testar_latencia_ai", lambda *a, **k: fake_res)

    client = TestClient(server.app)
    resp = client.post("/api/ai/latency-test")
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "sucesso"
    assert dados["local_online"] is True
    assert dados["ttft_ms"] == 235.0


def test_qwen_local_live_endpoint_se_disponivel():
    """Teste de integração real se a porta 8008 estiver ativa no PC."""
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:8008/v1/models", headers={"Authorization": "Bearer sk-local"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status != 200:
                pytest.skip("Porta 8008 não retornou 200")
    except Exception:
        pytest.skip("Qwen local não está rodando na porta 8008 no momento")

    res = providers.chat_complete("qwen_local", "qwen2.5-1.5b-instruct",
                                 [{"role": "user", "content": "Diga 'OK' em uma palavra."}], timeout=15)
    assert res["texto"].strip()
    assert res["latencia_s"] > 0
