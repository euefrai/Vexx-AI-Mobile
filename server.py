"""Vexx AI relay: authentication + ephemeral WebSocket RPC only.
No chat history or SQLite file is stored on Render.
"""
import asyncio
import base64
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path

from argon2 import PasswordHasher, exceptions as argon_errors
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from workspace_store import WorkspaceBatch

import env_local
env_local.carregar_env_local()  # .env local do PC (nunca sobrescreve o sistema)

log = logging.getLogger("JULIA-mobile")
ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Vexx AI Relay", docs_url=None, redoc_url=None, openapi_url=None)
ph = PasswordHasher()
SESSION_LIFETIME = 12 * 60 * 60
DOC_UPLOAD_MAX_BYTES = 15 * 1024 * 1024
DOC_UPLOAD_REQUEST_MAX_BYTES = DOC_UPLOAD_MAX_BYTES + 1024 * 1024


class DocumentUploadBodyLimit:
    """Bound actual multipart request bytes before Starlette spools uploaded files."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/docs/upload":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > DOC_UPLOAD_REQUEST_MAX_BYTES:
                    response = JSONResponse(
                        {"detail": "Pedido de upload excede o limite permitido."}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse({"detail": "Content-Length inválido."}, status_code=400)
                await response(scope, receive, send)
                return
        total = 0

        async def receive_limited():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > DOC_UPLOAD_REQUEST_MAX_BYTES:
                    raise HTTPException(413, "Pedido de upload excede o limite permitido.")
            return message

        try:
            await self.app(scope, receive_limited, send)
        except HTTPException as exc:
            if exc.status_code != 413:
                raise
            response = JSONResponse({"detail": exc.detail}, status_code=413)
            await response(scope, receive, send)


app.add_middleware(DocumentUploadBodyLimit)


def config():
    return {
        "user": os.environ.get("JULIA_USERNAME", ""),
        "password_hash": os.environ.get("JULIA_PASSWORD_HASH", ""),
        "agent_token": os.environ.get("JULIA_AGENT_TOKEN", ""),
        "session_secret": os.environ.get("JULIA_SESSION_SECRET", ""),
        "production": os.environ.get("JULIA_ENV") == "production",
    }


def is_ready():
    c = config()
    return all(c[k] for k in ("user", "password_hash", "agent_token", "session_secret"))


def signer():
    secret = config()["session_secret"]
    if not secret:
        raise HTTPException(503, "Servidor ainda não configurado")
    return URLSafeTimedSerializer(secret, salt="JULIA-mobile-session-v1")


def sessao_dados(request: Request) -> dict:
    """Sessão autenticada: {uid, user, sid}. uid é o dono dos dados no PC."""
    token = request.cookies.get("JULIA_session")
    if not token:
        raise HTTPException(status_code=401, detail="Faça login")
    try:
        data = signer().loads(token, max_age=SESSION_LIFETIME)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Sessão expirada") from None
    if data.get("user") != config()["user"] and "uid" not in data:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return data


def sessao_usuario(request: Request) -> str:
    """Dono autenticado da sessão (base do isolamento multiusuário)."""
    data = sessao_dados(request)
    uid = str(data.get("uid") or "")
    if uid:
        return uid
    return "local"  # sessão legada (só username): dono proprietário


def emitir_sessao(response: Response, uid: str, nome: str, sid: str = "") -> dict:
    token = signer().dumps({"user": config()["user"], "uid": uid,
                            "nome": nome, "sid": sid or secrets.token_hex(8),
                            "nonce": secrets.token_hex(16)})
    response.set_cookie(
        "JULIA_session", token, httponly=True, secure=config()["production"],
        samesite="strict", max_age=SESSION_LIFETIME, path="/"
    )
    return {"authenticated": True, "csrf": csrf_value(token), "user": nome, "uid": uid}


# Revogação no PC; falhas transitórias nunca desabilitam a verificação.
revogados = {"sids": set(), "ts": 0.0, "suportado": True, "falhas": 0}
REVOGA_TTL = 60.0


async def revogacao_ok(request: Request) -> str:
    """uid autenticado + sessão não revogada. Levanta 401 caso contrário."""
    data = sessao_dados(request)
    uid = str(data.get("uid") or "") or "local"
    sid = str(data.get("sid") or "")
    if sid:
        agora = time.monotonic()
        if sid in revogados["sids"]:
            raise HTTPException(status_code=401, detail="Sessão revogada")
        if agora - revogados["ts"] > REVOGA_TTL and relay.ws is None:
            raise HTTPException(503, "Computador offline; não foi possível verificar a sessão")
        if agora - revogados["ts"] > REVOGA_TTL and relay.ws is not None:
            try:
                res = await relay.exchange({"type": "sess_revogados"}, timeout=5.0)
                if res.get("type") == "sess_revogados":
                    revogados["sids"] = set(res.get("sids", []))
                    revogados["ts"] = agora
                    revogados["falhas"] = 0
                else:
                    raise HTTPException(503, "Não foi possível verificar a sessão")
            except HTTPException:
                revogados["falhas"] += 1
                raise HTTPException(503, "Não foi possível verificar a sessão; tente novamente") from None
        if sid in revogados["sids"]:
            raise HTTPException(status_code=401, detail="Sessão revogada")
    return uid


def verify_session(request: Request) -> str:
    sessao_usuario(request)
    token = request.cookies.get("JULIA_session")
    return token or ""


def csrf_value(token: str) -> str:
    return hmac.new(config()["session_secret"].encode(), (token + ":csrf").encode(), "sha256").hexdigest()


def require_csrf(request: Request) -> None:
    token = verify_session(request)
    candidate = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(candidate, csrf_value(token)):
        raise HTTPException(403, "Token de requisição inválido")
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        host = request.headers.get("host", "")
        if parsed.netloc.lower() != host.lower():
            raise HTTPException(403, "Origem inválida")
        if config()["production"] and parsed.scheme != "https":
            raise HTTPException(403, "Conexão segura obrigatória")


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class Message(BaseModel):
    id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: str = Field(min_length=3, max_length=100)
    role: str = Field(pattern=r"^(user|assistant)$")
    text: str = Field(min_length=1, max_length=10000)
    created_at: str = Field(min_length=10, max_length=48)
    origin: str = Field(pattern=r"^mobile$")


class SyncBody(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)


class AIRequest(BaseModel):
    scene_state: str = Field(default="", max_length=4000)
    message_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: str = Field(min_length=3, max_length=100)
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9_.:/+-]*$")
    memory: int = Field(default=1, ge=0, le=1)
    local_time: str = Field(default="", max_length=48)
    timezone: str = Field(default="", max_length=80)
    city: str = Field(default="", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # Piggyback anti-corrida: a mensagem vai junto; o agente persiste
    # (INSERT OR IGNORE, mesmas regras do /api/sync) antes de responder.
    text: str = Field(default="", max_length=10000)
    created_at: str = Field(default="", max_length=48)


class ExportMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    text: str = Field(max_length=10000)
    created_at: str = Field(default="", max_length=48)


class XlsxExport(BaseModel):
    title: str = Field(default="Conversa", max_length=100)
    messages: list[ExportMessage] = Field(min_length=1, max_length=500)


class InputBody(BaseModel):
    kind: str = Field(pattern=r"^(move|click|double|right|scroll|key|text)$")
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    dx: int = Field(default=0, ge=-10, le=10)
    dy: int = Field(default=0, ge=-10, le=10)
    key: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=200)


# Single Render instance / single paired PC. All values intentionally volatile.
class AgentRelay:
    def __init__(self):
        self.ws: WebSocket | None = None
        self.ws_desde: float | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.streams: dict[str, asyncio.Queue] = {}
        self.send_lock = asyncio.Lock()
        # Live research: sub_id -> {job_id, owner, fila}. Teto anti-abuso.
        self.research_subs: dict[str, dict] = {}

    def ha(self) -> int:
        if self.ws is None or not self.ws_desde:
            return -1
        return max(0, int(time.monotonic() - self.ws_desde))

    async def exchange(self, payload: dict, timeout: float = 12.0) -> dict:
        ws = self.ws
        if ws is None:
            raise HTTPException(503, "Computador desconectado; mensagens continuam no celular")
        request_id = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self.pending[request_id] = fut
        try:
            async with self.send_lock:
                if ws is not self.ws:
                    raise HTTPException(503, "Agente reconectando")
                await ws.send_json({**payload, "request_id": request_id})
            return await asyncio.wait_for(fut, timeout)
        except (asyncio.TimeoutError, RuntimeError, WebSocketDisconnect, OSError):
            raise HTTPException(503, "Não houve confirmação do computador; tentaremos novamente") from None
        finally:
            self.pending.pop(request_id, None)

    def fail_pending(self):
        for future in self.pending.values():
            if not future.done():
                future.set_exception(HTTPException(503, "Agente desconectado"))
        for fila in self.streams.values():
            while not fila.empty():
                fila.get_nowait()
            fila.put_nowait({"type": "ai_error", "error": "Agente desconectado", "codigo": "desconectado"})
        for sub in self.research_subs.values():
            try:
                sub["fila"].put_nowait({"seq": -1, "tipo": "relay_desconectado"})
            except asyncio.QueueFull:
                pass


relay = AgentRelay()
# Basic, non-durable login rate limiting; reinforce with Cloudflare / WAF for production.
login_failures: dict[str, list[float]] = {}


class ResearchSSECursor:
    """Ordena/deduplica eventos por seq e tolera replay fora de ordem.

    O backlog é autoritativo, mas push ao vivo pode repetir ou chegar
    invertido. Só libera `vistos+1` em diante; no evento terminal (ou após
    timeout) libera o que restou em ordem, para não prolongar a conexão por
    uma lacuna que não será preenchida.
    """

    TERMINAIS = {"research_completed", "research_failed", "research_cancelled"}

    def __init__(self, apos_seq: int = 0):
        self.vistos = max(0, int(apos_seq or 0))
        self.pendentes: dict[int, dict] = {}

    def oferecer(self, ev: dict) -> list[dict]:
        seq = ev.get("seq") if isinstance(ev, dict) else None
        if not isinstance(seq, int) or seq <= self.vistos:
            return []
        self.pendentes[seq] = ev
        out = []
        while self.vistos + 1 in self.pendentes:
            self.vistos += 1
            out.append(self.pendentes.pop(self.vistos))
        return out

    def liberar_tudo(self) -> list[dict]:
        out = [self.pendentes[s] for s in sorted(self.pendentes)
               if s > self.vistos]
        if out:
            self.vistos = max(self.vistos, out[-1]["seq"])
            self.pendentes.clear()
        return out

    @classmethod
    def terminal(cls, ev: dict) -> bool:
        return isinstance(ev, dict) and ev.get("tipo") in cls.TERMINAIS


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "configured": is_ready()}


def erro_relay(result: dict, padrao_msg: str, padrao_status: int = 503) -> HTTPException:
    """Traduz erro do agente: conta bloqueada/pendente vira 403 explicável,
    nunca 503 de 'conectividade' (que mascarou o problema real)."""
    detalhe = result.get("error", padrao_msg) if isinstance(result, dict) else padrao_msg
    codigo = result.get("codigo", "") if isinstance(result, dict) else ""
    if codigo in ("bloqueada", "pendente"):
        return HTTPException(403, detalhe or "Conta indisponível. Fale com o administrador.")
    return HTTPException(padrao_status, detalhe)


INSTANCE_ID = secrets.token_hex(4)


@app.get("/api/diag")
def diag():
    """Diagnóstico público SEM dados sensíveis: o relay vê o agente?

    `instance` destingue instâncias (dreno de deploy): respostas iguais
    vêm do mesmo processo; diferentes = split-brain entre instâncias.
    """
    return {"pc_online": relay.ws is not None, "agente_ha": relay.ha(),
            "commit": os.environ.get("RENDER_GIT_COMMIT", "local")[:12],
            "instance": INSTANCE_ID}


def _limite_tentativas(request: Request, chave: str, teto: int, janela: float) -> None:
    source = (request.client.host if request.client else "unknown") + ":" + chave
    agora = time.monotonic()
    tentativas = [t for t in login_failures.get(source, []) if agora - t < janela]
    if len(tentativas) >= teto:
        raise HTTPException(429, "Muitas tentativas; tente novamente mais tarde")
    tentativas.append(agora)
    login_failures[source] = tentativas


def _limpa_tentativas(request: Request, chave: str) -> None:
    login_failures.pop(((request.client.host if request.client else "unknown") + ":" + chave), None)


@app.post("/api/login")
async def login(credentials: Credentials, request: Request, response: Response):
    if not is_ready():
        raise HTTPException(503, "Configure as variáveis secretas no servidor")
    cfg = config()
    if hmac.compare_digest(credentials.username, cfg["user"]):
        _limite_tentativas(request, "login:" + credentials.username.strip().lower()[:40], 5, 300)
        try:
            if ph.verify(cfg["password_hash"], credentials.password):
                _limpa_tentativas(request, "login:" + credentials.username.strip().lower()[:40])
                return emitir_sessao(response, "local", cfg["user"])
        except (argon_errors.VerifyMismatchError, argon_errors.VerificationError,
                argon_errors.InvalidHashError):
            pass
        raise HTTPException(401, "Usuário ou senha inválidos")
    # Conta comum: verifica no PC (exige agente online; sem simulação).
    if relay.ws is None:
        raise HTTPException(503, "Login de contas do PC indisponível: conecte o computador.")
    _limite_tentativas(request, "login:" + credentials.username.strip().lower()[:40], 5, 300)
    try:
        result = await relay.exchange({"type": "auth_login", "username": credentials.username,
                                       "password": credentials.password}, timeout=20.0)
    except HTTPException:
        raise HTTPException(401, "Usuário ou senha inválidos") from None
    if result.get("type") == "auth_error" and result.get("codigo") == "pendente":
        raise HTTPException(403, "Conta aguardando aprovação.")
    if result.get("type") != "auth_ok":
        raise HTTPException(401, "Usuário ou senha inválidos")
    _limpa_tentativas(request, "login:" + credentials.username.strip().lower()[:40])
    return emitir_sessao(response, result["uid"], result["display"],
                         sid=result.get("sid", ""))


class Registro(BaseModel):
    display: str = Field(min_length=2, max_length=40)
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    invite: str = Field(default="", max_length=32)


@app.get("/api/auth/config")
async def auth_config(request: Request):
    if relay.ws is None:
        return {"modo": "fechado", "exigir_aprovacao": True, "agent_online": False}
    try:
        result = await relay.exchange({"type": "auth_config"}, timeout=10.0)
    except HTTPException:
        return {"modo": "fechado", "exigir_aprovacao": True, "agent_online": False}
    if result.get("type") != "auth_config":
        return {"modo": "fechado", "exigir_aprovacao": True, "agent_online": True}
    return {"modo": result.get("modo", "convite"),
            "exigir_aprovacao": result.get("exigir_aprovacao", True),
            "agent_online": True}


@app.post("/api/register")
async def register(body: Registro, request: Request, response: Response):
    if relay.ws is None:
        raise HTTPException(503, "Cadastro indisponível: computador offline. Tente quando online.")
    _limite_tentativas(request, "register", 3, 3600)
    try:
        result = await relay.exchange({"type": "auth_register", "display": body.display,
                                       "username": body.username, "password": body.password,
                                       "invite": body.invite}, timeout=20.0)
    except HTTPException:
        raise HTTPException(503, "Cadastro indisponível no momento.") from None
    if result.get("type") == "auth_error":
        codigo = result.get("codigo", "")
        status = 409 if codigo == "duplicado" else 422 if codigo in (
            "username_invalido", "senha_fraca", "nome_invalido", "convite_necessario",
            "convite_invalido", "fechado") else 503
        raise HTTPException(status, result.get("error", "Não foi possível cadastrar"))
    if result.get("type") != "auth_registered":
        raise HTTPException(503, "Cadastro indisponível no momento.")
    if result.get("status") == "pendente" or not result.get("sid"):
        return {"registered": True, "status": "pendente", "username": result.get("username", "")}
    return emitir_sessao(response, result["uid"], result["display"], sid=result.get("sid", ""))


@app.get("/api/session")
async def session(request: Request):
    data = sessao_dados(request)
    uid = str(data.get("uid") or "") or "local"
    nome = str(data.get("nome") or data.get("user") or config()["user"])
    if uid == "local":
        papel = "admin"  # proprietário legado: sem depender do PC
    else:
        papel = "user"
        if relay.ws is not None:
            try:
                result = await relay.exchange({"type": "auth_whoami", "sid": str(data.get("sid") or "")},
                                              timeout=10.0)
                if result.get("type") == "auth_user" and result.get("user"):
                    if result["user"].get("uid") != uid:
                        raise HTTPException(status_code=401, detail="Sessão inválida")
                    papel = result["user"].get("role", "user")
                    nome = result["user"].get("display", nome)
            except HTTPException as exc:
                if exc.status_code == 401:
                    raise
    token = request.cookies.get("JULIA_session", "")
    return {"authenticated": True, "csrf": csrf_value(token), "user": nome,
            "uid": uid, "role": papel}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    require_csrf(request)
    sid = str(sessao_dados(request).get("sid") or "")
    if sid:
        result = await relay.exchange({"type": "auth_logout", "sid": sid}, timeout=10.0)
        if result.get("type") != "auth_logged_out":
            raise HTTPException(503, "O PC não confirmou o encerramento da sessão")
        revogados["sids"].add(sid)
    response.delete_cookie("JULIA_session", path="/")
    return {"ok": True}


class TrocaSenha(BaseModel):
    atual: str = Field(min_length=1, max_length=128)
    nova: str = Field(min_length=8, max_length=128)


@app.get("/api/account")
async def account_me(request: Request):
    data = sessao_dados(request)
    uid = str(data.get("uid") or "") or "local"
    if uid == "local":
        return {"uid": "local", "username": config()["user"],
                "display": config()["user"], "role": "admin", "local": True}
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "auth_whoami",
                                   "sid": str(data.get("sid") or "")}, timeout=10.0)
    if result.get("type") != "auth_user" or not result.get("user") or result["user"].get("uid") != dono:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return result["user"]


@app.post("/api/account/password")
async def account_password(request: Request, body: TrocaSenha):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if dono == "local":
        raise HTTPException(422, "A senha do proprietário se troca nas variáveis do servidor.")
    result = await relay.exchange({"type": "account_password", "uid": dono,
                                   "atual": body.atual, "nova": body.nova}, timeout=20.0)
    if result.get("type") != "account_ok":
        raise HTTPException(422 if result.get("type") == "op_error" else 503,
                            result.get("error", "Falha ao trocar senha"))
    return {"ok": True}


class ExcluiConta(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@app.post("/api/account/delete")
async def account_delete(request: Request, body: ExcluiConta, response: Response):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if dono == "local":
        raise HTTPException(422, "A conta do proprietário não se exclui por aqui.")
    result = await relay.exchange({"type": "account_delete", "uid": dono,
                                   "password": body.password}, timeout=30.0)
    if result.get("type") != "account_deleted":
        raise HTTPException(422 if result.get("type") == "op_error" else 503,
                            result.get("error", "Falha ao excluir"))
    response.delete_cookie("JULIA_session", path="/")
    return {"ok": True, "apagados": result.get("apagados", 0)}


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
    """Valida sessão + CSRF e retorna uid se o usuário for admin ativo."""
    verify_session(request)
    data = sessao_dados(request)
    uid = str(data.get("uid") or "") or "local"
    # Owner legado é sempre admin
    if uid == "local":
        return uid
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "auth_whoami", "sid": str(data.get("sid") or "")},
                                  timeout=10.0)
    if result.get("type") != "auth_user" or not result.get("user"):
        raise HTTPException(401, "Sessão inválida")
    user = result["user"]
    if user.get("uid") != uid:
        raise HTTPException(401, "Sessão inválida")
    if user.get("role") != "admin" or user.get("status") != "ativo":
        raise HTTPException(403, "Permissão de administrador necessária")
    return uid


@app.get("/api/admin/users")
async def admin_users(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_users", "owner": uid}, timeout=20.0)
    if result.get("type") != "admin_users":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return result


@app.post("/api/admin/users/create")
async def admin_create_user(request: Request, body: AdminCreateUser):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({
        "type": "admin_user_create", "owner": uid,
        "username": body.username, "display": body.display,
        "password": body.password, "role": body.role,
        "limites": body.limites,
    }, timeout=20.0)
    if result.get("type") != "admin_user_created":
        raise HTTPException(422, result.get("error", "Falha ao criar"))
    return result


@app.post("/api/admin/users/role")
async def admin_set_role(request: Request, body: AdminRoleBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_role", "owner": uid,
                                   "uid": body.uid, "role": body.role}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.post("/api/admin/users/status")
async def admin_set_status(request: Request, body: AdminStatusBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_status", "owner": uid,
                                   "uid": body.uid, "status": body.status,
                                   "dias": body.dias}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.post("/api/admin/users/sessions")
async def admin_revoke_sessions(request: Request, body: AdminUidBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_sess_revoke", "owner": uid,
                                   "uid": body.uid}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.post("/api/admin/users/delete")
async def admin_delete_user(request: Request, body: AdminUidBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_delete", "owner": uid,
                                   "uid": body.uid}, timeout=30.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True, "apagados": result.get("apagados", 0)}


@app.post("/api/admin/users/limits")
async def admin_set_limits(request: Request, body: AdminLimitsBody):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_user_limits", "owner": uid,
                                   "uid": body.uid,
                                   "max_ai_hora": body.max_ai_hora,
                                   "max_ia_simult": body.max_ia_simult,
                                   "remote_ok": body.remote_ok}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.post("/api/admin/quality/run")
async def admin_quality_run(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "quality_run", "owner": uid}, timeout=120.0)
    if result.get("type") != "quality_run":
        raise HTTPException(503, result.get("error", "Benchmark indisponível"))
    return {"run_id": result.get("run_id"), "summary": result.get("summary", {}),
            "dataset": result.get("dataset", {})}


@app.get("/api/admin/quality/runs")
async def admin_quality_runs(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "quality_runs", "owner": uid}, timeout=20.0)
    if result.get("type") != "quality_runs":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return {"runs": result.get("runs", [])}


@app.get("/api/admin/invites")
async def admin_invites(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_invites", "owner": uid}, timeout=20.0)
    if result.get("type") != "admin_invites":
        raise HTTPException(503, "Indisponível")
    return result


@app.post("/api/admin/invites/create")
async def admin_create_invite(request: Request, body: AdminInviteCreate):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({
        "type": "admin_invite_create", "owner": uid,
        "max_usos": body.max_usos, "dias": body.dias, "nota": body.nota,
    }, timeout=20.0)
    if result.get("type") != "admin_invite":
        raise HTTPException(422, result.get("error", "Falha"))
    return result


@app.post("/api/admin/invites/revoke")
async def admin_revoke_invite(request: Request, body: AdminRegDecide):
    uid = await admin_uid(request)
    if body.id <= 0:
        raise HTTPException(422, "ID inválido")
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_invite_revoke", "owner": uid,
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.get("/api/admin/regs")
async def admin_regs(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_regs", "owner": uid}, timeout=20.0)
    if result.get("type") != "admin_regs":
        raise HTTPException(503, "Indisponível")
    return result


@app.post("/api/admin/regs/decide")
async def admin_decide_reg(request: Request, body: AdminRegDecide):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_reg_decide", "owner": uid,
                                   "id": body.id, "aprovar": body.aprovar}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.get("/api/admin/config")
async def admin_config_get(request: Request):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "auth_config"}, timeout=10.0)
    if result.get("type") != "auth_config":
        raise HTTPException(503, result.get("error", "Indisponível"))
    return result


@app.post("/api/admin/config")
async def admin_config_set(request: Request, body: AdminConfigSet):
    uid = await admin_uid(request)
    if body.modo and body.modo not in ("fechado", "convite", "aberto"):
        raise HTTPException(422, "Modo inválido")
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_config_set", "owner": uid,
                                   "modo": body.modo, "exigir_aprovacao": body.exigir_aprovacao}, timeout=20.0)
    if result.get("type") != "admin_ok":
        raise HTTPException(422, result.get("error", "Falha"))
    return {"ok": True}


@app.get("/api/admin/audit")
async def admin_audit(request: Request, limite: int = 200):
    uid = await admin_uid(request)
    if relay.ws is None:
        raise HTTPException(503, "Computador offline.")
    result = await relay.exchange({"type": "admin_audit", "owner": uid,
                                   "limite": limite}, timeout=20.0)
    if result.get("type") != "admin_audit":
        raise HTTPException(503, "Indisponível")
    return result


@app.get("/api/status")
def status(request: Request):
    verify_session(request)
    return {"pc_online": relay.ws is not None, "agente_ha": relay.ha(),
            "messages_stored_on": "computer"}


@app.post("/api/export/xlsx")
async def export_xlsx(request: Request, body: XlsxExport):
    """Gera planilha de uma conversa já carregada no dispositivo autenticado."""
    require_csrf(request)
    await revogacao_ok(request)
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    def cell_text(value: str) -> str:
        text = str(value or "")
        return "'" + text if text.startswith(("=", "+", "-", "@")) else text

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversa"
    sheet.append(["Conversa", cell_text(body.title)])
    sheet.append(["Autor", "Data e hora", "Mensagem"])
    for cell in sheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4F46E5")
    for message in body.messages:
        sheet.append([
            "Júlia" if message.role == "assistant" else "Você",
            cell_text(message.created_at),
            cell_text(message.text),
        ])
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = f"A2:C{sheet.max_row}"
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 25
    sheet.column_dimensions["C"].width = 80
    for row in sheet.iter_rows(min_row=3, min_col=3, max_col=3):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="conversa.xlsx"'},
    )


@app.post("/api/sync")
async def sync_messages(request: Request, body: SyncBody):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "sync", "owner": dono,
                                   "messages": [m.model_dump() for m in body.messages]})
    if result.get("type") == "op_error":
        raise erro_relay(result, "Confirmação do PC não recebida")
    if result.get("type") != "ack":
        raise HTTPException(503, "Confirmação do PC não recebida")
    confirmed = set(result.get("confirmed_ids", []))
    submitted = {m.id for m in body.messages}
    return {"confirmed_ids": sorted(confirmed & submitted)}


@app.get("/api/messages")
async def messages(request: Request, conversation_id: str = "", cursor: str = ""):
    verify_session(request)
    dono = await revogacao_ok(request)
    before = None
    if cursor:
        try:
            if len(cursor) > 400:
                raise ValueError()
            before = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if not (isinstance(before, list) and len(before) == 2 and
                    all(isinstance(v, str) for v in before) and len(before[0]) <= 48 and len(before[1]) <= 100):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise HTTPException(422, "Cursor inválido") from None
    result = await relay.exchange({"type": "list", "owner": dono, "limit": 200,
                                   "conversation_id": conversation_id, "before": before})
    if result.get("type") != "history":
        raise HTTPException(503, "Histórico não disponível")
    msgs = result.get("messages", [])[:200]
    if conversation_id:
        msgs = [m for m in msgs if m.get("conversation_id") == conversation_id]
    next_cursor = ""
    if len(msgs) == 200:
        first = msgs[0]
        next_cursor = base64.urlsafe_b64encode(json.dumps(
            [first["created_at"], first["id"]]).encode()).decode()
    return {"messages": msgs, "next_cursor": next_cursor}


@app.post("/api/workspace/sync")
async def workspace_sync(request: Request, body: WorkspaceBatch):
    require_csrf(request)
    owner = await revogacao_ok(request)
    result = await relay.exchange({"type": "workspace_sync", "owner": owner,
                                   "records": [r.model_dump() for r in body.records]}, timeout=20.0)
    if result.get("type") == "op_error":
        raise erro_relay(result, "Não foi possível sincronizar os projetos")
    if result.get("type") != "workspace_synced":
        raise HTTPException(503, "O PC não confirmou a organização dos chats")
    return {"records": result.get("records", [])}


@app.get("/api/conversations")
async def conversations(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "conversations", "owner": dono,
                                   "limit": 100}, timeout=20.0)
    if result.get("type") != "conversations":
        raise HTTPException(503, "Sessões indisponíveis")
    return {"conversations": result.get("conversations", [])[:100]}


class DocAsk(BaseModel):
    doc_id: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class DocSearch(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    doc_id: str = Field(default="", max_length=64, pattern=r"^(|[a-zA-Z0-9_-]+)$")
    limit: int = Field(default=5, ge=1, le=20)


class DocCompare(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    doc_ids: list[str] = Field(min_length=1, max_length=20)


@app.post("/api/docs/upload")
async def docs_upload(request: Request, file: UploadFile = File(...),
                      conversation_id: str = Form(default="geral", max_length=100)):
    """Recebe um documento (até 15MB) e encaminha ao PC para leitura."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    limite = DOC_UPLOAD_MAX_BYTES
    recebido = bytearray()
    try:
        while len(recebido) <= limite:
            parte = await file.read(min(64 * 1024, limite - len(recebido) + 1))
            if not parte:
                break
            recebido.extend(parte)
        if len(recebido) > limite:
            raise HTTPException(413, "Arquivo grande demais (limite 15MB)")
    finally:
        await file.close()
    raw = bytes(recebido)
    if not raw:
        raise HTTPException(422, "Arquivo vazio")
    import base64 as _b64
    conv = conversation_id if 3 <= len(conversation_id) <= 100 else "geral"
    result = await relay.exchange(
        {"type": "doc_upload", "owner": dono,
         "name": (file.filename or "arquivo")[:120],
         "conversation_id": conv,
         "data_b64": _b64.b64encode(raw).decode("ascii")}, timeout=90.0)
    if result.get("type") == "doc_error":
        raise HTTPException(422, result.get("error", "Não consegui ler o arquivo"))
    if result.get("type") != "doc_uploaded":
        raise HTTPException(503, "PC não processou o documento")
    return {k: result.get(k) for k in (
        "doc_id", "name", "title", "ext", "chars", "chunks", "paginas_aprox",
        "sections", "table_hints", "content_hash", "version")}


