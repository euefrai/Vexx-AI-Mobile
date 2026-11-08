"""Router: WebSocket do agente do PC (canal RPC autenticado por token)."""
import asyncio
import hmac

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from relay_core import config, drift_agente, is_ready, log, relay, revogados

router = APIRouter()

@router.websocket("/api/agent/ws")
async def agent_ws(websocket: WebSocket):
    if not is_ready():
        await websocket.close(code=4403)
        return
    provided = websocket.headers.get("authorization", "")
    expected = "Bearer " + config()["agent_token"]
    if not hmac.compare_digest(provided, expected):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    old = relay.ws
    if old is not None:
        try:
            await old.close(code=1001)
        except RuntimeError:
            pass
    relay.conectar(websocket)
    revogados["suportado"] = True
    revogados["falhas"] = 0
    relay.fail_pending()
    try:
        while True:
            body = await websocket.receive_json()
            if isinstance(body, dict) and body.get("type") == "agent_hello":
                info = relay.registrar_hello(body)
                drift = drift_agente()
                if drift["drift"]:
                    log.error("DRIFT DE DEPLOY: relay=%s agente=%s (pid=%s). "
                              "Publique o mesmo commit no Render e no PC.",
                              drift["relay_commit"], drift["agent_commit"],
                              info.get("pid"))
                elif drift["status"] == "desconhecido":
                    log.warning("Agente conectado sem commit verificavel "
                                "(pid=%s); drift nao pode ser avaliado.",
                                info.get("pid"))
                else:
                    log.info("Agente conectado: commit=%s pid=%s db_ok=%s.",
                             drift["agent_commit"] or "local", info.get("pid"),
                             info.get("db_ok"))
                continue
            request_id = body.get("request_id") if isinstance(body, dict) else None
            if not isinstance(request_id, str):
                continue
            if isinstance(body, dict) and body.get("type") in (
                    "ai_delta", "ai_done", "ai_error", "ai_cancelled"):
                fila = relay.streams.get(request_id)
                if fila is not None:
                    try:
                        fila.put_nowait(body)
                    except asyncio.QueueFull:
                        # Never silently lose a terminal result or a delta.
                        while not fila.empty():
                            fila.get_nowait()
                        fila.put_nowait(body if body.get("type") != "ai_delta" else {
                            "type": "ai_error", "codigo": "backpressure",
                            "error": "Conexão lenta; a resposta parcial ficará salva. Tente novamente."})
                    continue
                # Sem stream ativa: ai_done/ai_error de POST /api/ai caem no pending.
            if isinstance(body, dict) and body.get("type") == "research_event_push":
                job_id, owner = str(body.get("job_id", "")), str(body.get("owner", ""))
                ev = body.get("event") if isinstance(body.get("event"), dict) else None
                if job_id and ev and isinstance(ev.get("seq"), int):
                    for sub in list(relay.research_subs.values()):
                        if sub["job_id"] != job_id or sub["owner"] != owner:
                            continue  # isolamento: só o dono recebe
                        try:
                            sub["fila"].put_nowait(ev)
                        except asyncio.QueueFull:
                            sub["perdidos"] = sub.get("perdidos", 0) + 1
                continue
            pending = relay.pending.get(request_id)
            if pending and not pending.done():
                pending.set_result(body)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if relay.desconectar(websocket):
            log.warning("Agente desconectado; mensagens continuam no celular.")
            relay.fail_pending()
