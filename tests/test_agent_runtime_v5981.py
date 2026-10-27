import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import agent_runtime as ar


def test_os_lock_ownership_stale_metadata_and_reuse(tmp_path):
    path = tmp_path/'lock'
    first = ar.InstanceLock(path).acquire()
    try:
        with pytest.raises(RuntimeError):
            ar.InstanceLock(path).acquire()
        script = 'import agent_runtime as a; a.InstanceLock(__import__("sys").argv[1]).acquire()'
        r = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True)
        assert r.returncode != 0
    finally:
        first.close()
    path.write_text('stale pid 123 reused')
    ar.InstanceLock(path).acquire().close()
    crash='import os,agent_runtime as a,sys; lock=a.InstanceLock(sys.argv[1]).acquire(); os._exit(9)'
    assert subprocess.run([sys.executable,'-c',crash,str(path)],capture_output=True).returncode==9
    ar.InstanceLock(path).acquire().close()


def test_identity_and_isolated_development():
    assert ar.identity('https://example.org/') == ar.identity('https://example.org')
    assert ar.identity('http://localhost:8000','development') != ar.identity('https://example.org')
    with pytest.raises(ValueError):
        ar.identity('https://example.org', 'development')
    with pytest.raises(ValueError):
        ar.identity('https://secret@example.org')
    with pytest.raises(ValueError):
        ar.identity('https://example.org','production','second-consumer')


def test_real_local_authenticated_channel_and_drain_timeout(tmp_path):
    r = ar.Runtime('http://localhost:12345', directory=tmp_path/'runtime').start()
    try:
        assert ar.command(r.directory)['pid'] == os.getpid()
        assert ar.command(r.directory, 'shell')['error'] == 'unsupported_action'
        r.drain = lambda: False
        result = ar.command(r.directory, 'stop', timeout=1)
        assert result['state'] in ('STOP_ACCEPTED','STOPPING_NEW_JOBS','DRAINING')
        time.sleep(1.3)
        assert r.state == 'BLOCKED_DRAIN_TIMEOUT'
        with pytest.raises(RuntimeError):
            with r.operation():
                pass
        with pytest.raises(RuntimeError):
            ar.InstanceLock(r.directory/'instance.lock').acquire()
    finally:
        r.close()


def test_wrong_key_and_stale_process_are_rejected(tmp_path):
    r = ar.Runtime('http://localhost:23456', directory=tmp_path/'runtime').start()
    try:
        keyfile = r.directory/'control.key'
        original = keyfile.read_bytes()
        keyfile.write_bytes(b'x'*32)
        assert ar.command(r.directory)['error'] == 'unauthorized'
        keyfile.write_bytes(original)
        from multiprocessing.connection import Client
        with Client(r.address,family=r.family,authkey=None) as client:
            client.recv_bytes(128);client.send_bytes(b'[]')
            assert json.loads(client.recv_bytes(4096))['error']=='invalid_request'
        assert ar.command(r.directory)['pid']==r.pid
        status = r.directory/'status.json'
        data = json.loads(status.read_text()); data['generation'] = 'old-pid'
        status.write_text(json.dumps(data))
        assert ar.command(r.directory)['error'] == 'stale_process'
        data['generation']=r.generation;data['process_created']=(r.created or 0)-1
        status.write_text(json.dumps(data))
        assert ar.command(r.directory)['error']=='stale_process'
    finally:
        r.close()


def test_startup_failure_releases_only_its_own_lock(tmp_path,monkeypatch):
    r=ar.Runtime('http://localhost:45678',directory=tmp_path/'runtime')
    def fail(*a,**kw):raise OSError('QA listener unavailable')
    monkeypatch.setattr(ar,'Listener',fail)
    with pytest.raises(OSError):r.start()
    ar.InstanceLock(r.directory/'instance.lock').acquire().close()


def test_operation_finishes_without_force(tmp_path):
    r = ar.Runtime('http://localhost:34567', directory=tmp_path/'runtime').start()
    finished = threading.Event()
    class Connection:
        def close(self):
            finished.set()
    r.connection = Connection()
    try:
        with r.operation():
            ar.command(r.directory,'stop',timeout=2)
            assert not finished.wait(.2)
        assert finished.wait(2)
    finally:
        r.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows pythonw integration')
