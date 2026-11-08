"""Router: Administração de usuários, convites, limites e configuração."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from relay_core import _rate_limit, relay, sessao_dados

router = APIRouter()

# ---------------------------------------------------------------------------
# Admin HTTP endpoints — require admin session, proxy to PC agent via relay.
# ---------------------------------------------------------------------------

class AdminCreateUser(BaseModel):
    display: str = Field(min_length=2, max_length=40)
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user")
    limites: dict = Field(default_factory=dict)


class AdminRoleBody(BaseModel):
    uid: str
    role: str


class AdminStatusBody(BaseModel):
    uid: str
    status: str
    dias: int = Field(default=0, ge=0, le=365)


class AdminUidBody(BaseModel):
    uid: str


class AdminInviteCreate(BaseModel):
    max_usos: int = Field(default=1, ge=1, le=999)
    dias: int = Field(default=7, ge=1, le=365)
    nota: str = Field(default="", max_length=200)


class AdminRegDecide(BaseModel):
    id: int
    aprovar: bool


class AdminConfigSet(BaseModel):
    modo: str = Field(default="", max_length=20)
    exigir_aprovacao: bool = False


class AdminLimitsBody(BaseModel):
    uid: str
    max_ai_hora: int = Field(default=0, ge=0)
    max_ia_simult: int = Field(default=0, ge=0)
    remote_ok: bool | None = None


async def admin_uid(request: Request) -> str:
    import admin_http
    return await admin_http.guard(request, __import__("sys").modules["server"])


@router.get("/api/admin/users")
async def admin_users(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_users", "owner": uid, "sid": str(sessao_dados(request).get("sid") or "")}, timeout=20.0)
    if result.get("type") != "admin_users":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return result


@router.post("/api/admin/users/create")
async def admin_create_user(request: Request, body: AdminCreateUser):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({
        "type": "admin_user_create", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
        "username": body.username, "display": body.display,
        "password": body.password, "role": body.role,
        "limites": body.limites,
    }, timeout=20.0)
    if result.get("type") != "admin_user_created":
        raise HTTPException(422, result.get("error", "Falha ao criar"))
    return result


@router.post("/api/admin/users/role")
async def admin_set_role(request: Request, body: AdminRoleBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_role", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "uid": body.uid, "role": body.role}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.post("/api/admin/users/status")
async def admin_set_status(request: Request, body: AdminStatusBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_status", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "uid": body.uid, "status": body.status,
                                   "dias": body.dias}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.post("/api/admin/users/sessions")
async def admin_revoke_sessions(request: Request, body: AdminUidBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_sess_revoke", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "uid": body.uid}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.post("/api/admin/users/delete")
async def admin_delete_user(request: Request, body: AdminUidBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_delete", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "uid": body.uid}, timeout=30.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True, "apagados": result.get("apagados", 0)}


@router.post("/api/admin/users/limits")
async def admin_set_limits(request: Request, body: AdminLimitsBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_limits", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "uid": body.uid,
                                   "max_ai_hora": body.max_ai_hora,
                                   "max_ia_simult": body.max_ia_simult,
                                   "remote_ok": body.remote_ok}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.post("/api/admin/quality/run")
async def admin_quality_run(request: Request):
    uid = await admin_uid(request)
    _rate_limit(request, "admin_quality", uid)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "quality_run", "owner": uid, "sid": str(sessao_dados(request).get("sid") or "")}, timeout=120.0)
    if result.get("type") != "quality_run":
        raise HTTPException(503, result.get("error", "Benchmark indisponível"))
    return {"run_id": result.get("run_id"), "summary": result.get("summary", {}),
            "dataset": result.get("dataset", {})}


@router.get("/api/admin/quality/runs")
async def admin_quality_runs(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "quality_runs", "owner": uid, "sid": str(sessao_dados(request).get("sid") or "")}, timeout=20.0)
    if result.get("type") != "quality_runs":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return {"runs": result.get("runs", [])}


@router.get("/api/admin/invites")
async def admin_invites(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_invites", "owner": uid, "sid": str(sessao_dados(request).get("sid") or "")}, timeout=20.0)
    if result.get("type") != "admin_invites":
        raise HTTPException(503, "Indisponível")
    return result


@router.post("/api/admin/invites/create")
async def admin_create_invite(request: Request, body: AdminInviteCreate):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({
        "type": "admin_invite_create", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
        "max_usos": body.max_usos, "dias": body.dias, "nota": body.nota,
    }, timeout=20.0)
    if result.get("type") != "admin_invite":
        raise HTTPException(422, result.get("error", "Falha"))
    return result


@router.post("/api/admin/invites/revoke")
async def admin_revoke_invite(request: Request, body: AdminRegDecide):
    uid = await admin_uid(request)
    if body.id <= 0:
        raise HTTPException(422, "ID inválido")
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_invite_revoke", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.get("/api/admin/regs")
async def admin_regs(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_regs", "owner": uid, "sid": str(sessao_dados(request).get("sid") or "")}, timeout=20.0)
    if result.get("type") != "admin_regs":
        raise HTTPException(503, "Indisponível")
    return result


@router.post("/api/admin/regs/decide")
async def admin_decide_reg(request: Request, body: AdminRegDecide):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_reg_decide", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "id": body.id, "aprovar": body.aprovar}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.get("/api/admin/config")
async def admin_config_get(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "auth_config"}, timeout=10.0)
    if result.get("type") != "auth_config":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return result


@router.post("/api/admin/config")
async def admin_config_set(request: Request, body: AdminConfigSet):
    uid = await admin_uid(request)
    if body.modo and body.modo not in ("fechado", "convite", "aberto"):
        raise HTTPException(422, "Modo inválido")
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_config_set", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "modo": body.modo, "exigir_aprovacao": body.exigir_aprovacao}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@router.get("/api/admin/audit")
async def admin_audit(request: Request, limite: int = 200):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_audit", "owner": uid, "sid": str(sessao_dados(request).get("sid") or ""),
                                   "limite": limite}, timeout=20.0)
    if result.get("type") != "admin_audit":
        raise HTTPException(503, "Indisponível")
    return result
