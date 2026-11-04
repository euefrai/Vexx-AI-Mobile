"""Real HTTPS + outbound WSS smoke. Auth/inference and native desktop are fixtures.

Run from repo root: python -m pip install trustme; python tools/verify_pc_companion_tls.py
Never connects to production or executes native input. No operator credentials are loaded.
"""
import asyncio
import base64
import io
import json
import os
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(JULIA_SESSION_SECRET=secrets.token_hex(32), JULIA_AGENT_TOKEN=secrets.token_hex(32),
                  JULIA_USERNAME='qa-companion', JULIA_PASSWORD_HASH='qa-unused', JULIA_ENV='development',
                  JULIA_ENV_FILE=str(Path(tempfile.gettempdir()) / ('vexx-qa-absent-' + secrets.token_hex(16))))

import httpx
import trustme
import uvicorn
from fastapi import HTTPException
from PIL import Image
import companion_registry
import julia_auth
import remoto
import server
from pc_companion.app import create_app


def serve(app, **config):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0)); sock.listen(128)
    process = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, **config))
    thread = threading.Thread(target=lambda: process.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not process.started and time.monotonic() < deadline:
        time.sleep(.05)
    if not process.started:
        raise RuntimeError('QA server did not start')
    return process, thread, sock.getsockname()[1]


def main():
    with tempfile.TemporaryDirectory(prefix='vexx-companion-tls-') as tmp:
        root = Path(tmp)
        ca = trustme.CA()
        cert = ca.issue_cert('127.0.0.1', 'localhost')
        ca.cert_pem.write_to_path(root / 'ca.pem')
        cert.private_key_pem.write_to_path(root / 'key.pem')
        cert.cert_chain_pems[0].write_to_path(root / 'cert.pem')
        os.environ['SSL_CERT_FILE'] = str(root / 'ca.pem')
        db = sqlite3.connect(root / 'accounts.sqlite3', check_same_thread=False)
        julia_auth.criar_tabelas(db)
        user = julia_auth.criar_usuario(db, 'alice', 'Alice QA', 'qa-companion-only-password', criado_por='local')

        async def account(request):
            return user['uid']
        def csrf(request):
            if request.headers.get('x-csrf-token') != 'qa-tls':
                raise HTTPException(403)
        async def registry(req, **kw):
            if req.get('type') != 'companion_registry':
                raise HTTPException(503, 'QA only supports device registry')
            return companion_registry.handle(db, req)
        server.require_csrf, server.revogacao_ok, server.relay.exchange = csrf, account, registry
        pic = io.BytesIO(); Image.new('RGB', (2, 2), 'green').save(pic, format='JPEG')
        native_calls = []
        remoto.capturar = lambda *a, **kw: {'imagem':base64.b64encode(pic.getvalue()).decode(), 'largura':2, 'altura':2}
        def input_fixture(cmd, **kw):
            native_calls.append((cmd, kw))
            return {'ok':True, 'kind':cmd['kind'], **({'text':'QA clipboard'} if cmd['kind']=='clipboard_get' else {})}
        remoto.executar = input_fixture
        relay, relay_thread, relay_port = serve(server.app, ssl_keyfile=str(root / 'key.pem'), ssl_certfile=str(root / 'cert.pem'))
        local_app = create_app(root / 'local', [Path(__file__).resolve().parents[1] / 'pc_companion'])
        local, local_thread, local_port = serve(local_app)
        try:
            origin = f'https://127.0.0.1:{relay_port}'
            with httpx.Client(base_url=origin, verify=str(root / 'ca.pem'), timeout=15, headers={'X-CSRF-Token':'qa-tls'}) as site, \
                 httpx.Client(base_url=f'http://127.0.0.1:{local_port}', timeout=15) as pc:
                pc.get('/').raise_for_status()
                pc.headers['X-Vexx-Token'] = pc.get('/api/bootstrap').json()['token']
                code = site.post('/api/companion/pair').json()['code']
                pair = pc.post('/api/pair', json={'relay':origin, 'code':code})
                assert pair.status_code == 200, pair.text
                until = time.monotonic() + 12
                while not pc.get('/api/status').json()['connection']['online'] and time.monotonic() < until:
                    time.sleep(.2)
                assert site.get('/api/companion/status').json()['online']
                assert site.get('/api/companion/remote/frame').status_code == 403
                assert site.post('/api/companion/remote/request').json()['pending']
                assert pc.get('/api/status').json()['connection']['pending']
                pc.post('/api/action',json={'action':'allow','control':True}).raise_for_status()
                start = time.perf_counter()
                frame = site.get('/api/companion/remote/frame')
                assert frame.status_code == 200 and frame.content.startswith(b'\xff\xd8')
                frame_ms = round((time.perf_counter() - start) * 1000, 1)
                command = site.post('/api/companion/input',json={'kind':'key','key':'enter'})
                assert command.status_code == 200 and len(native_calls) == 1 and native_calls[0][1]['autorizado']
                clip = site.post('/api/companion/input',json={'kind':'clipboard_get'})
                assert clip.status_code == 200 and clip.json()['text'] == 'QA clipboard'
                pc.post('/api/action',json={'action':'pause'}).raise_for_status()
                assert site.post('/api/companion/input',json={'kind':'key','key':'enter'}).status_code == 403
                assert len(native_calls) == 2
                site.post('/api/companion/unlink').raise_for_status()
                pc.post('/api/action',json={'action':'unlink'}).raise_for_status()
                assert not pc.get('/api/status').json()['linked']
                report = {'https_pairing':True, 'outbound_wss':True, 'remote_request':True,
                          'local_consent':True, 'jpeg_transport':True, 'native_input_fixture_only':True,
                          'pause_blocks_input':True, 'server_and_local_unlink':True, 'fixture_frame_ms':frame_ms}
                print(json.dumps(report, indent=2))
        finally:
            local.should_exit = True; relay.should_exit = True
            local_thread.join(5); relay_thread.join(5)
            db.close()


if __name__ == '__main__':
    main()
