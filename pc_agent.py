"""PC-side durable SQLite agent. Run only on a trusted Windows computer."""
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import hermes_bridge
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("julia-pc")

SYSTEM_PADRAO = ("Você é a Júlia, assistente pessoal do usuário. "
                 "Responda em português, de forma direta e útil.")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    try:
        db.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe (migração idempotente)
    db.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
        user_message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL,
        reply_id TEXT, response_text TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
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
    rows = db.execute("""SELECT id, conversation_id, origin, role, text, created_at,
                                COALESCE(model, '')
                         FROM messages WHERE origin=? ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", min(max(int(limit), 1), 200))).fetchall()
    cols = ["id", "conversation_id", "origin", "role", "text", "created_at", "model"]
    return [dict(zip(cols, row)) for row in reversed(rows)]


def ai_config() -> dict:
    return {
        "proxy": os.environ.get("HERMES_PROXY_URL", hermes_bridge.DEFAULT_PROXY_URL),
        "model": os.environ.get("JULIA_AI_MODEL", hermes_bridge.DEFAULT_MODEL),
        "system": os.environ.get("JULIA_SYSTEM_PROMPT", SYSTEM_PADRAO)[:2000],
        "context": min(max(int(os.environ.get("JULIA_AI_CONTEXT", "20")), 1), 50),
        "max_tokens": min(max(int(os.environ.get("JULIA_AI_MAX_TOKENS", "2000")), 1), 8000),
    }


def contexto_conversa(db, conversation_id: str, limite: int) -> list:
    rows = db.execute("""SELECT role, text FROM messages
                         WHERE origin=? AND conversation_id=?
                         ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", conversation_id, limite)).fetchall()
    return [{"role": role, "content": (text or "")[:4000]}
            for role, text in reversed(rows) if role in ("user", "assistant")]


def ai_estado(db, user_message_id: str):
    row = db.execute("SELECT state, reply_id, response_text, error, model FROM ai_requests "
                     "WHERE user_message_id=?", (user_message_id,)).fetchone()
    if not row:
        return None
    return {"state": row[0], "reply_id": row[1], "response_text": row[2],
            "error": row[3], "model": row[4]}


def ai_marcar(db, user_message_id, conversation_id, model, state,
              reply_id=None, response_text=None, error=None):
    with db:
        db.execute("""INSERT INTO ai_requests
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_message_id) DO UPDATE SET state=excluded.state,
             reply_id=excluded.reply_id, response_text=excluded.response_text,
             error=excluded.error, updated_at=excluded.updated_at""",
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, agora_iso(), agora_iso()))


def ai_preparar(db, payload: dict, cfg: dict) -> dict:
    """Valida e aplica idempotência. Retorna {user_text, model, reply_id} ou {replay|busy|error}."""
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    if not (isinstance(conv, str) and 3 <= len(conv) <= 100):
        return {"error": "conversation_id inválido.", "codigo": "invalido"}
    modelo = payload.get("model") or cfg["model"]
    if not (isinstance(modelo, str) and 1 <= len(modelo) <= 120):
        return {"error": "Modelo inválido.", "codigo": "invalido"}
    previo = ai_estado(db, mid)
    if previo and previo["state"] == "completed":
        return {"replay": True, "reply_id": previo["reply_id"],
                "response_text": previo["response_text"], "model": previo["model"]}
    if previo and previo["state"] == "processing":
        return {"busy": True}
    row = db.execute("SELECT text FROM messages WHERE id=? AND origin='mobile' "
                     "AND role='user' AND conversation_id=?", (mid, conv)).fetchone()
    if not row:
        return {"error": "Mensagem do usuário não encontrada. Sincronize primeiro.",
                "codigo": "sem_mensagem"}
    ai_marcar(db, mid, conv, modelo, "queued")
    return {"user_text": row[0], "model": modelo,
            "reply_id": f"{mid}-r1", "conversation_id": conv}


def ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto) -> None:
    with db:
        db.execute("""INSERT OR IGNORE INTO messages
            (id, conversation_id, origin, role, text, created_at, received_at, model)
            VALUES (?, ?, 'mobile', 'assistant', ?, ?, ?, ?)""",
            (reply_id, conv, texto, agora_iso(), agora_iso(), modelo))
    ai_marcar(db, mid, conv, modelo, "completed",
              reply_id=reply_id, response_text=texto)


