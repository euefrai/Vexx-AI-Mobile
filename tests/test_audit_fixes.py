"""Regression cases from the October audit; isolated data, no real providers."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import julia_auth
import model3d_catalog
import pc_agent
import research_agents
import server
import workspace_store as workspace


@pytest.fixture
def db(tmp_path):
    connection = pc_agent.open_db(tmp_path / "regression.sqlite3")
    yield connection
    connection.close()


def message(n=0, conv="chat-a", **extra):
    return dict(id=f"message-{n:06}", conversation_id=conv, origin="mobile",
                role="user", text="Synthetic content", created_at="2026-01-01T00:00:00Z", **extra)


def test_conflicting_retry_is_not_acknowledged(db):
    original = message()
    assert pc_agent.persist_messages(db, [original], "alice") == [original["id"]]
    assert pc_agent.persist_messages(db, [original], "alice") == [original["id"]]
    for field, value in (("text", "Changed"), ("conversation_id", "chat-b"), ("role", "assistant")):
        assert pc_agent.persist_messages(db, [{**original, field: value}], "alice") == []
    assert pc_agent.list_messages(db, owner="alice")[0]["text"] == original["text"]
    result = pc_agent.ai_preparar(db, dict(message_id=original["id"], conversation_id="chat-a",
        text="Changed", owner="alice"), {"model": "test"})
    assert result["codigo"] == "conflito"


def test_deletion_blocks_stale_sync_and_inflight_reply(db):
    original = message()
    for owner in ("alice", "bob"):
        pc_agent.persist_messages(db, [original], owner)
    workspace.forget_chat(db, "alice", "chat-a")
    assert pc_agent.persist_messages(db, [original], "alice") == []
    workspace.merge_records(db, [dict(id="chat-a", kind="chat", title="Stale",
        updated_at="2099-01-01T00:00:00Z", change_id="future")], "alice")
    pc_agent.ai_guardar_resposta(db, original["id"], "chat-a", "test", "reply-0001", "Late", "alice")
    pc_agent.ai_marcar(db, original["id"], "chat-a", "test", "running", owner="alice")
    assert workspace.chat_deleted(db, "alice", "chat-a")
    assert pc_agent.list_messages(db, owner="alice") == []
    assert db.execute("SELECT count(*) FROM ai_requests WHERE owner_id='alice'").fetchone()[0] == 0
    assert len(pc_agent.list_messages(db, owner="bob")) == 1


def test_history_filters_before_limit_and_paginates_without_gaps(db, monkeypatch):
    pc_agent.persist_messages(db, [message(n) for n in range(450)], "alice")
    pc_agent.persist_messages(db, [message(999, "old-chat")], "alice")
    pc_agent.persist_messages(db, [message(998)], "bob")
    async def owner(_): return "alice"
    async def exchange(payload, **kwargs):
        return {"type": "history", "messages": pc_agent.list_messages(db,
            owner=payload["owner"], conversation_id=payload["conversation_id"], before=payload["before"])}
    monkeypatch.setattr(server, "verify_session", lambda _: "")
    monkeypatch.setattr(server, "revogacao_ok", owner)
    monkeypatch.setattr(server.relay, "exchange", exchange)
    async def run():
        assert len((await server.messages(None, "old-chat"))["messages"]) == 1
        seen, cursor = [], ""
        while True:
            page = await server.messages(None, "chat-a", cursor)
            seen.extend(row["id"] for row in page["messages"])
            cursor = page["next_cursor"]
            if not cursor: break
        assert len(seen) == len(set(seen)) == 450
        for cursor in ("invalid", "e30=", "x" * 401):
            with pytest.raises(server.HTTPException) as error:
                await server.messages(None, "chat-a", cursor)
            assert error.value.status_code == 422
    asyncio.run(run())


def test_revocation_failures_do_not_disable_future_checks(monkeypatch):
    cache = {"sids": set(), "ts": 0, "suportado": True, "falhas": 0}
    calls = []
    async def exchange(*args, **kwargs):
        calls.append(1)
        if len(calls) <= 2: raise server.HTTPException(503, "offline")
        return {"type": "sess_revogados", "sids": ["revoked"]}
    monkeypatch.setattr(server, "revogados", cache)
    monkeypatch.setattr(server, "sessao_dados", lambda _: {"uid": "alice", "sid": "revoked"})
    monkeypatch.setattr(server.relay, "ws", object())
    monkeypatch.setattr(server.relay, "exchange", exchange)
    async def run():
        for status in (503, 503, 401):
            with pytest.raises(server.HTTPException) as error:
                await server.revogacao_ok(None)
            assert error.value.status_code == status
    asyncio.run(run())
    assert len(calls) == 3 and cache["suportado"]


def test_revoked_sessions_have_no_500_limit_and_legacy_logout_is_durable(db):
    db.executemany("INSERT INTO user_sessions(sid,uid,created_at,expira_em,revogada) VALUES(?,?,?,?,1)",
        [(f"revoked-{n}", "local", "2026-01-01", "2099-01-01") for n in range(501)])
    db.commit()
    julia_auth.revogar_sessao(db, "legacy-unregistered")
    revoked = julia_auth.sids_revogados(db)
    assert len(revoked) == 502
    assert "revoked-0" in revoked and "legacy-unregistered" in revoked
    path = db.execute("PRAGMA database_list").fetchone()[2]
    other = pc_agent.open_db(Path(path))
    try: assert "legacy-unregistered" in julia_auth.sids_revogados(other)
    finally: other.close()


def test_ui_states_reject_stale_values_and_page_all_rows(db):
    def state(n, value=1, date="2026-01-01T00:00:00Z"):
        return dict(k=f"state-{n:04}", message_id="message-000001", slot="0",
                    state=json.dumps({"value": value}), updated_at=date)
    for start in (0, 200, 400):
        workspace.save_ui_states(db, "alice", [state(n) for n in range(start, min(start + 200, 505))])
    assert workspace.save_ui_states(db, "alice", [state(0, 9, "2025-01-01T00:00:00Z")]) == 0
    assert workspace.save_ui_states(db, "bob", [state(0, 9, "2099-01-01T00:00:00Z")]) == 0
    seen, cursor = [], ""
    while True:
        page = workspace.ui_state_page(db, "alice", cursor)
        seen.extend(page)
        if len(page) < 200: break
        cursor = page[-1]["k"]
    assert len(seen) == 505 and json.loads(seen[0]["state"])["value"] == 1
    assert workspace.ui_state_page(db, "bob") == []
    # Equal timestamps converge deterministically in either arrival order.
    workspace.save_ui_states(db, "alice", [state(0, 3), state(0, 2)])
    assert json.loads(workspace.ui_state_page(db, "alice")[0]["state"])["value"] == 3


def test_research_media_roundtrip_and_oversize_preserves_previous_job(db):
    job = research_agents.criar_job(db, "local", "Synthetic objective", conv="chat-a", modo="rapida")
    job["midia"] = [{"url": "https://example.invalid/image.png", "tipo": "image"}]
    research_agents.salvar_job(db, job)
    previous = research_agents.carregar_job(db, "local", job["id"])
    assert previous["midia"] == job["midia"]
    job["achados"] = [{"texto": "x" * 61000}]
    with pytest.raises(ValueError, match="JSON"):
        research_agents.salvar_job(db, job)
    assert research_agents.carregar_job(db, "local", job["id"]) == previous


def test_research_size_limit_finishes_with_recoverable_checkpoint(db, monkeypatch):
    job = research_agents.criar_job(db, "local", "Synthetic objective", conv="chat-a", modo="rapida")
    job["plano"] = [{"id": "step1", "tipo": "busca", "status": "pendente", "alvo": "test"}]
    research_agents.salvar_job(db, job)
    def oversized(db, job, *args, **kwargs):
        job["achados"] = [{"texto": "x" * 61000}]
        return []
    monkeypatch.setattr(research_agents, "agente_busca", oversized)
    research_agents.executar(db, job["id"], "local", [])
    loaded = research_agents.carregar_job(db, "local", job["id"])
    assert loaded["status"] == "falhou"
    assert loaded["achados"] == []
    assert any("JSON" in error for error in loaded["erros"]), loaded["erros"]


def test_post_stream_passes_json_context_to_authenticated_handler(monkeypatch):
    received = []
    async def stream(request, **kwargs):
        server.require_csrf(request)
        received.append(kwargs)
        return {"ok": True}
    monkeypatch.setenv("JULIA_SESSION_SECRET", "synthetic-only-" * 4)
    monkeypatch.setattr(server, "ai_stream", stream)
    with TestClient(server.app) as client:
        token = server.signer().dumps({"user": "preview", "uid": "alice", "sid": ""})
        client.cookies.set("JULIA_session", token)
        body = dict(message_id="message-000001", conversation_id="chat-a", text="Private prompt", memory=0)
        assert client.post("/api/ai/stream", json=body).status_code == 403
        response = client.post("/api/ai/stream", json=body, headers={"X-CSRF-Token": server.csrf_value(token)})
        assert response.status_code == 200, response.text
        assert received[0]["text"] == body["text"] and received[0]["memory"] == 0
        assert response.request.url.query == b""


def test_catalog_does_not_substitute_distinct_models():
    assert model3d_catalog.resolver("xbox series x") == "console"
    assert model3d_catalog.resolver("xbox series s") == "xbox"
    assert model3d_catalog.resolver("motor eletrico") != "motor_v8"
    assert model3d_catalog.resolver("motor v8") == "motor_v8"


def test_research_connects_exact_validated_ip_and_rejects_rebinding(monkeypatch):
    import research
    import socket
    calls, connected = [], []
    answers = ["93.184.216.34", "127.0.0.1"]
    def dns(host, port, *args):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers.pop(0), port or 80))]
    class FakeSocket:
        def settimeout(self, value): pass
        def connect(self, address): connected.append(address)
        def close(self): pass
    monkeypatch.setattr(research.socket, "getaddrinfo", dns)
    monkeypatch.setattr(research.socket, "socket", lambda *args: FakeSocket())
    research._conectar_publico(("changing.example", 443), 1)
    assert connected == [("93.184.216.34", 443)] and len(calls) == 1
    with pytest.raises(research.ResearchErro, match="não público"):
        research._conectar_publico(("changing.example", 443), 1)
    assert len(connected) == 1
    # Initial URL validation must not allow a later private DNS answer at connect.
    answers[:] = ["93.184.216.34", "127.0.0.1"]
    research.url_segura("https://changing.example/")
    with pytest.raises(research.ResearchErro):
        research._conectar_publico(("changing.example", 443), 1)
    secure = research._HTTPSPublico("changing.example")
    assert secure.host == "changing.example"
    assert secure._context.check_hostname


def test_stream_bounds_and_memory_zero_and_disconnect_cleanup(monkeypatch):
    relay = server.AgentRelay()
    sent = []
    class Socket:
        async def send_json(self, payload):
            sent.append(payload)
            if payload["type"] == "ai_stream":
                queue = relay.streams[payload["request_id"]]
                assert queue.maxsize == 256
                queue.put_nowait({"type": "ai_delta", "seq": 1, "trecho": "Partial"})
                queue.put_nowait({"type": "ai_done", "response_text": "Complete", "reply_id": "reply-001"})
    async def owner(_): return "alice"
    monkeypatch.setattr(server, "relay", relay)
    monkeypatch.setattr(server, "require_csrf", lambda _: None)
    monkeypatch.setattr(server, "revogacao_ok", owner)
    relay.ws = Socket()
    async def run():
        response = await server.ai_stream(None, message_id="message-0001", conversation_id="chat-a", memory=0)
        chunks = [chunk async for chunk in response.body_iterator]
        assert "event: delta" in chunks[0] and "Complete" in chunks[1]
        assert sent[0]["memory"] == "0" and not relay.streams
        response = await server.ai_stream(None, message_id="message-0002", conversation_id="chat-a")
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
        assert sent[-1]["type"] == "ai_cancel" and not relay.streams
        relay.streams = {str(i): asyncio.Queue(maxsize=1) for i in range(8)}
        for queue in relay.streams.values(): queue.put_nowait({"type": "ai_delta"})
        with pytest.raises(server.HTTPException) as error:
            await server.ai_stream(None, message_id="message-0003", conversation_id="chat-a")
        assert error.value.status_code == 429
        relay.fail_pending()
        assert all(q.get_nowait()["type"] == "ai_error" for q in relay.streams.values())
    asyncio.run(run())
