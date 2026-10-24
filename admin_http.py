"""Recent admin authorization layered on the existing relay session, not a login system."""
import hashlib
import hmac
import time
from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from itsdangerous import BadSignature, SignatureExpired
from pydantic import BaseModel, Field

SECONDS = 600
COOKIE = 'VEXX_admin'


class Password(BaseModel):
    password: str = Field(min_length=1, max_length=128)


async def guard(request, server, recent=True):
    server.verify_session(request)
    if request.method not in ('GET','HEAD','OPTIONS'):
        server.require_csrf(request)
    data=server.sessao_dados(request)
    uid=str(data.get('uid') or 'local')
    if server.relay.ws is None:
        raise HTTPException(503,'Computador offline; autorização administrativa indisponível')
    if uid != 'local':
        result=await server.relay.exchange({'type':'auth_whoami','sid':str(data.get('sid') or '')},timeout=10)
        user=result.get('user') or {}
        if result.get('type') != 'auth_user' or user.get('uid') != uid:
            raise HTTPException(401,'Sessão inválida')
        if user.get('role') != 'admin' or user.get('status') != 'ativo':
            raise HTTPException(403,'Permissão de administrador necessária')
    result=await server.relay.exchange({'type':'admin_identity','owner':uid,'sid':str(data.get('sid') or ''),'require_session':recent},timeout=10)
    if result.get('type') != 'admin_identity':
        raise HTTPException(403,'Conta ou sessão administrativa indisponível')
    identity=result.get('identity') or {}
    if identity.get('uid') != uid or identity.get('role') != 'admin' or not identity.get('approved'):
        raise HTTPException(403,'Permissão de administrador necessária')
    server._rate_limit(request,'admin',uid)
    request.state.admin_identity=identity
    if recent:
        try:
            grant,issued=server.signer().loads(request.cookies.get(COOKIE,''),max_age=SECONDS,return_timestamp=True)
            session=hashlib.sha256(request.cookies.get('JULIA_session','').encode()).hexdigest()
            if not (grant.get('purpose')=='admin' and grant.get('uid')==uid and
                    hmac.compare_digest(str(grant.get('session','')),session) and
                    grant.get('revision')==identity.get('revision')):
                raise BadSignature('invalid grant')
            request.state.admin_remaining=max(0,int(SECONDS-(time.time()-issued.timestamp())))
        except (BadSignature,SignatureExpired,TypeError,ValueError,AttributeError):
            raise HTTPException(403,'Reautenticação administrativa necessária') from None
    return uid


def install(app, server):
    @app.get('/api/admin/access')
    async def access(request:Request):
        uid=await guard(request,server,recent=False)
        return JSONResponse({'eligible':True,'uid':uid,'expires_in':SECONDS},headers={'Cache-Control':'no-store'})

    @app.post('/api/admin/reauth')
    async def reauth(request:Request,body:Password,response:Response):
        uid=await guard(request,server,recent=False)
        server._limite_tentativas(request,'admin-reauth:'+uid,5,300)
        data=server.sessao_dados(request)
        payload={'type':'admin_verify_password','owner':uid,'sid':str(data.get('sid') or ''),'cliente':server.client_ip(request)}
        if uid=='local':
            try:
                ok=server.ph.verify(server.config()['password_hash'],body.password)
            except (server.argon_errors.VerifyMismatchError,server.argon_errors.VerificationError,server.argon_errors.InvalidHashError):
                ok=False
            payload['legacy_verified']=bool(ok)
        else:
            payload['password']=body.password
        result=await server.relay.exchange(payload,timeout=20)
        if result.get('type')!='admin_verified':
            raise HTTPException(401,'Credenciais inválidas')
        identity=result.get('identity') or {}
        if identity.get('uid')!=uid or identity.get('revision')!=request.state.admin_identity.get('revision'):
            raise HTTPException(403,'Autorização alterada; tente novamente')
        grant=server.signer().dumps({'purpose':'admin','uid':uid,'revision':identity['revision'],
                 'session':hashlib.sha256(request.cookies.get('JULIA_session','').encode()).hexdigest()})
        response.set_cookie(COOKIE,grant,httponly=True,secure=server.config()['production'],samesite='strict',max_age=SECONDS,path='/api/admin')
        response.headers['Cache-Control']='no-store'
        server._limpa_tentativas(request,'admin-reauth:'+uid)
        return {'authorized':True,'expires_in':SECONDS}

    @app.post('/api/admin/leave')
    async def leave(request:Request,response:Response):
        server.require_csrf(request)
        response.delete_cookie(COOKIE,path='/api/admin')
        return {'authorized':False}

    @app.get('/api/admin/overview')
    async def overview(request:Request):
        uid=await guard(request,server)
        result=await server.relay.exchange({'type':'admin_console_overview','owner':uid,
                     'sid':str(server.sessao_dados(request).get('sid') or '')},timeout=20)
        if result.get('type')!='admin_console_overview':
            raise HTTPException(503,'Diagnóstico indisponível')
        result['admin_expires_in']=request.state.admin_remaining
        return JSONResponse(result,headers={'Cache-Control':'no-store'})

    @app.get('/api/admin/audit')
    async def audit(request:Request):
        uid=await guard(request,server)
        result=await server.relay.exchange({'type':'admin_console_audit','owner':uid,
                     'sid':str(server.sessao_dados(request).get('sid') or '')},timeout=15)
        if result.get('type')!='admin_console_audit':
            raise HTTPException(503,'Auditoria indisponível')
        return JSONResponse(result,headers={'Cache-Control':'no-store'})

    @app.get('/admin',include_in_schema=False)
    async def page():
        # Only the auth shell is public. Operational data always requires guard.
        return FileResponse(server.ROOT/'public'/'admin.html',headers={'Cache-Control':'no-store'})
