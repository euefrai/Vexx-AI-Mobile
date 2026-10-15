"""Integração Hermes Proxy (Opção A): bridge, agente, relay e SQLite.

Unidade usa um servidor HTTP OpenAI-compatible falso (stdlib). Integração usa
processos reais: uvicorn (server.py) + pc_agent.py de verdade, com o falso só
na fronteira Hermes (marcador `e2e_real`; pula sem uvicorn; readiness com
polling e log dos filhos em falha).
Status Hermes real em 15/10/2026: proxy em 127.0.0.1:8645 lista modelos
(`/v1/models` OK), mas a inferência falhou — `laguna-s-2.1:free` devolveu
resposta vazia e outros slugs deram "modelo não encontrado no proxy".
Inferência real: BLOQUEADA no provedor; sem quota gasta em testes.
"""
import http.cookiejar
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from e2e_processes import LoggedProcess, available_loopback_port
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
    srv._serve_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    srv._serve_thread.start()
    FakeHermes.chamadas = []
    return srv


def encerra_fake(srv):
    srv.shutdown()
    srv.server_close()
    srv._serve_thread.join(timeout=5)
    if srv._serve_thread.is_alive():
        raise RuntimeError("fake Hermes server thread did not stop")


def setup_module():
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
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
        encerra_fake(srv)


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
        encerra_fake(srv)


def test_bridge_stream_emite_delta_antes_do_fim_da_resposta():
    class StreamSSELento(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for texto in ("um", "dois", "três"):
                corpo = json.dumps(
                    {"choices": [{"delta": {"content": texto}}]}).encode()
                evento = b"data: " + corpo + b"\n\n"
                self.wfile.write(f"{len(evento):X}\r\n".encode() + evento + b"\r\n")
                self.wfile.flush()
                time.sleep(0.3)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), StreamSSELento)
    serve_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    serve_thread.start()
    tempos_delta = []
    inicio = time.monotonic()
    try:
        resultado = hermes_bridge.chat_stream(
            f"http://127.0.0.1:{srv.server_port}/v1", "fake-model", [],
            on_delta=lambda seq, trecho: tempos_delta.append(time.monotonic() - inicio),
            timeout=5.0)
        duracao = time.monotonic() - inicio
        assert resultado["texto"] == "umdoistrês"
        assert len(tempos_delta) == 3
        assert tempos_delta[0] < duracao - 0.2
    finally:
        srv.shutdown()
        srv.server_close()
        serve_thread.join(timeout=5)
        if serve_thread.is_alive():
            raise RuntimeError("streaming fake server thread did not stop")


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


def test_ai_preparar_piggyback_primeira_tentativa(tmp_path):
    """Corrida sync→IA: sem a linha no PC, o texto do pedido persiste e segue."""
    db = pc_agent.open_db(tmp_path / "piggy.sqlite3")
    base = {"message_id": "pg-user-001", "conversation_id": "conv-pg", "owner": "u-x"}
    r = pc_agent.ai_preparar(db, dict(base), {"model": "m", "context": 5, "max_tokens": 10})
    assert r["codigo"] == "sem_mensagem"  # sem texto: continua falhando
    r = pc_agent.ai_preparar(db, dict(base, text="olá, Júlia",
                                      created_at="2026-10-16T10:00:00.000Z"),
                             {"model": "m", "context": 5, "max_tokens": 10})
    assert r["user_text"] == "olá, Júlia" and r["reply_id"] == "pg-user-001-r1"
    row = db.execute("SELECT role, text FROM messages WHERE id='pg-user-001'").fetchone()
    assert row == ("user", "olá, Júlia")  # persistida com as regras do sync
    vazio = dict(base, message_id="pg-user-002", text="")
    assert pc_agent.ai_preparar(db, vazio,  # texto vazio não salva
                                {"model": "m", "context": 5, "max_tokens": 10})["codigo"] == "sem_mensagem"
    # isolamento: piggyback de outro dono não lê nem escreve fora
    r = pc_agent.ai_preparar(db, dict(base, text="outro", owner="u-y"),
                             {"model": "m", "context": 5, "max_tokens": 10})
    assert r["user_text"] == "outro"
    assert db.execute("SELECT COUNT(*) FROM messages WHERE owner_id='u-y'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM messages WHERE id='pg-user-001'").fetchone()[0] == 2
    db.close()


