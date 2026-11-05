"""Per-account companion relay, separate from the privileged inference agent."""
import asyncio
import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from pc_companion.release import BUNDLE_FILES, bundle, manifest, installer_url

ROOT = Path(__file__).resolve().parent


class PairClaim(BaseModel):
    code: str = Field(min_length=8, max_length=12, pattern=r'^[A-Z0-9-]+$')
    name: str = Field(min_length=1, max_length=80)


class PCIdentity(BaseModel):
    nick: str = Field(min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._-]{2,29}$')
    pin: str = Field(min_length=6, max_length=12, pattern=r'^[0-9]{6,12}$')


class IdentityClaim(PCIdentity):
    name: str = Field(min_length=1, max_length=80)


class CompanionHub:
    def __init__(self, host):
        self.host = host
        self.codes = {}
        self.connections = {}
        self.cache = {}

    async def registry(self, owner, action='status', **data):
        result = await self.host.relay.exchange({'type': 'companion_registry', 'owner': owner,
                                                 'action': action, **data}, timeout=8)
        if result.get('type') != 'companion_registry' or result.get('error'):
            raise HTTPException(503, 'Atualize o agente central para vincular computadores.')
        if action in ('enroll', 'revoke', 'identity_set', 'identity_delete'):
            self.cache.pop(owner, None)
        return result

    async def status(self, owner):
        cached = self.cache.get(owner)
        if cached and time.monotonic() - cached[0] < 10:
            return cached[1]
        result = await self.registry(owner)
        self.cache[owner] = (time.monotonic(), result)
        return result

    async def exchange(self, owner, body, timeout=12):
        state = await self.status(owner)
        if not state.get('linked'):
            return None  # Only the legacy installation has no companion record.
        conn = self.connections.get(owner)
        if not state.get('active') or not conn or conn['device_id'] != state.get('device_id'):
            raise HTTPException(503, 'Seu Vexx PC está desconectado ou desvinculado. Abra o aplicativo no seu computador.')
        if len(conn['pending']) >= 8:
            raise HTTPException(429, 'Computador ocupado. Aguarde.')
        rid = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        conn['pending'][rid] = future
        try:
            await conn['ws'].send_json({**body, 'request_id': rid})
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, RuntimeError, WebSocketDisconnect):
            raise HTTPException(503, 'Seu computador não respondeu.') from None
        finally:
            conn['pending'].pop(rid, None)

    async def disconnect(self, owner):
        conn = self.connections.pop(owner, None)
        if conn:
            for fut in conn['pending'].values():
                if not fut.done():
                    fut.set_exception(HTTPException(503, 'Computador desconectado'))
            await conn['ws'].close(code=1000)


