"""Outbound TLS connection; remote access starts paused and requires local consent."""
import asyncio
import hashlib
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
    def __init__(self, config, save, log, permanent_changed=None):
        self.config, self.save, self.log = config, save, log
        self.permanent_changed=permanent_changed
        self.online, self.approved, self.pending, self.control = False, False, False, False
        self.task, self.ws = None, None
        self.last_error = ''
        self.relink_required = False
        self.guard = asyncio.Lock()
        self.grant_until = 0
        if self._permanent():
            try:
                if self.permanent_changed:self.permanent_changed(True)
                self.approved,self.control=True,True
                self.grant_until=float('inf')
            except Exception:
                self.config.pop('permanent_control',None);self.save()
                self.last_error='Não foi possível reativar o início automático do controle permanente.'
                self.log(self.last_error+' Autorize novamente no painel local.')

    def _permanent(self):
        saved=self.config.get('permanent_control')
        token=self.config.get('token')
        return bool(isinstance(saved,dict) and token and self.config.get('device_id')
                    and saved.get('device_id')==self.config['device_id']
                    and saved.get('credential')==hashlib.sha256(token.encode()).hexdigest())

    def status(self):
        capture = all(importlib.util.find_spec(name) for name in ('mss', 'PIL'))
        approved = self.approved and time.monotonic() < self.grant_until
        return {'device_name': platform.node(), 'platform': platform.system(), 'supported': platform.system() == 'Windows',
                'capture_ready': bool(capture), 'approved': approved, 'view_allowed': approved,
                'control_allowed': approved and self.control, 'pending': self.pending,
                'confirmation_open': self.pending, 'code': '', 'online': self.online, 'error': self.last_error,
                'relink_required':self.relink_required, 'permanent_control':self._permanent()}

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
                    self.relink_required = False
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
                    self.relink_required = True
                self.last_error = ('Vínculo recusado ou expirado. Informe novamente seu nick e PIN.'
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
            if not (self._permanent() and self.approved):
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

    async def permission(self, allow, control=False, permanent=False, preserve=False):
        # Serialize consent/revocation with in-flight native commands.
        async with self.guard:
            if permanent and (not allow or not control or not self.config.get('token') or not self.config.get('device_id')):
                raise ValueError('Vincule este computador antes de permitir controle permanente.')
            if not preserve:
                previous=self.config.get('permanent_control')
                self.config.pop('permanent_control',None)
                if permanent:
                    self.config['permanent_control']={'device_id':self.config['device_id'],
                        'credential':hashlib.sha256(self.config['token'].encode()).hexdigest()}
                self.save()
                if self.permanent_changed:
                    try:self.permanent_changed(permanent)
                    except Exception as exc:
                        if permanent:
                            if previous is not None:self.config['permanent_control']=previous
                            else:self.config.pop('permanent_control',None)
                            self.save()
                            try:self.permanent_changed(False)
                            except Exception:pass
                            raise ValueError('Não foi possível configurar o início automático no login do Windows; o controle permanente não foi ativado.') from exc
                        self.log('A autorização foi revogada, mas não foi possível remover o início automático do Vexx PC.')
            self.approved, self.control, self.pending = allow, allow and control, False
            self.grant_until = float('inf') if permanent else time.monotonic() + 3600 if allow else 0
            self.log('Controle permanente autorizado para a conta vinculada.' if permanent else 'Acesso remoto autorizado por uma hora.' if allow else 'Acesso remoto pausado.')

    async def restart(self):
        if self.ws:
            await self.ws.close()

    async def unlink(self):
        await self.permission(False)
        self.relink_required = False
        self.config.pop('token', None)
        self.config.pop('device_id', None)
        self.save()
        await self.restart()
        self.log('Computador desvinculado localmente.')
