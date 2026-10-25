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
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
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
    monkeypatch.delenv("JULIA_REMOTE", raising=False)
    assert remoto.entrada_ativada() is False
    with pytest.raises(remoto.RemotoErro) as exc:
        remoto.executar({"kind": "move", "x": 0.1, "y": 0.1})
    assert exc.value.codigo == "desativado"


# ── Windows-only de verdade: remoto usa ctypes.windll (entrada/captura) — no
# Linux/macOS essas APIs nem existem, então o skip é plataforma, não falha. ──
_windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="remoto usa ctypes.windll/SetCursorPos e captura via mss só no "
           "Windows (remoto.py: 'Entrada/Captura só no Windows')")


@_windows_only
def test_ritmo_barra_rajada(monkeypatch):
    monkeypatch.setenv("JULIA_REMOTE", "1")
    monkeypatch.setattr(remoto, "tamanho_tela", lambda: (100, 100))
    calls = []
    monkeypatch.setattr("ctypes.windll.user32.SetCursorPos",
                        lambda x, y: calls.append((x, y)))
    assert remoto.executar({"kind": "move", "x": 0.5, "y": 0.5})["ok"] is True
    assert calls == [(50, 50)]
    with pytest.raises(remoto.RemotoErro) as exc:
        remoto.executar({"kind": "move", "x": 0.5, "y": 0.5})
    assert exc.value.codigo == "ritmo"


@_windows_only
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


def test_gate_agente_nega_sem_grant(tmp_path):
    """V4.2 §2: conta comum sem grant não vê tela nem controla (sem vazar imagem)."""
    import julia_auth as _ja

    import pc_agent
    db = pc_agent.open_db(tmp_path / "gate_nega.sqlite3")
    _ja.criar_usuario(db, "visit", "Visita", "senha-forte-1", criado_por="t")
    uid = _ja.buscar_usuario(db, "visit")["uid"]
    r = pc_agent.resposta_screen(db, {"max_w": 800, "q": 50}, uid, "r1")
    assert r["type"] == "screen_error" and r["codigo"] == "sem_permissao"
    assert "imagem" not in r and r["request_id"] == "r1"
    r = pc_agent.resposta_input(db, {"cmd": {"kind": "click", "x": 0.5, "y": 0.5}}, uid, "r2")
    assert r["type"] == "input_error" and r["codigo"] == "sem_permissao"
    db.close()


def test_gate_agente_permite_grant_e_local(tmp_path, monkeypatch):
    """Grant explícito libera; dono local sempre; bloqueio revoga mesmo com grant."""
    import julia_auth as _ja

    import pc_agent
    monkeypatch.setattr(remoto, "capturar",
                        lambda *a, **k: {"imagem": "x", "largura": 1, "altura": 1, "ms": 0})
    monkeypatch.setattr(remoto, "executar", lambda cmd: {"ok": True, "kind": cmd["kind"]})
    db = pc_agent.open_db(tmp_path / "gate_ok.sqlite3")
    _ja.criar_usuario(db, "visit", "Visita", "senha-forte-1", criado_por="t")
    uid = _ja.buscar_usuario(db, "visit")["uid"]
    assert pc_agent.resposta_screen(db, {}, "local", "r1")["type"] == "screen"
    _ja.update_limits(db, "local", uid, 0, 0, True)
    assert pc_agent.resposta_screen(db, {}, uid, "r2")["type"] == "screen"
    r = pc_agent.resposta_input(db, {"cmd": {"kind": "click", "x": 0.5, "y": 0.5}}, uid, "r3")
    assert r["type"] == "input_done" and r["kind"] == "click"
    _ja.update_limits(db, "local", uid, 0, 0, False)
    assert pc_agent.resposta_screen(db, {}, uid, "r4")["codigo"] == "sem_permissao"
    _ja.update_limits(db, "local", uid, 0, 0, True)
    _ja.definir_status(db, "local", uid, "bloqueado")
    assert pc_agent.resposta_screen(db, {}, uid, "r5")["codigo"] == "sem_permissao"
    assert pc_agent.resposta_input(
        db, {"cmd": {"kind": "click", "x": 0.5, "y": 0.5}}, uid, "r6")["codigo"] == "sem_permissao"
    db.close()


def test_screen_input_via_agente_fake(monkeypatch):
    # Exercise the real revocation handshake even when the suite takes >60s.
    # A fake agent must answer control messages before screen/input commands.
    monkeypatch.setattr(server, 'revogados', {'sids': set(), 'ts': 0.0, 'suportado': True, 'falhas': 0})
    with TestClient(server.app) as client:
        csrf = _login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            out = {}
            revocation_checks = []

            def receber_comando(expected):
                for _ in range(4):
                    message = ws.receive_json()
                    if message['type'] == 'sess_revogados':
                        assert message.get('request_id')
                        revocation_checks.append(message['request_id'])
                        ws.send_json({'request_id': message['request_id'], 'type': 'sess_revogados', 'sids': []})
                        continue
                    assert message['type'] == expected
                    return message
                pytest.fail('Revocation control messages did not lead to the requested command')

            def tela():
                out["s"] = client.get("/api/screen?max_w=800&q=50",
                                     headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=tela)
            t.start()
            req = receber_comando('screen')
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
            req = receber_comando('input')
            ws.send_json({"request_id": req["request_id"], "type": "input_done", "kind": "click"})
            t.join(timeout=8)
            assert out["i"].json() == {"ok": True, "kind": "click"}

            def negado():
                out["n"] = client.post("/api/input", json={"kind": "click", "x": 0.5, "y": 0.5},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=negado)
            t.start()
            req = receber_comando('input')
            ws.send_json({"request_id": req["request_id"], "type": "input_error",
                          "error": "Controle desativado", "codigo": "desativado"})
            t.join(timeout=8)
            assert out["n"].status_code == 503
            assert revocation_checks