def install(host):
    hub = CompanionHub(host)
    app = host.app

    def signer():
        return URLSafeTimedSerializer(host.config()['session_secret'], salt='vexx-companion-v1')

    async def account(request):
        host.require_csrf(request)
        return await host.revogacao_ok(request)

    @app.get('/api/companion/release')
    async def release():
        return Response(json.dumps(await asyncio.to_thread(manifest)), media_type='application/json',
                        headers={'Cache-Control': 'no-store'})

    @app.get('/downloads/vexx-pc-agent-windows.zip')
    async def download():
        return Response(await asyncio.to_thread(bundle), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="Vexx-PC-Windows.zip"',
                                 'Cache-Control': 'public, max-age=300'})

    @app.get('/downloads/vexx-pc-agent-setup.exe')
    async def download_installer():
        return RedirectResponse(installer_url(), status_code=302, headers={'Cache-Control':'no-store'})

    @app.post('/api/companion/pair')
    async def pair(request: Request):
        owner = await account(request)
        if host.rate_limiter.hit('companion-pair:' + owner, 5, 600):
            raise HTTPException(429, 'Aguarde para gerar outro código.')
        now = time.monotonic()
        hub.codes = {k: v for k, v in hub.codes.items() if v['until'] > now and v['owner'] != owner}
        if len(hub.codes) >= 1000:
            raise HTTPException(429, 'Tente novamente em alguns minutos.')
        code = secrets.token_hex(4).upper()
        hub.codes[code] = {'owner': owner, 'until': now + 180}
        return {'code': code, 'expires_in': 180}

    @app.get('/api/companion/identity')
    async def identity_get(request: Request):
        owner = await account(request)
        result = await hub.registry(owner, 'identity_get')
        return {'configured':result['configured'], 'nick':result['nick']}

    @app.post('/api/companion/identity')
    async def identity_set(request: Request, body: PCIdentity):
        owner = await account(request)
        if host.rate_limiter.hit('companion-identity:' + owner, 10, 600):
            raise HTTPException(429, 'Aguarde antes de alterar novamente.')
        result = await hub.registry(owner, 'identity_set', nick=body.nick.lower(), pin=body.pin)
        if result.get('conflict'):
            raise HTTPException(409, 'Este nick já está em uso. Escolha outro.')
        if not result.get('ok'):
            raise HTTPException(400, 'Revise o nick e o PIN.')
        hub.codes = {k:v for k,v in hub.codes.items() if v['owner'] != owner}
        await hub.disconnect(owner)
        return {'ok':True, 'nick':body.nick.lower()}

    @app.delete('/api/companion/identity')
    async def identity_delete(request: Request):
        owner = await account(request)
        await hub.registry(owner, 'identity_delete')
        hub.codes = {k:v for k,v in hub.codes.items() if v['owner'] != owner}
        await hub.disconnect(owner)
        return {'ok':True}

    @app.post('/api/companion/connect')
    async def identity_claim(request: Request, body: IdentityClaim):
        from rate_limit import client_ip
        if host.rate_limiter.hit('companion-connect:' + client_ip(request), 10, 600):
            raise HTTPException(429, 'Muitas tentativas. Aguarde antes de tentar novamente.')
        result = await hub.registry('', 'authenticate_identity', nick=body.nick.lower(), pin=body.pin)
        if result.get('denied') or not result.get('owner'):
            raise HTTPException(403, 'Nick ou PIN inválidos, indisponíveis ou temporariamente bloqueados.')
        owner, device = result['owner'], uuid.uuid4().hex
        token = signer().dumps({'owner':owner, 'device_id':device})
        enrolled = await hub.registry(owner, 'enroll', device_id=device, name=body.name,
                         token_hash=hashlib.sha256(token.encode()).hexdigest(), generation=result['generation'])
        if enrolled.get('denied'):
            raise HTTPException(403, 'As credenciais foram alteradas. Conecte novamente.')
        await hub.disconnect(owner)
        return {'token':token, 'device_id':device, 'nick':body.nick.lower()}

    @app.post('/api/companion/claim')
    async def claim(request: Request, body: PairClaim):
        from rate_limit import client_ip
        if host.rate_limiter.hit('companion-claim:' + client_ip(request), 10, 600):
            raise HTTPException(429, 'Muitas tentativas de vínculo.')
        item = hub.codes.pop(body.code.replace('-', ''), None)
        if not item or item['until'] < time.monotonic():
            raise HTTPException(400, 'Código inválido ou expirado. Gere outro no site.')
        owner = item['owner']
        device = uuid.uuid4().hex
        token = signer().dumps({'owner': owner, 'device_id': device})
        await hub.registry(owner, 'enroll', device_id=device, name=body.name,
                           token_hash=hashlib.sha256(token.encode()).hexdigest())
        await hub.disconnect(owner)
        return {'token': token, 'device_id': device}

    @app.get('/api/companion/status')
    async def status(request: Request):
        owner = await account(request)
        state = await hub.status(owner)
        return {**{k: v for k, v in state.items() if k != 'type'}, 'online': owner in hub.connections}

    @app.post('/api/companion/unlink')
    async def unlink(request: Request):
        owner = await account(request)
        await hub.registry(owner, 'revoke')
        await hub.disconnect(owner)
        return {'ok': True}

    @app.post('/api/companion/device-revoke')
    async def device_revoke_credential(request: Request):
        token = request.headers.get('authorization', '').removeprefix('Bearer ')
        try:
            identity = signer().loads(token, max_age=90 * 86400)
            owner = identity['owner']
            result = await hub.registry(owner, 'validate', device_id=identity['device_id'], token=token)
            if not result.get('allowed'):
                raise ValueError('revoked')
        except (BadSignature, ValueError, KeyError, TypeError):
            raise HTTPException(401, 'Credencial inválida') from None
        await hub.registry(owner, 'revoke')
        await hub.disconnect(owner)
        return {'ok': True}

    async def remote_status(request, action):
        owner = await account(request)
        host._rate_limit(request, 'remote_request' if action == 'remote_request' else 'remote_status', owner)
        state = await hub.status(owner)
        if not state.get('active') or owner not in hub.connections:
            return {'supported': True, 'capture_ready': False, 'approved': False,
                    'view_allowed': False, 'control_allowed': False, 'platform': 'Windows',
                    'device_name': state.get('name', 'Meu computador'), 'offline': True}
        result = await hub.exchange(owner, {'type': action})
        if not result or result.get('type') != 'remote_status':
            raise HTTPException(503, 'Não foi possível consultar seu computador.')
        return {k: v for k, v in result.items() if k not in ('type', 'request_id')}

    @app.get('/api/companion/remote/status')
    async def device_status(request: Request):
        return await remote_status(request, 'remote_status')

    @app.post('/api/companion/remote/request')
    async def device_request(request: Request):
        return await remote_status(request, 'remote_request')

    @app.post('/api/companion/remote/revoke')
    async def device_revoke(request: Request):
        return await remote_status(request, 'remote_revoke')

    @app.get('/api/companion/screen')
    async def screen(request: Request, max_w: int = 1280, q: int = 72):
        owner = await account(request)
        host._rate_limit(request, 'screen', owner)
        result = await hub.exchange(owner, {'type': 'screen', 'max_w': max(320, min(max_w, 1920)),
                                            'q': max(30, min(q, 85))}, timeout=20)
        if not result or result.get('type') != 'screen':
            raise HTTPException(403, (result or {}).get('error', 'Vincule e autorize seu computador.'))
        return {k: v for k, v in result.items() if k not in ('type', 'request_id')}

    @app.get('/api/companion/remote/frame')
    async def frame(request: Request, max_w: int = 1280, q: int = 72):
        import base64
        result = await screen(request, max_w, q)
        try:
            raw = base64.b64decode(result['imagem'], validate=True)
        except (ValueError, KeyError, TypeError):
            raise HTTPException(503, 'Quadro inválido') from None
        if len(raw) > 4_000_000 or not raw.startswith(b'\xff\xd8'):
            raise HTTPException(503, 'Quadro inválido')
        headers = {'Cache-Control': 'no-store, private',
            'X-Frame-Width': str(result.get('largura', 0)), 'X-Frame-Height': str(result.get('altura', 0)),
            'X-Remote-Control': '1' if result.get('remote_enabled') else '0'}
        import math
        cursor = result.get('cursor')
        if isinstance(cursor, dict) and all(type(cursor.get(k)) in (float, int) and
                math.isfinite(cursor[k]) and 0 <= cursor[k] <= 1 for k in ('x', 'y')):
            headers.update({'X-Cursor-X': str(cursor['x']), 'X-Cursor-Y': str(cursor['y'])})
        return Response(raw, media_type='image/jpeg', headers=headers)

    async def input_command(request, batch=False):
        from pydantic import ValidationError
        owner = await account(request)
        try:
            body = (host.InputBatch if batch else host.InputBody).model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(422, 'Comando inválido') from None
        commands = body.commands if batch else [body]
        for _ in commands:
            host._rate_limit(request, 'input', owner)
        if batch and (sum(len(c.text) for c in commands) > 400 or any(c.kind == 'drag' for c in commands)):
            raise HTTPException(422, 'Lote excede os limites')
        cmd = {'kind': 'batch', 'commands': [c.model_dump() for c in commands]} if batch else body.model_dump()
        result = await hub.exchange(owner, {'type': 'input', 'cmd': cmd})
        if not result or result.get('type') != 'input_done':
            raise HTTPException(403, (result or {}).get('error', 'Comando recusado'))
        response = {'ok': True, 'kind': result.get('kind', '')}
        if not batch and body.kind == 'clipboard_get':
            response['text'] = str(result.get('text', ''))[:4000]
        return response

    @app.post('/api/companion/input')
    async def device_input(request: Request):
        return await input_command(request)

    @app.post('/api/companion/input/batch')
    async def device_batch(request: Request):
        return await input_command(request, True)

    @app.websocket('/api/companion/ws')
    async def websocket(ws: WebSocket):
        from rate_limit import client_ip
        if host.rate_limiter.hit('companion-socket:' + client_ip(ws), 20, 60):
            await ws.close(code=1008)
            return
        token = ws.headers.get('authorization', '').removeprefix('Bearer ')
        try:
            identity = signer().loads(token, max_age=90 * 86400)
            owner, device = identity['owner'], identity['device_id']
            validated = await hub.registry(owner, 'validate', device_id=device, token=token)
            if not validated.get('allowed'):
                raise ValueError('revoked')
        except (BadSignature, KeyError, TypeError, ValueError, HTTPException):
            await ws.close(code=1008)
            return
        await hub.disconnect(owner)
        await ws.accept()
        conn = {'ws': ws, 'device_id': device, 'pending': {}}
        hub.connections[owner] = conn
        checked = time.monotonic()
        try:
            while True:
                # Revalidate blocked/deleted accounts and revocations during idle sessions too.
                try:
                    raw = await asyncio.wait_for(ws.receive_text(), 30)
                except TimeoutError:
                    raw = '{}'
                if len(raw) > 6_000_000:
                    break
                if time.monotonic() - checked >= 30:
                    signer().loads(token, max_age=90 * 86400)
                    valid = await hub.registry(owner, 'validate', device_id=device, token=token)
                    checked = time.monotonic()
                    if not valid.get('allowed'):
                        break
                body = json.loads(raw)
                if not isinstance(body, dict):
                    break
                future = conn['pending'].get(body.get('request_id'))
                if future and not future.done():
                    future.set_result(body)
        except (WebSocketDisconnect, RuntimeError, ValueError, HTTPException, BadSignature):
            pass
        finally:
            if hub.connections.get(owner) is conn:
                await hub.disconnect(owner)
    return hub
