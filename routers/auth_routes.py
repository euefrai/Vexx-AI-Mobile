"""Router: Autenticação, cadastro, sessão e conta."""
import hmac
import julia_auth

from argon2 import exceptions as argon_errors
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from rate_limit import client_ip

from relay_core import (
    _limite_tentativas, _limpa_tentativas, _rate_limit, config, Credentials, csrf_value,
    emitir_sessao, is_ready, ph, relay, require_csrf, revogacao_ok, revogados, sessao_dados,
)

router = APIRouter()

@router.post("/api/login")
async def login(credentials: Credentials, request: Request, response: Response):
    if not is_ready():
        raise HTTPException(503, "Configure as variáveis secretas no servidor")
    _rate_limit(request, "login", client_ip(request))
    cfg = config()
    legado = hmac.compare_digest(credentials.username, cfg["user"])
    if legado and not julia_auth.login_legado_permitido():
        raise HTTPException(401, "Usuário ou senha inválidos")
    if legado:
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
                                       "password": credentials.password,
                                       "cliente": client_ip(request)}, timeout=20.0)
    except HTTPException:
        raise HTTPException(401, "Usuário ou senha inválidos") from None
    if result.get("type") == "auth_error" and result.get("codigo") == "rate":
        espera = max(1, int(result.get("retry_after", 60) or 60))
        raise HTTPException(429, "Muitas tentativas; tente novamente mais tarde",
                            headers={"Retry-After": str(espera)})
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


ultima_auth_config: dict = {}


def _auth_config_indisponivel(online: bool) -> dict:
    """Preserva a ultima configuracao conhecida e a marca como stale."""
    base = dict(ultima_auth_config) if ultima_auth_config else {
        "modo": "fechado", "exigir_aprovacao": True}
    return {**base, "agent_online": online, "stale": True}


@router.get("/api/auth/config")
async def auth_config(request: Request):
    if relay.ws is None:
        return _auth_config_indisponivel(False)
    try:
        result = await relay.exchange({"type": "auth_config"}, timeout=10.0)
    except HTTPException:
        return _auth_config_indisponivel(True)
    if result.get("type") != "auth_config":
        return _auth_config_indisponivel(True)
    configuracao = {"modo": result.get("modo", "convite"),
                    "exigir_aprovacao": result.get("exigir_aprovacao", True)}
    ultima_auth_config.clear()
    ultima_auth_config.update(configuracao)
    return {**configuracao, "agent_online": True, "stale": False}


@router.post("/api/register")
async def register(body: Registro, request: Request, response: Response):
    _rate_limit(request, "register", client_ip(request))
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


@router.get("/api/session")
async def session(request: Request):
    data = sessao_dados(request)
    uid = str(data.get("uid") or "")
    nome = str(data.get("nome") or data.get("user") or config()["user"])
    if uid == "local":
        papel = "admin"  # somente quando o login legado está habilitado
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


@router.post("/api/logout")
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


@router.get("/api/account")
async def account_me(request: Request):
    data = sessao_dados(request)
    uid = str(data.get("uid") or "")
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


@router.post("/api/account/password")
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


@router.post("/api/account/delete")
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