@app.get("/api/docs")
async def docs_list(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_list", "owner": dono,
                                   "limit": 50}, timeout=20.0)
    if result.get("type") != "doc_list":
        raise HTTPException(503, "Documentos indisponíveis")
    return {"documents": result.get("documents", [])[:50]}


@app.post("/api/docs/search")
async def docs_search(request: Request, body: DocSearch):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_search", "owner": dono,
                                   "query": body.query, "doc_id": body.doc_id,
                                   "limit": body.limit}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(404 if result.get("codigo") == "nao_encontrado" else 422,
                            result.get("error", "Falha na busca documental"))
    if result.get("type") != "doc_search":
        raise HTTPException(503, "Busca documental indisponível")
    return {"results": result.get("results", [])}


@app.post("/api/docs/compare")
async def docs_compare(request: Request, body: DocCompare):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_compare", "owner": dono,
                                   "query": body.query, "doc_ids": body.doc_ids}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(422, result.get("error", "Falha ao comparar documentos"))
    if result.get("type") != "doc_compare":
        raise HTTPException(503, "Comparação documental indisponível")
    return {k: v for k, v in result.items() if k != "type"}


@app.delete("/api/docs/{doc_id}")
async def docs_delete(request: Request, doc_id: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{4,64}", doc_id):
        raise HTTPException(422, "Identificador de documento inválido")
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_delete", "owner": dono,
                                   "doc_id": doc_id}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(404, result.get("error", "Documento não encontrado"))
    if result.get("type") != "doc_deleted":
        raise HTTPException(503, "Exclusão documental indisponível")
    return {"ok": True, "doc_id": doc_id}


