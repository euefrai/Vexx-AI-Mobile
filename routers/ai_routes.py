"""Router: Chat de IA: completar, continuar, regenerar, modelos, chaves e streaming."""
import asyncio
import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from relay_core import (
    _rate_limit, AIRequest, erro_relay, log, relay, require_csrf, revogacao_ok, sessao_usuario,
)

router = APIRouter()

@router.post("/api/ai")
async def ai_complete(request: Request, body: AIRequest):
    """Resposta completa (sem streaming). Idempotente por message_id no agente."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "ai", dono)
    result = await relay.exchange({"type": "ai", "owner": dono,
                                   "message_id": body.message_id,
                                   "conversation_id": body.conversation_id,
                                   "model": body.model, "memory": body.memory,
                                   "local_time": body.local_time, "timezone": body.timezone,
                                   "city": body.city, "latitude": body.latitude,
                                   "longitude": body.longitude, "text": body.text,
                                   "created_at": body.created_at, "scene_state": body.scene_state, **({"image": body.image} if body.image else {})}, timeout=180.0)
    if result.get("type") != "ai_done" or "response_text" not in result:
        if result.get("type") == "ai_error":
            raise erro_relay(result, "IA indisponível")
        raise HTTPException(503, "Resposta da IA não recebida")
    return {"reply_id": result.get("reply_id"), "response_text": result["response_text"],
            "model": result.get("model", "")}


class AIContinue(BaseModel):
    message_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: str = Field(min_length=3, max_length=100)
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9_.:/+-]*$")
    local_time: str = Field(default="", max_length=48)
    timezone: str = Field(default="", max_length=80)
    city: str = Field(default="", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


@router.post("/api/ai/regenerate")
async def ai_regenerate(request: Request, body: AIContinue):
    """Apaga resposta anterior (PC + idempotência) para gerar de novo."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "ai", dono)
    result = await relay.exchange({"type": "ai_reset", "owner": dono,
                                   "message_id": body.message_id,
                                   "conversation_id": body.conversation_id}, timeout=20.0)
    if result.get("type") == "ai_error":
        raise erro_relay(result, "Falha ao reiniciar")
    if result.get("type") != "ai_reset_ok":
        raise HTTPException(503, "PC não confirmou")
    return {"ok": True, "reply_id": result.get("reply_id")}


@router.post("/api/ai/continue")
async def ai_continue(request: Request, body: AIContinue):
    """Continua a resposta anterior, anexando ao mesmo reply_id."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "ai", dono)
    result = await relay.exchange({"type": "ai_continue", "owner": dono,
                                   "message_id": body.message_id,
                                   "conversation_id": body.conversation_id,
                                   "model": body.model,
                                   "local_time": body.local_time, "timezone": body.timezone,
                                   "city": body.city, "latitude": body.latitude,
                                   "longitude": body.longitude}, timeout=180.0)
    if result.get("type") == "ai_error":
        raise erro_relay(result, "Falha ao continuar")
    if result.get("type") != "ai_done" or "response_text" not in result:
        raise HTTPException(503, "Continuação não recebida")
    return {"reply_id": result.get("reply_id"), "response_text": result["response_text"],
            "model": result.get("model", "")}


class ProviderKey(BaseModel):
    provider: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    action: str = Field(default="set", pattern=r"^(set|del)$")
    key: str = ""


@router.post("/api/providers")
async def provider_key(request: Request, body: ProviderKey):
    """Salva/remove chave de provedor externo NO PC (o relay só transporta).

    Sem persistência e sem log do valor; a resposta final NUNCA inclui a
    chave (nem fragmento). O PC grava no .env local e aplica na hora."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    chave = body.key.strip() if body.action == "set" else ""
    if body.action == "set" and not 8 <= len(chave) <= 400:
        raise HTTPException(422, "Chave com tamanho inválido (8 a 400 caracteres)")
    result = await relay.exchange({"type": "provider_key", "owner": dono,
                                   "provider": body.provider, "action": body.action,
                                   "key": chave}, timeout=20.0)
    if result.get("type") == "ai_error":
        raise erro_relay(result, "Não foi possível salvar a chave")
    if result.get("type") != "provider_key_ok":
        raise HTTPException(503, "PC não confirmou")
    return {"ok": True, "provider": result.get("provider", body.provider),
            "configured": bool(result.get("configured")),
            "source": result.get("source", "")}

@router.get("/api/ai/models")
async def ai_models(request: Request):
    dono = sessao_usuario(request)
    _rate_limit(request, "ai", dono)
    result = await relay.exchange({"type": "ai_models"}, timeout=30.0)
    if result.get("type") == "ai_error":
        raise HTTPException(503, result.get("error", "Hermes indisponível"))
    if result.get("type") != "ai_models":
        raise HTTPException(503, "Modelos indisponíveis")
    # providers/items: só metadados — chaves nunca saem do PC.
    provs = result.get("providers", [])
    if not isinstance(provs, list):
        provs = []
    itens = result.get("items", [])
    if not isinstance(itens, list):
        itens = []
    return {"models": result.get("models", [])[:2000], "default": result.get("default", ""),
            "items": [{k: i.get(k) for k in ("id", "provider", "free")
                       if k != "free" or isinstance(i.get(k), bool)}
                      for i in itens if isinstance(i, dict)][:2000],
            "providers": [{k: p.get(k) for k in ("id", "label", "configured", "auth_error", "source")
                           if p.get(k) is not None}
                          for p in provs if isinstance(p, dict)][:20]}


