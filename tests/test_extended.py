"""Extended real-behavior tests: validation, agent-side safety, concurrency, lockout."""
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import pc_agent
import server


def setup_module():
    os.environ["FAJULTO_USERNAME"] = "efrai"
    os.environ["FAJULTO_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["FAJULTO_SESSION_SECRET"] = "a" * 64
    os.environ["FAJULTO_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()


def authenticate(client):
    r = client.post("/api/login", json={"username": "efrai", "password": "strong-example-password"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def msg(**over):
    base = {"id": "message001", "origin": "mobile", "role": "user",
            "text": "testando offline", "created_at": "2026-10-10T20:00:00.000Z",
            "conversation_id": "conversation-001"}
    base.update(over)
    return base


def test_invalid_payloads_rejected_with_422():
    with TestClient(server.app) as client:
        csrf = authenticate(client)
        bad_cases = [
            msg(origin="extension"),   # only mobile accepted
            msg(role="system"),        # only user|assistant
            msg(id="curto"),           # min 8 chars
            msg(text=""),              # min 1 char
            msg(conversation_id="ab"),  # min 3 chars
            msg(text="x" * 10001),     # max 10000 chars
        ]
        for bad in bad_cases:
            r = client.post("/api/sync", json={"messages": [bad]},
                            headers={"X-CSRF-Token": csrf})
            assert r.status_code == 422, (bad, r.status_code, r.text[:200])


def test_agent_stores_adversarial_text_literally_without_damage(tmp_path):
    db = pc_agent.open_db(tmp_path / "adv.sqlite3")
    rows = [
        msg(id="adv-xss-001", text="<script>alert(1)</script>"),
        msg(id="adv-sqli-001", text="'; DROP TABLE messages;--"),
        msg(id="adv-bad-001", origin="extension", text="must not persist"),
        "not-a-dict",
    ]
    confirmed = pc_agent.persist_messages(db, rows)
    assert confirmed == ["adv-xss-001", "adv-sqli-001"]
    stored = {m["id"]: m["text"] for m in pc_agent.list_messages(db)}
    assert stored["adv-xss-001"] == "<script>alert(1)</script>"  # safe: frontend renders via textContent
    assert stored["adv-sqli-001"] == "'; DROP TABLE messages;--"  # safe: parameterized query
    assert "adv-bad-001" not in stored
    tables = db.execute("select name from sqlite_master where type='table'").fetchall()
    assert ("messages",) in tables
    # Idempotent under retry (COMMIT happened, ACK lost scenario).
    assert pc_agent.persist_messages(db, rows[:1]) == ["adv-xss-001"]
    assert len(pc_agent.list_messages(db)) == 2
    db.close()


def test_concurrent_duplicate_sync_both_confirm_no_crash():
    with TestClient(server.app) as client:
        csrf = authenticate(client)
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["FAJULTO_AGENT_TOKEN"]}) as ws:
            results = []

            def submit():
                results.append(client.post("/api/sync", json={"messages": [msg()]},
                                           headers={"X-CSRF-Token": csrf}))

            threads = [threading.Thread(target=submit) for _ in range(2)]
            for t in threads:
                t.start()
            acks = 0
            for _ in range(4):
                req = ws.receive_json()
                if req["type"] == "sess_revogados":
                    ws.send_json({"request_id": req["request_id"],
                                  "type": "sess_revogados", "sids": []})
                    continue
                assert req["type"] == "sync"
                ws.send_json({"request_id": req["request_id"], "type": "ack",
                              "confirmed_ids": ["message001"]})
                acks += 1
                if acks == 2:
                    break
            assert acks == 2
            for t in threads:
                t.join(timeout=8)
            assert not any(t.is_alive() for t in threads)
            assert len(results) == 2
            for r in results:
                assert r.status_code == 200, r.text
                assert r.json()["confirmed_ids"] == ["message001"]


def test_z_brute_force_lockout_after_five_failures():
    # MUST stay last: it intentionally trips the in-memory IP rate limiter.
    server.login_failures.clear()
    with TestClient(server.app) as client:
        codes = [client.post("/api/login",
                             json={"username": "efrai", "password": "wrong"}).status_code
                 for _ in range(6)]
        assert codes == [401, 401, 401, 401, 401, 429], codes
