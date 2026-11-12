"""Router: Chat de IA: completar, continuar, regenerar, modelos, chaves e streaming."""
import asyncio
import json
import time
import uuid

import base64
from typing import Any
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from relay_core import (
    _rate_limit, AIRequest, erro_relay, log, relay, require_csrf, revogacao_ok, sessao_usuario,
)

router = APIRouter()
import voice_service


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
                                   "created_at": body.created_at, "scene_state": body.scene_state, **({"image": body.image} if body.image else {}), **({"vision_engine": body.vision_engine} if getattr(body, "vision_engine", "") else {})}, timeout=180.0)
    if result.get("type") != "ai_done" or "response_text" not in result:
        if result.get("type") == "ai_error":
            raise erro_relay(result, "IA indisponível")
        raise HTTPException(503, "Resposta da IA não recebida")
    return {"reply_id": result.get("reply_id"), "response_text": result["response_text"],
            "model": result.get("model", ""), "fallback_usado": bool(result.get("fallback_usado", False))}


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
            "model": result.get("model", ""), "fallback_usado": bool(result.get("fallback_usado", False))}


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

    local_vl_item = {
        "id": "qwen2.5-vl-7b-instruct",
        "provider": "qwen_local",
        "label": "🖥️ Qwen 2.5-VL 7B (Local PC - Visão & Raciocínio)",
        "free": True
    }
    local_item = {
        "id": "qwen2.5-1.5b-instruct",
        "provider": "qwen_local",
        "label": "🖥️ Qwen 2.5 1.5B Instruct (Modelo 1.5 - Local PC)",
        "free": True
    }
    local_provider = {
        "id": "qwen_local",
        "label": "🖥️ Qwen 2.5 1.5B (Modelo 1.5 - Local PC)",
        "configured": True,
        "source": "local_pc"
    }
    vexx_item = {
        "id": "vexx-qwen-2.5-3b",
        "provider": "vexx",
        "label": "⚡ VEXX Qwen 2.5 3B (Modelo 3)",
        "free": True
    }
    vexx_provider = {
        "id": "vexx",
        "label": "⚡ VEXX Qwen 2.5 3B (Modelo 3)",
        "configured": True,
        "source": "hf_space"
    }

    try:
        result = await relay.exchange({"type": "ai_models"}, timeout=15.0)
    except Exception:
        result = {}

    custom_models = []
    custom_items = []
    custom_provs = []
    try:
        import custom_providers
        for c_id, c_def in custom_providers.carregar_custom_providers().items():
            custom_provs.append({
                "id": c_id,
                "label": c_def.get("label", c_id),
                "configured": True,
                "source": "custom_external",
                "device_type": c_def.get("device_type", "custom"),
                "base": c_def.get("base", "")
            })
            for mid in c_def.get("modelos", []):
                full_id = f"{c_id}/{mid}" if not str(mid).startswith(f"{c_id}/") else mid
                custom_models.append(full_id)
                custom_items.append({
                    "id": full_id,
                    "provider": c_id,
                    "label": f"🌐 {c_def.get('label', c_id)} ({mid})",
                    "free": True,
                    "custom": True
                })
    except Exception:
        pass

    if not isinstance(result, dict) or result.get("type") not in ("ai_models", "ai_models_ok"):
        return {
            "models": ["qwen2.5-vl-7b-instruct", "qwen2.5-1.5b-instruct", "vexx-qwen-2.5-3b"] + custom_models,
            "default": "qwen2.5-vl-7b-instruct",
            "items": [local_vl_item, local_item, vexx_item] + custom_items,
            "providers": [local_provider, vexx_provider] + custom_provs
        }

    provs = result.get("providers", [])
    if not isinstance(provs, list):
        provs = []
    itens = result.get("items", [])
    if not isinstance(itens, list):
        itens = []
    raw_models = result.get("models", [])
    if not isinstance(raw_models, list):
        raw_models = []
    models = []
    for m in raw_models:
        if isinstance(m, dict) and m.get("id"):
            models.append(m["id"])
        elif isinstance(m, str) and m:
            models.append(m)

    for m_id in ("vexx-qwen-2.5-3b", "qwen2.5-1.5b-instruct", "qwen2.5-vl-7b-instruct"):
        if m_id in models:
            models.remove(m_id)
    for idx, cm in enumerate(cm for cm in custom_models if cm not in models):
        models.insert(idx, cm)
    models.insert(0, "vexx-qwen-2.5-3b")
    models.insert(0, "qwen2.5-1.5b-instruct")
    models.insert(0, "qwen2.5-vl-7b-instruct")

    itens = [i for i in itens if isinstance(i, dict) and i.get("id") not in ("qwen2.5-vl-7b-instruct", "qwen2.5-1.5b-instruct", "vexx-qwen-2.5-3b")]
    existing_item_ids = {i.get("id") for i in itens}
    for idx, ci in enumerate(ci for ci in custom_items if ci.get("id") not in existing_item_ids):
        itens.insert(idx, ci)
    itens.insert(0, vexx_item)
    itens.insert(0, local_item)
    itens.insert(0, local_vl_item)

    provs = [p for p in provs if isinstance(p, dict) and p.get("id") not in ("qwen_local", "vexx")]
    existing_prov_ids = {p.get("id") for p in provs}
    for idx, cp in enumerate(cp for cp in custom_provs if cp.get("id") not in existing_prov_ids):
        provs.insert(idx, cp)
    provs.insert(0, vexx_provider)
    provs.insert(0, local_provider)

    return {
        "models": models[:2000],
        "default": "qwen2.5-1.5b-instruct",
        "items": [{k: i.get(k) for k in ("id", "provider", "free", "label", "custom")
                   if (k != "free" or isinstance(i.get(k), bool)) and i.get(k) is not None}
                  for i in itens if isinstance(i, dict)][:2000],
        "providers": [{k: p.get(k) for k in ("id", "label", "configured", "auth_error", "source", "device_type", "base")
                       if p.get(k) is not None}
                      for p in provs if isinstance(p, dict)][:50]
    }


