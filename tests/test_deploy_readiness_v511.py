"""P0-4/P0-5: hello do agente, drift de commit e readiness real.

O relay so deve se declarar pronto quando o agente esta conectado, o SQLite
foi verificado e o commit do checkout e o mesmo do relay. `/api/health`
continua sendo liveness e nunca substitui `/api/ready`.
"""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import server


COMMIT = "a" * 12


def setup_module():
    os.environ.setdefault("JULIA_USERNAME", "efrai")
    os.environ.setdefault("JULIA_PASSWORD_HASH", "x")
    os.environ.setdefault("JULIA_SESSION_SECRET", "a" * 64)
    os.environ.setdefault("JULIA_AGENT_TOKEN", "b" * 64)


def _hello(commit=COMMIT, db_ok=True):
    return {
        "type": "agent_hello",
        "commit": commit,
        "pid": 4242,
        "uptime_s": 77,
        "started_at": "2026-11-01T12:00:00+00:00",
        "db_ok": db_ok,
        "python": "3.13.0",
    }


def _esperar(condicao, timeout=4.0):
    fim = time.time() + timeout
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return False


def _agent_ws(client):
    return client.websocket_connect(
        "/api/agent/ws",
        headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]})


def test_health_e_liveness_mas_ready_falha_offline(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    with TestClient(server.app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ready = client.get("/api/ready")
        assert ready.status_code == 503
        corpo = ready.json()
        assert corpo["status"] == "offline"
        assert corpo["ready"] is False and corpo["stale"] is True
        assert corpo["checks"]["agent_online"] is False
        assert corpo["pc_online"] is False


def test_hello_expoe_pid_uptime_commit_e_sqlite(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    with TestClient(server.app) as client:
        with _agent_ws(client) as ws:
            ws.send_json(_hello())
            assert _esperar(
                lambda: client.get("/api/diag").json().get("agent_commit"))
            d = client.get("/api/diag").json()
            assert d["pc_online"] is True
            assert d["agent_commit"] == COMMIT
            assert d["agent_pid"] == 4242
            assert d["agent_uptime_s"] == 77
            assert d["agent_started_at"].startswith("2026-11-01")
            assert d["agent_db_ok"] is True
            assert d["drift"] is True
            assert d["drift_status"] == "divergente"
            assert d["stale"] is True


def test_ready_200_quando_agente_sqlite_e_commit_batem(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", COMMIT + "c" * 28)
    with TestClient(server.app) as client:
        with _agent_ws(client) as ws:
            ws.send_json(_hello())
            assert _esperar(
                lambda: client.get("/api/ready").json().get("ready") is True)
            ready = client.get("/api/ready")
            assert ready.status_code == 200
            corpo = ready.json()
            assert corpo["status"] == "ok"
            assert corpo["stale"] is False
            assert corpo["checks"] == {
                "configured": True, "agent_online": True,
                "agent_hello": True, "database": True,
                "commit_aligned": True,
            }
            assert corpo["drift"] is False


def test_ready_503_quando_sqlite_nao_esta_integro(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", COMMIT + "c" * 28)
    with TestClient(server.app) as client:
        with _agent_ws(client) as ws:
            ws.send_json(_hello(db_ok=False))
            assert _esperar(
                lambda: client.get("/api/diag").json().get("agent_db_ok") is False)
            ready = client.get("/api/ready")
            assert ready.status_code == 503
            assert ready.json()["status"] == "degraded"
            assert ready.json()["checks"]["database"] is False


def test_diag_alerta_apos_limite_offline(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    with TestClient(server.app) as client:
        server.relay.offline_desde = time.monotonic() - 1000
        d = client.get("/api/diag").json()
        assert d["pc_online"] is False
        assert d["offline_s"] >= 1000
        assert d["alert"] is True


def test_auth_config_preserva_ultima_config_com_stale(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    with TestClient(server.app) as client:
        offline = client.get("/api/auth/config").json()
        assert offline["agent_online"] is False
        assert offline["stale"] is True

        with _agent_ws(client) as ws:
            resultado = {}

            def consultar():
                resultado["resp"] = client.get("/api/auth/config")

            thread = threading.Thread(target=consultar)
            thread.start()
            pedido = ws.receive_json()
            assert pedido["type"] == "auth_config"
            ws.send_json({"request_id": pedido["request_id"],
                          "type": "auth_config", "modo": "convite",
                          "exigir_aprovacao": True})
            thread.join(timeout=6)
            assert not thread.is_alive()
            online = resultado["resp"]
            assert online.status_code == 200
            assert online.json() == {"modo": "convite",
                                     "exigir_aprovacao": True,
                                     "agent_online": True, "stale": False}

        depois = client.get("/api/auth/config").json()
        assert depois["modo"] == "convite"
        assert depois["exigir_aprovacao"] is True
        assert depois["agent_online"] is False
        assert depois["stale"] is True


def test_normalizar_hello_rejeita_campos_fora_do_contrato():
    info = server.normalizar_hello({
        "commit": "z" * 100,
        "pid": "9" * 40,
        "uptime_s": -5,
        "started_at": "x" * 500,
        "db_ok": "true",
        "python": "y" * 100,
    })
    assert info["commit"] == "desconhecido"
    assert info["pid"] == 2**31 - 1
    assert info["uptime_s"] == 0
    assert len(info["started_at"]) == 40
    assert info["db_ok"] is False
    assert len(info["python"]) == 20


def test_agente_anuncia_commit_pid_e_sqlite(tmp_path):
    db = pc_agent.open_db(tmp_path / "qa.sqlite")
    try:
        hello = pc_agent.hello_agente(db)
        assert hello["type"] == "agent_hello"
        assert hello["commit"] == pc_agent.revisao_agente()
        assert hello["commit"] == "desconhecido" or len(hello["commit"]) == 12
        assert hello["pid"] == os.getpid()
        assert hello["uptime_s"] >= 0
        assert hello["db_ok"] is True
        assert "memory.sqlite3" not in str(hello)
    finally:
        db.close()


def test_sqlite_integro_detecta_banco_fechado(tmp_path):
    db = sqlite3.connect(tmp_path / "qa.sqlite")
    assert pc_agent.sqlite_integro(db) is True
    db.close()
    assert pc_agent.sqlite_integro(db) is False


@pytest.mark.parametrize("valor", ["", "local", "zzzz", "a" * 6])
def test_commit_curto_so_aceita_sha_verificavel(valor):
    assert server.commit_curto(valor) == ""