@app.post("/api/docs/resumo")
async def docs_resumo(request: Request, body: DocAsk):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_resumo", "owner": dono,
                                   "doc_id": body.doc_id}, timeout=180.0)
    if result.get("type") == "doc_error":
        raise HTTPException(503, result.get("error", "Falha ao resumir"))
    if result.get("type") != "doc_resumo":
        raise HTTPException(503, "Resumo não recebido")
    return {"doc_id": result.get("doc_id"), "resumo": result.get("resumo", "")}


@app.post("/api/docs/topicos")
async def docs_topicos(request: Request, body: DocAsk):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_topicos", "owner": dono,
                                   "doc_id": body.doc_id}, timeout=180.0)
    if result.get("type") == "doc_error":
        raise HTTPException(503, result.get("error", "Falha ao extrair tópicos"))
    if result.get("type") != "doc_topicos":
        raise HTTPException(503, "Tópicos não recebidos")
    return {"doc_id": result.get("doc_id"), "topicos": result.get("topicos", "")}


class UiStateItem(BaseModel):
    k: str = Field(min_length=3, max_length=200, pattern=r"^[\w#:.\-]{3,200}$")
    message_id: str = Field(min_length=8, max_length=100)
    slot: str = Field(min_length=1, max_length=40)
    state: dict = Field(default_factory=dict)
    updated_at: str = Field(min_length=10, max_length=48)