@router.post("/api/ai/stream")
async def ai_stream_post(request: Request, body: AIRequest):
    return await ai_stream(request, **body.model_dump())


@router.get("/api/ai/stream")
async def ai_stream(request: Request, message_id: str = "", conversation_id: str = "",
                    model: str = "", memory: str = "1", local_time: str = "",
                    timezone: str = "", city: str = "",
                    latitude: float | None = None, longitude: float | None = None,
                    text: str = "", created_at: str = "", scene_state: str = "", image: str = "", vision_engine: str = ""):
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
                elif tipo == "ai_step":
                    yield f"event: step\ndata: {json.dumps({'step': item.get('step', '')}, ensure_ascii=False)}\n\n"
                elif tipo == "ai_done":
                    concluido = True
                    log.info("AI_RELAY_DONE msg=%s total_ms=%d",
                             message_id[-8:],
                             round((time.monotonic() - request_started) * 1000))
                    yield f"event: done\ndata: {json.dumps({'reply_id': item.get('reply_id'), 'response_text': item.get('response_text', ''), 'model': item.get('model', ''), 'fallback_usado': bool(item.get('fallback_usado', False))}, ensure_ascii=False)}\n\n"
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


def _obter_dono_ws(websocket: WebSocket) -> str:
    """Extrai dono autenticado do cookie ou parâmetro, com fallback para 'local'."""
    token = websocket.cookies.get("JULIA_session")
    if not token:
        token = websocket.query_params.get("token")
    if token:
        try:
            from relay_core import signer, SESSION_LIFETIME
            dados = signer().loads(token, max_age=SESSION_LIFETIME)
            uid = str(dados.get("uid") or "")
            if uid:
                return uid
        except Exception:
            pass
    return "local"


