"""Controle remoto: validação, trava de segurança, ritmo, captura e relay."""
import base64
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import remoto
import server


def setup_module():
    from argon2 import PasswordHasher
    os.environ["fajulto_USERNAME"] = "efrai"
    os.environ["fajulto_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["fajulto_SESSION_SECRET"] = "a" * 64
    os.environ["fajulto_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()


@pytest.fixture(autouse=True)
def limpa_ritmo():
    remoto._janela.clear()
    yield
    remoto._janela.clear()


def test_validacao_comandos():
    assert remoto.validar_comando({"kind": "click", "x": 0.5, "y": 0.5})["kind"] == "click"
    assert remoto.validar_comando({"kind": "scroll", "dx": 99, "dy": -99}) == {
        "kind": "scroll", "dx": 10, "dy": -10}
    assert remoto.validar_comando({"kind": "key", "key": "Enter"})["key"] == "enter"
    assert remoto.validar_comando({"kind": "text", "text": "oi"})["text"] == "oi"
    for ruim in ({"kind": "rm -rf"}, {"kind": "click", "x": 2, "y": 0},
                 {"kind": "click"}, {"kind": "key", "key": "F13+power"},
                 {"kind": "text", "text": ""}, {"kind": "text", "text": "x" * 201},
                 "texto", None):
        with pytest.raises(remoto.RemotoErro):
            remoto.validar_comando(ruim)


def test_entrada_desativada_por_padrao(monkeypatch):
    monkeypatch.delenv("fajulto_REMOTE", raising=False)
    assert remoto.entrada_ativada() is False
    with pytest.raises(remoto.RemotoErro) as exc:
        remoto.executar({"kind": "move", "x": 0.1, "y": 0.1})
    assert exc.value.codigo == "desativado"


def test_ritmo_barra_rajada(monkeypatch):
    monkeypatch.setenv("fajulto_REMOTE", "1")
    monkeypatch.setattr(remoto, "tamanho_tela", lambda: (100, 100))
    calls = []
    monkeypatch.setattr("ctypes.windll.user32.SetCursorPos",
                        lambda x, y: calls.append((x, y)))
    assert remoto.executar({"kind": "move", "x": 0.5, "y": 0.5})["ok"] is True
    assert calls == [(50, 50)]
    with pytest.raises(remoto.RemotoErro) as exc:
        remoto.executar({"kind": "move", "x": 0.5, "y": 0.5})
    assert exc.value.codigo == "ritmo"


def test_captura_jpeg_real():
    img = remoto.capturar(640, 50)
    raw = base64.b64decode(img["imagem"])
    assert raw[:2] == b"\xff\xd8"  # JPEG de verdade
    assert img["largura"] <= 640 and img["ms"] >= 0


def _login(client):
    r = client.post("/api/login", json={"username": "efrai", "password": "strong-example-password"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def test_relay_exige_auth_e_valida():
    with TestClient(server.app) as client:
        assert client.get("/api/screen").status_code == 401
        assert client.post("/api/input", json={"kind": "click", "x": 0.5, "y": 0.5}).status_code == 401
        csrf = _login(client)
        assert client.post("/api/input", json={"kind": "format", "x": 0.5, "y": 0.5},
                           headers={"X-CSRF-Token": csrf}).status_code == 422
        assert client.post("/api/input", json={"kind": "text", "text": "x" * 201},
                           headers={"X-CSRF-Token": csrf}).status_code == 422


def test_screen_input_via_agente_fake():
    with TestClient(server.app) as client:
        csrf = _login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["fajulto_AGENT_TOKEN"]}) as ws:
            out = {}

            def tela():
                out["s"] = client.get("/api/screen?max_w=800&q=50",
                                     headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=tela)
            t.start()
            req = ws.receive_json()
            assert req["type"] == "screen" and req["max_w"] == 800
            ws.send_json({"request_id": req["request_id"], "type": "screen",
                          "imagem": "abc", "largura": 800, "altura": 450,
                          "ms": 10, "remote_enabled": False})
            t.join(timeout=8)
            assert out["s"].json()["remote_enabled"] is False

            def cmd():
                out["i"] = client.post("/api/input", json={"kind": "click", "x": 0.5, "y": 0.5},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=cmd)
            t.start()
            req = ws.receive_json()
            ws.send_json({"request_id": req["request_id"], "type": "input_done", "kind": "click"})
            t.join(timeout=8)
            assert out["i"].json() == {"ok": True, "kind": "click"}

            def negado():
                out["n"] = client.post("/api/input", json={"kind": "click", "x": 0.5, "y": 0.5},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=negado)
            t.start()
            req = ws.receive_json()
            ws.send_json({"request_id": req["request_id"], "type": "input_error",
                          "error": "Controle desativado", "codigo": "desativado"})
            t.join(timeout=8)
            assert out["n"].status_code == 503