class UiStateBody(BaseModel):
    states: list[UiStateItem] = Field(min_length=1, max_length=300)


@app.post("/api/ui-state")
async def ui_state_save(request: Request, body: UiStateBody):
    """Persiste estados de interfaces JDUI no SQLite do PC (idempotente por k)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    import json as _json
    itens = []
    for s in body.states:
        try:
            bruto = _json.dumps(s.state, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        if len(bruto) > 8000:
            continue
        itens.append({"k": s.k, "message_id": s.message_id, "slot": s.slot,
                      "state": bruto, "updated_at": s.updated_at})
    if not itens:
        raise HTTPException(422, "Nenhum estado válido")
    result = await relay.exchange({"type": "ui_state_save", "owner": dono,
                                   "states": itens}, timeout=20.0)
    if result.get("type") != "ui_state_saved":
        raise HTTPException(503, "PC não confirmou os estados")
    return {"saved": result.get("saved", 0)}


@app.get("/api/ui-state")
async def ui_state_list(request: Request, cursor: str = ""):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "ui_state_list", "owner": dono, "cursor": cursor[:200]},
                                  timeout=20.0)
    if result.get("type") != "ui_state_list":
        raise HTTPException(503, "Estados indisponíveis")
    import json as _json
    out = []
    for r in result.get("states", [])[:500]:
        try:
            out.append({"k": r["k"], "message_id": r.get("message_id", ""),
                        "slot": r.get("slot", ""),
                        "state": _json.loads(r.get("state", "{}")),
                        "updated_at": r.get("updated_at", "")})
        except (ValueError, KeyError, TypeError):
            continue
    return {"states": out, "next_cursor": result.get("next_cursor", "")}


@app.delete("/api/conversations/{conversation_id}")
async def conversation_forget(request: Request, conversation_id: str):
    """Apaga conversa do SQLite do PC (mensagens + pedidos de IA). Tombstone fica no celular."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", conversation_id):
        raise HTTPException(422, "Conversa inválida")
    result = await relay.exchange({"type": "conv_forget", "owner": dono,
                                   "conversation_id": conversation_id}, timeout=20.0)
    if result.get("type") != "conv_forgotten":
        raise HTTPException(503, "PC não confirmou a exclusão")
    return {"ok": True, "deleted": result.get("deleted", 0)}


