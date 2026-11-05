"""Reviewed project plans, project-owned environments and process trees. No shell interpolation."""
import ast
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import quote

import httpx
import psutil
from .files import Paths
from .process_group import ProcessGroup, windows_listener_pids

FOLDERS=('backend','server','api','frontend','client','web','src')
ENTRIES=('main.py','app.py','server.py','manage.py')


def free_port(preferred=0):
    try:
        with socket.socket() as sock:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            sock.bind(('127.0.0.1',preferred));return sock.getsockname()[1]
    except OSError:
        raise ValueError('A porta local '+str(preferred)+' está ocupada ou indisponível. Nenhum processo existente será encerrado.') from None


def npm_command():
    node,npm=shutil.which('node'),shutil.which('npm')
    cli=Path(npm).parent/'node_modules/npm/bin/npm-cli.js' if npm else Path('/missing-npm')
    if npm and Path(npm).resolve().suffix=='.js':cli=Path(npm).resolve()
    if not cli.is_file() and node:cli=Path(node).resolve().parent/'node_modules/npm/bin/npm-cli.js'
    return [node,str(cli)] if node and cli.is_file() else []


def read(path):
    if path.stat().st_size>262144:raise ValueError('Um manifesto ou arquivo de entrada é grande demais para análise automática.')
    return path.read_text('utf-8-sig')


