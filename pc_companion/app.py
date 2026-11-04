"""Loopback-only authenticated desktop dashboard; no shell execution endpoint."""
import asyncio
import json
import os
import secrets
import time
import unicodedata
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .connection import Connection, relay_url
from .indexer import FileIndex
from .system import SystemMonitor
from .updater import Updater
from . import __version__

WEB = Path(__file__).parent / 'web'


def data_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'VexxPC'


def default_roots():
    import psutil
    if os.name == 'nt':
        return [p.mountpoint for p in psutil.disk_partitions() if 'fixed' in p.opts and not p.mountpoint.startswith('\\\\')]
    return [str(Path.home())]


def create_app(directory=None, roots=None):
    directory = Path(directory) if directory else data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / 'config.json'
    try:
        config = json.loads(config_path.read_text('utf-8'))
    except (OSError, ValueError):
        config = {}
    local_token = secrets.token_urlsafe(32)
    logs = deque(maxlen=300)
    monitor = SystemMonitor()
    index = FileIndex(directory / 'files.sqlite3', roots if roots is not None else default_roots())

    def log(message):
        logs.append({'time': time.strftime('%H:%M:%S'), 'message': message})

    def save():
        temp = config_path.with_suffix('.tmp')
        temp.write_text(json.dumps(config), 'utf-8')
        temp.replace(config_path)
        try:
            config_path.chmod(0o600)
        except OSError:
            pass

    connection = Connection(config, save, log)
    def shutdown():
        callback = getattr(app.state, 'request_exit', None)
        if callback:
            callback()
    updater = Updater(directory, config, connection, log, shutdown)
    updater.roots = index.roots
    state = {'system': {}, 'monitor_error': ''}

    async def sample():
        while True:
            try:
                state['system'] = await asyncio.to_thread(monitor.snapshot)
                state['monitor_error'] = ''
            except Exception:
                state['monitor_error'] = 'Não foi possível atualizar os sensores.'
            await asyncio.sleep(3)

    async def reindex():
        while True:
            # Initial pass on startup; resume stale metadata automatically in the background.
            index.start()
            await asyncio.sleep(1800)

    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(sample()), asyncio.create_task(connection.run()), asyncio.create_task(reindex()),
                 asyncio.create_task(updater.poll())]
        runtime = getattr(app.state, 'runtime', None)
        if runtime:
            from .apply_update import atomic_json
            atomic_json(directory / 'runtime.json', runtime)
        try:
            previous = json.loads((directory / 'update-result.json').read_text('utf-8'))
            if previous.get('state') == 'failed':
                log(previous.get('message', 'A atualização não foi concluída; versão anterior preservada.'))
        except (OSError, ValueError):
            pass
        log('Vexx PC iniciado. Acesso remoto pausado.')
        try:
            yield
        finally:
            index.stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.local_token, app.state.index, app.state.connection = local_token, index, connection
    app.state.updater, app.state.directory = updater, directory

    async def payload(request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, 'JSON inválido') from None
        if not isinstance(body, dict):
            raise HTTPException(400, 'Pedido inválido')
        return body

    @app.middleware('http')
    async def secure(request: Request, call_next):
        # Strict Host + Origin prevents DNS rebinding and cross-site local requests.
        host = request.url.hostname
        if host not in ('127.0.0.1', 'localhost'):
            return JSONResponse({'detail': 'Host inválido'}, 403)
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Origem inválida'}, 403)
        if request.url.path.startswith('/api/'):
            provided = request.headers.get('x-vexx-token', '')
            cookie = request.cookies.get('vexx_local', '')
            # Read token from a protected bootstrap endpoint, never from a query or log.
            if request.url.path == '/api/bootstrap':
                if not secrets.compare_digest(cookie, local_token):
                    return JSONResponse({'detail': 'Abra pelo atalho Vexx PC'}, 401)
            elif not secrets.compare_digest(provided, local_token):
                return JSONResponse({'detail': 'Sessão local inválida'}, 401)
            try:
                if int(request.headers.get('content-length', 0)) > 8192:
                    return JSONResponse({'detail': 'Pedido muito grande'}, 413)
                if len(await request.body()) > 8192:
                    return JSONResponse({'detail': 'Pedido muito grande'}, 413)
            except ValueError:
                return JSONResponse({'detail': 'Pedido inválido'}, 400)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
            'Referrer-Policy': 'no-referrer'})
        return response

    @app.get('/')
    async def home():
        response = FileResponse(WEB / 'index.html')
        # Browser policy blocks reading this response from any foreign origin.
        response.set_cookie('vexx_local', local_token, httponly=True, samesite='strict')
        return response

    @app.get('/health')
    async def health():
        return {'service': 'vexx-pc', 'version': __version__,
                'pid':os.getpid(), 'instance_id':getattr(app.state, 'instance_id', '')}

    @app.get('/favicon.ico', status_code=204)
    async def favicon():
        from fastapi import Response
        return Response(status_code=204)

    @app.get('/api/bootstrap')
    async def bootstrap():
        return {'token': local_token}

    @app.get('/api/status')
    async def status():
        return {**state, 'index': index.status(), 'connection': connection.status(), 'update':updater.status(),
                'linked': bool(config.get('token')), 'relay': config.get('relay', '')}

    @app.post('/api/update/check')
    async def update_check():
        return await updater.check()

    @app.post('/api/update/apply')
    async def update_apply():
        if not getattr(app.state, 'request_exit', None):
            raise HTTPException(409, 'Abra a versão instalada do Vexx PC para atualizar.')
        try:
            return await updater.apply()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get('/api/search')
    async def search(q: str = '', offset: int = 0, kind: str = 'all'):
        return await asyncio.to_thread(index.search, q, offset, kind)

    @app.get('/api/logs')
    async def get_logs():
        return {'items': list(logs)}

    @app.post('/api/action')
    async def action(request: Request):
        body = await payload(request)
        action = body.get('action')
        if action == 'index_pause':
            index.paused.set()
            log('Indexação pausada.')
        elif action == 'index_resume':
            index.paused.clear()
            index.start()
            log('Indexação retomada.')
        elif action == 'index_refresh':
            index.start()
        elif action == 'allow':
            await connection.permission(True, body.get('control') is True)
        elif action == 'pause':
            await connection.permission(False)
        elif action == 'unlink':
            await connection.permission(False)
            # Revoke persistently on server before removing the only local credential.
            token = config.get('token')
            if token:
                try:
                    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                        r = await client.post(relay_url(config['relay']) + '/api/companion/device-revoke',
                                              headers={'Authorization': 'Bearer ' + token})
                        if r.status_code not in (401, 403):  # already revoked or expired: safe to forget locally
                            r.raise_for_status()
                except (ValueError, httpx.HTTPError):
                    raise HTTPException(503, 'Não foi possível revogar no site. Use Desvincular na sua conta ou tente novamente.') from None
            await connection.unlink()
        elif action == 'shutdown':
            await connection.permission(False)
            index.stop.set()
            callback = getattr(app.state, 'request_exit', None)
            if callback:
                asyncio.get_running_loop().call_later(.3, callback)
        elif action == 'show_window':
            callback = getattr(app.state, 'show_window', None)
            if not callback:
                raise HTTPException(409, 'Esta execução está em modo de diagnóstico.')
            await asyncio.to_thread(callback)
        else:
            raise HTTPException(400, 'Ação desconhecida')
        return {'ok': True}

    @app.post('/api/pair')
    async def pair(request: Request):
        body = await payload(request)
        try:
            relay = relay_url(str(body.get('relay', '')))
            code = str(body.get('code', '')).replace('-', '').strip().upper()
            if len(code) != 8 or not all(c in '0123456789ABCDEF' for c in code):
                raise ValueError('Código deve ter 8 caracteres. Gere-o no site Vexx AI.')
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                result = await client.post(relay + '/api/companion/claim', json={'code': code, 'name': __import__('platform').node()})
                if result.status_code != 200:
                    raise ValueError('O site recusou o código. Verifique o endereço e gere outro código.')
                data = result.json()
                if not isinstance(data.get('token'), str) or not isinstance(data.get('device_id'), str):
                    raise ValueError('Resposta de vínculo inválida.')
            await connection.permission(False)
            config.update(relay=relay, token=data['token'], device_id=data['device_id'])
            save()
            await connection.restart()
            asyncio.create_task(updater.check())
            log('Computador vinculado à conta. Autorize o acesso quando precisar.')
            return {'ok': True}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except httpx.HTTPError:
            raise HTTPException(503, 'Não foi possível conectar ao site Vexx AI.') from None

    @app.post('/api/copilot')
    async def copilot(request: Request):
        body = await payload(request)
        text = str(body.get('text', ''))[:500].strip()
        normalized = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
        if normalized.startswith(('buscar ', 'busque ', 'pesquisar ', 'procure ')):
            query = text.split(' ', 1)[1]
            result = await asyncio.to_thread(index.search, query)
            return {'reply': f"Encontrei {len(result['items'])} resultados nesta página do índice local.", 'search': query}
        if any(word in normalized for word in ('paus', 'revog', 'desativ')) and 'acesso' in normalized:
            await connection.permission(False)
            return {'reply': 'Acesso remoto pausado neste computador.'}
        if 'paus' in normalized and ('indice' in normalized or 'index' in normalized):
            index.paused.set()
            return {'reply': 'Indexação pausada. Os arquivos já indexados continuam pesquisáveis.'}
        if any(word in normalized for word in ('retom', 'atualiz')) and ('indice' in normalized or 'index' in normalized):
            index.paused.clear()
            index.start()
            return {'reply': 'Índice atualizando em segundo plano.', 'page': 'pc'}
        if any(word in normalized for word in ('rede', 'conexao', 'internet')):
            adapters = state['system'].get('adapters', [])
            return {'reply': 'Interfaces ativas: ' + (', '.join(a['name'] for a in adapters) or 'nenhuma detectada') +
                    '. Conexão com sua conta: ' + ('ativa.' if connection.online else 'desconectada. Interfaces ativas não garantem acesso à internet.'), 'page': 'network'}
        if 'log' in normalized:
            return {'reply': 'Abri os eventos desta sessão. Use o filtro para localizar um evento.', 'page': 'logs'}
        if any(word in normalized for word in ('status', 'memoria', 'ram', 'cpu', 'computador', 'disco')):
            s = state['system']
            if not s:
                return {'reply': 'Aguardando a primeira amostra dos sensores.'}
            return {'reply': f"CPU: {s['cpu_percent']}%. RAM: {s['ram']['percent']}%. Ligado há {int(s['uptime']//60)} minutos. "
                    f"Índice: {index.count} entradas. Acesso remoto: {'autorizado' if connection.status()['approved'] else 'pausado'}.", 'page': 'overview'}
        return {'reply': 'Posso consultar CPU/RAM/disco, diagnosticar a conexão, buscar arquivos por nome, abrir logs, pausar acesso e pausar/atualizar o índice. Exemplos: “buscar relatorio.pdf”, “status do computador”, “pausar acesso”.'}

    app.mount('/assets', StaticFiles(directory=WEB), name='assets')
    return app
