"""Loopback-only authenticated desktop dashboard with reviewed local actions."""
import asyncio
import json
import os
import re
import subprocess
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
from .files import Files, installed_apps, referenced_local_paths, fingerprint, analyze_local_paths
from .projects import Projects
from . import __version__
from .capabilities import FEATURES, copilot_guide
from .system_audit import collect as collect_system_audit, report as system_audit_report

WEB = Path(__file__).parent / 'web'


def data_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'VexxPC'


def set_login_startup(enabled):
    if os.name!='nt':return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if not enabled:
            try:winreg.DeleteValue(key,'VexxPC')
            except FileNotFoundError:pass
            return
        try:record=json.loads((Path(__file__).resolve().parents[1]/'installation.json').read_text('utf-8'))
        except (OSError,ValueError) as exc:raise ValueError('Esta instalação não tem um iniciador estável para o login.') from exc
        root=Path(record.get('install_root','')).resolve();launcher=root/'launch.py'
        pythonw=root/'runtime'/'pythonw.exe'
        if not launcher.is_file() or not pythonw.is_file():raise ValueError('O iniciador do Vexx PC não está instalado em um caminho estável.')
        winreg.SetValueEx(key,'VexxPC',0,winreg.REG_SZ,f'"{pythonw}" "{launcher}" --start-hidden')


def requested_wifi_ssid(text):
    quoted=re.search(r'["“]([^"”\r\n]{1,32})["”]',text)
    if quoted:return quoted.group(1).strip()
    match=re.search(r'(?i)(?:wi[\s-]?fi|rede)(?:\s+(?:chamada|com nome|de nome))?\s+(.+)$',text.strip())
    if not match:return ''
    value=match.group(1).strip().rstrip('.,;:!?')
    value=re.sub(r'(?i)^(?:da|do|de)\s+','',value)
    value=re.sub(r'(?i)\s+(?:por favor|agora|para mim)$','',value).strip()
    return value[:32] if value else ''


def asks_for_system_audit(text):
    explicit=('auditoria','audite','analise completa','diagnostico completo','diagnostico geral',
              'analise o sistema','analise meu pc','analise meu computador','verifique meu computador','avalie o sistema')
    if any(term in text for term in explicit):return True
    action=any(term in text for term in ('analis','verifique','avalie','diagnost','revise','mostre','liste'))
    scope=any(term in text for term in ('sistema','computador',' pc','tudo','geral','configur','lixeira','nuvem'))
    return action and scope and any(term in text for term in ('complet','inteir','tudo','arquivo','pasta','configur','lixeira','nuvem','espaco','memoria'))


def asks_for_cleanup(text):
    target=any(term in text for term in ('arquivo','pasta','app','aplicativo','programa','disco','espaco','computador',' pc','hd','ssd'))
    action=any(term in text for term in ('exclu','apag','remov','liber','limp','inutil','desnecess','nao uso','ocupando muito','pesado'))
    question=any(term in text for term in ('o que posso','o que da para','o que dá para','tem algum','quais'))
    return target and (action or question and any(term in text for term in ('espaco','arquivo','app','programa','inutil','pesado')))


def default_roots():
    import psutil
    if os.name == 'nt':
        return [p.mountpoint for p in psutil.disk_partitions() if 'fixed' in p.opts and not p.mountpoint.startswith('\\\\')]
    return [str(Path.home())]