class Projects:
    def __init__(self, directory, roots):
        self.directory=Path(directory);self.paths=Paths(roots)
        self.plans={};self.runs={};self.guard=threading.RLock()

    def inspect(self, value):
        path=self.paths.check(value)
        root=path if path.is_dir() else path.parent
        if root==Path(root.anchor) or root==Path.home():raise ValueError('Escolha a pasta específica de um projeto.')
        if root.name.casefold() in FOLDERS and (any((root.parent/d/'package.json').is_file() for d in ('frontend','client','web')) or (root.parent/'vexx-project.json').is_file()):root=root.parent
        sources={};services=[];blockers=[];warnings=[]
        def content(file):
            checked=self.paths.check(str(file));text=read(checked);sources[str(checked)]=hashlib.sha256(text.encode()).hexdigest();return text
        config=root/'vexx-project.json'
        if config.is_file():
            data=json.loads(content(config))
            if not isinstance(data,dict) or not isinstance(data.get('services'),list) or not 1<=len(data['services'])<=8:raise ValueError('vexx-project.json precisa de 1 a 8 serviços.')
            for item in data['services']:
                if not isinstance(item,dict):raise ValueError('Serviço inválido.')
                cwd=self.paths.check(str(root/str(item.get('cwd','.'))))
                if not cwd.is_dir() or not cwd.is_relative_to(root):raise ValueError('Cada serviço deve ficar dentro do projeto.')
                command=item.get('command')
                if not isinstance(command,list) or not 1<=len(command)<=40 or not all(isinstance(s,str) and s and len(s)<2000 and '\x00' not in s for s in command):raise ValueError('Comandos precisam ser listas de argumentos.')
                if command[0] in ('npm','npm.cmd'):
                    npm=npm_command()
                    if not npm:blockers.append('Node.js com npm indisponível.')
                    else:command=[*npm,*command[1:]]
                if command[0] in ('python','python3'):command=[sys.executable,*command[1:]]
                exe=Path(command[0]);resolved=str(exe) if exe.is_absolute() and exe.is_file() else shutil.which(command[0])
                if not resolved or Path(resolved).suffix.casefold() in ('.cmd','.bat','.ps1') or Path(resolved).stem.casefold() in ('cmd','powershell','pwsh','sh','bash'):
                    blockers.append('Executável indisponível ou shell genérico não permitido: '+command[0]);resolved=command[0]
                port=item.get('port',0)
                if type(port) is not int:raise ValueError('Porta precisa ser um número inteiro.')
                if port and not 1024<=port<=65535:raise ValueError('Use uma porta local de 1024 a 65535.')
                services.append({'name':str(item.get('name','Serviço'))[:80],'cwd':str(cwd),'command':[resolved,*command[1:]],'port':port,'kind':'custom','prepare':[]})
            warnings.append('Os serviços do manifesto serão iniciados na ordem declarada; revise os comandos e portas.')
        else:
            directories=[root,*[root/name for name in FOLDERS if (root/name).is_dir()]]
            node=[];python=[]
            for folder in directories:
                manifest=folder/'package.json'
                if manifest.is_file():
                    data=json.loads(content(manifest))
                    if not isinstance(data,dict) or not isinstance(data.get('scripts',{}),dict):raise ValueError('package.json precisa conter um objeto de scripts válido.')
                    scripts=data.get('scripts',{})
                    script='dev' if scripts.get('dev') else 'start' if scripts.get('start') else ''
                    if script and not isinstance(scripts[script],str):raise ValueError('O script de início precisa ser texto.')
                    if script:node.append((folder,script,str(scripts[script])))
                candidates=[path] if path.is_file() and path.suffix=='.py' and path.parent==folder else [folder/name for name in ENTRIES if (folder/name).is_file()]
                if candidates:python.append(candidates[0])
            if len(python)>1:
                selected=[p for p in python if p==path]
                if selected:python=selected
                else:blockers.append('Há várias entradas Python. Abra o arquivo desejado ou defina vexx-project.json.');python=[]
            if len(node)>1:
                selected=[p for p in node if p[0]==path.parent or p[0]==path]
                if selected:node=selected
                else:blockers.append('Há várias interfaces Node. Defina a ordem em vexx-project.json.');node=[]
            proxy_ports=set()
            for folder,_,_ in node:
                for name in ('vite.config.js','vite.config.ts','vite.config.mjs'):
                    file=folder/name
                    if file.is_file():
                        proxy_ports.update(int(p) for p in re.findall(r'''target\s*:\s*['"]http://(?:127\.0\.0\.1|localhost):(\d+)''',content(file)))
            if len(proxy_ports)>1 and python:blockers.append('Há vários destinos de proxy. Defina as portas no manifesto do projeto.')
            for entry in python:
                code=content(entry)
                try:tree=ast.parse(code)
                except SyntaxError:raise ValueError('A entrada Python tem erro de sintaxe.') from None
                app=None;kind='python'
                for stmt in tree.body:
                    if isinstance(stmt,ast.Assign) and isinstance(stmt.value,ast.Call):
                        call=stmt.value.func;name=call.id if isinstance(call,ast.Name) else call.attr if isinstance(call,ast.Attribute) else ''
                        if name in ('FastAPI','Flask') and isinstance(stmt.targets[0],ast.Name):app=stmt.targets[0].id;kind=name.lower()
                if entry.name=='manage.py' and 'django' in code:kind='django'
                folder=entry.parent;venv=folder/'.vexx-venv';exe=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
                if venv.exists():self.paths.check(str(venv))
                port=free_port(next(iter(proxy_ports)) if len(proxy_ports)==1 else 0) if kind!='python' else 0
                target=entry.stem+':'+app if app else ''
                command=([str(exe),'-m','uvicorn',target,'--host','127.0.0.1','--port',str(port)] if kind=='fastapi' else
                         [str(exe),'-m','flask','--app',target,'run','--host','127.0.0.1','--port',str(port)] if kind=='flask' else
                         [str(exe),str(entry),'runserver','127.0.0.1:'+str(port),'--noreload'] if kind=='django' else [str(exe),str(entry)])
                prepare=[]
                if not exe.is_file():prepare.append([sys.executable,'-m','venv',str(venv)])
                requirements=next((p for p in (folder/'requirements.txt',root/'requirements.txt') if p.is_file()),None)
                if requirements:
                    content(requirements);prepare.append([str(exe),'-m','pip','install','--disable-pip-version-check','-r',str(requirements)])
                elif kind in ('fastapi','flask','django'):
                    prepare.append([str(exe),'-m','pip','install','--disable-pip-version-check',*({'fastapi':['fastapi','uvicorn'],'flask':['flask'],'django':['django']}[kind])])
                if (folder/'pyproject.toml').is_file() and not requirements:
                    import tomllib
                    metadata=tomllib.loads(content(folder/'pyproject.toml'))
                    if metadata.get('project') or metadata.get('build-system'):
                        prepare.append([str(exe),'-m','pip','install','--disable-pip-version-check','-e',str(folder)])
                    if metadata.get('project',{}).get('requires-python'):warnings.append('Python requerido: '+metadata['project']['requires-python']+'. O ambiente usa a versão do Python incluído no Vexx PC.')
                receipt=venv/'vexx-ready.json'
                # The first venv creation command is not part of the stable dependency receipt.
                recipe=hashlib.sha256(json.dumps({'commands':[c for c in prepare if 'venv' not in c],'sources':sources},sort_keys=True).encode()).hexdigest()
                try:
                    if exe.is_file() and json.loads(receipt.read_text('utf-8')).get('recipe')==recipe:prepare=[]
                except (OSError,ValueError):pass
                services.append({'name':entry.name,'cwd':str(folder),'command':command,'port':port,'kind':kind,'prepare':prepare})
                services[-1].update(receipt=str(receipt),recipe=recipe)
            for folder,script,declared in node:
                npm=npm_command()
                if not npm:blockers.append('Instale Node.js com npm para iniciar '+folder.name+'.');npm=['node','npm-cli.js']
                vite=bool(re.match(r'^(?:npx\s+)?vite(?:\s|$)',declared))
                port=free_port() if vite else 0
                command=[*npm,'run',script,*(['--','--host','127.0.0.1','--port',str(port),'--strictPort'] if vite else [])]
                lock=folder/'package-lock.json'
                if lock.is_file():content(lock)
                prepare=[] if (folder/'node_modules').is_dir() else [[*npm,'ci' if lock.is_file() else 'install']]
                services.append({'name':folder.name+' / npm '+script,'cwd':str(folder),'command':command,'port':port,'kind':'node','prepare':prepare,'script':declared})
            if not services and path.is_file() and path.suffix.casefold() in ('.js','.mjs','.cjs'):
                content(path);node=shutil.which('node')
                if not node:blockers.append('Instale Node.js para iniciar este arquivo.')
                services.append({'name':path.name,'cwd':str(root),'command':[node or 'node',str(path)],'port':0,'kind':'node','prepare':[]})
            if not services:
                html=path if path.is_file() and path.suffix.casefold() in ('.html','.htm') else next((p for p in (root/'index.html',root/'public/index.html') if p.is_file()),None)
                if html:
                    content(html);port=free_port();nonce=secrets.token_hex(16)
                    services.append({'name':html.name,'cwd':str(root),'command':[sys.executable,str(Path(__file__).with_name('project_host.py')),'--root',str(root),'--port',str(port),'--nonce',nonce],
                                     'port':port,'kind':'static','nonce':nonce,'page':'/'+quote(str(html.relative_to(root)).replace('\\','/')),'prepare':[]})
            if not services and not blockers:blockers.append('Não encontrei uma entrada suportada. Escolha main.py, app.py, index.html, package.json ou crie vexx-project.json.')
        now=time.monotonic();token=secrets.token_urlsafe(24)
        with self.guard:
            self.plans={k:v for k,v in self.plans.items() if v['until']>now}
            if len(self.plans)>=8:raise ValueError('Aguarde ou reutilize um plano recente.')
            self.plans[token]={'root':str(root),'sources':sources,'services':services,'until':now+300,'blockers':blockers}
        return {'token':token,'root':str(root),'services':services,'blockers':blockers,'warnings':warnings,
                'notice':'Projetos e instalações executam código do projeto e de dependências. Inicie apenas projetos em que você confia.'}

    def start(self, token, prepare=False):
        with self.guard:
            plan=self.plans.get(token)
            if not plan or plan['until']<time.monotonic():raise ValueError('O plano expirou. Analise a pasta novamente.')
            if plan['blockers']:raise ValueError('Resolva as pendências antes de iniciar.')
            if len([r for r in self.runs.values() if r['state'] in ('preparing','starting','running')])>=3:raise ValueError('Já há três projetos ativos. Pare um antes de iniciar outro.')
            for name,digest in plan['sources'].items():
                if hashlib.sha256(read(self.paths.check(name)).encode()).hexdigest()!=digest:raise ValueError('O projeto mudou desde a análise. Revise um novo plano.')
            if any(s['prepare'] for s in plan['services']) and not prepare:raise ValueError('Este plano precisa da autorização para preparar dependências.')
            self.plans.pop(token)
            history=[key for key,run in self.runs.items() if run['state'] in ('failed','stopped','completed')]
            for key in history[:-17]:self.runs.pop(key,None)
            identity=uuid.uuid4().hex;run={'id':identity,'root':plan['root'],'state':'preparing','services':[], 'logs':deque(maxlen=300),'urls':{},'stop':threading.Event(),'processes':[],'created':time.time(),'group':ProcessGroup()}
            self.runs[identity]=run
            threading.Thread(target=self._run,args=(run,plan,prepare),name='vexx-project-'+identity[:6],daemon=True).start()
            return {'id':identity}

    def _spawn(self, run, command, cwd, environment):
        if run['stop'].is_set():raise ValueError('Início cancelado.')
        child=subprocess.Popen(command,cwd=cwd,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               creationflags=(subprocess.CREATE_NO_WINDOW|0x00000004) if os.name=='nt' else 0)
        try:
            run['group'].attach(child.pid)
            if os.name=='nt':psutil.Process(child.pid).resume()
        except Exception:
            child.terminate();child.wait(timeout=5);raise
        run['processes'].append((child,psutil.Process(child.pid).create_time()))
        def output():
            for line in iter(lambda:child.stdout.readline(4096),b''):
                text=line[:2000].decode('utf-8',errors='replace').rstrip();run['logs'].append(text)
                for url in re.findall(r'https?://(?:localhost|127\.0\.0\.1):\d{2,5}(?:/[^\s\x1b]*)?',text):
                    run['urls'].setdefault(child.pid,deque(maxlen=8)).append(url.rstrip('.,)'))
        threading.Thread(target=output,name='vexx-project-output',daemon=True).start()
        return child

    def _owned_listener(self, run, child, port):
        if os.name=='nt':
            if not set(run['group'].pids()).intersection(windows_listener_pids(port)):return False
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.3):return True
            except OSError:return False
        else:owned=[psutil.Process(child.pid),*psutil.Process(child.pid).children(recursive=True)]
        for process in owned:
            try:
                if any(c.status==psutil.CONN_LISTEN and c.laddr.port==port for c in process.net_connections(kind='tcp')):return True
            except (psutil.AccessDenied,psutil.NoSuchProcess):continue
        return False

    def _run(self, run, plan, prepare):
        try:
            backend=next(('http://127.0.0.1:'+str(s['port']) for s in plan['services'] if s['kind'] in ('fastapi','flask','django')),None)
            for service in plan['services']:
                cwd=self.paths.check(service['cwd']);environment=os.environ.copy()
                if backend and service['kind']=='node':
                    for key in ('VITE_API_URL','VITE_API_BASE_URL','NEXT_PUBLIC_API_URL','API_URL'):environment[key]=backend
                environment['PYTHONUNBUFFERED']='1'
                if prepare:
                    for command in service['prepare']:
                        run['logs'].append('Preparando: '+subprocess.list2cmdline(command))
                        # Keep unrelated broken PATH junctions out of Python's pip bootstrap.
                        install_env=environment.copy()
                        if os.name=='nt' and '-m' in command:
                            windows=Path(environment.get('SystemRoot','C:/Windows'))
                            install_env['PATH']=os.pathsep.join(map(str,(Path(command[0]).parent,windows/'System32',windows)))
                        process=self._spawn(run,command,cwd,install_env)
                        deadline=time.monotonic()+600
                        while process.poll() is None and time.monotonic()<deadline:
                            if run['stop'].wait(.2):raise ValueError('Preparação cancelada.')
                        if process.poll()!=0:raise ValueError('A preparação das dependências falhou ou excedeu o tempo. Confira os logs.')
                    if service.get('receipt'):
                        Path(service['receipt']).write_text(json.dumps({'recipe':service['recipe']}),'utf-8')
                run['state']='starting'
                if service['port']:free_port(service['port'])  # Fresh check; no adoption of a foreign listener.
                run['logs'].append('Iniciando: '+subprocess.list2cmdline(service['command']))
                process=self._spawn(run,service['command'],cwd,environment)
                status={'name':service['name'],'pid':process.pid,'url':'','state':'starting'};run['services'].append(status)
                if service['port']:
                    deadline=time.monotonic()+60;url='http://127.0.0.1:'+str(service['port'])
                    while time.monotonic()<deadline:
                        if run['stop'].wait(.2):raise ValueError('Início cancelado.')
                        try:
                            if service['kind']=='static':
                                data=httpx.get(url+'/_vexx_health',timeout=1,trust_env=False).json()
                                ready=data.get('nonce')==service['nonce'] and data.get('pid') in {process.pid,*(p.pid for p in psutil.Process(process.pid).children(recursive=True))}
                            else:ready=self._owned_listener(run,process,service['port'])
                            if ready:break
                        except (OSError,ValueError,psutil.Error,httpx.HTTPError):pass
                    else:raise ValueError('O serviço não confirmou uma porta própria. Confira os logs e o ambiente.')
                    status['url']=url+service.get('page','/')
                else:
                    if run['stop'].wait(.6):raise ValueError('Início cancelado.')
                    if process.poll() not in (None,0):raise ValueError('O programa encerrou com erro durante o início. Confira os logs.')
                status['state']='completed' if not service['port'] and process.poll()==0 else 'running'
            run['state']='running'
            while not run['stop'].wait(.5):
                service_by_pid={s['pid']:s for s in run['services']}
                for child,_ in run['processes']:
                    if child.pid not in service_by_pid:continue
                    status=service_by_pid[child.pid]
                    if child.poll() not in (None,0):raise ValueError('Um serviço encerrou com erro. O grupo foi parado para evitar dependências órfãs.')
                    if child.poll()==0 and not status['url']:status['state']='completed'
                    if not status['url']:
                        from urllib.parse import urlsplit
                        for url in reversed(list(run['urls'].get(child.pid,[]))):
                            if self._owned_listener(run,child,urlsplit(url).port):
                                status['url']=url;status['state']='running';break
                if all(child.poll() is not None for child,_ in run['processes']) and not run['group'].pids():
                    run['state']='completed';return
        except Exception as exc:
            run['logs'].append(str(exc) if isinstance(exc,ValueError) else 'Falha ao iniciar: '+type(exc).__name__)
            run['state']='failed'
        finally:
            self._terminate(run)
            if run['state'] not in ('failed','completed'):run['state']='stopped'

    def _terminate(self, run):
        # Only fresh child trees created by this manager, checked against PID reuse.
        run['group'].close()
        for child,created in reversed(run['processes']):
            if child.poll() is not None:continue
            try:
                parent=psutil.Process(child.pid)
                if abs(parent.create_time()-created)>.01:continue
                children=parent.children(recursive=True)
                for process in reversed(children):
                    try:process.terminate()
                    except psutil.NoSuchProcess:pass
                parent.terminate()
                psutil.wait_procs([parent,*children],timeout=3)
            except psutil.NoSuchProcess:continue

    def stop(self, identity):
        with self.guard:
            run=self.runs.get(identity)
            if not run:raise ValueError('Projeto não encontrado nesta sessão.')
            run['stop'].set()
        return {'ok':True}

    def close(self):
        for run in list(self.runs.values()):
            run['stop'].set();self._terminate(run)

    def status(self, selected=''):
        items=[]
        for r in list(self.runs.values())[-20:]:
            processes=[]
            for pid in r['group'].pids():
                try:processes.append({'pid':pid,'name':psutil.Process(pid).name()})
                except psutil.Error:continue
            items.append({'id':r['id'],'root':r['root'],'state':r['state'],'services':r['services'][:],'processes':processes,
                          'logs':list(r['logs'])[-80:] if r['id']==selected else [],'created':r['created']})
        return {'items':items}