@app.get("/api/memories")
async def memories_list(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_list":
        raise HTTPException(503, "Memória indisponível")
    return {"memories": result.get("memories", [])[:100]}


@app.delete("/api/memories/{key}")
async def memories_forget(request: Request, key: str):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
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


@app.get("/api/memories/full")
async def memories_full(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_list_full", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_list_full":
        raise HTTPException(503, "Memória indisponível")
    return {"memories": result.get("memories", [])[:200]}


@app.post("/api/memories/confirm")
async def memories_confirm(request: Request):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_confirm", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_confirmed":
        raise HTTPException(503, "Nada para confirmar")
    return result


@app.put("/api/memories/{key}")
async def memories_update(request: Request, key: str, body: MemUpdate):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-z0-9_]{1,60}", key):
        raise HTTPException(422, "Chave inválida")
    result = await relay.exchange({"type": "mem_update", "owner": dono,
                                   "key": key, "value": body.value}, timeout=20.0)
    if result.get("type") != "mem_updated":
        raise HTTPException(503, result.get("error", "Falha ao corrigir"))
    return {"ok": True, "key": key}


@app.get("/api/memory/settings")
async def memory_settings_get(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_settings", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "mem_settings":
        raise HTTPException(503, "Configuração indisponível")
    return {"learning": result.get("learning", True)}


@app.post("/api/memory/settings")
async def memory_settings_set(request: Request, body: MemSettings):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "mem_settings", "owner": dono,
                                   "learning": "1" if body.learning else "0"}, timeout=20.0)
    if result.get("type") != "mem_settings":
        raise HTTPException(503, "Falha ao salvar")
    return {"learning": result.get("learning", True)}


@app.get("/api/memory/events")
async def memory_events(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "event_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "event_list":
        raise HTTPException(503, "Eventos indisponíveis")
    return {"events": result.get("events", [])[:20]}


@app.post("/api/ai")
async def ai_complete(request: Request, body: AIRequest):
    """Resposta completa (sem streaming). Idempotente por message_id no agente."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "ai", "owner": dono,
                                   "message_id": body.message_id,
                                   "conversation_id": body.conversation_id,
                                   "model": body.model, "memory": body.memory,
                                   "local_time": body.local_time, "timezone": body.timezone,
                                   "city": body.city, "latitude": body.latitude,
                                   "longitude": body.longitude, "text": body.text,
                                   "created_at": body.created_at, "scene_state": body.scene_state}, timeout=180.0)
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


@app.post("/api/ai/regenerate")
async def ai_regenerate(request: Request, body: AIContinue):
    """Apaga resposta anterior (PC + idempotência) para gerar de novo."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "ai_reset", "owner": dono,
                                   "message_id": body.message_id,
                                   "conversation_id": body.conversation_id}, timeout=20.0)
    if result.get("type") == "ai_error":
        raise erro_relay(result, "Falha ao reiniciar")
    if result.get("type") != "ai_reset_ok":
        raise HTTPException(503, "PC não confirmou")
    return {"ok": True, "reply_id": result.get("reply_id")}


