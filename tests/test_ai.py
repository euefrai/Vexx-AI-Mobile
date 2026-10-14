"""Integração Hermes Proxy (Opção A): bridge, agente, relay e SQLite.

Unidade usa um servidor HTTP OpenAI-compatible falso (stdlib). Integração usa
processos reais: uvicorn (server.py) + pc_agent.py de verdade, com o falso só
na fronteira Hermes. Inferência no proxy real foi validada manualmente
(laguna-s-2.1:free respondeu 'OK_FAJULTO' + SSE) para não gastar quota em testes.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import hermes_bridge
import pc_agent
import server


# ── Hermes falso (fronteira de teste) ──────────────────────────────────
class FakeHermes(BaseHTTPRequestHandler):
    chamadas = []
    stream_deltas = ["Olá, ", "sou a Júlia."]

    def log_message(self, *a):
        pass

    def _json(self, obj, codigo=200):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._json({"data": [{"id": "fake-model"}, {"id": "outro"}]})
        return self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):
        tam = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(tam).decode() or "{}")
        FakeHermes.chamadas.append(corpo)
        if corpo.get("model") == "modelo-inexistente":
            return self._json({"error": "not found"}, 404)
        if corpo.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for trecho in FakeHermes.stream_deltas:
                carga = json.dumps({"choices": [{"delta": {"content": trecho}}]})
                self.wfile.write(f": keepalive\n\ndata: {carga}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        return self._json({"choices": [{"message": {"content": "RESPOSTA_FAKE"}}]})


def sobe_fake():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeHermes)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeHermes.chamadas = []
    return srv


def setup_module():
    os.environ["FAJULTO_USERNAME"] = "efrai"
    os.environ["FAJULTO_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["FAJULTO_SESSION_SECRET"] = "a" * 64
    os.environ["FAJULTO_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()


def login(client):
    r = client.post("/api/login", json={"username": "efrai", "password": "strong-example-password"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def umsg(i="ai-user-001"):
    return {"id": i, "origin": "mobile", "role": "user", "text": "olá, Júlia",
            "created_at": "2026-10-11T12:00:00.000Z", "conversation_id": "conv-ai"}


# ── Unidade: bridge ───────────────────────────────────────────────────
def test_proxy_url_bloqueia_ssrf():
    for ruim in ("http://exemplo.com/v1", "https://127.0.0.1:8645/v1",
                 "http://user:pass@127.0.0.1:8645/v1", "http://192.168.0.1:8645/v1", ""):
        try:
            hermes_bridge.proxy_url(ruim if ruim else "   ")
            raise AssertionError(f"deveria bloquear {ruim!r}")
        except hermes_bridge.BridgeErro:
            pass
    assert hermes_bridge.proxy_url("http://127.0.0.1:8645/v1").endswith("/v1")


def test_bridge_models_e_complete_no_fake():
    srv = sobe_fake()
    base = f"http://127.0.0.1:{srv.server_port}/v1"
    try:
        assert hermes_bridge.listar_modelos(base) == ["fake-model", "outro"]
        r = hermes_bridge.chat_complete(base, "fake-model",
                                        [{"role": "user", "content": "oi"}])
        assert r["texto"] == "RESPOSTA_FAKE" and "latencia_s" in r
        try:
            hermes_bridge.chat_complete(base, "modelo-inexistente",
                                        [{"role": "user", "content": "oi"}])
            raise AssertionError("modelo inválido deveria falhar")
        except hermes_bridge.BridgeErro as exc:
            assert exc.codigo == "modelo-nao-encontrado"
        assert FakeHermes.chamadas and FakeHermes.chamadas[0]["max_tokens"] >= 1
    finally:
        srv.shutdown()
        srv.server_close()


def test_bridge_stream_deltas_e_cancel():
    srv = sobe_fake()
    base = f"http://127.0.0.1:{srv.server_port}/v1"
    try:
        got = []
        r = hermes_bridge.chat_stream(base, "fake-model",
                                      [{"role": "user", "content": "oi"}],
                                      on_delta=lambda s, t: got.append((s, t)))
        assert "".join(t for _, t in got) == "Olá, sou a Júlia."
        assert [s for s, _ in got] == [1, 2]
        assert r["texto"] == "Olá, sou a Júlia."
        r2 = hermes_bridge.chat_stream(base, "fake-model",
                                       [{"role": "user", "content": "oi"}],
                                       on_delta=lambda s, t: None,
                                       deve_parar=lambda: True)
        assert r2.get("cancelada") is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_sse_fragmentado_e_done():
    ac = hermes_bridge.AcumuladorSSE()
    assert ac.alimentar(b'data: {"choices": [{"delta": {"cont') == []
    got = ac.alimentar(b'ent": "X"}}]}\n\n: vivo\n\ndata: [DONE]\n\n')
    assert got == [(1, "X")] and ac.concluido is True
    assert hermes_bridge.extrair_delta({"choices": [{"delta": {}}]}) == ""
    try:
        hermes_bridge.extrair_texto({"choices": []})
        raise AssertionError("formato ruim deveria falhar")
    except hermes_bridge.BridgeErro:
        pass


# ── Unidade: agente (idempotência, estados, migração) ──────────────────
def test_agente_ai_idempotente_sem_rechamada(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "ai.sqlite3")
    cols = [c[1] for c in db.execute("PRAGMA table_info(messages)").fetchall()]
    assert "model" in cols  # migração
    pc_agent.persist_messages(db, [umsg()])
    cfg = {"proxy": "http://127.0.0.1:9/v1", "model": "fake-model",
           "system": "s", "context": 20, "max_tokens": 50}
    chamadas = []
    monkeypatch.setattr(hermes_bridge, "chat_complete",
                        lambda *a, **k: (chamadas.append(1), {"texto": "RESP", "latencia_s": 0.1})[1])
    p = {"message_id": "ai-user-001", "conversation_id": "conv-ai"}
    r1 = pc_agent.ai_completa(db, p, cfg)
    assert r1["response_text"] == "RESP" and r1["reply_id"] == "ai-user-001-r1"
    r2 = pc_agent.ai_completa(db, p, cfg)  # replay: sem nova chamada
    assert r2.get("replay") is True and len(chamadas) == 1
    rows = {m["id"]: m for m in pc_agent.list_messages(db)}
    assert rows["ai-user-001-r1"]["role"] == "assistant"
    assert rows["ai-user-001-r1"]["text"] == "RESP"
    assert pc_agent.ai_estado(db, "x-inexistente") is None
    assert pc_agent.ai_completa(db, {"message_id": "curto", "conversation_id": "conv-ai"}, cfg)["codigo"] == "invalido"
    assert pc_agent.ai_completa(db, {"message_id": "ai-user-999", "conversation_id": "conv-ai"}, cfg)["codigo"] == "sem_mensagem"
    db.close()


# ── Unidade: relay (auth, validação, roteamento de stream) ─────────────
def test_ai_exige_auth_e_valida_modelo():
    with TestClient(server.app) as client:
        assert client.post("/api/ai", json={"message_id": "ai-user-001",
                                            "conversation_id": "conv-ai"}).status_code == 401
        csrf = login(client)
        r = client.post("/api/ai", json={"message_id": "ai-user-001",
                                         "conversation_id": "conv-ai",
                                         "model": "mau modelo!"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422
        r = client.get("/api/ai/stream?message_id=x&conversation_id=y",
                       headers={"X-CSRF-Token": csrf})
        assert r.status_code in (422, 503)


def test_ai_models_e_complete_via_agente_fake():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["FAJULTO_AGENT_TOKEN"]}) as ws:
            out = {}

            def chama_models():
                out["m"] = client.get("/api/ai/models", headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=chama_models)
            t.start()
            req = ws.receive_json()
            assert req["type"] == "ai_models"
            ws.send_json({"request_id": req["request_id"], "type": "ai_models",
                          "models": ["fake-model"], "default": "fake-model"})
            t.join(timeout=8)
            assert out["m"].json() == {"models": ["fake-model"], "default": "fake-model"}

            def chama_ai():
                out["a"] = client.post("/api/ai", json={"message_id": "ai-user-001",
                                                       "conversation_id": "conv-ai"},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=chama_ai)
            t.start()
            for _ in range(3):
                req = ws.receive_json()
                if req["type"] == "sess_revogados":
                    ws.send_json({"request_id": req["request_id"],
                                  "type": "sess_revogados", "sids": []})
                    continue
                break
            assert req["type"] == "ai"
            ws.send_json({"request_id": req["request_id"], "type": "ai_done",
                          "reply_id": "ai-user-001-r1", "response_text": "OI",
                          "model": "fake-model"})
            t.join(timeout=8)
            assert out["a"].json()["response_text"] == "OI"


def test_sync_rejeita_placeholder_de_ia_lote_inteiro():
    """Regressão: placeholder 'generating' (texto vazio) no lote dava 422 e
    travava toda a sincronização. O app agora só envia role=user pendentes;
    aqui prova-se que o lote contaminado é rejeitado e o limpo passa."""
    with TestClient(server.app) as client:
        csrf = login(client)
        contaminado = [umsg(), {"id": "x-reply-1", "origin": "mobile", "role": "assistant",
                                "text": "", "created_at": "2026-10-11T12:00:00.000Z",
                                "conversation_id": "conv-ai"}]
        r = client.post("/api/sync", json={"messages": contaminado},
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422
        limpo = client.post("/api/sync", json={"messages": [umsg()]},
                            headers={"X-CSRF-Token": csrf})
        assert limpo.status_code == 503  # passou na validação; PC offline
        assert limpo.json()["detail"].startswith("Computador desconectado")


def test_stream_delta_roteado_para_fila():
    with TestClient(server.app) as client:
        login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["FAJULTO_AGENT_TOKEN"]}) as ws:
            q = server.asyncio.Queue()
            server.relay.streams["s1"] = q
            try:
                ws.send_json({"request_id": "s1", "type": "ai_delta", "seq": 1, "trecho": "Olá"})
                ws.send_json({"request_id": "s1", "type": "ai_done", "reply_id": "r",
                              "response_text": "Olá", "model": "m"})
                for _ in range(100):
                    if q.qsize() >= 2:
                        break
                    time.sleep(0.05)
                assert q.get_nowait()["trecho"] == "Olá"
                assert q.get_nowait()["type"] == "ai_done"
            finally:
                server.relay.streams.pop("s1", None)


# ── Integração: processos reais (relay + agente + Hermes falso) ────────
def test_e2e_ai_completo_com_processos_reais():
    fake = sobe_fake()
    base = f"http://127.0.0.1:{fake.server_port}/v1"
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["FAJULTO_USERNAME"] = "efrai"
        env["FAJULTO_PASSWORD_HASH"] = os.environ["FAJULTO_PASSWORD_HASH"]
        env["FAJULTO_SESSION_SECRET"] = "a" * 64
        env["FAJULTO_AGENT_TOKEN"] = "b" * 64
        env["FAJULTO_RELAY_URL"] = "http://127.0.0.1:8941"
        env["FAJULTO_SQLITE_PATH"] = str(Path(tmp) / "ai.sqlite3")
        env["HERMES_PROXY_URL"] = base
        env["FAJULTO_AI_MODEL"] = "fake-model"
        raiz = str(Path(__file__).resolve().parents[1])
        srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app",
                                "--host", "127.0.0.1", "--port", "8941"],
                               cwd=raiz, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT)
        try:
            time.sleep(6)
            agt = subprocess.Popen([sys.executable, "pc_agent.py"], cwd=raiz, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            try:
                time.sleep(4)
                import http.cookiejar
                cj = http.cookiejar.CookieJar()
                op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

                def call(path, data=None, csrf=None):
                    req = urllib.request.Request(
                        "http://127.0.0.1:8941" + path,
                        data=json.dumps(data).encode() if data is not None else None,
                        headers={"Content-Type": "application/json"})
                    if csrf:
                        req.add_header("X-CSRF-Token", csrf)
                    with op.open(req, timeout=60) as r:
                        return json.loads(r.read().decode() or "{}")

                sess = call("/api/login", {"username": "efrai",
                                           "password": "strong-example-password"})
                csrf = sess["csrf"]
                n_antes = len(FakeHermes.chamadas)
                assert call("/api/sync", {"messages": [umsg()]}, csrf)["confirmed_ids"] == ["ai-user-001"]
                r1 = call("/api/ai", {"message_id": "ai-user-001",
                                      "conversation_id": "conv-ai"}, csrf)
                assert r1["response_text"] == "RESPOSTA_FAKE", r1
                assert len(FakeHermes.chamadas) == n_antes + 1
                r2 = call("/api/ai", {"message_id": "ai-user-001",
                                      "conversation_id": "conv-ai"}, csrf)
                assert r2["response_text"] == "RESPOSTA_FAKE"  # replay idempotente
                assert len(FakeHermes.chamadas) == n_antes + 1  # sem rechamada
                con = sqlite3.connect(env["FAJULTO_SQLITE_PATH"])
                rows = con.execute("SELECT id, role, text FROM messages ORDER BY created_at").fetchall()
                con.close()
                assert ("ai-user-001-r1", "assistant", "RESPOSTA_FAKE") in rows
                # Stream SSE real
                req = urllib.request.Request(
                    "http://127.0.0.1:8941/api/ai/stream?message_id=ai-user-002&conversation_id=conv-ai",
                    headers={"X-CSRF-Token": csrf})
                assert call("/api/sync", {"messages": [umsg("ai-user-002")]}, csrf)["confirmed_ids"] == ["ai-user-002"]
                with op.open(req, timeout=60) as r:
                    raw = b""
                    while True:
                        ch = r.read(1)
                        if not ch:
                            break
                        raw += ch
                        partes = raw.decode("utf-8", "ignore").split("\n\n")
                        completos = [p for p in partes[:-1] if p.strip()]
                        if any("event: done" in p or "event: error" in p
                               or "event: cancelled" in p for p in completos):
                            break
                    eventos = [p for p in raw.decode("utf-8").split("\n\n") if p.strip()]
                deltas = [e for e in eventos if "event: delta" in e]
                assert len(deltas) == 2, eventos
                assert any("event: done" in e and "Olá, sou a Júlia." in e for e in eventos), eventos
            finally:
                agt.terminate()
                agt.wait(timeout=15)
        finally:
            srv.terminate()
            srv.wait(timeout=15)
    fake.shutdown()
    fake.server_close()