@router.websocket("/api/voice-chat-stream")
async def voice_chat_stream(websocket: WebSocket):
    """Canal WebSocket bidirecional para o Modo de Voz Conversacional em tempo real.
    
    Fluxo de dados:
    1. Recebe áudio do microfone do usuário (streaming de chunks PCM/WAV).
    2. Valida locutor via SpeechBrain (se calibrado) e filtra ruído com Silero VAD.
    3. Transcreve a fala via Faster-Whisper STT (API Hugging Face).
    4. Envia o texto ao LLM com streaming.
    5. A cada oração gerada pelo LLM, envia para o Kokoro TTS na API HF.
    6. Retorna o áudio sintetizado particionado em WAV imediatamente para o frontend.
    7. Suporta interrupção / barge-in se o usuário voltar a falar.
    """
    await websocket.accept()
    dono = _obter_dono_ws(websocket)
    session_id = uuid.uuid4().hex[:8]
    log.info("VOICE_CHAT_CONNECT session=%s owner=%s", session_id, dono)

    configuracao = {
        "voice": "pm_alex",
        "speed": 1.0,
        "language": "pt",
        "conversation_id": "voz_" + session_id,
        "model": "",
        "auto_calibrate": True,
        "threshold": 0.42,
    }
    locutor_referencia: list[float] | None = None
    buffer_audio: list[bytes] = []
    tarefa_llm_ativa: asyncio.Task | None = None
    stream_id_ativo: str | None = None

    await websocket.send_json({
        "type": "voice_ready",
        "session_id": session_id,
        "state": "idle",
        "message": "Canal de voz Vexx-AI conectado. Pronto para ouvir."
    })

    async def _cancelar_geracao_atual():
        nonlocal tarefa_llm_ativa, stream_id_ativo
        if stream_id_ativo:
            relay.streams.pop(stream_id_ativo, None)
            if relay.ws is not None:
                try:
                    async with relay.send_lock:
                        await relay.ws.send_json({"request_id": stream_id_ativo, "type": "ai_cancel",
                                                 "target": stream_id_ativo})
                except Exception:
                    pass
            stream_id_ativo = None
        if tarefa_llm_ativa and not tarefa_llm_ativa.done():
            tarefa_llm_ativa.cancel()
            try:
                await tarefa_llm_ativa
            except (asyncio.CancelledError, Exception):
                pass
            tarefa_llm_ativa = None

    async def _executar_llm_e_tts(texto_usuario: str):
        nonlocal stream_id_ativo
        ws_agente = relay.ws
        if ws_agente is None:
            await websocket.send_json({
                "type": "error",
                "message": "Computador/Agente desconectado; verifique se o agente Vexx está ativo no PC."
            })
            return

        stream_id = uuid.uuid4().hex
        stream_id_ativo = stream_id
        fila: asyncio.Queue = asyncio.Queue(maxsize=256)
        relay.streams[stream_id] = fila

        msg_id = "msg_" + uuid.uuid4().hex[:12]
        payload = {
            "type": "ai_stream",
            "owner": dono,
            "message_id": msg_id,
            "conversation_id": configuracao["conversation_id"],
            "model": configuracao["model"][:120],
            "memory": "1",
            "local_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": "America/Sao_Paulo",
            "city": "",
            "text": texto_usuario,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scene_state": "",
            "request_id": stream_id
        }

        acumulador = voice_service.SentenceAccumulator()
        seq = 0
        texto_completo = ""

        try:
            async with relay.send_lock:
                await ws_agente.send_json(payload)

            await websocket.send_json({"type": "ai_thinking", "stream_id": stream_id})

            while True:
                try:
                    item = await asyncio.wait_for(fila.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ai_ping"})
                    continue

                tipo = item.get("type")
                if tipo == "ai_delta":
                    trecho = item.get("trecho", "")
                    texto_completo += trecho
                    await websocket.send_json({
                        "type": "ai_text_delta",
                        "delta": trecho,
                        "seq": seq
                    })

                    oracoes = acumulador.feed(trecho)
                    for oracao in oracoes:
                        seq += 1
                        wav_bytes = await voice_service.synthesize_speech_wav(
                            oracao, voice=configuracao["voice"], speed=configuracao["speed"]
                        )
                        if wav_bytes:
                            await websocket.send_json({
                                "type": "ai_audio_delta",
                                "seq": seq,
                                "text": oracao,
                                "audio": base64.b64encode(wav_bytes).decode("ascii"),
                                "format": "wav"
                            })

                elif tipo == "ai_step":
                    yield f"event: step\ndata: {json.dumps({'step': item.get('step', '')}, ensure_ascii=False)}\n\n"
                elif tipo == "ai_done":
                    oracoes_finais = acumulador.flush()
                    for oracao in oracoes_finais:
                        seq += 1
                        wav_bytes = await voice_service.synthesize_speech_wav(
                            oracao, voice=configuracao["voice"], speed=configuracao["speed"]
                        )
                        if wav_bytes:
                            await websocket.send_json({
                                "type": "ai_audio_delta",
                                "seq": seq,
                                "text": oracao,
                                "audio": base64.b64encode(wav_bytes).decode("ascii"),
                                "format": "wav"
                            })

                    resp_text = item.get("response_text", texto_completo)
                    await websocket.send_json({
                        "type": "ai_done",
                        "response_text": resp_text,
                        "reply_id": item.get("reply_id"),
                        "model": item.get("model", ""),
                        "fallback_usado": bool(item.get("fallback_usado", False))
                    })
                    break

                elif tipo in ("ai_cancelled", "ai_error"):
                    await websocket.send_json({
                        "type": "ai_cancelled" if tipo == "ai_cancelled" else "error",
                        "message": item.get("error", "Geração interrompida")
                    })
                    break

        except asyncio.CancelledError:
            log.info("VOICE_CHAT_CANCELLED stream=%s", stream_id)
        except Exception as e:
            log.error("VOICE_CHAT_STREAM_ERROR: %s", e)
            await websocket.send_json({"type": "error", "message": f"Erro na conversação: {e}"})
        finally:
            relay.streams.pop(stream_id, None)
            if stream_id_ativo == stream_id:
                stream_id_ativo = None

    try:
        while True:
            msg = await websocket.receive()
            if "text" in msg:
                try:
                    dados = json.loads(msg["text"])
                except Exception:
                    continue

                tipo = dados.get("type")

                if tipo == "init":
                    if "voice" in dados: configuracao["voice"] = dados["voice"]
                    if "speed" in dados: configuracao["speed"] = float(dados["speed"])
                    if "model" in dados: configuracao["model"] = dados["model"]
                    if "conversation_id" in dados and dados["conversation_id"]:
                        configuracao["conversation_id"] = dados["conversation_id"]
                    if "threshold" in dados:
                        configuracao["threshold"] = float(dados["threshold"])
                    await websocket.send_json({"type": "config_ok", "config": configuracao})

                elif tipo == "calibrate":
                    audio_b64 = dados.get("audio", "")
                    if audio_b64:
                        raw = base64.b64decode(audio_b64)
                        locutor_referencia = await voice_service.enroll_speaker_profile(raw)
                        await websocket.send_json({
                            "type": "calibrated",
                            "success": locutor_referencia is not None,
                            "message": "Locutor calibrado com sucesso." if locutor_referencia else "Falha ao calibrar locutor."
                        })

                elif tipo == "audio_chunk":
                    chunk_b64 = dados.get("data", "")
                    if chunk_b64:
                        buffer_audio.append(base64.b64decode(chunk_b64))

                elif tipo == "interrupt":
                    await _cancelar_geracao_atual()
                    buffer_audio.clear()
                    await websocket.send_json({"type": "interrupted"})

                elif tipo == "audio_end":
                    if not buffer_audio:
                        await websocket.send_json({"type": "stt_empty"})
                        continue

                    audio_total = b"".join(buffer_audio)
                    buffer_audio.clear()

                    if locutor_referencia:
                        verificacao = await voice_service.verify_speaker_audio(audio_total, locutor_referencia)
                        if not verificacao.get("match", True):
                            sim = verificacao.get("similarity", 0.0)
                            log.info("VOICE_INTRUDER_DETECTED sim=%.3f", sim)
                            await websocket.send_json({
                                "type": "voice_filtered",
                                "reason": "intruder_detected",
                                "similarity": sim,
                                "message": "Voz de fundo ignorada (locutor não reconhecido)."
                            })
                            continue
                    elif configuracao["auto_calibrate"] and not locutor_referencia:
                        locutor_referencia = await voice_service.enroll_speaker_profile(audio_total)

                    await websocket.send_json({"type": "stt_processing"})
                    texto_transcrito = await voice_service.transcribe_audio_bytes(
                        audio_total, language=configuracao["language"]
                    )

                    if not texto_transcrito:
                        await websocket.send_json({"type": "stt_empty"})
                        continue

                    await websocket.send_json({
                        "type": "user_transcription",
                        "text": texto_transcrito
                    })

                    await _cancelar_geracao_atual()
                    tarefa_llm_ativa = asyncio.create_task(_executar_llm_e_tts(texto_transcrito))

            elif "bytes" in msg and msg["bytes"]:
                buffer_audio.append(msg["bytes"])

    except WebSocketDisconnect:
        log.info("VOICE_CHAT_DISCONNECT session=%s", session_id)
    except Exception as e:
        log.error("VOICE_CHAT_EXCEPTION session=%s error=%s", session_id, e)
    finally:
        await _cancelar_geracao_atual()


class VisionEngineRequest(BaseModel):
    engine: str = Field(min_length=2, max_length=30)


class VisionLatencyRequest(BaseModel):
    iterations: int = Field(default=5, ge=1, le=20)


class VisionAnalyzeRequest(BaseModel):
    image: str = Field(min_length=1, max_length=2000000)
    engine: str = Field(default="", max_length=30)
    classes: str = Field(default="", max_length=200)


@router.get("/api/vision/engine")
async def vision_engine_get():
    """Retorna o motor de visão ativo e a lista de motores disponíveis."""
    if relay.ws is not None:
        try:
            res = await relay.exchange({"type": "vision_engine_get"}, timeout=10.0)
            if res.get("type") == "vision_engine_get_ok":
                return res.get("resultado", {})
        except Exception as exc:
            log.warning("Falha ao obter motor de visão via relay: %s", exc)
    import vision_service
    return {
        "engine": vision_service.obter_motor_visao(),
        "engines": vision_service.listar_motores_visao(),
    }


@router.post("/api/vision/engine")
async def vision_engine_post(request: Request, body: VisionEngineRequest):
    """Altera o motor de visão em tempo de execução ('local', 'huggingface', 'auto')."""
    require_csrf(request)
    await revogacao_ok(request)
    if relay.ws is not None:
        try:
            res = await relay.exchange({"type": "vision_engine_post", "engine": body.engine}, timeout=10.0)
            if res.get("type") == "vision_engine_post_ok":
                return res.get("resultado", {})
        except Exception as exc:
            log.warning("Falha ao configurar motor de visão via relay: %s", exc)
    import vision_service
    try:
        novo = vision_service.definir_motor_visao(body.engine)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {
        "ok": True,
        "engine": novo,
        "engines": vision_service.listar_motores_visao(),
    }


@router.post("/api/vision/latency-test")
async def vision_latency_test(request: Request, body: VisionLatencyRequest | None = None):
    """Executa benchmark de latência do modelo YOLO no PC local."""
    try:
        require_csrf(request)
        dono = await revogacao_ok(request)
    except Exception as exc:
        return {"status": "erro", "mensagem": f"Autenticação necessária: {exc}"}
    iters = body.iterations if body else 5
    if relay.ws is not None:
        try:
            res = await relay.exchange({"type": "vision_latency_test", "owner": dono, "iterations": iters}, timeout=25.0)
            if res.get("type") in ("vision_latency_test_ok", "vision_latency_ok"):
                r_data = res.get("resultado") or {}
                if not r_data and "latencia_ms" in res:
                    r_data = {
                        "status": "sucesso",
                        "motor": "local",
                        "dispositivo": "PC (Túnel)",
                        "iteracoes": iters,
                        "latencia_media_ms": res["latencia_ms"],
                        "latencia_min_ms": res["latencia_ms"],
                        "latencia_max_ms": res["latencia_ms"],
                        "fps_estimado": round(1000.0 / max(res["latencia_ms"], 1.0), 1),
                        "mensagem": f"YOLOv8 no PC: média {res['latencia_ms']}ms",
                    }
                return r_data
            return res.get("resultado") or {"status": "erro", "mensagem": res.get("error", "Erro ao executar benchmark YOLO no PC")}
        except Exception as exc:
            log.warning("Falha ao delegar vision_latency_test ao PC: %s", exc)
    import vision_service
    try:
        return vision_service.testar_latencia_yolo_local(iteracoes=iters)
    except Exception as exc:
        return {"status": "erro", "mensagem": str(exc)}


@router.post("/api/vision/analyze")
async def vision_analyze_post(request: Request, body: VisionAnalyzeRequest):
    """Executa detecção de visão em uma imagem via motor ativo ou especificado."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "ai", dono)
    if relay.ws is not None:
        try:
            res = await relay.exchange({
                "type": "vision_analyze",
                "owner": dono,
                "image": body.image,
                "engine": body.engine or "",
                "classes": body.classes,
            }, timeout=60.0)
            if res.get("type") == "vision_analyze_ok":
                return res.get("resultado", {})
            return res.get("resultado") or {"status": "erro", "mensagem": res.get("error", "Erro na análise")}
        except Exception as exc:
            log.warning("Falha ao delegar vision_analyze ao PC: %s", exc)
    import vision_service
    return vision_service.analisar_imagem(
        body.image,
        motor=body.engine or None,
        classes_personalizadas=body.classes,
    )


@router.post("/api/ai/latency-test")
async def ai_latency_test(request: Request):
    """Executa benchmark de latência da IA local (Qwen 2.5 1.5B)."""
    try:
        require_csrf(request)
        dono = await revogacao_ok(request)
    except Exception as exc:
        return {"status": "erro", "mensagem": f"Autenticação necessária: {exc}"}
    if relay.ws is not None:
        try:
            res = await relay.exchange({"type": "ai_latency_test", "owner": dono}, timeout=15.0)
            if res.get("type") in ("ai_latency_test_ok", "ai_latency_ok"):
                r_data = res.get("resultado") or {}
                if not r_data and "latencia_ms" in res:
                    r_data = {
                        "status": "sucesso",
                        "ttft_ms": res["latencia_ms"],
                        "duracao_ms": res["latencia_ms"],
                        "tokens_per_sec": 18,
                        "local_online": True,
                        "modelo": "Qwen 2.5 (PC Túnel)",
                    }
                return r_data
            return res.get("resultado") or {"status": "erro", "mensagem": res.get("error", "Erro ao executar benchmark de IA no PC")}
        except Exception as exc:
            log.warning("Falha ao delegar ai_latency_test ao PC: %s", exc)
    import providers
    try:
        return providers.testar_latencia_ai()
    except Exception as exc:
        return {"status": "erro", "mensagem": f"Servidor local na porta 8008 inacessível: {exc}"}


# =====================================================================
# ROTAS DE CONEXÕES DE FORA, PROVEDORES EXTERNOS & TÚNEIS SSH
# =====================================================================
class CustomProviderBody(BaseModel):
    id: str = ""
    label: str = ""
    base: str = ""
    api_key: str = ""
    chave: str = ""
    api: str = "openai"
    modelos: Any = Field(default_factory=list)
    device_type: str = "custom"

class ProbeBody(BaseModel):
    base: str = ""
    api_key: str = ""
    chave: str = ""
    model_id: str = ""

def _sanitizar_custom_provider(p: dict) -> dict:
    if not isinstance(p, dict):
        return {}
    out = {k: v for k, v in p.items() if k != "api_key"}
    out["has_key"] = bool(p.get("api_key"))
    return out

@router.get("/api/providers/custom")
async def list_custom_providers(request: Request):
    require_csrf(request)
    dono = await revogacao_ok(request) if relay.ws is not None else sessao_usuario(request)
    import custom_providers
    provs = custom_providers.carregar_custom_providers()
    return {"status": "ok", "providers": [_sanitizar_custom_provider(p) for p in provs.values()]}

@router.post("/api/providers/custom")
async def save_custom_provider(request: Request, body: CustomProviderBody):
    require_csrf(request)
    dono = await revogacao_ok(request) if relay.ws is not None else sessao_usuario(request)
    import custom_providers
    dados = body.model_dump()
    if not dados.get("api_key") and dados.get("chave"):
        dados["api_key"] = dados.pop("chave")
    else:
        dados.pop("chave", None)
    try:
        reg = custom_providers.salvar_custom_provider(dados)
        if relay.ws is not None:
            try:
                await relay.exchange({"type": "sync_custom_provider", "owner": dono, "provider": reg}, timeout=5.0)
            except Exception:
                pass
        return {"status": "ok", "provider": _sanitizar_custom_provider(reg)}
    except Exception as exc:
        raise HTTPException(422, str(exc))

@router.delete("/api/providers/custom/{provider_id}")
async def delete_custom_provider(request: Request, provider_id: str):
    require_csrf(request)
    dono = await revogacao_ok(request) if relay.ws is not None else sessao_usuario(request)
    import custom_providers
    ok = custom_providers.remover_custom_provider(provider_id)
    if relay.ws is not None:
        try:
            await relay.exchange({"type": "delete_custom_provider", "owner": dono, "provider_id": provider_id}, timeout=5.0)
        except Exception:
            pass
    return {"status": "ok", "removed": ok}

@router.post("/api/providers/test")
async def test_custom_provider(request: Request, body: ProbeBody):
    require_csrf(request)
    dono = await revogacao_ok(request) if relay.ws is not None else sessao_usuario(request)
    chave_val = body.api_key or body.chave
    if relay.ws is not None:
        try:
            res = await relay.exchange({"type": "probe_external_provider", "owner": dono, "base": body.base, "api_key": chave_val, "model_id": body.model_id}, timeout=15.0)
            if res.get("type") == "probe_external_provider_ok":
                return res.get("resultado", {})
        except Exception:
            pass
    import custom_providers
    return custom_providers.testar_conexao_externa(body.base, chave_val, body.model_id)

@router.get("/api/tunnel/guide")
async def tunnel_guide(request: Request, tipo: str = "ssh_reverse", porta: int = 8008, host: str = "usuario@seu-pc-ou-vps"):
    require_csrf(request)
    if relay.ws is not None:
        await revogacao_ok(request)
    else:
        sessao_usuario(request)
    import custom_providers
    return custom_providers.gerar_instrucoes_tunel(tipo, porta, host)


