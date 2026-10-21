"""Small compatibility fixes; no external service or real user data."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research
import server
import workspace_store as workspace


def test_chat_accepts_model_alias_already_supported_by_agent():
    model = "provider/model~fast:free"
    assert pc_agent._lista_fallbacks(model) == [model]
    body = server.AIRequest(message_id="test-model-001", conversation_id="test-chat", model=model)
    assert body.model == model
    for invalid in ("model with spaces", "model\nheader", "<script>"):
        with pytest.raises(ValidationError):
            server.AIRequest(message_id="test-model-001", conversation_id="test-chat", model=invalid)


@pytest.mark.parametrize("port", ["abc", "-1", "0", "65536"])
def test_bad_url_port_is_a_controlled_error_before_dns(monkeypatch, port):
    def unexpected_dns(host):
        pytest.fail("Invalid URL should not reach DNS")
    monkeypatch.setattr(research, "_ips_globais", unexpected_dns)
    with pytest.raises(research.ResearchErro) as error:
        research.url_segura(f"https://example.invalid:{port}/article")
    assert error.value.codigo == "ssrf"


def test_valid_custom_port_keeps_public_host_validation(monkeypatch):
    seen = []
    monkeypatch.setattr(research, "_ips_globais", seen.append)
    url = "https://example.invalid:8443/article"
    assert research.url_segura(url) == url
    assert seen == ["example.invalid"]


def test_ui_timestamp_is_validated_and_normalized_before_relay(monkeypatch):
    from fastapi.testclient import TestClient
    calls = []
    async def owner(_): return "alice"
    async def exchange(payload, **kwargs):
        calls.append(payload)
        return {"type": "ui_state_saved", "saved": 1}
    monkeypatch.setattr(server, "require_csrf", lambda _: None)
    monkeypatch.setattr(server, "revogacao_ok", owner)
    monkeypatch.setattr(server.relay, "exchange", exchange)
    item = dict(k="message-001#quiz", message_id="message-001", slot="quiz", state={})
    with TestClient(server.app) as client:
        for timestamp in ("not-a-real-date", "2026-10-21T10:00:00", "2026-99-21T10:00:00Z"):
            response = client.post("/api/ui-state", json={"states": [{**item, "updated_at": timestamp}]})
            assert response.status_code == 422
        assert calls == []
        response = client.post("/api/ui-state", json={"states": [{**item, "updated_at": "2026-10-21T10:00:00-03:00"}]})
        assert response.status_code == 200
        assert calls[0]["states"][0]["updated_at"] == "2026-10-21T13:00:00.000Z"


def test_delete_wins_over_rename_attempt_during_metadata_read(tmp_path):
    import sqlite3
    from types import SimpleNamespace
    path = tmp_path / "delete-race.sqlite3"
    db = pc_agent.open_db(path)
    other = sqlite3.connect(path, timeout=0.05)
    original = dict(id="chat-race", kind="chat", title="Original", change_id="change-001",
                    updated_at="2026-01-01T00:00:00Z")
    workspace.merge_records(db, [original], "alice")
    attempts = []
    class ConcurrentRename:
        @property
        def in_transaction(self): return db.in_transaction
        def __enter__(self): db.__enter__(); return self
        def __exit__(self, *args): return db.__exit__(*args)
        def execute(self, sql, params=()):
            result = db.execute(sql, params)
            if sql.startswith("SELECT payload") and not attempts:
                old = result.fetchone()
                result.close()
                try:
                    workspace.merge_records(other, [{**original, "title": "Concurrent rename",
                        "updated_at": "2099-01-01T00:00:00Z"}], "alice")
                    attempts.append("renamed")
                except sqlite3.OperationalError as exc:
                    assert "locked" in str(exc)
                    attempts.append("locked")
                return SimpleNamespace(fetchone=lambda: old)
            return result
    try:
        workspace.forget_chat(ConcurrentRename(), "alice", "chat-race")
        assert attempts == ["locked"]
        assert workspace.chat_deleted(db, "alice", "chat-race")
        workspace.merge_records(other, [{**original, "updated_at": "2099-01-01T00:00:00Z"}], "alice")
        assert workspace.chat_deleted(db, "alice", "chat-race")
    finally:
        other.close()
        db.close()