def terminate_process(pid,created):
    import psutil
    try:
        pid=int(pid);process=psutil.Process(pid)
        if pid in (0,4,os.getpid()) or abs(process.create_time()-float(created))>.01:raise ValueError('O processo mudou desde a análise.')
        name=process.name().casefold();exe=Path(process.exe()).resolve() if process.exe() else None
        windows=Path(os.environ.get('WINDIR','C:/Windows')).resolve()
        protected={'system','registry','memory compression','idle','system interrupts','csrss.exe','wininit.exe','services.exe','lsass.exe','smss.exe','winlogon.exe'}
        if (exe and exe.is_relative_to(windows)) or name in protected:raise ValueError('Este processo do Windows é protegido.')
        process.terminate()
        try:process.wait(3)
        except psutil.TimeoutExpired:raise ValueError('O processo não encerrou no prazo.') from None
        return True
    except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess):
        raise ValueError('O processo não está disponível ou não pode ser encerrado.') from None


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

    connection = Connection(config, save, log, set_login_startup)
    ai = AI(directory)
    files = Files(directory,index)
    projects = Projects(directory,index.roots)
    command_reviews={}
    apps_cache={'at':0,'items':[]}
    system_audits={}
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
                limit=160000 if request.url.path=='/api/copilot' else 65536 if request.url.path=='/api/files/prepare' else 8192
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

    @app.get('/api/recommendations')
    async def recommendations():
        result=await asyncio.to_thread(index.search,'',0,'files','largest')
        largest=[item for item in result['items'] if not item.get('directory') and files.removable(item['path'])][:5]
        if os.name=='nt' and time.monotonic()-apps_cache['at']>120:
            catalog=await asyncio.to_thread(installed_apps)
            apps_cache.update(at=time.monotonic(),items=catalog['items'] if catalog['supported'] else [])
        apps=[item for item in apps_cache['items'] if item['size']>=1024**3][:3]
        return {'files':largest,'apps':apps,'sampled_at':time.time()}

    @app.post('/api/system/apply')
    async def system_apply(request: Request):
        body=await payload(request);audit_id=str(body.get('audit_id',''));selected=body.get('items')
        audit=system_audits.get(audit_id)
        if not audit or audit['expires']<time.monotonic():raise HTTPException(400,'A auditoria expirou. Faça uma nova análise.')
        if not isinstance(selected,list) or not 1<=len(selected)<=15 or not all(isinstance(x,str) for x in selected):raise HTTPException(400,'Selecione de 1 a 15 ações da auditoria.')
        actions=audit['actions'];chosen=[actions[x] for x in dict.fromkeys(selected) if x in actions]
        if len(chosen)!=len(set(selected)):raise HTTPException(400,'Uma ação mudou desde a auditoria. Analise o sistema novamente.')
        done=[];failed=[];file_actions=[]
        for item in (x for x in chosen if x['kind']=='file'):
            try:
                path=files.paths.check(item['path'],write=True)
                if not files.removable(str(path)) or fingerprint(path)!=item['fingerprint']:
                    raise ValueError('O arquivo foi alterado ou é protegido; faça outra análise.')
                file_actions.append(item)
            except (OSError,ValueError) as exc:failed.append({'name':item['name'],'error':str(exc)})
        if file_actions:
            try:
                plan=await asyncio.to_thread(files.prepare,'trash',[x['path'] for x in file_actions])
                result=await asyncio.to_thread(files.execute,plan['token'],'')
                done.extend({'name':Path(p).name,'action':'movido para a Lixeira Vexx'} for p in result['done'])
                failed.extend({'name':Path(x['path']).name,'error':'Não foi possível mover para a Lixeira Vexx.'} for x in result['failed'])
            except ValueError as exc:failed.extend({'name':x['name'],'error':str(exc)} for x in file_actions)
        for item in (x for x in chosen if x['kind']=='process'):
            for process in item.get('processes',[]):
                try:
                    await asyncio.to_thread(terminate_process,process['pid'],process['created'])
                    done.append({'name':item['name'],'action':'processo encerrado'})
                except (ValueError,OSError) as exc:failed.append({'name':item['name'],'error':str(exc)})
        system_audits.pop(audit_id,None)
        if done:log('Plano da auditoria aplicado · '+str(len(done))+' ação(ões) concluídas · '+str(len(failed))+' pendentes.')
        return {'done':done,'failed':failed}

    @app.post('/api/system/open-settings')
    async def system_open_settings(request: Request):
        body=await payload(request);setting=str(body.get('setting',''))
        targets={'storage':'ms-settings:storage','startup':'ms-settings:startupapps','apps':'ms-settings:appsfeatures',
                 'power':'ms-settings:powersleep','network':'ms-settings:network-status','wifi':'ms-settings:network-wifi',
                 'windows-trash':'shell:RecycleBinFolder'}
        if os.name!='nt' or setting not in targets:raise HTTPException(400,'Esta página de configurações não está disponível neste sistema.')
        if setting=='windows-trash':await asyncio.to_thread(subprocess.Popen,['explorer.exe','shell:RecycleBinFolder'])
        else:await asyncio.to_thread(os.startfile,targets[setting])
        return {'ok':True}

    @app.post('/api/network/wifi/connect')
    async def wifi_connect(request: Request):
        body=await payload(request);ssid=str(body.get('ssid','')).strip()
        if os.name!='nt':raise HTTPException(400,'A conexão Wi-Fi está disponível no Windows.')
        if not 1<=len(ssid)<=32 or any(ord(char)<32 for char in ssid):raise HTTPException(400,'Nome de rede Wi-Fi inválido.')
        try:
            result=await asyncio.to_thread(subprocess.run,['netsh','wlan','connect','name='+ssid,'ssid='+ssid],
                capture_output=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError,subprocess.TimeoutExpired):return {'ok':False,'saved_profile':False}
        return {'ok':result.returncode==0,'saved_profile':result.returncode==0}
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

    @app.post('/api/process/stop')
    async def stop_process(request: Request):
        body=await payload(request)
        try:return await asyncio.to_thread(terminate_process,body.get('pid',0),body.get('created',0))
        except ValueError as exc:raise HTTPException(400,str(exc)) from None

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
            app.state.exiting=True
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

    async def create_system_audit():
        now=time.monotonic()
        if now-apps_cache['at']>120:
            catalog=await asyncio.to_thread(installed_apps)
            apps_cache.update(at=now,items=catalog['items'] if catalog['supported'] else [])
        sample=state['system'] or await asyncio.to_thread(monitor.snapshot)
        audit=await asyncio.to_thread(collect_system_audit,index,files,sample,apps_cache['items'])
        audit_id=secrets.token_urlsafe(18)
        actions=audit['files']+audit['processes']
        audit['suggestions']=[{key:value for key,value in item.items() if key!='fingerprint'} for item in actions]
        system_audits.clear()
        system_audits[audit_id]={'expires':now+600,'actions':{item['id']:item for item in actions}}
        return {'reply':system_audit_report(audit),'audit':audit,'audit_id':audit_id}

    @app.post('/api/copilot')
    async def copilot(request: Request):
        body = await payload(request)
        provider_analysis=body.get('provider_analysis') is True
        text = str(body.get('text', ''))[:30000 if provider_analysis else 2000].strip()
        normalized = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
        if provider_analysis:
            if not ai.status()['enabled']:raise HTTPException(400,'Configure uma IA antes de enviar a auditoria.')
            try:return await ai.chat(text)
            except ValueError as exc:raise HTTPException(400,str(exc)) from None
        attachments=body.get('paths',[]);uploaded=body.get('attachments',[])
        if not isinstance(uploaded,list) or len(uploaded)>10 or any(not isinstance(f,dict) or len(str(f.get('text','')))>12000 for f in uploaded):raise HTTPException(400,'Anexos de texto inválidos.')
        if uploaded:text+='\n\nArquivos anexados pelo usuário:\n'+'\n'.join('### '+str(f.get('name','arquivo'))+'\n'+str(f.get('text','')) for f in uploaded)
        if not isinstance(attachments,list) or len(attachments)>10 or not all(isinstance(p,str) for p in attachments):raise HTTPException(400,'Anexe até 10 caminhos locais.')
        attachments=referenced_local_paths(files,text,attachments)
        cleanup_intent=asks_for_cleanup(normalized)
        delete_action=bool(re.search(r'\b(?:exclua|apague|delete|remova|mova para a lixeira)\b',normalized))
        audit_request=normalized.startswith(('!auditar','!auditoria')) or asks_for_system_audit(normalized)
        if audit_request:return await create_system_audit()
        if cleanup_intent and not attachments:
            result=await create_system_audit()
            result['reply']='Vou listar candidatos reais que podem ser revisados para liberar espaço. Nada será alterado até você selecionar itens e confirmar.\n\n'+result['reply']
            return result
        if attachments and delete_action:
            try:
                paths=[files.paths.check(path) for path in attachments]
                if any(not path.is_file() for path in paths):raise ValueError('A exclusão em lote aceita arquivos individuais; pastas não são removidas recursivamente.')
            except (OSError,ValueError) as exc:raise HTTPException(400,str(exc)) from None
            return {'reply':'Abri uma revisão com os caminhos selecionados. Confira os nomes e tamanhos; só serão movidos à Lixeira Vexx se você confirmar.','file_review':[str(path) for path in paths]}
        if any(term in normalized for term in ('o que voce pode fazer','o que o aplicativo faz','o que faz o vexx pc','quais abas','quais funcoes','suas funcoes','quais funcionalidades','suas habilidades','suas capacidades','como voce funciona','conhece o vexx pc')):
            return {'reply':copilot_guide()}
        if re.search(r'\b(?:conecte|conectar|conecta|entre na rede)\b',normalized) and any(net in normalized for net in ('wifi','wi-fi','rede')):
            ssid=requested_wifi_ssid(text)
            if not ssid:return {'reply':'Abrirei as configurações de Wi-Fi para você escolher a rede e, se necessário, informar a senha diretamente ao Windows.','page':'network','open_wifi_settings':True}
            return {'reply':'Vou pedir ao Windows para conectar ao perfil Wi-Fi salvo “'+ssid+'”. Confirme para continuar; nenhuma senha será enviada ao Copiloto.','confirmation_action':'connect_wifi','ssid':ssid}
        if 'permanente' in normalized and any(word in normalized for word in ('controle','mouse','teclado','remoto')) and any(word in normalized for word in ('ativ','permit','inici','liber','habil','quero','ligue','ligar')):
            if not config.get('token') or not config.get('device_id'):
                return {'reply':'Vincule este computador primeiro usando o nick e PIN de Meu PC. Depois posso solicitar a autorização permanente.','page':'overview'}
            if connection.status()['permanent_control']:
                return {'reply':'O controle permanente já está ativo para o PC vinculado e configurado para iniciar oculto ao entrar no Windows. Você pode revogá-lo em Visão geral.','page':'overview'}
            return {'reply':'Posso ativar o controle de tela, mouse e teclado para o PC vinculado e configurar o Vexx PC para iniciar oculto no login do Windows. Confirme a autorização. Você pode revogá-la no painel ou no site.','confirmation_action':'permanent_control'}
        if 'permanente' in normalized and any(word in normalized for word in ('controle','mouse','teclado','remoto')) and any(word in normalized for word in ('revog','desativ','paus','deslig','remov')):
            if not connection.status()['permanent_control']:return {'reply':'Não há controle permanente ativo para revogar.','page':'overview'}
            return {'reply':'Vou revogar a autorização permanente e remover o início automático do Vexx PC. Confirme para continuar.','confirmation_action':'revoke_permanent_control'}
        if 'controle permanente' in normalized and any(word in normalized for word in ('esta ativo','esta ligado','status','funciona')):
            return {'reply':'Controle permanente: '+('ativo e configurado para iniciar no login do Windows.' if connection.status()['permanent_control'] else 'inativo. Você pode pedir para ativar; o Vexx solicitará confirmação local.'),'page':'overview'}
        if any(term in normalized for term in ('abra a aba','abra a guia','navegue para','va para','ir para','mostre a aba','abra o painel')):
            aliases={'overview':('visao geral','inicio'),'pc':('arquivo','pasta'),'cleaner':('limpeza','lixeira'),
                     'projects':('projeto',),'network':('rede','wifi','wi-fi'),'logs':('log',),'ai':('copiloto','ia')}
            for item in FEATURES:
                page=item['page'];terms=aliases.get(page,())
                if any(term in normalized for term in terms):return {'reply':'Abrindo '+dict(overview='Visão geral',pc='Arquivos',cleaner='Limpeza',projects='Projetos',network='Rede',logs='Logs',ai='Copiloto')[page]+'.','page':page}
        search_intent=any(term in normalized for term in ('busque','buscar','pesquise','pesquisar','procure','procurar','encontre','localize','ache','onde esta','onde fica'))
        if search_intent and any(term in normalized for term in ('arquivo','pasta','documento','imagem','foto','video','app','programa')):
            query=re.sub(r'(?i)^\s*(?:por favor\s+)?(?:busque|buscar|pesquise|pesquisar|procure|procurar|encontre|localize|ache|onde está|onde esta|onde fica)\s+','',text).strip()
            query=re.sub(r'(?i)^(?:o|a|um|uma)\s+(?:arquivo|pasta|documento|imagem|foto|vídeo|video|app|programa)\s+(?:chamado\s+|chamada\s+|com nome\s+)?','',query).strip(' .?!')
            if len(query)<3:return {'reply':'Digite pelo menos três caracteres do nome ou caminho para pesquisar no índice local.','page':'pc'}
            result=await asyncio.to_thread(index.search,query)
            return {'reply':f"Encontrei até {len(result['items'])} correspondências para “{query}” no índice local. Abri Arquivos para você revisar os caminhos.",'search':query}
        if attachments:
            try:analysis=await asyncio.to_thread(analyze_local_paths,files,attachments,True)
            except ValueError as exc:raise HTTPException(400,str(exc)) from None
            return {'reply':analysis,'attachments':len(attachments),'local_analysis':analysis[:50000],
                    'needs_provider_analysis':ai.status()['enabled']}
        if normalized.startswith('!confirmar '):
            review=text.split(' ',1)[1].strip();entry=command_reviews.pop(review,None)
            if not entry or entry['expires']<time.monotonic():raise HTTPException(400,'A revisão expirou. Prepare o comando novamente.')
            command=entry['command']
            args=['shutdown.exe',*command.split()[1:]] if command.startswith('shutdown ') else ['cmd.exe','/d','/s','/c',command]
            try:process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=str(Path.home()),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except OSError:raise HTTPException(400,'O Windows não conseguiu iniciar o comando.') from None
            return {'reply':'Comando iniciado após sua confirmação. Processo '+str(process.pid)+'.'}
        if normalized.startswith('!cmd '):
            command=text[5:].strip()
            if os.name!='nt':raise HTTPException(400,'Comandos CMD estão disponíveis apenas no Windows.')
            if not command or len(command)>2000 or '\x00' in command:raise HTTPException(400,'Comando inválido ou muito longo.')
            command_reviews.clear();review=secrets.token_urlsafe(24);command_reviews[review]={'command':command,'expires':time.monotonic()+300}
            return {'reply':'Revise o comando completo. Ele será executado como seu usuário do Windows e pode alterar arquivos ou configurações.','command_preview':command,'confirmation':review}
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
        if re.search(r'deslig\w*',normalized) and ('computador' in normalized or 'pc' in normalized):
            match=re.search(r'(\d+)\s*(minutos|minuto|min|horas|hora)',normalized)
            if match:
                seconds=int(match.group(1))* (3600 if 'hora' in match.group(2) else 60)
                if seconds>604800:raise HTTPException(400,'O agendamento aceita no máximo sete dias.')
                command=f'shutdown /s /t {seconds}';review=secrets.token_urlsafe(24);command_reviews[review]={'command':command,'expires':time.monotonic()+300}
                return {'reply':f"Vou agendar o desligamento do computador em {match.group(1)} {match.group(2)}. Revise e confirme para prosseguir.",'command_preview':command,'confirmation':review}
        status_request=any(word in normalized for word in ('status','memoria','ram','cpu','disco')) or bool(re.search(r'\bcomo (?:esta|está) (?:o )?(?:computador|pc)\b',normalized))
        if status_request:
            s = state['system']
            if not s:
                return {'reply': 'Aguardando a primeira amostra dos sensores.'}
            return {'reply': f"CPU: {s['cpu_percent']}%. RAM: {s['ram']['percent']}%. Ligado há {int(s['uptime']//60)} minutos. "
                    f"Índice: {index.count} entradas. Rede Wi-Fi: {s.get('ssid') or 'não conectada ou não detectada'}. "
                    f"Acesso remoto: {'autorizado' if connection.status()['approved'] else 'pausado'}.", 'page': 'overview'}
        if ai.status()['enabled']:
            try:
                return await ai.chat(text)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
        return {'reply': 'Posso analisar arquivos e pastas deste PC, consultar recursos e sugerir ações. Para outros comandos, escreva !cmd seguido do comando completo; vou mostrar exatamente o que será executado para você revisar e confirmar.', 'page':'ai'}

    app.mount('/assets', StaticFiles(directory=WEB), name='assets')
    return app
