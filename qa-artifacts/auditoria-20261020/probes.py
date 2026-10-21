"""Read-only product audit: synthetic data in temporary SQLite, no production access."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pc_agent
import server
import workspace_store
import julia_auth
import research_agents
import model3d

results = {}

async def run():
    with tempfile.TemporaryDirectory(prefix="vexx-audit-") as folder:
        db = pc_agent.open_db(Path(folder) / "audit.sqlite3")
        def msg(mid, conv, when):
            return dict(id=mid, conversation_id=conv, origin="mobile", role="user",
                        text="synthetic audit", created_at=when)
        old = msg("audit-old-message", "audit-old-chat", "2026-01-01T12:00:00Z")
        rows = [old] + [msg(f"audit-new-{n:04}", "audit-new-chat", f"2026-02-01T12:00:{n % 60:02}Z") for n in range(200)]
        pc_agent.persist_messages(db, rows, "local")
        async def owner(_): return "local"
        async def exchange(payload, **kwargs):
            return {"type": "history", "messages": pc_agent.list_messages(db, owner="local")}
        with patch.object(server, "verify_session", lambda _: ""), patch.object(server, "revogacao_ok", owner), patch.object(server.relay, "exchange", exchange):
            history = await server.messages(None, conversation_id="audit-old-chat")
        results["history"] = {"stored_old_chat": db.execute("SELECT count(*) FROM messages WHERE conversation_id='audit-old-chat'").fetchone()[0], "api_returned": len(history["messages"])}
        record = dict(id="audit-old-chat", kind="chat", title="Audit", deleted=True,
                      updated_at="2026-10-20T00:00:00Z", change_id="audit-delete")
        workspace_store.merge_records(db, [record], "local")
        before = db.execute("SELECT count(*) FROM messages WHERE conversation_id='audit-old-chat'").fetchone()[0]
        pc_agent.persist_messages(db, [old], "local")
        results["deleted_chat_resync"] = {"before": before, "after_stale_sync": db.execute("SELECT count(*) FROM messages WHERE conversation_id='audit-old-chat'").fetchone()[0], "tombstone_still_deleted": workspace_store.list_records(db, "local")[0]["deleted"]}
        # Conflicting retry receives ACK despite keeping different data.
        changed = {**old, "text": "different synthetic content"}
        ack = pc_agent.persist_messages(db, [changed], "local")
        stored = db.execute("SELECT text FROM messages WHERE id=?", (old["id"],)).fetchone()[0]
        results["conflicting_message_ack"] = {"acknowledged": old["id"] in ack, "stored_matches_submitted": stored == changed["text"]}
        db.executemany("INSERT INTO user_sessions(sid,uid,created_at,expira_em,revogada) VALUES(?,?,?,?,1)",
                       [(f"audit-sid-{n}", "local", "2026-10-20", "2099-01-01",) for n in range(501)])
        db.commit()
        ids = julia_auth.sids_revogados(db)
        results["revocation_limit"] = {"stored": 501, "returned": len(ids), "oldest_revoked_included": "audit-sid-0" in ids}
        job = research_agents.criar_job(db, "local", "Synthetic audit objective", conv="audit-job", modo="rapida")
        job["midia"] = [{"url": "https://audit.invalid/image.png", "tipo": "image"}]
        research_agents.salvar_job(db, job)
        loaded = research_agents.carregar_job(db, "local", job["id"])
        results["uncommitted_media_persistence"] = {"saved_items": len(job["midia"]), "loaded_items": len(loaded.get("midia", []))}
        job["achados"] = [{"texto": "x" * 61000}]
        research_agents.salvar_job(db, job)
        try:
            research_agents.carregar_job(db, "local", job["id"])
            error = None
        except research_agents.AgentErro as exc:
            error = str(exc)
        results["research_json_truncation"] = {"valid_input_json_length": len(json.dumps(job["achados"])), "load_error": error}
        db.close()
    calls = []
    async def unavailable(*args, **kwargs):
        calls.append(1)
        raise server.HTTPException(503, "synthetic offline")
    cache = {"sids": set(), "ts": 0, "suportado": True, "falhas": 0}
    with patch.object(server, "revogados", cache), patch.object(server.relay, "ws", object()), patch.object(server, "sessao_dados", lambda _: {"uid": "local", "sid": "revoked-but-not-cached"}), patch.object(server.relay, "exchange", unavailable):
        allowed = [await server.revogacao_ok(None) for _ in range(3)]
    results["revocation_after_timeouts"] = {"allowed_requests": len(allowed), "rpc_calls": len(calls), "checks_enabled": cache["suportado"]}
    results["model3d_mismatch"] = []
    for question in ("Mostre um Xbox Series X em 3D", "Mostre um motor elétrico em 3D"):
        response = model3d.respond(question)
        results["model3d_mismatch"].append({"question": question, "title": response[1]["title"]})

asyncio.run(run())
print(json.dumps(results, indent=2))
