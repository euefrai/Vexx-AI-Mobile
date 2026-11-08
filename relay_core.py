"""Núcleo do relay Vexx AI: configuração, app FastAPI, middlewares,
sessão/CSRF, revogação, rate limit e o AgentRelay (RPC WebSocket com o PC).

Nenhum histórico de chat ou SQLite é guardado no Render. As rotas de cada
domínio ficam em routers/*.py; server.py só compõe a aplicação.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from argon2 import PasswordHasher, exceptions as argon_errors
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field, field_validator
from rate_limit import RateLimiter, client_ip, env_int
from workspace_store import WorkspaceBatch, WorkspaceRecord

import env_local
env_local.carregar_env_local()  # .env local do PC (nunca sobrescreve o sistema)

import julia_auth

log = logging.getLogger("JULIA-mobile")
ROOT = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app):
    tarefa = asyncio.create_task(_monitor_agente_offline())
    try:
        yield
    finally:
        tarefa.cancel()
        try:
            await tarefa
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Vexx AI Relay", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=lifespan)
ph = PasswordHasher()
SESSION_LIFETIME = 12 * 60 * 60
DOC_UPLOAD_MAX_BYTES = 15 * 1024 * 1024
DOC_UPLOAD_REQUEST_MAX_BYTES = DOC_UPLOAD_MAX_BYTES + 1024 * 1024
API_BODY_MAX_BYTES = 2 * 1024 * 1024
XLSX_REQUEST_MAX_BYTES = 8 * 1024 * 1024

# Limites de corpo por rota. Qualquer outro JSON de /api/ fica no teto padrão.
REQUEST_BODY_LIMITS = {
    "/api/docs/upload": DOC_UPLOAD_REQUEST_MAX_BYTES,
    "/api/export/xlsx": XLSX_REQUEST_MAX_BYTES,
}


class RequestBodyLimit:
    """Limita bytes reais antes do parse/spool (Content-Length e streaming)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        limite = REQUEST_BODY_LIMITS.get(path, API_BODY_MAX_BYTES)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > limite:
                    response = JSONResponse(
                        {"detail": "Pedido excede o limite permitido."}, status_code=413)
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
                if total > limite:
                    raise HTTPException(413, "Pedido excede o limite permitido.")
            return message

        try:
            await self.app(scope, receive_limited, send)
        except HTTPException as exc:
            if exc.status_code != 413:
                raise
            response = JSONResponse({"detail": exc.detail}, status_code=413)
            await response(scope, receive, send)


app.add_middleware(RequestBodyLimit)
# Compatibilidade com testes/importadores do limitador antigo de upload.
DocumentUploadBodyLimit = RequestBodyLimit


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
    uid = str(data.get("uid") or "")
    if not uid and "uid" not in data and data.get("user") == config()["user"]:
        uid = "local"
    if not uid:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    if uid == "local" and not julia_auth.login_legado_permitido():
        raise HTTPException(status_code=401, detail="Sessão legada desativada")
    data["uid"] = uid
    return data


def sessao_usuario(request: Request) -> str:
    """Dono autenticado da sessão (base do isolamento multiusuário)."""
    return str(sessao_dados(request)["uid"])


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
    uid = str(data.get("uid") or "")
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
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9_~.:/+-]*$")
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


class RemotePoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class InputBody(BaseModel):
    kind: str = Field(pattern=r"^(move|click|double|right|scroll|wheel|key|text|drag|clipboard_get|clipboard_set)$")
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    dx: int = Field(default=0, ge=-10, le=10)
    dy: int = Field(default=0, ge=-10, le=10)
    delta_x: int = Field(default=0, ge=-1200, le=1200)
    delta_y: int = Field(default=0, ge=-1200, le=1200)
    key: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=200)
    points: list[RemotePoint] | None = Field(default=None, min_length=2, max_length=32)


class InputBatch(BaseModel):
    commands: list[InputBody] = Field(min_length=1, max_length=12)


_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def commit_curto(valor) -> str:
    """Normaliza um SHA de commit; vazio quando o valor nao e verificavel."""
    texto = str(valor or "").strip().lower()
    return texto[:12] if _COMMIT_RE.fullmatch(texto) else ""


def commit_relay() -> str:
    return commit_curto(os.environ.get("RENDER_GIT_COMMIT", ""))


def _inteiro_limitado(valor, teto: int) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return max(0, min(teto, numero))


def normalizar_hello(body: dict) -> dict:
    """Aceita apenas metadata tecnica e limitada do agente."""
    return {
        "commit": commit_curto(body.get("commit")) or "desconhecido",
        "pid": _inteiro_limitado(body.get("pid"), 2**31 - 1),
        "uptime_s": _inteiro_limitado(body.get("uptime_s"), 10**9),
        "started_at": str(body.get("started_at") or "")[:40],
        "db_ok": body.get("db_ok") is True,
        "python": str(body.get("python") or "")[:20],
    }


