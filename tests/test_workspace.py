"""Durability, conflict resolution, account boundaries and relay authorization."""
import sys
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workspace_store as workspace
import server


def record(id="project-one", kind="project", title="Estudos", **extra):
    return dict(id=id, kind=kind, title=title, updated_at="2026-10-15T12:00:00.000Z",
                change_id="change-one", **extra)


def test_projects_chats_move_rename_reopen_and_owner_isolation(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    db = sqlite3.connect(path)
    workspace.create_tables(db)
    first = record()
    chats = [record(id="chat-one", kind="chat", title="Primeiro", project_id=first["id"]),
             record(id="chat-two", kind="chat", title="Segundo", project_id=first["id"])]
    workspace.merge_records(db, [first, *chats], "alice")
    assert workspace.list_records(db, "bob") == []
    # Same identifiers are valid for another user, with independent contents.
    workspace.merge_records(db, [record(title="Bob")], "bob")
    renamed = dict(first, title="Projeto final", updated_at="2026-10-15T12:01:00.000Z")
    moved = dict(chats[0], project_id="", updated_at="2026-10-15T12:02:00.000Z")
    workspace.merge_records(db, [renamed, moved], "alice")
    # Stale offline data cannot undo newer organization, even after reconnect.
    workspace.merge_records(db, [first, *chats], "alice")
    db.close()
    db = sqlite3.connect(path)
    data = {r["id"]: r for r in workspace.list_records(db, "alice")}
    assert data["project-one"]["title"] == "Projeto final"
    assert data["chat-one"]["project_id"] == ""
    assert data["chat-two"]["project_id"] == "project-one"
    assert workspace.list_records(db, "bob")[0]["title"] == "Bob"
    db.close()


def test_retries_are_idempotent_ties_converge_and_invalid_batch_is_atomic():
    db = sqlite3.connect(":memory:")
    workspace.create_tables(db)
    older = record()
    newer = dict(older, change_id="change-z", title="Novo nome")
    workspace.merge_records(db, [newer, older, newer], "alice")
    assert len(workspace.list_records(db, "alice")) == 1
    assert workspace.list_records(db, "alice")[0]["title"] == "Novo nome"
    with pytest.raises(ValidationError):
        workspace.merge_records(db, [record(id="project-valid"), record(id="project-bad", title="   ")], "alice")
    assert len(workspace.list_records(db, "alice")) == 1
    with pytest.raises(ValidationError):
        workspace.merge_records(db, [record(project_id="nested-project")], "alice")
    db.close()


def test_offline_chat_deletion_is_durable_and_does_not_delete_other_accounts(tmp_path):
    import pc_agent
    db = pc_agent.open_db(tmp_path / "deleted.sqlite3")
    for owner in ("alice", "bob"):
        pc_agent.persist_messages(db, [dict(id=owner + "-message-one", conversation_id="chat-one",
            origin="mobile", role="user", text="private", created_at="2026-10-15T12:00:00.000Z")], owner)
    original = record(id="chat-one", kind="chat", title="Conversa")
    workspace.merge_records(db, [original], "alice")
    deleted = dict(original, deleted=True, updated_at="2026-10-15T12:01:00.000Z")
    workspace.merge_records(db, [deleted, original], "alice")
    assert pc_agent.list_messages(db, owner="alice") == []
    assert len(pc_agent.list_messages(db, owner="bob")) == 1
    assert workspace.list_records(db, "alice")[0]["deleted"] is True
    db.close()


def test_relay_requires_session_csrf_and_uses_authenticated_owner(monkeypatch):
    monkeypatch.setenv("JULIA_SESSION_SECRET", "workspace-tests-only-" * 4)
    monkeypatch.setenv("JULIA_USERNAME", "preview")
    db = sqlite3.connect(":memory:", check_same_thread=False)
    workspace.create_tables(db)
    calls = []

    async def exchange(payload, **kwargs):
        calls.append(payload)
        workspace.merge_records(db, payload["records"], payload["owner"])
        return {"type": "workspace_synced", "records": workspace.list_records(db, payload["owner"])}

    async def revoked(request):
        return server.sessao_usuario(request)

    monkeypatch.setattr(server.relay, "exchange", exchange)
    monkeypatch.setattr(server, "revogacao_ok", revoked)
    with TestClient(server.app) as client:
        body = {"records": [record()], "owner": "bob"}
        assert client.post("/api/workspace/sync", json=body).status_code == 401
        token = server.signer().dumps({"user": "preview", "uid": "alice", "sid": ""})
        client.cookies.set("JULIA_session", token)
        assert client.post("/api/workspace/sync", json=body).status_code == 403
        csrf = server.csrf_value(token)
        response = client.post("/api/workspace/sync", json=body, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200, response.text
        assert calls[0]["owner"] == "alice"
        assert response.json()["records"][0]["title"] == "Estudos"
        assert workspace.list_records(db, "bob") == []
    db.close()
