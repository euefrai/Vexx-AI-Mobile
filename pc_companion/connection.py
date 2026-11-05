"""Outbound TLS connection; remote access starts paused and requires local consent."""
import asyncio
import importlib.util
import json
import platform
import time
from urllib.parse import urlsplit

import websockets


def relay_url(value):
    p = urlsplit(value.strip().rstrip('/'))
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('Use a origem HTTPS do seu site Vexx AI, sem caminho ou credenciais.')
    return 'https://' + p.netloc


class Connection:
    def __init__(self, config, save, log):
        self.config, self.save, self.log = config, save, log
        self.online, self.approved, self.pending, self.control = False, False, False, False
        self.task, self.ws = None, None
        self.last_error = ''
        self.guard = asyncio.Lock()
        self.grant_until = 0

    def status(self):
        capture = all(importlib.util.find_spec(name) for name in ('mss', 'PIL'))
        approved = self.approved and time.monotonic() < self.grant_until
        return {'device_name': platform.node(), 'platform': platform.system(), 'supported': platform.system() == 'Windows',
                'capture_ready': bool(capture), 'approved': approved, 'view_allowed': approved,
                'control_allowed': approved and self.control, 'pending': self.pending,
                'confirmation_open': self.pending, 'code': '', 'online': self.online, 'error': self.last_error}

    async def run(self):
        delay = 2
        while True:
            token, relay = self.config.get('token'), self.config.get('relay')
            if not token or not relay:
                await asyncio.sleep(2)
                continue
            try:
                url = 'wss://' + urlsplit(relay_url(relay)).netloc + '/api/companion/ws'
                async with websockets.connect(url, additional_headers={'Authorization': 'Bearer ' + token},
                                              max_size=64000, ping_interval=20, open_timeout=10) as ws:
                    self.ws, self.online = ws, True
                    self.last_error = ''
                    self.log('Conexão com sua conta estabelecida.')
                    delay = 2
                    async for raw in ws:
                        req = json.loads(raw)
                        response = await self.handle(req)
                        await ws.send(json.dumps({**response, 'request_id': req.get('request_id')}))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if status in (401, 403):
                    await self.permission(False)
                self.last_error = ('Vínculo recusado ou expirado. Desvincule e conecte novamente com seu nick e PIN.'
                                   if status in (401, 403) else 'Sem conexão com o site. Verifique a rede e o endereço configurado.')
                # Never log credential-bearing URLs, headers or third-party response bodies.
                if self.online:
                    self.log('Conexão interrompida. Tentando reconectar.')
            finally:
                self.online, self.ws = False, None
            await asyncio.sleep(delay)
            delay = min(60, delay * 2)

    async def handle(self, req):
        kind = req.get('type')
        if kind == 'remote_request':
            self.pending = True
            self.approved = False
            self.log('Pedido de acesso recebido. Autorize no painel local deste computador.')
        if kind == 'remote_revoke':
            await self.permission(False)
        if kind in ('remote_status', 'remote_request', 'remote_revoke'):
            return {'type': 'remote_status', **self.status()}
        if kind not in ('screen', 'input'):
            return {'type': 'op_error', 'error': 'Ação indisponível.'}
        async with self.guard:
            if not self.status()['approved'] or self.pending:
                return {'type': kind + '_error', 'codigo': 'sem_permissao', 'error': 'Autorize o acesso no Vexx PC local.'}
            try:
                import remoto
                if kind == 'screen':
                    image = await asyncio.to_thread(remoto.capturar, max(320, min(int(req.get('max_w', 1280)), 1920)),
                                                    max(30, min(int(req.get('q', 72)), 85)))
                    return {'type': 'screen', **image, 'remote_enabled': self.control}
                if not self.control:
                    raise ValueError('Controle pausado')
                cmd = remoto.validar_comando(req.get('cmd'))
                result = await asyncio.to_thread(remoto.executar, cmd, autorizado=True)
                return {'type': 'input_done', **result}
            except Exception:
                return {'type': kind + '_error', 'error': 'Ação recusada ou recurso indisponível.', 'codigo': 'sem_permissao'}

    async def permission(self, allow, control=False):
        # Serialize consent/revocation with in-flight native commands.
        async with self.guard:
            self.approved, self.control, self.pending = allow, allow and control, False
            self.grant_until = time.monotonic() + 3600 if allow else 0
            self.log('Acesso remoto autorizado por uma hora.' if allow else 'Acesso remoto pausado.')

    async def restart(self):
        if self.ws:
            await self.ws.close()

    async def unlink(self):
        await self.permission(False)
        self.config.pop('token', None)
        self.config.pop('device_id', None)
        self.save()
        await self.restart()
        self.log('Computador desvinculado localmente.')