def ai_completa(db, payload: dict, cfg: dict) -> dict:
    prep = ai_preparar(db, payload, cfg)
    if "error" in prep or "replay" in prep or "busy" in prep:
        return prep
    mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
    ai_marcar(db, mid, conv, modelo, "processing")
    messages = [{"role": "system", "content": cfg["system"]},
                *contexto_conversa(db, conv, cfg["context"])]
    try:
        res = hermes_bridge.chat_complete(cfg["proxy"], modelo, messages,
                                          max_tokens=cfg["max_tokens"])
    except hermes_bridge.BridgeErro as exc:
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc))
        return {"error": str(exc), "codigo": exc.codigo}
    ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], res["texto"])
    log.info("IA %s respondeu em %ss (msg %s)", modelo, res["latencia_s"], mid)
    return {"reply_id": prep["reply_id"], "response_text": res["texto"],
            "model": modelo, "truncada": res.get("truncada", False)}


class SessaoStream:
    def __init__(self):
        self.parar = threading.Event()
        self.lock_envio = threading.Lock()


def ai_stream_worker(db_path: Path, cfg: dict, payload: dict, request_id: str,
                     websocket, sessao: SessaoStream, cancelados: dict) -> None:
    """Roda em thread: deltas saem pelo lock; a thread principal só recebe."""
    db = open_db(db_path)
    try:
        prep = ai_preparar(db, payload, cfg)
        if "error" in prep or "replay" in prep or "busy" in prep:
            with sessao.lock_envio:
                websocket.send(json.dumps({"request_id": request_id, "type": "ai_error",
                                           **{k: prep[k] for k in ("error", "codigo", "reply_id",
                                                                   "response_text", "model", "busy")
                                               if k in prep}},
                                          ensure_ascii=False))
            return
        mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
        ai_marcar(db, mid, conv, modelo, "processing")
        messages = [{"role": "system", "content": cfg["system"]},
                    *contexto_conversa(db, conv, cfg["context"])]

        def emitir(seq, trecho):
            with sessao.lock_envio:
                websocket.send(json.dumps({"request_id": request_id, "type": "ai_delta",
                                           "seq": seq, "trecho": trecho},
                                          ensure_ascii=False))

        try:
            res = hermes_bridge.chat_stream(cfg["proxy"], modelo, messages, emitir,
                                            deve_parar=sessao.parar.is_set,
                                            max_tokens=cfg["max_tokens"])
        except hermes_bridge.BridgeErro as exc:
            ai_marcar(db, mid, conv, modelo, "failed", error=str(exc))
            with sessao.lock_envio:
                websocket.send(json.dumps({"request_id": request_id, "type": "ai_error",
                                           "error": str(exc), "codigo": exc.codigo},
                                          ensure_ascii=False))
            return
        if res.get("cancelada"):
            ai_marcar(db, mid, conv, modelo, "cancelled",
                      reply_id=prep["reply_id"], response_text=res["texto"])
            with sessao.lock_envio:
                websocket.send(json.dumps({"request_id": request_id, "type": "ai_cancelled",
                                           "reply_id": prep["reply_id"],
                                           "partial": res["texto"]},
                                          ensure_ascii=False))
            return
        ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], res["texto"])
        log.info("IA %s (stream) em %ss (msg %s)", modelo, res["latencia_s"], mid)
        with sessao.lock_envio:
            websocket.send(json.dumps({"request_id": request_id, "type": "ai_done",
                                       "reply_id": prep["reply_id"],
                                       "response_text": res["texto"], "model": modelo},
                                      ensure_ascii=False))
    finally:
        cancelados.pop(request_id, None)
        db.close()


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
    cfg = ai_config()
    try:
        modelos = hermes_bridge.listar_modelos(cfg["proxy"])
        log.info("Hermes proxy OK: %d modelos (padrão %s)", len(modelos), cfg["model"])
    except hermes_bridge.BridgeErro as exc:
        log.warning("Hermes indisponível no boot (%s). Mensagens serão guardadas; IA tenta depois.",
                    exc)
    pause = 2
    log.info("SQLite local preparado: %s", database_path())
    cancelados: dict = {}
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
                    elif req.get("type") == "ai":
                        res = ai_completa(db, req, cfg)
                        reply = {"request_id": request_id, "type": "ai_done", **res}
                    elif req.get("type") == "ai_models":
                        try:
                            reply = {"request_id": request_id, "type": "ai_models",
                                     "models": hermes_bridge.listar_modelos(cfg["proxy"]),
                                     "default": cfg["model"]}
                        except hermes_bridge.BridgeErro as exc:
                            reply = {"request_id": request_id, "type": "ai_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "ai_stream":
                        sessao = SessaoStream()
                        cancelados[request_id] = sessao
                        threading.Thread(target=ai_stream_worker,
                                         args=(database_path(), cfg, req, request_id,
                                               websocket, sessao, cancelados),
                                         daemon=True).start()
                        continue
                    elif req.get("type") == "ai_cancel":
                        alvo = req.get("target") if isinstance(req.get("target"), str) else request_id
                        sessao = cancelados.get(alvo)
                        if sessao is not None:
                            sessao.parar.set()
                        continue
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