@app.post("/api/ai/continue")
async def ai_continue(request: Request, body: AIContinue):
    """Continua a resposta anterior, anexando ao mesmo reply_id."""
    require_csrf(request)
    dono = await revogacao_ok(request)
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


@app.post("/api/providers")
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


@app.get("/api/screen")
async def screen(request: Request, max_w: int = 800, q: int = 55):
    """Foto atual da tela do PC (JPEG base64). Exige login + CSRF + grant remoto."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "screen", "owner": dono,
                                   "max_w": max(320, min(max_w, 960)),
                                   "q": max(30, min(q, 80))}, timeout=20.0)
    if result.get("type") != "screen":
        if result.get("codigo") == "sem_permissao":
            raise HTTPException(403, result.get("error", "Sem autorização."))
        raise HTTPException(503, result.get("error", "Tela indisponível"))
    return {"imagem": result["imagem"], "largura": result.get("largura", 0),
            "altura": result.get("altura", 0), "ms": result.get("ms", 0),
            "remote_enabled": result.get("remote_enabled", False)}


@app.post("/api/input")
async def remote_input(request: Request, body: InputBody):
    """Executa mouse/teclado no PC. Exige login + CSRF + grant remoto (além de JULIA_REMOTE=1)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "input", "owner": dono,
                                   "cmd": body.model_dump()}, timeout=15.0)
    if result.get("type") != "input_done":
        if result.get("codigo") == "sem_permissao":
            raise HTTPException(403, result.get("error", "Sem autorização."))
        raise HTTPException(503, result.get("error", "Comando recusado"))
    return {"ok": True, "kind": result.get("kind", "")}


class LearnAttemptIn(BaseModel):
    assessment_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class LearnAnswerIn(BaseModel):
    attempt_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    question_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    resposta: str = Field(min_length=1, max_length=2000)


class LearnFinishIn(BaseModel):
    attempt_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class LearnAvulsoIn(BaseModel):
    titulo: str = Field(default="Quiz", max_length=160)
    assunto: str = Field(default="", max_length=120)
    certas: int = Field(ge=0, le=1000)
    total: int = Field(ge=1, le=1000)


def _learn_erro(result: dict) -> HTTPException:
    """learn_error do agente vira HTTP: bloqueada→403, ausente→404, resto→503."""
    codigo = result.get("codigo", "erro")
    if codigo == "bloqueada":
        return erro_relay(result, "Conta indisponível.")
    if codigo in ("ausente", "finalizada"):
        raise HTTPException(404 if codigo == "ausente" else 409,
                            result.get("error", "Não encontrado"))
    return HTTPException(503, result.get("error", "Aprendizado indisponível"))


@app.get("/api/learn/assessments/{aid}")
async def learn_assessment(request: Request, aid: str):
    """Prova sem gabarito (o gabarito só aparece na correção)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(aid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_get", "owner": dono, "id": aid},
                                  timeout=20.0)
    if result.get("type") != "learn_assessment":
        raise _learn_erro(result)
    return {"id": result["id"], "titulo": result.get("titulo", ""),
            "assunto": result.get("assunto", ""), "origem": result.get("origem", ""),
            "questions": result.get("questions", [])}


@app.post("/api/learn/attempts")
async def learn_attempt(request: Request, body: LearnAttemptIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_attempt", "owner": dono,
                                   "assessment_id": body.assessment_id}, timeout=20.0)
    if result.get("type") != "learn_attempt":
        raise _learn_erro(result)
    return {"id": result["id"], "assessment_id": result.get("assessment_id", "")}


@app.post("/api/learn/answer")
async def learn_answer(request: Request, body: LearnAnswerIn):
    """Correção objetiva determinística no PC; discursiva = avaliação assistida."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_answer", "owner": dono,
                                   "attempt_id": body.attempt_id,
                                   "question_id": body.question_id,
                                   "resposta": body.resposta}, timeout=20.0)
    if result.get("type") != "learn_answer":
        raise _learn_erro(result)
    saida = {"correta": result.get("correta")}
    if "avaliacao" in result:
        saida["avaliacao"] = result["avaliacao"]
        saida["aviso"] = result.get("aviso", "")
    return saida


@app.post("/api/learn/finish")
async def learn_finish(request: Request, body: LearnFinishIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_finish", "owner": dono,
                                   "attempt_id": body.attempt_id}, timeout=20.0)
    if result.get("type") != "learn_result":
        raise _learn_erro(result)
    return {"id": result["id"], "nota": result.get("nota", 0.0),
            "certas": result.get("certas", 0), "total": result.get("total", 0),
            "pendentes_avaliacao": result.get("pendentes_avaliacao", 0),
            "erradas": result.get("erradas", [])[:10]}


@app.post("/api/learn/avulso")
async def learn_avulso(request: Request, body: LearnAvulsoIn):
    """Registra resultado de quiz inline (JDUI quiz). Origem marcada como quiz-inline."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_avulso", "owner": dono,
                                   "titulo": body.titulo, "assunto": body.assunto,
                                   "certas": body.certas, "total": body.total},
                                  timeout=20.0)
    if result.get("type") != "learn_avulso_ok":
        raise _learn_erro(result)
    return {"ok": True, "assessment_id": result.get("assessment_id", ""),
            "attempt_id": result.get("attempt_id", "")}


@app.get("/api/learn/stats")
async def learn_stats(request: Request):
    """Resumo + desempenho por assunto (só dados reais; vazio útil sem dados)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_stats", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_stats":
        raise _learn_erro(result)
    return {"resumo": result.get("resumo", {}), "por_assunto": result.get("por_assunto", [])}


class LearnPlanIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=160)
    objetivo: str = Field(default="", max_length=500)
    assunto: str = Field(default="", max_length=120)
    prazo_iso: str = Field(default="", max_length=32)
    min_dia: int = Field(default=30, ge=5, le=480)
    itens: list = Field(default=[], min_length=1, max_length=50)
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")


class LearnPlanItemIn(BaseModel):
    plan_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    item_id: int = Field(ge=1)
    feito: bool = True


class LearnPlanUpdateIn(BaseModel):
    plan_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    mudancas: dict = Field(default={})


class LearnCardsIn(BaseModel):
    cards: list = Field(min_length=1, max_length=100)


class LearnReviewIn(BaseModel):
    flashcard_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    acertou: bool = True


class LearnFlagIn(BaseModel):
    question_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    motivo: str = Field(min_length=5, max_length=500)