def test_migracao_pk_por_dono_preserva_dados(tmp_path):
    import sqlite3 as _sq
    caminho = tmp_path / "legado.sqlite3"
    con = _sq.connect(caminho)
    con.execute("""CREATE TABLE messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        created_at TEXT NOT NULL, received_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local')""")
    con.execute("INSERT INTO messages VALUES ('m1abcdef','c','mobile','user','oi','2026-10-01T10:00:00','t','local')")
    con.execute("""CREATE TABLE ai_requests (
        user_message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL, reply_id TEXT,
        response_text TEXT, error TEXT, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'local')""")
    con.execute("INSERT INTO ai_requests VALUES ('m1abcdef','c','m','completed','m1abcdef-r1','R','','t','t','local')")
    con.commit()
    con.close()
    db = pc_agent.open_db(caminho)  # migra
    assert db.execute("SELECT text FROM messages WHERE id='m1abcdef'").fetchone()[0] == "oi"
    assert db.execute("SELECT response_text FROM ai_requests WHERE user_message_id='m1abcdef'").fetchone()[0] == "R"
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='messages'").fetchone()[0]
    assert "PRIMARY KEY (owner_id, id)" in sql
    # agora o mesmo id serve a outro dono sem colidir
    assert pc_agent.persist_messages(db, [{"id": "m1abcdef", "conversation_id": "conv-leg",
                                           "origin": "mobile", "role": "user", "text": "outro",
                                           "created_at": "2026-10-16T10:00:00.000Z"}], "u-z") == ["m1abcdef"]
    assert db.execute("SELECT COUNT(*) FROM messages WHERE id='m1abcdef'").fetchone()[0] == 2
    assert pc_agent.ai_preparar(db, {"message_id": "m1abcdef", "conversation_id": "conv-leg",
                                     "owner": "u-z", "text": "outro"},
                                {"model": "m", "context": 5, "max_tokens": 10})["user_text"] == "outro"
    db.close()


