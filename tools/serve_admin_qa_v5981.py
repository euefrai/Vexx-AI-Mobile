"""Disposable local relay + real PC Agent + temporary SQLite. No real credentials/model."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa-artifacts'/'v5981'
PASSWORD='qa-password-long-5981'


def main():
    QA.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='v5981-admin-qa-') as folder:
        temp=Path(folder)
        os.environ.update(JULIA_ENV_FILE=str(temp/'none.env'),JULIA_ENV='test',JULIA_USERNAME='ownerqa',
                JULIA_SESSION_SECRET='fixture-session-secret-'+'q'*64,JULIA_AGENT_TOKEN='fixture-agent-token-'+'r'*64,
                JULIA_SQLITE_PATH=str(temp/'qa.sqlite'),JULIA_REMOTE='0',VEXX_AGENT_ROLE='development',
                VEXX_AGENT_RUNTIME_DIR=str(temp/'runtime'),JULIA_RATE_ADMIN_USER='1000')
        from argon2 import PasswordHasher
        os.environ['JULIA_PASSWORD_HASH']=PasswordHasher().hash(PASSWORD)
        import pc_agent,julia_auth,uvicorn,server,agent_runtime
        db=pc_agent.open_db(temp/'qa.sqlite')
        julia_auth.vincular_proprietario(db,'ownerqa','Owner QA',PASSWORD)
        julia_auth.criar_usuario(db,'alice','Alice QA',PASSWORD,papel='admin',criado_por='qa-fixture')
        julia_auth.criar_usuario(db,'bob','<svg/onload=alert(1)>',PASSWORD,criado_por='qa-fixture')
        db.close()
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        os.environ['JULIA_RELAY_URL']=f'http://127.0.0.1:{port}'
        appserver=uvicorn.Server(uvicorn.Config(server.app,host='127.0.0.1',port=port,log_level='warning'))
        runner=temp/'backend.py'
        runner.write_text('''import sys,os
sys.path.insert(0,os.environ['VEXX_QA_ROOT'])
import pc_agent,agent_runtime
pc_agent.hermes_bridge.listar_modelos=lambda *a,**kw:[]
pc_agent.providers.listar_tudo=lambda *a,**kw: {'models':[],'items':[],'default':'qa:free','providers':[]}
pc_agent.VEXX_BACKEND_REVISION='QA development checkout'
agent_runtime.launch(pc_agent)
''')
        env=dict(os.environ,VEXX_QA_ROOT=str(ROOT))
        log=(temp/'backend.log').open('wb')
        child=None
        stopfile=QA/'qa-stop'
        stopfile.unlink(missing_ok=True)
        def supervisor():
            nonlocal child
            while not appserver.started:
                time.sleep(.05)
            child=subprocess.Popen([sys.executable,str(runner)],env=env,cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+30
            while time.monotonic()<deadline and not (temp/'runtime'/'status.json').exists():
                time.sleep(.1)
            (QA/'qa-runtime-private.json').write_text(json.dumps({'pid':os.getpid(),'child':child.pid,
                     'url':f'http://127.0.0.1:{port}','database':str(temp/'qa.sqlite'),'runtime':str(temp/'runtime')}),encoding='utf-8')
            print(f'QA relay ready at http://127.0.0.1:{port}/admin',flush=True)
            while not stopfile.exists():time.sleep(.2)
            try:
                agent_runtime.command(temp/'runtime','stop',10)
                child.wait(timeout=15)
            finally:
                appserver.should_exit=True
        threading.Thread(target=supervisor,daemon=True).start()
        try:
            appserver.run(sockets=[sock])
        finally:
            if child and child.poll() is None:
                child.terminate();child.wait(5) # Disposable QA child only.
            log.close()
            (QA/'qa-backend.log').write_bytes((temp/'backend.log').read_bytes())


if __name__=='__main__':main()
