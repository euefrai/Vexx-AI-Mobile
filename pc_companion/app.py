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
from .ai import AI
from .files import Files, installed_apps
from .projects import Projects
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
    ai = AI(directory)
    files = Files(directory,index)
    projects = Projects(directory,index.roots)
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
        log('Vexx PC iniciado. '+('Controle permanente ativo para a conta vinculada.' if connection.status()['approved'] else 'Acesso remoto pausado.'))
        try:
            yield
        finally:
            index.stop.set()
            await asyncio.to_thread(projects.close)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.local_token, app.state.index, app.state.connection = local_token, index, connection
    app.state.updater, app.state.directory = updater, directory
    app.state.files, app.state.projects = files,projects

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
                limit=65536 if request.url.path=='/api/files/prepare' else 8192
                if int(request.headers.get('content-length', 0)) > limit:
                    return JSONResponse({'detail': 'Pedido muito grande'}, 413)
                if len(await request.body()) > limit:
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
                'linked': bool(config.get('token')), 'relay': config.get('relay', ''), 'nick':config.get('nick',''), 'ai':ai.status()}

    @app.get('/api/ai/config')
    async def ai_config():
        return ai.status()

    @app.post('/api/ai/config')
    async def ai_save(request: Request):
        try:
            result = await asyncio.to_thread(ai.save, await payload(request))
            log('Configuração de IA atualizada neste computador.')
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post('/api/ai/test')
    async def ai_test():
        try:
            return await ai.models()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

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
    async def search(q: str = '', offset: int = 0, kind: str = 'all', sort: str = 'relevance', min_size: int = 0, age_days: int = 0, folder: str = ''):
        result=await asyncio.to_thread(index.search, q, offset, kind, sort,min_size,age_days,folder)
        for item in result['items']:item['removable']=not item['directory'] and files.removable(item['path'])
        return result

    async def local_work(fn,*args):
        try:return await asyncio.to_thread(fn,*args)
        except ValueError as exc:raise HTTPException(400,str(exc)) from None
        except OSError:raise HTTPException(400,'Não foi possível acessar o item. Confira se existe, está disponível e permite acesso.') from None

    @app.get('/api/files/browse')
    async def browse(path: str = '', offset: int = 0, sort: str = 'name'):
        result=await local_work(files.browse,path,offset,sort)
        for item in result['items']:item['removable']=not item['directory'] and files.removable(item['path'])
        return result

    @app.get('/api/files/trash')
    async def trash_items(offset: int = 0):return await local_work(files.trash_items,offset)

    @app.post('/api/files/pick-folder')
    async def pick_folder():
        callback=getattr(app.state,'pick_folder',None)
        if not callback:raise HTTPException(409,'Cole o caminho ou use Raízes locais. O seletor de pastas está disponível na janela Windows.')
        result=await asyncio.to_thread(callback)
        if not result:return {'path':''}
        path=await local_work(files.paths.check,result[0])
        return {'path':str(path)}

    @app.post('/api/files/prepare')
    async def files_prepare(request: Request):
        body=await payload(request)
        return await local_work(files.prepare,body.get('mode','trash'),body.get('items'))

    @app.post('/api/files/execute')
    async def files_execute(request: Request):
        body=await payload(request)
        result=await local_work(files.execute,str(body.get('token','')),str(body.get('confirmation','')))
        log('Operação de arquivos: '+result['mode']+' · '+str(len(result['done']))+' concluídos · '+str(len(result['failed']))+' pendentes.')
        return result

    @app.post('/api/files/open-folder')
    async def open_folder(request: Request):
        body=await payload(request)
        path=await local_work(files.paths.check,body.get('path',''))
        if os.name!='nt':raise HTTPException(400,'Abrir pastas no sistema está disponível no Windows.')
        await asyncio.to_thread(os.startfile,str(path if path.is_dir() else path.parent))
        return {'ok':True}

    @app.get('/api/apps')
    async def apps():return await local_work(installed_apps)

    @app.post('/api/apps/manage')
    async def manage_apps():
        if os.name!='nt':raise HTTPException(400,'Gerencie os aplicativos pelo Windows.')
        await asyncio.to_thread(os.startfile,'ms-settings:appsfeatures')
        return {'ok':True}

    @app.post('/api/projects/inspect')
    async def project_inspect(request: Request):
        body=await payload(request)
        return await local_work(projects.inspect,body.get('path',''))

    @app.post('/api/projects/start')
    async def project_start(request: Request):
        body=await payload(request)
        return await local_work(projects.start,str(body.get('token','')),body.get('prepare') is True)

    @app.get('/api/projects/status')
    async def project_status(id: str = ''):return projects.status(id)

    @app.post('/api/projects/stop')
    async def project_stop(request: Request):
        body=await payload(request)
        return await local_work(projects.stop,str(body.get('id','')))

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
            try:await connection.permission(True, body.get('control') is True, permanent=body.get('permanent') is True)
            except ValueError as exc:raise HTTPException(400,str(exc)) from None
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
            await connection.permission(False,preserve=True)
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
            relay = relay_url(str(body.get('relay') or 'https://vexx-ai.onrender.com'))
            if body.get('nick'):
                import re
                nick, pin = str(body['nick']).strip().lower(), str(body.get('pin',''))
                if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,29}', nick) or not re.fullmatch(r'[0-9]{6,12}', pin):
                    raise ValueError('Informe o nick do site e o PIN de 6 a 12 números.')
                path, claim = '/api/companion/connect', {'nick':nick,'pin':pin,'name':__import__('platform').node()}
            else:  # Compatibility with installed 1.1/1.2 clients and existing diagnostic tools.
                code = str(body.get('code', '')).replace('-', '').strip().upper()
                if len(code) != 8 or not all(c in '0123456789ABCDEF' for c in code):
                    raise ValueError('Informe seu nick e PIN cadastrados em Meu PC no site.')
                path, claim = '/api/companion/claim', {'code':code,'name':__import__('platform').node()}
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                result = await client.post(relay + path, json=claim)
                if result.status_code != 200:
                    raise ValueError('O site recusou o vínculo. Confira nick e PIN; após muitas tentativas, aguarde 15 minutos.')
                data = result.json()
                if not isinstance(data.get('token'), str) or not isinstance(data.get('device_id'), str):
                    raise ValueError('Resposta de vínculo inválida.')
            await connection.permission(False)
            config.update(relay=relay, token=data['token'], device_id=data['device_id'])
            if data.get('nick'):
                config['nick'] = data['nick']
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
        text = str(body.get('text', ''))[:2000].strip()
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
        if ai.status()['enabled']:
            try:
                return await ai.chat(text)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
        return {'reply': 'Posso consultar CPU/RAM/disco, buscar arquivos e diagnosticar a conexão. Para conversar com um modelo, configure seu provedor na aba IA.', 'page':'ai'}

    app.mount('/assets', StaticFiles(directory=WEB), name='assets')
    return app
