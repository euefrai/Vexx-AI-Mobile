"""Júlia Mobile relay: authentication + ephemeral WebSocket RPC only.
No chat history or SQLite file is stored on Render.
"""
import asyncio
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path

from argon2 import PasswordHasher, exceptions as argon_errors
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

log = logging.getLogger("julia-mobile")
ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Júlia Mobile Relay", docs_url=None, redoc_url=None, openapi_url=None)
ph = PasswordHasher()
SESSION_LIFETIME = 12 * 60 * 60


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
    return URLSafeTimedSerializer(secret, salt="julia-mobile-session-v1")


def verify_session(request: Request) -> str:
    token = request.cookies.get("julia_session")
    if not token:
        raise HTTPException(status_code=401, detail="Faça login")
    try:
        data = signer().loads(token, max_age=SESSION_LIFETIME)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Sessão expirada") from None
    if data.get("user") != config()["user"]:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return token


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
    message_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: str = Field(min_length=3, max_length=100)
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9_.:/+-]*$")


# Single Render instance / single paired PC. All values intentionally volatile.
class AgentRelay:
    def __init__(self):
        self.ws: WebSocket | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.streams: dict[str, asyncio.Queue] = {}
        self.send_lock = asyncio.Lock()

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
            try:
                fila.put_nowait({"type": "ai_error", "error": "Agente desconectado",
                                 "codigo": "desconectado"})
            except asyncio.QueueFull:
                pass


relay = AgentRelay()
# Basic, non-durable login rate limiting; reinforce with Cloudflare / WAF for production.
login_failures: dict[str, list[float]] = {}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "configured": is_ready()}


@app.post("/api/login")
def login(credentials: Credentials, request: Request, response: Response):
    if not is_ready():
        raise HTTPException(503, "Configure as variáveis secretas no servidor")
    source = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = [t for t in login_failures.get(source, []) if now - t < 300]
    if len(attempts) >= 5:
        raise HTTPException(429, "Muitas tentativas; tente novamente mais tarde")
    cfg = config()
    valid_user = hmac.compare_digest(credentials.username, cfg["user"])
    try:
        valid_password = ph.verify(cfg["password_hash"], credentials.password)
    except (argon_errors.VerifyMismatchError, argon_errors.VerificationError, argon_errors.InvalidHashError):
        valid_password = False
    if not (valid_user and valid_password):
        attempts.append(now)
        login_failures[source] = attempts
        raise HTTPException(401, "Usuário ou senha inválidos")
    login_failures.pop(source, None)
    token = signer().dumps({"user": cfg["user"], "nonce": secrets.token_hex(16)})
    response.set_cookie(
        "julia_session", token, httponly=True, secure=cfg["production"],
        samesite="strict", max_age=SESSION_LIFETIME, path="/"
    )
    return {"authenticated": True, "csrf": csrf_value(token), "user": cfg["user"]}


@app.get("/api/session")
def session(request: Request):
    token = verify_session(request)
    return {"authenticated": True, "csrf": csrf_value(token), "user": config()["user"]}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    require_csrf(request)
    response.delete_cookie("julia_session", path="/")
    return {"ok": True}


@app.get("/api/status")
def status(request: Request):
    verify_session(request)
    return {"pc_online": relay.ws is not None, "messages_stored_on": "computer"}


@app.post("/api/sync")
async def sync_messages(request: Request, body: SyncBody):
    require_csrf(request)
    result = await relay.exchange({"type": "sync", "messages": [m.model_dump() for m in body.messages]})
    if result.get("type") != "ack":
        raise HTTPException(503, "Confirmação do PC não recebida")
    confirmed = set(result.get("confirmed_ids", []))
    submitted = {m.id for m in body.messages}
    return {"confirmed_ids": sorted(confirmed & submitted)}


@app.get("/api/messages")
async def messages(request: Request):
    verify_session(request)
    result = await relay.exchange({"type": "list", "limit": 200})
    if result.get("type") != "history":
        raise HTTPException(503, "Histórico não disponível")
    return {"messages": result.get("messages", [])[:200]}


@app.post("/api/ai")
async def ai_complete(request: Request, body: AIRequest):
    """Resposta completa (sem streaming). Idempotente por message_id no agente."""
    require_csrf(request)
    result = await relay.exchange({"type": "ai", "message_id": body.message_id,
                                   "conversation_id": body.conversation_id,
                                   "model": body.model}, timeout=180.0)
    if result.get("type") != "ai_done" or "response_text" not in result:
        if result.get("type") == "ai_error":
            raise HTTPException(503, result.get("error", "IA indisponível"))
        raise HTTPException(503, "Resposta da IA não recebida")
    return {"reply_id": result.get("reply_id"), "response_text": result["response_text"],
            "model": result.get("model", "")}


@app.get("/api/ai/models")
async def ai_models(request: Request):
    verify_session(request)
    result = await relay.exchange({"type": "ai_models"}, timeout=30.0)
    if result.get("type") == "ai_error":
        raise HTTPException(503, result.get("error", "Hermes indisponível"))
    if result.get("type") != "ai_models":
        raise HTTPException(503, "Modelos indisponíveis")
    return {"models": result.get("models", [])[:500], "default": result.get("default", "")}


@app.get("/api/ai/stream")
async def ai_stream(request: Request, message_id: str = "", conversation_id: str = "",
                    model: str = ""):
    """SSE com deltas reais do Hermes (via agente). Fechar a conexão cancela."""
    require_csrf(request)
    if not (8 <= len(message_id) <= 100) or not (3 <= len(conversation_id) <= 100):
        raise HTTPException(422, "Parâmetros inválidos")
    from fastapi.responses import StreamingResponse

    ws = relay.ws
    if ws is None:
        raise HTTPException(503, "Computador desconectado; mensagens continuam no celular")
    stream_id = uuid.uuid4().hex
    fila: asyncio.Queue = asyncio.Queue()
    relay.streams[stream_id] = fila
    payload = {"type": "ai_stream", "message_id": message_id,
               "conversation_id": conversation_id, "model": model[:120]}

    async def gerar():
        concluido = False
        espera = 0.0
        try:
            async with relay.send_lock:
                if relay.ws is not ws:
                    yield 'event: error\ndata: {"error": "Agente reconectando"}\n\n'
                    return
                await ws.send_json({**payload, "request_id": stream_id})
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
                    yield f"event: delta\ndata: {json.dumps({'seq': item.get('seq', 0), 'trecho': item.get('trecho', '')}, ensure_ascii=False)}\n\n"
                elif tipo == "ai_done":
                    concluido = True
                    yield f"event: done\ndata: {json.dumps({'reply_id': item.get('reply_id'), 'response_text': item.get('response_text', ''), 'model': item.get('model', '')}, ensure_ascii=False)}\n\n"
                    return
                elif tipo == "ai_cancelled":
                    concluido = True
                    yield f"event: cancelled\ndata: {json.dumps({'reply_id': item.get('reply_id'), 'partial': item.get('partial', '')}, ensure_ascii=False)}\n\n"
                    return
                else:
                    concluido = True
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
                        pass
                    continue
                # Sem stream ativa: ai_done/ai_error de POST /api/ai caem no pending.
            pending = relay.pending.get(request_id)
            if pending and not pending.done():
                pending.set_result(body)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if relay.ws is websocket:
            relay.ws = None
            relay.fail_pending()


app.mount("/", StaticFiles(directory=str(ROOT / "public"), html=True), name="mobile-static")