@app.post("/api/learn/plans")
async def learn_plan_create(request: Request, body: LearnPlanIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_create", "owner": dono,
                                   "titulo": body.titulo, "objetivo": body.objetivo,
                                   "assunto": body.assunto, "prazo_iso": body.prazo_iso,
                                   "min_dia": body.min_dia, "itens": body.itens,
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "learn_plan":
        raise _learn_erro(result)
    return {"id": result["id"], "itens": result.get("itens", 0)}


@app.get("/api/learn/plans")
async def learn_plans(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plans", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_plans":
        raise _learn_erro(result)
    return {"planos": result.get("planos", [])}


@app.get("/api/learn/plans/{pid}")
async def learn_plan_get(request: Request, pid: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(pid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_plan_get", "owner": dono, "id": pid},
                                  timeout=20.0)
    if result.get("type") != "learn_plan_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@app.post("/api/learn/plans/item")
async def learn_plan_item(request: Request, body: LearnPlanItemIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_item", "owner": dono,
                                   "plan_id": body.plan_id, "item_id": body.item_id,
                                   "feito": "1" if body.feito else "0"}, timeout=20.0)
    if result.get("type") != "learn_plan_progress":
        raise _learn_erro(result)
    return {"progresso": result.get("progresso", {})}


@app.post("/api/learn/plans/update")
async def learn_plan_update(request: Request, body: LearnPlanUpdateIn):
    """Atualização compatível: concluídos preservados (match por título)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_update", "owner": dono,
                                   "plan_id": body.plan_id, "mudancas": body.mudancas},
                                  timeout=20.0)
    if result.get("type") != "learn_plan_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@app.post("/api/learn/cards")
async def learn_cards_create(request: Request, body: LearnCardsIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_create", "owner": dono,
                                   "cards": body.cards}, timeout=20.0)
    if result.get("type") != "learn_cards":
        raise _learn_erro(result)
    return {"ids": result.get("ids", []), "total": result.get("total", 0)}


@app.get("/api/learn/cards/due")
async def learn_cards_due(request: Request, limite: int = 50):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_due", "owner": dono,
                                   "limite": max(1, min(limite, 200))}, timeout=20.0)
    if result.get("type") != "learn_cards_due":
        raise _learn_erro(result)
    return {"cards": result.get("cards", [])}


@app.post("/api/learn/cards/review")
async def learn_cards_review(request: Request, body: LearnReviewIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_review", "owner": dono,
                                   "flashcard_id": body.flashcard_id,
                                   "acertou": "1" if body.acertou else "0"}, timeout=20.0)
    if result.get("type") != "learn_cards_review":
        raise _learn_erro(result)
    return {"id": result.get("id", ""), "acertou": result.get("acertou", True),
            "intervalo_d": result.get("intervalo_d", 1),
            "proxima_iso": result.get("proxima_iso", "")}


@app.get("/api/learn/recommend")
async def learn_recommend(request: Request):
    """Recomendações determinísticas; sem dados → lista vazia com motivo."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_recommend", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_recommend":
        raise _learn_erro(result)
    return {"recomendacoes": result.get("recomendacoes", []),
            "motivo": result.get("motivo", "sem_dados"),
            "aviso": result.get("aviso", "")}


@app.post("/api/learn/flag")
async def learn_flag(request: Request, body: LearnFlagIn):
    """Sinaliza gabarito duvidoso (registra; não reescreve o histórico)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_flag", "owner": dono,
                                   "question_id": body.question_id,
                                   "motivo": body.motivo}, timeout=20.0)
    if result.get("type") != "learn_flag_ok":
        raise _learn_erro(result)
    return {"ok": True, "question_id": result.get("question_id", "")}


@app.get("/api/learn/mistakes")
async def learn_mistakes(request: Request, limite: int = 20):
    """Erros recentes do dono (base p/ refazer e simulados de reforço)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_mistakes", "owner": dono,
                                   "limite": max(1, min(limite, 100))}, timeout=20.0)
    if result.get("type") != "learn_mistakes":
        raise _learn_erro(result)
    return {"erradas": result.get("erradas", [])}


class LearnLessonIn(BaseModel):
    aula: dict
    origem: str = Field(default="ia", max_length=20)
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")


class LearnLessonSectionIn(BaseModel):
    lesson_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    ordem: int = Field(ge=0, le=50)


@app.post("/api/learn/lessons")
async def learn_lesson_create(request: Request, body: LearnLessonIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lesson_create", "owner": dono,
                                   "aula": body.aula, "origem": body.origem,
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "learn_lesson":
        raise _learn_erro(result)
    return {"id": result["id"], "secoes": result.get("secoes", 0)}


@app.get("/api/learn/lessons")
async def learn_lessons(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lessons", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_lessons":
        raise _learn_erro(result)
    return {"aulas": result.get("aulas", [])}


@app.get("/api/learn/lessons/{lid}")
async def learn_lesson_get(request: Request, lid: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(lid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_lesson_get", "owner": dono, "id": lid},
                                  timeout=20.0)
    if result.get("type") != "learn_lesson_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@app.post("/api/learn/lessons/section")
async def learn_lesson_section(request: Request, body: LearnLessonSectionIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lesson_section", "owner": dono,
                                   "lesson_id": body.lesson_id, "ordem": body.ordem},
                                  timeout=20.0)
    if result.get("type") != "learn_lesson_progress":
        raise _learn_erro(result)
    return {"estado": result.get("estado", ""), "progresso": result.get("progresso", {})}


@app.get("/api/learn/history")
async def learn_history(request: Request, limite: int = 50):
    """Tentativas finalizadas do dono (séries factuais p/ gráficos de evolução)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_history", "owner": dono,
                                   "limite": max(1, min(limite, 200))}, timeout=20.0)
    if result.get("type") != "learn_history":
        raise _learn_erro(result)
    return {"tentativas": result.get("tentativas", [])}


class ResearchStartIn(BaseModel):
    objetivo: str = Field(min_length=3, max_length=500)
    conv: str = Field(default="", max_length=100)
    modo: str = Field(default="", max_length=20)


class ResearchJobIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


def _research_erro(result: dict) -> HTTPException:
    codigo = result.get("codigo", "erro")
    if codigo == "bloqueada":
        return erro_relay(result, "Conta indisponível.")
    if codigo == "ausente":
        raise HTTPException(404, result.get("error", "Pesquisa não encontrada"))
    if codigo == "ocupado":
        raise HTTPException(409, result.get("error", "Pesquisa em andamento"))
    return HTTPException(503, result.get("error", "Pesquisa indisponível"))


@app.post("/api/research/start")
async def research_start(request: Request, body: ResearchStartIn):
    """Inicia pesquisa agêntica em background (1 ativa por dono)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_start", "owner": dono,
                                   "objetivo": body.objetivo, "conv": body.conv,
                                   "modo": body.modo}, timeout=20.0)
    if result.get("type") != "research_job":
        raise _research_erro(result)
    return {"job_id": result["job_id"], "modo": result.get("modo", ""),
            "etapas": result.get("etapas", 0)}


@app.get("/api/research/status")
async def research_status(request: Request, job_id: str, apos_seq: int = 0):
    """Estado + eventos desde apos_seq (polling; dedupe por seq no cliente)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": apos_seq}, timeout=20.0)
    if result.get("type") != "research_status":
        raise _research_erro(result)
    return {"resumo": result.get("resumo", {}), "eventos": result.get("eventos", [])}


@app.post("/api/research/cancel")
async def research_cancel(request: Request, body: ResearchJobIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_cancel", "owner": dono,
                                   "job_id": body.job_id}, timeout=20.0)
    if result.get("type") != "research_cancelled":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@app.get("/api/research/jobs")
async def research_jobs(request: Request):
    """Histórico de pesquisas do dono (memória de investigações)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_jobs_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "research_jobs":
        raise _research_erro(result)
    return {"jobs": result.get("jobs", [])}