@router.post("/api/ai/stream")
async def ai_stream_post(request: Request, body: AIRequest):
    return await ai_stream(request, **body.model_dump())


@router.get("/api/ai/stream")
async def ai_stream(request: Request, message_id: str = "", conversation_id: str = "",
                    model: str = "", memory: str = "1", local_time: str = "",
                    timezone: str = "", city: str = "",
                    latitude: float | None = None, longitude: float | None = None,
                    text: str = "", created_at: str = "", scene_state: str = "", image: str = ""):
    """SSE com deltas reais do Hermes (via agente). Fechar a conexão cancela."""
    request_started = time.monotonic()
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "ai", dono)
    auth_completed = time.monotonic()
    if not (8 <= len(message_id) <= 100) or not (3 <= len(conversation_id) <= 100):
        raise HTTPException(422, "Parâmetros inválidos")
    if len(text) > 10000 or len(created_at) > 48 or len(scene_state)>4000:
        raise HTTPException(422, "Parâmetros inválidos")
    from fastapi.responses import StreamingResponse

    ws = relay.ws
    if ws is None:
        raise HTTPException(503, "Computador desconectado; mensagens continuam no celular")
    if len(local_time) > 48 or len(timezone) > 80 or len(city) > 100:
        raise HTTPException(422, "Contexto local inválido")
    if latitude is not None and not -90 <= latitude <= 90:
        raise HTTPException(422, "Latitude inválida")
    if longitude is not None and not -180 <= longitude <= 180:
        raise HTTPException(422, "Longitude inválida")
    if len(relay.streams) >= 8:
        raise HTTPException(429, "Muitas respostas simultâneas; aguarde uma terminar")
    stream_id = uuid.uuid4().hex
    fila: asyncio.Queue = asyncio.Queue(maxsize=256)
    relay.streams[stream_id] = fila
    payload = {"type": "ai_stream", "owner": dono,
               "message_id": message_id,
               "conversation_id": conversation_id, "model": model[:120],
               "memory": "0" if str(memory) == "0" else "1",
               "local_time": local_time, "timezone": timezone, "city": city,
               "latitude": latitude, "longitude": longitude,
               "text": text, "created_at": created_at, "scene_state": scene_state, **({"image": image[:2000000]} if image else {})}

    async def gerar():
        concluido = False
        espera = 0.0
        forwarded_at = 0.0
        first_delta_logged = False
        try:
            async with relay.send_lock:
                if relay.ws is not ws:
                    yield 'event: error\ndata: {"error": "Agente reconectando"}\n\n'
                    return
                await ws.send_json({**payload, "request_id": stream_id})
                forwarded_at = time.monotonic()
            while True:
                try:
                    item = await asyncio.wait_for(fila.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    espera += 15.0
                    if espera >= 180.0:
                        yield 'event: error\ndata: {"error": "Tempo esgotado aguardando a IA"}\n\n'
                        return
                    yield ": ping\n\n"  # mantém SSE vivo através de proxies
                    continue
                tipo = item.get("type")
                if tipo == "ai_delta":
                    espera = 0.0  # timeout measures inactivity, not accumulated pauses
                    if not first_delta_logged:
                        first_delta_logged = True
                        now = time.monotonic()
                        log.info(
                            "AI_RELAY_STAGE msg=%s auth_ms=%d forward_ms=%d first_delta_ms=%d",
                            message_id[-8:], round((auth_completed - request_started) * 1000),
                            round((forwarded_at - auth_completed) * 1000),
                            round((now - request_started) * 1000))
                    yield f"event: delta\ndata: {json.dumps({'seq': item.get('seq', 0), 'trecho': item.get('trecho', '')}, ensure_ascii=False)}\n\n"
                elif tipo == "ai_done":
                    concluido = True
                    log.info("AI_RELAY_DONE msg=%s total_ms=%d",
                             message_id[-8:],
                             round((time.monotonic() - request_started) * 1000))
                    yield f"event: done\ndata: {json.dumps({'reply_id': item.get('reply_id'), 'response_text': item.get('response_text', ''), 'model': item.get('model', '')}, ensure_ascii=False)}\n\n"
                    return
                elif tipo == "ai_cancelled":
                    concluido = True
                    yield f"event: cancelled\ndata: {json.dumps({'reply_id': item.get('reply_id'), 'partial': item.get('partial', '')}, ensure_ascii=False)}\n\n"
                    return
                else:
                    concluido = item.get("codigo") != "backpressure"
                    log.info("AI_RELAY_ERROR msg=%s total_ms=%d code=%s",
                             message_id[-8:],
                             round((time.monotonic() - request_started) * 1000),
                             str(item.get("codigo", "erro"))[:40])
                    yield f"event: error\ndata: {json.dumps({'error': item.get('error', 'IA indisponível'), 'codigo': item.get('codigo', 'erro')}, ensure_ascii=False)}\n\n"
                    return
        finally:
            relay.streams.pop(stream_id, None)
            if not concluido and relay.ws is not None and relay.ws is ws:
                try:
                    async with relay.send_lock:
                        await ws.send_json({"request_id": stream_id, "type": "ai_cancel",
                                            "target": stream_id})
                except (RuntimeError, OSError):
                    pass

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