# Single Render instance / single paired PC. All values intentionally volatile.
class AgentRelay:
    def __init__(self):
        self.ws: WebSocket | None = None
        self.ws_desde: float | None = None
        self.agent_info: dict | None = None
        self.agent_info_desde: float | None = None
        self.offline_desde: float = time.monotonic()
        self.pending: dict[str, asyncio.Future] = {}
        self.streams: dict[str, asyncio.Queue] = {}
        self.send_lock = asyncio.Lock()
        # Live research: sub_id -> {job_id, owner, fila}. Teto anti-abuso.
        self.research_subs: dict[str, dict] = {}

    def conectar(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.ws_desde = time.monotonic()
        self.agent_info = None
        self.agent_info_desde = None
        self.offline_desde = 0.0

    def desconectar(self, websocket: WebSocket) -> bool:
        if self.ws is not websocket:
            return False
        self.ws = None
        self.ws_desde = None
        self.agent_info = None
        self.agent_info_desde = None
        self.offline_desde = time.monotonic()
        return True

    def registrar_hello(self, body: dict) -> dict:
        info = normalizar_hello(body)
        self.agent_info = info
        self.agent_info_desde = time.monotonic()
        return info

    def offline_s(self) -> int:
        if self.ws is not None:
            return 0
        return max(0, int(time.monotonic() - self.offline_desde))

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


def drift_agente() -> dict:
    """Compara o commit do relay com o commit anunciado pelo agente."""
    esperado = commit_relay()
    info = relay.agent_info or {}
    recebido = commit_curto(info.get("commit"))
    if not relay.ws:
        return {"drift": False, "status": "offline", "relay_commit": esperado,
                "agent_commit": recebido}
    if not recebido:
        return {"drift": False, "status": "desconhecido",
                "relay_commit": esperado, "agent_commit": ""}
    if not esperado:
        return {"drift": False, "status": "local", "relay_commit": "",
                "agent_commit": recebido}
    iguais = esperado == recebido
    return {"drift": not iguais, "status": "ok" if iguais else "divergente",
            "relay_commit": esperado, "agent_commit": recebido}


def estado_prontidao() -> dict:
    """Readiness: relay configurado, agente conectado, SQLite ok e commit igual.

    `/api/health` e liveness do processo; este estado e o que autoriza dizer
    que o produto esta utilizavel. Sem hello do agente nao ha como provar
    SQLite nem commit, entao readiness falha de forma explicita.
    """
    online = relay.ws is not None
    info = relay.agent_info or {}
    drift = drift_agente()
    db_ok = info.get("db_ok") if online and info else None
    checks = {
        "configured": bool(is_ready()),
        "agent_online": online,
        "agent_hello": bool(info),
        "database": db_ok is True,
        "commit_aligned": online and drift["status"] in ("ok", "local"),
    }
    pronto = all(checks.values())
    if not online:
        status = "offline"
    elif pronto:
        status = "ok"
    else:
        status = "degraded"
    return {
        "status": status,
        "ready": pronto,
        "stale": not pronto,
        "checks": checks,
        "pc_online": online,
        "agente_ha": relay.ha(),
        "offline_s": relay.offline_s(),
        "agent_commit": drift["agent_commit"],
        "relay_commit": drift["relay_commit"],
        "drift": drift["drift"],
        "drift_status": drift["status"],
        "agent_pid": info.get("pid"),
        "agent_uptime_s": info.get("uptime_s"),
        "agent_started_at": info.get("started_at", ""),
        "db_ok": db_ok,
    }


async def _monitor_agente_offline():
    """Alerta no log quando o PC passa tempo demais desconectado.

    O readiness (/api/ready) e a superficie para monitoramento externo; este
    laco garante que a queda tambem apareca no log do relay sem depender de
    alguem consultar o endpoint.
    """
    alertado = False
    while True:
        try:
            await asyncio.sleep(30)
            limite = max(60, env_int("JULIA_OFFLINE_ALERT_S", 180))
            if relay.ws is None and relay.offline_s() >= limite and not alertado:
                log.error("ALERTA: agente do PC offline ha %ss (limite %ss).",
                          relay.offline_s(), limite)
                alertado = True
            elif relay.ws is not None:
                alertado = False
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Falha no monitor de disponibilidade; seguindo.")


# Throttle por usuário/IP do relay (defesa em profundidade, volátil).
# A fonte definitiva para contas do PC é o SQLite do agente.
login_failures: dict[str, list[float]] = {}
MAX_LOGIN_CHAVES = 4096
rate_limiter = RateLimiter()

# ação -> (env por sujeito, teto, janela, env global, teto global, janela global)
RATE_RULES = {
    "login": ("JULIA_RATE_LOGIN_IP", 20, 60,
              "JULIA_RATE_LOGIN_GLOBAL", 300, 60),
    "register": ("JULIA_RATE_REGISTER_IP", 20, 3600,
                 "JULIA_RATE_REGISTER_GLOBAL", 60, 3600),
    "ai": ("JULIA_RATE_AI_USER", 60, 60,
           "JULIA_RATE_AI_GLOBAL", 240, 60),
    "research_start": ("JULIA_RATE_RESEARCH_START_USER", 10, 60,
                       "JULIA_RATE_RESEARCH_START_GLOBAL", 40, 60),
    "research_stream": ("JULIA_RATE_RESEARCH_STREAM_USER", 20, 60,
                        "JULIA_RATE_RESEARCH_STREAM_GLOBAL", 80, 60),
    "docs": ("JULIA_RATE_DOCS_USER", 30, 60,
             "JULIA_RATE_DOCS_GLOBAL", 120, 60),
    "admin": ("JULIA_RATE_ADMIN_USER", 60, 60,
              "JULIA_RATE_ADMIN_GLOBAL", 240, 60),
    "admin_quality": ("JULIA_RATE_ADMIN_QUALITY_USER", 5, 60,
                      "JULIA_RATE_ADMIN_QUALITY_GLOBAL", 10, 60),
    "screen": ("JULIA_RATE_SCREEN_USER", 600, 60,
               "JULIA_RATE_SCREEN_GLOBAL", 1800, 60),
    "remote_request": ("JULIA_RATE_REMOTE_REQUEST_USER", 3, 600,
                       "JULIA_RATE_REMOTE_REQUEST_GLOBAL", 6, 600),
    "remote_status": ("JULIA_RATE_REMOTE_STATUS_USER", 30, 60,
                      "JULIA_RATE_REMOTE_STATUS_GLOBAL", 120, 60),
    "input": ("JULIA_RATE_INPUT_USER", 720, 60,
              "JULIA_RATE_INPUT_GLOBAL", 2160, 60),
}


def _rate_limit(request: Request, acao: str, sujeito: str) -> None:
    """Aplica teto por sujeito e teto global; 429 sempre com Retry-After."""
    env_sujeito, teto, janela, env_global, teto_global, janela_global = RATE_RULES[acao]
    sujeito = str(sujeito or "anon")[:120]
    esperas = [
        rate_limiter.hit(f"{acao}:sujeito:{sujeito}",
                         env_int(env_sujeito, teto), env_int(f"{env_sujeito}_JANELA", janela)),
        rate_limiter.hit(f"{acao}:global",
                         env_int(env_global, teto_global), env_int(f"{env_global}_JANELA", janela_global)),
    ]
    espera = max(esperas)
    if espera:
        raise HTTPException(429, "Muitos pedidos; tente novamente mais tarde",
                            headers={"Retry-After": str(espera)})


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
    response.headers["Permissions-Policy"] = ("camera=(), microphone=(), payment=(), usb=(), "
                                               "serial=(), bluetooth=(), midi=(), geolocation=(self)")
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if config()["production"]:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.get("/api/health")
def health():
    """Liveness do relay. Nao prova que o PC nem o SQLite estao disponiveis."""
    return {"status": "ok", "configured": is_ready()}


@app.get("/api/ready")
def ready(response: Response):
    """Readiness real: agente + SQLite + commit. 503 quando nao utilizavel."""
    estado = estado_prontidao()
    response.status_code = 200 if estado["ready"] else 503
    return {**estado, "instance": INSTANCE_ID}


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
    drift = drift_agente()
    info = relay.agent_info or {}
    offline_s = relay.offline_s()
    limite = max(60, env_int("JULIA_OFFLINE_ALERT_S", 180))
    return {"pc_online": relay.ws is not None, "agente_ha": relay.ha(),
            "commit": os.environ.get("RENDER_GIT_COMMIT", "local")[:12],
            "instance": INSTANCE_ID,
            "agent_commit": drift["agent_commit"],
            "agent_pid": info.get("pid"),
            "agent_uptime_s": info.get("uptime_s"),
            "agent_started_at": info.get("started_at", ""),
            "agent_db_ok": info.get("db_ok"),
            "drift": drift["drift"],
            "drift_status": drift["status"],
            "stale": relay.ws is None or drift["drift"] or not info,
            "offline_s": offline_s,
            "alert": relay.ws is None and offline_s >= limite}


def _limite_tentativas(request: Request, chave: str, teto: int, janela: float) -> None:
    source = client_ip(request) + ":" + chave
    agora = time.monotonic()
    tentativas = [t for t in login_failures.get(source, []) if agora - t < janela]
    if len(tentativas) >= teto:
        espera = max(1, int(janela - (agora - tentativas[0])))
        raise HTTPException(429, "Muitas tentativas; tente novamente mais tarde",
                            headers={"Retry-After": str(espera)})
    tentativas.append(agora)
    login_failures[source] = tentativas
    if len(login_failures) > 1024:
        for nome, marcas in list(login_failures.items()):
            if not marcas or agora - marcas[-1] > 3600:
                login_failures.pop(nome, None)
    if len(login_failures) > MAX_LOGIN_CHAVES:
        for nome in list(login_failures)[:len(login_failures) - MAX_LOGIN_CHAVES]:
            login_failures.pop(nome, None)


def _limpa_tentativas(request: Request, chave: str) -> None:
    login_failures.pop(client_ip(request) + ":" + chave, None)
