"""Router: Memórias do usuário, preferências e eventos de memória."""
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from relay_core import relay, require_csrf, revogacao_ok, verify_session

router = APIRouter()

@router.get("/api/memories")
async def memories_list(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_list":
        raise HTTPException(503, "Memória indisponível")
    return {"memories": result.get("memories", [])[:100]}


@router.delete("/api/memories/{key}")
async def memories_forget(request: Request, key: str):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[\w\-\.]{1,80}", key, re.UNICODE):
        raise HTTPException(422, "Chave inválida")
    result = await relay.exchange({"type": "mem_forget", "owner": dono,
                                   "key": key}, timeout=20.0)
    if result.get("type") != "mem_forgotten":
        raise HTTPException(503, "Não foi possível esquecer")
    return {"ok": True, "key": key}


class MemUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=500)


class MemSettings(BaseModel):
    learning: bool


@router.get("/api/memories/full")
async def memories_full(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_list_full", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_list_full":
        raise HTTPException(503, "Memória indisponível")
    return {"memories": result.get("memories", [])[:200]}


@router.post("/api/memories/confirm")
async def memories_confirm(request: Request):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_confirm", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_confirmed":
        raise HTTPException(503, "Nada para confirmar")
    return result


@router.put("/api/memories/{key}")
async def memories_update(request: Request, key: str, body: MemUpdate):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[\w\-\.]{1,80}", key, re.UNICODE):
        raise HTTPException(422, "Chave inválida")
    result = await relay.exchange({"type": "mem_update", "owner": dono,
                                   "key": key, "value": body.value}, timeout=20.0)
    if result.get("type") != "mem_updated":
        raise HTTPException(503, result.get("error", "Falha ao corrigir"))
    return {"ok": True, "key": key}


@router.get("/api/memory/settings")
async def memory_settings_get(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_settings", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_settings":
        raise HTTPException(503, "Configuração indisponível")
    return {"learning": result.get("learning", True)}


@router.post("/api/memory/settings")
async def memory_settings_set(request: Request, body: MemSettings):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_settings", "owner": dono,
                                   "learning": "1" if body.learning else "0"}, timeout=20.0)
    if result.get("type") != "mem_settings":
        raise HTTPException(503, "Falha ao salvar")
    return {"learning": result.get("learning", True)}


@router.get("/api/memory/events")
async def memory_events(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "event_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "event_list":
        raise HTTPException(503, "Eventos indisponíveis")
    return {"events": result.get("events", [])[:20]}