# ── Unidade: relay (auth, validação, roteamento de stream) ─────────────
def test_ai_piggyback_text_atravessa_relay():
    """O texto acompanha o pedido de IA até o agente (anti-corrida sync→IA)."""
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            out = {}

            def chama_ai():
                out["a"] = client.post("/api/ai", json={"message_id": "pg-relay-001",
                                                       "conversation_id": "conv-pg",
                                                       "text": "olá relay",
                                                       "created_at": "2026-10-16T10:00:00.000Z"},
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
            assert req.get("text") == "olá relay"  # piggyback presente
            assert req.get("owner") == "local"  # dono da sessão, nunca do cliente
            assert "text" not in str(req.get("model", ""))  # sem mistura
            ws.send_json({"request_id": req["request_id"], "type": "ai_done",
                          "reply_id": "pg-relay-001-r1", "response_text": "OI",
                          "model": "fake-model"})
            t.join(timeout=8)
            assert out["a"].json()["response_text"] == "OI"


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
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
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
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
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


def test_stream_encaminha_texto_piggyback():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            out = {}

            def chama_stream():
                try:
                    with client.stream("GET", "/api/ai/stream?message_id=pg-stream-001"
                                            "&conversation_id=conv-pg&text=ola+stream",
                                       headers={"X-CSRF-Token": csrf}) as r:
                        out["status"] = r.status_code
                        for _ in r.iter_bytes():
                            break
                except Exception as exc:
                    out["err"] = type(exc).__name__

            t = threading.Thread(target=chama_stream)
            t.start()
            for _ in range(60):
                req = ws.receive_json()
                if req.get("type") == "sess_revogados":
                    ws.send_json({"request_id": req["request_id"],
                                  "type": "sess_revogados", "sids": []})
                    continue
                break
            assert req["type"] == "ai_stream"
            assert req.get("text") == "ola stream"  # piggyback no stream
            ws.send_json({"request_id": req["request_id"], "type": "ai_error",
                          "error": "x", "codigo": "indisponivel"})
            t.join(timeout=10)


# ── Integração: processos reais (relay + agente + Hermes falso) ────────
def _aguardar_servico(url, cond, timeout, log_path, nome):
    """Polling de readiness (nunca sleep fixo): sobe quando pronto ou falha
    mostrando a causa + cauda do log do filho (antes era URLError opaco)."""
    inicio = time.monotonic()
    ultimo = None
    while time.monotonic() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if cond(json.loads(r.read().decode() or "{}")):
                    return
                ultimo = "resposta sem pronto"
        except Exception as exc:
            ultimo = exc
        time.sleep(0.5)
    cauda = ""
    try:
        cauda = Path(log_path).read_text(encoding="utf-8", errors="replace")[-3000:]
    except OSError:
        pass
    raise AssertionError(f"{nome} não ficou pronto em {url} ({ultimo}); log:\n{cauda}")


@pytest.mark.e2e_real
def test_e2e_ai_completo_com_processos_reais(tmp_path):
    if shutil.which(sys.executable) is None:
        pytest.skip("interpretador indisponível")
    import importlib.util
    if importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn ausente: e2e exige relay real")
    fake = sobe_fake()
    base = f"http://127.0.0.1:{fake.server_port}/v1"
    porta = available_loopback_port()
    try:
        env = dict(os.environ)
        env["JULIA_USERNAME"] = "efrai"
        env["JULIA_PASSWORD_HASH"] = os.environ["JULIA_PASSWORD_HASH"]
        env["JULIA_SESSION_SECRET"] = "a" * 64
        env["JULIA_AGENT_TOKEN"] = "b" * 64
        env["JULIA_RELAY_URL"] = f"http://127.0.0.1:{porta}"
        env["JULIA_SQLITE_PATH"] = str(tmp_path / "ai.sqlite3")
        env["HERMES_PROXY_URL"] = base
        env["JULIA_AI_MODEL"] = "fake-model"
        raiz = str(Path(__file__).resolve().parents[1])
        relay_log = tmp_path / "relay.log"
        agent_log = tmp_path / "agent.log"
        with LoggedProcess(
            [sys.executable, "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", str(porta)],
            relay_log, cwd=raiz, env=env,
        ):
            _aguardar_servico(
                f"http://127.0.0.1:{porta}/api/diag", lambda c: True,
                30.0, relay_log, "relay",
            )
            with LoggedProcess(
                [sys.executable, "pc_agent.py"],
                agent_log, cwd=raiz, env=env,
            ):
                _aguardar_servico(
                    f"http://127.0.0.1:{porta}/api/diag",
                    lambda c: c.get("pc_online") is True,
                    30.0, agent_log, "agente",
                )
                cj = http.cookiejar.CookieJar()
                op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

                def call(path, data=None, csrf=None):
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{porta}" + path,
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
                con = sqlite3.connect(env["JULIA_SQLITE_PATH"])
                try:
                    rows = con.execute(
                        "SELECT id, role, text FROM messages ORDER BY created_at"
                    ).fetchall()
                finally:
                    con.close()
                assert ("ai-user-001-r1", "assistant", "RESPOSTA_FAKE") in rows
                req = urllib.request.Request(
                    f"http://127.0.0.1:{porta}/api/ai/stream"
                    "?message_id=ai-user-002&conversation_id=conv-ai",
                    headers={"X-CSRF-Token": csrf})
                assert call(
                    "/api/sync", {"messages": [umsg("ai-user-002")]}, csrf
                )["confirmed_ids"] == ["ai-user-002"]
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
                    eventos = [
                        p for p in raw.decode("utf-8").split("\n\n") if p.strip()
                    ]
                deltas = [e for e in eventos if "event: delta" in e]
                assert len(deltas) == 2, eventos
                assert any(
                    "event: done" in e and "Olá, sou a Júlia." in e
                    for e in eventos
                ), eventos
    finally:
        encerra_fake(fake)


# ── FASE 3 (V4.3.1): fallback, erros e circuit breaker ──────────────
def test_bridge_mapeia_quota_e_pedido(monkeypatch):
    import urllib.error

    def falso_402(*a, **k):
        raise urllib.error.HTTPError("http://x", 402, "limite", {}, None)

    def falso_422(*a, **k):
        raise urllib.error.HTTPError("http://x", 422, "ruim", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", falso_402)
    try:
        hermes_bridge.chat_complete("http://127.0.0.1:8645/v1", "m", [])
        raise AssertionError("402 deveria falhar")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "quota"
    monkeypatch.setattr(urllib.request, "urlopen", falso_422)
    try:
        hermes_bridge.chat_complete("http://127.0.0.1:8645/v1", "m", [])
        raise AssertionError("422 deveria falhar")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "pedido"


def test_tentar_modelos_usa_proximo_e_registra(monkeypatch):
    hermes_bridge._CIRCUITO.clear()
    chamadas = []

    def falso(base, modelo, messages, timeout=60.0, max_tokens=2000):
        chamadas.append(modelo)
        if modelo == "ruim-vazio":
            raise hermes_bridge.BridgeErro("vazia", "vazia")
        return {"texto": "OK", "latencia_s": 0.1}

    monkeypatch.setattr(hermes_bridge, "chat_complete", falso)
    monkeypatch.setattr(hermes_bridge.time, "sleep", lambda s: None)
    res = hermes_bridge.tentar_modelos("http://127.0.0.1:1/v1", ["ruim-vazio", "bom"],
                                       [{"role": "user", "content": "oi"}])
    assert res["model_usado"] == "bom" and res["texto"] == "OK"
    assert [t["model"] for t in res["tentativas"]] == ["ruim-vazio"]
    assert res["tentativas"][0]["codigo"] == "vazia"
    assert chamadas == ["ruim-vazio", "bom"]
    assert "http://127.0.0.1:1/v1" not in hermes_bridge._CIRCUITO  # sucesso limpa


def test_tentar_modelos_para_em_auth_e_falha_total(monkeypatch):
    hermes_bridge._CIRCUITO.clear()
    chamadas = []

    def falso_auth(base, modelo, messages, timeout=60.0, max_tokens=2000):
        chamadas.append(modelo)
        raise hermes_bridge.BridgeErro("negado", "auth")

    monkeypatch.setattr(hermes_bridge, "chat_complete", falso_auth)
    try:
        hermes_bridge.tentar_modelos("http://127.0.0.1:2/v1", ["a", "b"], [])
        raise AssertionError("auth deveria parar")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "auth" and chamadas == ["a"]

    def falso_404(base, modelo, messages, timeout=60.0, max_tokens=2000):
        raise hermes_bridge.BridgeErro("nf", "modelo-nao-encontrado")

    monkeypatch.setattr(hermes_bridge, "chat_complete", falso_404)
    monkeypatch.setattr(hermes_bridge.time, "sleep", lambda s: None)
    try:
        hermes_bridge.tentar_modelos("http://127.0.0.1:3/v1", ["a", "b"], [])
        raise AssertionError("tudo 404 deveria falhar")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "todos_falharam" and "JULIA_AI_MODEL" in str(exc)


def test_circuito_abre_apos_falhas_repetidas(monkeypatch):
    hermes_bridge._CIRCUITO.clear()
    chamadas = []

    def falso(base, modelo, messages, timeout=60.0, max_tokens=2000):
        chamadas.append(modelo)
        raise hermes_bridge.BridgeErro("x", "provedor")

    monkeypatch.setattr(hermes_bridge, "chat_complete", falso)
    monkeypatch.setattr(hermes_bridge.time, "sleep", lambda s: None)
    base = "http://127.0.0.1:4/v1"
    for _ in range(4):
        try:
            hermes_bridge.tentar_modelos(base, ["a"], [])
        except hermes_bridge.BridgeErro:
            pass
    antes = len(chamadas)
    try:
        hermes_bridge.tentar_modelos(base, ["a"], [])
        raise AssertionError("circuito deveria estar aberto")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "circuito_aberto" and len(chamadas) == antes
    hermes_bridge._CIRCUITO.clear()


def test_stream_fb_troca_antes_do_primeiro_delta(monkeypatch):
    hermes_bridge._CIRCUITO.clear()

    def falso(base, modelo, messages, on_delta, deve_parar=None,
              timeout=180.0, max_tokens=2000):
        if modelo == "morto":
            raise hermes_bridge.BridgeErro("caiu", "indisponivel")
        on_delta(1, "oi")
        return {"texto": "oi", "latencia_s": 0.1}

    monkeypatch.setattr(hermes_bridge, "chat_stream", falso)
    monkeypatch.setattr(hermes_bridge.time, "sleep", lambda s: None)
    got = []
    res = hermes_bridge.chat_stream_fb("http://127.0.0.1:5/v1", ["morto", "vivo"], [],
                                       lambda s, t: got.append(t))
    assert res["model_usado"] == "vivo" and got == ["oi"]


def test_stream_fb_nao_troca_no_meio(monkeypatch):
    hermes_bridge._CIRCUITO.clear()

    def falso(base, modelo, messages, on_delta, deve_parar=None,
              timeout=180.0, max_tokens=2000):
        on_delta(1, "metade ")
        raise hermes_bridge.BridgeErro("caiu no meio", "indisponivel")

    monkeypatch.setattr(hermes_bridge, "chat_stream", falso)
    got = []
    try:
        hermes_bridge.chat_stream_fb("http://127.0.0.1:6/v1", ["a", "b"], [],
                                     lambda s, t: got.append(t))
        raise AssertionError("erro no meio deve propagar")
    except hermes_bridge.BridgeErro as exc:
        assert exc.codigo == "indisponivel" and got == ["metade "]
    hermes_bridge._CIRCUITO.clear()


def test_stream_vazio_nunca_e_sucesso():
    # chat_stream real contra fake sem deltas: erro, jamais done vazio.
    glyph = sobe_fake()
    base = f"http://127.0.0.1:{glyph.server_port}/v1"
    orig = FakeHermes.stream_deltas
    FakeHermes.stream_deltas = []
    try:
        try:
            hermes_bridge.chat_stream(base, "fake-model", [], lambda s, t: None, timeout=10.0)
            raise AssertionError("stream vazio deveria falhar")
        except hermes_bridge.BridgeErro as exc:
            assert exc.codigo == "vazia"
    finally:
        FakeHermes.stream_deltas = orig
        encerra_fake(glyph)


def test_fallbacks_config_e_modelos_tentativa(monkeypatch):
    assert pc_agent._lista_fallbacks("a, b,, a, " + "x" * 200) == ["a", "b", "x" * 120]
    assert pc_agent._lista_fallbacks("x, rm -rf;, a") == ["x", "a"]
    assert pc_agent._lista_fallbacks("") == []
    cfg = {"model": "pref", "fallbacks": ["fb1", "pref", "fb2"], "max_tokens": 10,
           "proxy": "http://127.0.0.1:7/v1"}
    assert pc_agent.modelos_tentativa(cfg, "") == ["pref", "fb1", "fb2"]
    assert pc_agent.modelos_tentativa(cfg, "outro") == ["outro", "fb1", "pref", "fb2"]
    vistos = {}

    def falso_tentar(base, modelos, messages, timeout_por_tentativa=60.0, max_tokens=2000):
        vistos["modelos"] = modelos
        return {"texto": "R", "model_usado": "fb1", "latencia_s": 0.1}

    monkeypatch.setattr(hermes_bridge, "tentar_modelos", falso_tentar)
    res = pc_agent.gerar_texto(cfg, [{"role": "user", "content": "oi"}], preferido="outro")
    assert vistos["modelos"] == ["outro", "fb1", "pref", "fb2"] and res["model_usado"] == "fb1"