@app.get("/api/research/evidence")
async def research_evidence(request: Request, job_id: str):
    """Evidências do job (links reais para o painel)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_evidence":
        raise _research_erro(result)
    return {"evidencias": result.get("evidencias", [])}


@app.get("/api/research/hypotheses")
async def research_hypotheses(request: Request, job_id: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_hypotheses":
        raise _research_erro(result)
    return {"hypotheses": result.get("hypotheses", [])}


@app.get("/api/research/report")
async def research_report(request: Request, job_id: str,
                          report_type: str = "executive_summary"):
    from research_reports import REPORT_TYPES

    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    if report_type not in REPORT_TYPES:
        raise HTTPException(422, "Tipo de relatório inválido")
    result = await relay.exchange({"type": "research_job_report", "owner": dono,
                                   "job_id": job_id, "report_type": report_type},
                                  timeout=20.0)
    if result.get("type") != "research_report":
        raise _research_erro(result)
    return {k: v for k, v in result.items() if k != "type"}


@app.get("/api/research/view")
async def research_view(request: Request, job_id: str):
    """JDUI 4.0 a partir de registros reais (componentes validados no backend)."""
    import research_view

    verify_session(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id or ""):
        raise HTTPException(422, "Identificador inválido")
    status = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": 0}, timeout=20.0)
    if status.get("type") != "research_status":
        raise _research_erro(status)
    evidence = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                     "job_id": job_id}, timeout=20.0)
    if evidence.get("type") != "research_evidence":
        raise _research_erro(evidence)
    hypotheses = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                       "job_id": job_id}, timeout=20.0)
    if hypotheses.get("type") != "research_hypotheses":
        raise _research_erro(hypotheses)
    message = research_view.build_view(
        status.get("resumo", {}), evidence.get("evidencias", []),
        hypotheses.get("hypotheses", []))
    return {"message": message}


@app.get("/api/research/export")
async def research_export(request: Request, job_id: str, formato: str = "md"):
    """Gera bytes reais no servidor a partir dos registros owner-scoped.

    Nada é persistido/rehospedado no Render.  O conteúdo vem do PC via relay;
    se o job não pertence ao dono autenticado, o PC responde ``ausente``.
    """
    import research_exports

    verify_session(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id or ""):
        raise HTTPException(422, "Identificador inválido")
    if formato not in research_exports.FORMATS:
        raise HTTPException(422, "Formato inválido; use md, csv ou json")
    status = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": 0}, timeout=20.0)
    if status.get("type") != "research_status":
        raise _research_erro(status)
    evidence = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                     "job_id": job_id}, timeout=20.0)
    if evidence.get("type") != "research_evidence":
        raise _research_erro(evidence)
    hypotheses = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                       "job_id": job_id}, timeout=20.0)
    if hypotheses.get("type") != "research_hypotheses":
        raise _research_erro(hypotheses)
    try:
        payload, media_type, filename = research_exports.build_export(
            status.get("resumo", {}), evidence.get("evidencias", []),
            hypotheses.get("hypotheses", []), formato)
    except research_exports.ExportError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(payload, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@app.delete("/api/research/{job_id}")
async def research_delete(request: Request, job_id: str):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_delete", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_deleted":
        raise _research_erro(result)
    return {"ok": True, "job_id": job_id}


class ResearchInterveneIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    op: str = Field(min_length=3, max_length=30, pattern=r"^[a-z_]+$")
    params: dict = Field(default={})


class ResearchPauseIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    pausar: bool = True


@app.post("/api/research/intervene")
async def research_intervene(request: Request, body: ResearchInterveneIn):
    """Alteração estruturada do plano (sem LLM; feita preservada)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_intervene", "owner": dono,
                                   "job_id": body.job_id, "op": body.op,
                                   "params": body.params}, timeout=20.0)
    if result.get("type") != "research_intervened":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@app.post("/api/research/pause")
async def research_pause(request: Request, body: ResearchPauseIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_pause", "owner": dono,
                                   "job_id": body.job_id,
                                   "pausar": "1" if body.pausar else "0"}, timeout=20.0)
    if result.get("type") != "research_paused":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@app.get("/api/research/stream")
async def research_stream(request: Request, job_id: str, apos_seq: int = 0):
    """SSE de telemetria real: backlog autoritativo + push ao vivo.

    Polling continua válido como fallback (mesmo contrato, mesmos seqs).
    """
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    if relay.ws is None:
        raise HTTPException(503, "Computador desconectado; use o painel com polling")
    if len(relay.research_subs) >= 20:
        raise HTTPException(429, "Muitos acompanhamentos; tente de novo")
    from fastapi.responses import StreamingResponse
    fila: asyncio.Queue = asyncio.Queue(maxsize=200)
    sub_id = uuid.uuid4().hex
    relay.research_subs[sub_id] = {"job_id": job_id, "owner": dono, "fila": fila,
                                   "perdidos": 0}
    backlog = await relay.exchange({"type": "research_job_status", "owner": dono,
                                    "job_id": job_id, "apos_seq": apos_seq}, timeout=20.0)
    if backlog.get("type") != "research_status":
        relay.research_subs.pop(sub_id, None)
        raise _research_erro(backlog)

    async def gerar():
        cursor = ResearchSSECursor(apos_seq)
        try:
            eventos_backlog = [e for e in backlog.get("eventos", [])
                               if isinstance(e, dict)]
            terminal_backlog = any(ResearchSSECursor.terminal(e)
                                   for e in eventos_backlog)
            for ev in eventos_backlog:
                for pronto in cursor.oferecer(ev):
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
            if terminal_backlog:
                for pronto in cursor.liberar_tudo():
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                return
            espera = 0.0
            while True:
                try:
                    ev = await asyncio.wait_for(fila.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    espera += 15.0
                    if espera >= 360.0:
                        return
                    # Lacuna não preenchida: libera o que chegou em ordem para
                    # não deixar a interface parada; o polling continua válido.
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    yield ": ping\n\n"
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("seq", 0) == -1:
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    yield ("event: error\n"
                           f"data: {json.dumps({'error': 'Agente desconectado'}, ensure_ascii=False)}\n\n")
                    return
                terminal = ResearchSSECursor.terminal(ev)
                for pronto in cursor.oferecer(ev):
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                if terminal:
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    return
        finally:
            relay.research_subs.pop(sub_id, None)

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/ai/models")
async def ai_models(request: Request):
    verify_session(request)
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
    return {"models": result.get("models", [])[:500], "default": result.get("default", ""),
            "items": [{k: i.get(k) for k in ("id", "provider")}
                      for i in itens if isinstance(i, dict)][:500],
            "providers": [{k: p.get(k) for k in ("id", "label", "configured", "auth_error", "source")
                           if p.get(k) is not None}
                          for p in provs if isinstance(p, dict)][:20]}


@app.post("/api/ai/stream")
async def ai_stream_post(request: Request, body: AIRequest):
    return await ai_stream(request, **body.model_dump())


@app.get("/api/ai/stream")
async def ai_stream(request: Request, message_id: str = "", conversation_id: str = "",
                    model: str = "", memory: str = "1", local_time: str = "",
                    timezone: str = "", city: str = "",
                    latitude: float | None = None, longitude: float | None = None,
                    text: str = "", created_at: str = "", scene_state: str = ""):
    """SSE com deltas reais do Hermes (via agente). Fechar a conexão cancela."""
    request_started = time.monotonic()
    require_csrf(request)
    dono = await revogacao_ok(request)
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
               "text": text, "created_at": created_at, "scene_state": scene_state}

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


@app.websocket("/api/agent/ws")
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
    relay.ws = websocket
    relay.ws_desde = time.monotonic()
    revogados["suportado"] = True
    revogados["falhas"] = 0
    relay.fail_pending()
    try:
        while True:
            body = await websocket.receive_json()
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
        if relay.ws is websocket:
            relay.ws = None
            relay.ws_desde = None
            relay.fail_pending()


@app.get('/vendor/three-engine.js')
async def three_engine_asset(request: Request):
    # Precompressed at build time: no per-request compression and no SSE buffering.
    accepts_gzip = False
    for entry in request.headers.get('accept-encoding', '').lower().split(','):
        parts = [part.strip() for part in entry.split(';')]
        if parts[0] != 'gzip':
            continue
        quality = next((part[2:] for part in parts[1:] if part.startswith('q=')), '1')
        try:
            accepts_gzip = 0 < float(quality) <= 1
        except ValueError:
            accepts_gzip = False
        break
    base = ROOT / 'public' / 'vendor' / 'three-engine.js'
    compressed = base.with_suffix('.js.gz')
    use_gzip = accepts_gzip and compressed.is_file()
    return FileResponse(compressed if use_gzip else base, media_type='text/javascript',
                        headers={'Vary':'Accept-Encoding', **({'Content-Encoding':'gzip'} if use_gzip else {})})


app.mount("/", StaticFiles(directory=str(ROOT / "public"), html=True), name="mobile-static")
