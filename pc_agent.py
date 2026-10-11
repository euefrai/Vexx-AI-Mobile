"""PC-side durable SQLite agent. Run only on a trusted Windows computer."""
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("julia-pc")


def database_path() -> Path:
    return Path(os.environ.get("JULIA_SQLITE_PATH", str(Path.home() / ".julia-mobile" / "memory.sqlite3")))


def open_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        created_at TEXT NOT NULL, received_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_created ON messages(origin, created_at)")
    db.commit()
    return db


def persist_messages(db, rows):
    confirmed = []
    with db:
        for m in rows:
            # The relay validates payloads, but the agent independently limits data.
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            txt = m.get("text")
            conv = m.get("conversation_id")
            created = m.get("created_at")
            if not (isinstance(mid, str) and 8 <= len(mid) <= 100 and
                    isinstance(txt, str) and 1 <= len(txt) <= 10000 and
                    isinstance(conv, str) and 3 <= len(conv) <= 100 and
                    isinstance(created, str) and 10 <= len(created) <= 48 and
                    m.get("origin") == "mobile" and m.get("role") in ("user", "assistant")):
                continue
            db.execute("""INSERT OR IGNORE INTO messages
                (id, conversation_id, origin, role, text, created_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (mid, conv, "mobile", m["role"], txt, created,
                 datetime.now(timezone.utc).isoformat()))
            confirmed.append(mid)
    return confirmed


def list_messages(db, limit=200):
    rows = db.execute("""SELECT id, conversation_id, origin, role, text, created_at
                         FROM messages WHERE origin=? ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", min(max(int(limit), 1), 200))).fetchall()
    cols = ["id", "conversation_id", "origin", "role", "text", "created_at"]
    return [dict(zip(cols, row)) for row in reversed(rows)]


def run():
    relay_url = os.environ.get("JULIA_RELAY_URL", "").strip().rstrip("/")
    token = os.environ.get("JULIA_AGENT_TOKEN", "")
    if not relay_url or not token:
        raise SystemExit("Configure JULIA_RELAY_URL e JULIA_AGENT_TOKEN")
    parsed = urlparse(relay_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise SystemExit("JULIA_RELAY_URL inválida")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("O agente exige HTTPS fora de localhost")
    ws_url = f"{'wss' if parsed.scheme == 'https' else 'ws'}://{parsed.netloc}/api/agent/ws"
    db = open_db(database_path())
    pause = 2
    log.info("SQLite local preparado: %s", database_path())
    while True:
        try:
            with connect(ws_url, additional_headers={"Authorization": "Bearer " + token},
                         open_timeout=15, ping_interval=25, ping_timeout=20, max_size=2_000_000) as websocket:
                log.info("Conectado ao relay. Nenhuma porta de entrada foi aberta no PC.")
                pause = 2
                for raw in websocket:
                    req = json.loads(raw)
                    request_id = req.get("request_id")
                    if not isinstance(request_id, str):
                        continue
                    if req.get("type") == "sync":
                        confirmed_ids = persist_messages(db, req.get("messages", []))
                        reply = {"request_id": request_id, "type": "ack", "confirmed_ids": confirmed_ids}
                    elif req.get("type") == "list":
                        reply = {"request_id": request_id, "type": "history", "messages": list_messages(db, req.get("limit", 200))}
                    else:
                        continue
                    websocket.send(json.dumps(reply, ensure_ascii=False))
        except (ConnectionClosed, ConnectionError, OSError, TimeoutError, ValueError) as exc:
            log.warning("Conexão interrompida (%s). Reconectando em %ss", type(exc).__name__, pause)
        except KeyboardInterrupt:
            break
        time.sleep(pause)
        pause = min(60, pause * 2)
    db.close()


if __name__ == "__main__":
    run()