def test_real_pythonw_wss_reconnect_named_pipe_stop_and_wal(tmp_path):
    """Real Windows process and local WebSocket; no production/model invocation."""
    import sqlite3
    from websockets.sync.server import serve
    received=[]
    admin_checks=[]
    phases=[]
    started=time.monotonic()
    ready=threading.Event()
    def handler(ws):
        index=len(received)+1
        ws.send(json.dumps({'type':'auth_config','request_id':f'qa-{index}'}))
        received.append(json.loads(ws.recv(timeout=12)))
        phases.append((f'auth-{index}',round(time.monotonic()-started,3)))
        if index==1:
            ws.close(code=1012,reason='QA reconnect')
        else:
            metadata=json.loads((tmp_path/'identity.json').read_text())
            request={'type':'admin_users','owner':metadata['uid'],'sid':metadata['sid']}
            ws.send(json.dumps({**request,'request_id':'admin-valid'}))
            assert json.loads(ws.recv(timeout=5))['type']=='admin_users'
            db=sqlite3.connect(tmp_path/'qa.sqlite')
            db.execute('update users set aprovado=0 where uid=?',(metadata['uid'],));db.commit()
            ws.send(json.dumps({**request,'request_id':'admin-unapproved'}))
            assert json.loads(ws.recv(timeout=5))['codigo']=='permissao'
            db.execute('update users set aprovado=1 where uid=?',(metadata['uid'],))
            db.execute('update user_sessions set revogada=1 where sid=?',(metadata['sid'],));db.commit();db.close()
            ws.send(json.dumps({**request,'request_id':'admin-revoked'}))
            assert json.loads(ws.recv(timeout=5))['codigo']=='permissao'
            admin_checks.extend(['valid','unapproved_denied','revoked_denied'])
            ready.set()
            try:
                ws.recv(timeout=15)
            except Exception:
                pass
    with serve(handler,'127.0.0.1',0) as ws_server:
        port=ws_server.socket.getsockname()[1]
        thread=threading.Thread(target=ws_server.serve_forever,daemon=True);thread.start()
        script=tmp_path/'qa_backend.py'
        script.write_text('''import sys,os
sys.path.insert(0,os.environ['VEXX_QA_ROOT'])
print('QA boot',flush=True)
import pc_agent,agent_runtime,time
print('QA imported',flush=True)
import julia_auth,json
from pathlib import Path
db=pc_agent.open_db(Path(os.environ['JULIA_SQLITE_PATH']))
user=julia_auth.criar_usuario(db,'qa-admin','QA Admin','qa-password-long-5981',papel='admin',criado_por='qa-fixture')
session=julia_auth.criar_sessao(db,user['uid']);db.close()
(Path(os.environ['JULIA_SQLITE_PATH']).parent/'identity.json').write_text(json.dumps({'uid':user['uid'],'sid':session['sid']}))
print('QA account ready',flush=True)
pc_agent.hermes_bridge.listar_modelos=lambda *a,**kw: []
class FastTime:
    def __getattr__(self,n):return getattr(time,n)
    def sleep(self,s):time.sleep(min(s,.05))
pc_agent.time=FastTime()
agent_runtime.launch(pc_agent)
''')
        directory=tmp_path/'runtime';database=tmp_path/'qa.sqlite'
        env=dict(os.environ,JULIA_ENV_FILE=str(tmp_path/'no.env'),JULIA_RELAY_URL=f'http://127.0.0.1:{port}',
                 JULIA_SQLITE_PATH=str(database),JULIA_AGENT_TOKEN='qa-local-token-not-production',
                 VEXX_AGENT_ROLE='development',VEXX_AGENT_RUNTIME_DIR=str(directory),VEXX_QA_ROOT=str(Path.cwd()))
        log=tmp_path/'backend.log'
        with log.open('wb') as output:
            child=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),str(script)],env=env,
                                  creationflags=subprocess.CREATE_NO_WINDOW,stdout=output,stderr=subprocess.STDOUT)
        try:
            assert ready.wait(15),f'QA readiness failed; phases={phases}; log={log.read_text(errors="replace")[-2000:]}'
            assert len(received)==2 and all(r['type']=='auth_config' for r in received)
            assert admin_checks==['valid','unapproved_denied','revoked_denied']
            duplicate=subprocess.run([sys.executable,str(Path.cwd()/'pc_agent.py')],env=env,
                        capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.returncode!=0 and b'RuntimeError' in duplicate.stderr
            assert len(received)==2 # No second WSS consumer reached the relay.
            status=ar.command(directory)
            assert status['pid']==child.pid or status['ppid']==child.pid # venv launcher may spawn pythonw
            ar.command(directory,'stop',timeout=5)
            assert child.wait(timeout=10)==0
            assert json.loads((directory/'status.json').read_text())['state']=='STOPPED'
            db=sqlite3.connect(database);assert db.execute('pragma quick_check').fetchone()[0]=='ok';db.close()
            ar.InstanceLock(directory/'instance.lock').acquire().close()
        finally:
            if child.poll() is None:
                child.terminate();child.wait(timeout=5) # Only our disposable QA process.
            ws_server.shutdown()
