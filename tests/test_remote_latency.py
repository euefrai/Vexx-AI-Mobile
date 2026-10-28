"""Remote latency transport/security and bounded scheduling regressions."""
import base64
import ctypes
import json
import os
import threading
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
import pc_agent, remoto, server, remote_access

@pytest.fixture
def client(monkeypatch):
    from argon2 import PasswordHasher
    monkeypatch.setenv('JULIA_USERNAME','latency-qa')
    monkeypatch.setenv('JULIA_PASSWORD_HASH',PasswordHasher().hash('test-password-12345'))
    monkeypatch.setenv('JULIA_SESSION_SECRET','r'*64)
    monkeypatch.setenv('JULIA_ENV','development')
    monkeypatch.setenv('JULIA_AGENT_TOKEN','t'*64)
    server.rate_limiter.clear() if hasattr(server.rate_limiter,'clear') else None
    async def owner(_):return 'u-real-owner'
    monkeypatch.setattr(server,'revogacao_ok',owner)
    with TestClient(server.app) as c:
        assert c.get('/api/remote/frame').status_code==401
        assert c.post('/api/input/batch',json={'commands':[{'kind':'key','key':'enter'}]}).status_code==401
        login=c.post('/api/login',json={'username':'latency-qa','password':'test-password-12345'})
        assert login.status_code==200
        c.headers['X-CSRF-Token']=login.json()['csrf']
        yield c

def test_binary_frame_preserves_auth_grant_metadata_and_no_cache(client,monkeypatch):
    calls=[]
    async def exchange(req,**kw):
        calls.append(req)
        return {'type':'screen','imagem':base64.b64encode(b'\xff\xd8JPEG-QA').decode(),
                'largura':1280,'altura':720,'remote_enabled':False,'cursor':{'x':.2,'y':.8}}
    monkeypatch.setattr(server.relay,'exchange',exchange)
    r=client.get('/api/remote/frame?max_w=9999&q=999&owner=u-victim')
    assert r.status_code==200 and r.content==b'\xff\xd8JPEG-QA'
    assert r.headers['content-type']=='image/jpeg'
    assert 'no-store' in r.headers['cache-control']
    assert r.headers['x-frame-width']=='1280' and r.headers['x-remote-control']=='0'
    assert r.headers['x-cursor-x']=='0.2'
    assert calls==[{'type':'screen','owner':'u-real-owner','max_w':1920,'q':85}]
    assert client.get('/api/remote/frame',headers={'X-CSRF-Token':'bad'}).status_code==403
    assert client.get('/api/remote/frame',headers={'Origin':'https://evil.example'}).status_code==403
    async def denied(*a,**kw):return {'type':'screen_error','codigo':'sem_permissao'}
    monkeypatch.setattr(server.relay,'exchange',denied)
    assert client.get('/api/remote/frame').status_code==403

def test_batch_derives_owner_validates_limits_and_never_retries(client,monkeypatch):
    seen=[]
    async def exchange(req,**kw):seen.append(req);return {'type':'input_done'}
    monkeypatch.setattr(server.relay,'exchange',exchange)
    commands=[{'kind':'text','text':'ação 🚀'},{'kind':'key','key':'enter'}]
    assert client.post('/api/input/batch',json={'commands':commands,'owner':'u-victim'}).status_code==200
    assert seen[0]['owner']=='u-real-owner' and seen[0]['cmd']['kind']=='batch'
    for items in [[],commands*7,[{'kind':'batch'}],[{'kind':'drag','points':[{'x':0,'y':0},{'x':1,'y':1}]}], [{'kind':'text','text':'x'*200}]*3]:
        assert client.post('/api/input/batch',json={'commands':items}).status_code==422
    assert len(seen)==1
    async def failed(req,**kw):seen.append(req);return {'type':'input_error','error':'not confirmed'}
    monkeypatch.setattr(server.relay,'exchange',failed)
    assert client.post('/api/input/batch',json={'commands':commands}).status_code==503
    assert len(seen)==2

def test_capture_does_not_block_input_and_drops_revoked_frame(tmp_path,monkeypatch):
    path=tmp_path/'qa.sqlite';db=pc_agent.open_db(path);db.close()
    entered=threading.Event();release=threading.Event();sent=[]
    def capture(*args):
        entered.set();assert release.wait(3)
        return {'type':'screen','request_id':'frame','imagem':'private pixels'}
    monkeypatch.setattr(pc_agent,'resposta_screen',capture)
    monkeypatch.setattr(pc_agent,'enviar_ws',lambda ws,obj:sent.append(obj))
    monkeypatch.setattr(remote_access,'allowed',lambda *a:False)
    future=pc_agent.submit_screen(path,{},'u-qa','frame',object())
    try:
        assert entered.wait(2) and not future.done()
        # The main dispatcher remains available while encoding is held.
        assert pc_agent.submit_screen(path,{},'u-qa','second',object()) is None
        assert sent[-1]['codigo']=='ocupado'
        release.set();future.result(3)
        assert sent[-1]['codigo']=='sem_permissao' and 'imagem' not in sent[-1]
    finally:
        release.set();future.result(3)

def test_batch_native_order_and_rate_cost(monkeypatch):
    events=[];remoto._janela.clear()
    monkeypatch.setattr(remoto.sys,'platform','win32')
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(mouse_event=lambda *a:events.append(('wheel',a[3])),keybd_event=lambda *a:events.append(('key',a[0])))),raising=False)
    monkeypatch.setattr(remoto,'_digitar_unicode',lambda text:events.append(('text',text)))
    cmd=remoto.validar_comando({'kind':'batch','commands':[{'kind':'text','text':'ação 🚀'},{'kind':'wheel','delta_y':20},{'kind':'key','key':'enter'}]})
    try:
        assert remoto.executar(cmd,autorizado=True)['completed']==3
        assert events==[('text','ação 🚀'),('wheel',20),('key',13),('key',13)]
        assert len(remoto._janela)==3
        with pytest.raises(remoto.RemotoErro):remoto.executar(cmd,autorizado=True)
    finally:remoto._janela.clear()

@pytest.mark.parametrize('cmd',[{'kind':'batch','commands':[{'kind':'batch','commands':[]}]}, {'kind':'batch','commands':[{'kind':'key','key':'a'}]*13}, {'kind':'wheel','delta_x':True}, {'kind':'wheel','delta_y':1201}, {'kind':'batch','commands':[{'kind':'text','text':'x'*200}]*3}])
def test_invalid_native_commands(cmd):
    with pytest.raises(remoto.RemotoErro):remoto.validar_comando(cmd)

def test_runtime_tracks_both_pools_and_restores_submit(tmp_path,monkeypatch):
    import agent_runtime as ar
    import time
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('JULIA_RELAY_URL','http://127.0.0.1:59999')
    monkeypatch.setenv('VEXX_AGENT_ROLE','development')
    monkeypatch.setenv('VEXX_AGENT_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('JULIA_SQLITE_PATH',str(tmp_path/'db.sqlite'))
    sint,screen=ThreadPoolExecutor(1),ThreadPoolExecutor(1)
    originals=[sint.submit,screen.submit]
    module=SimpleNamespace(threading=threading,time=time,connect=lambda *a,**kw:None,
        _SINT_POOL=sint,_SCREEN_POOL=screen,database_path=lambda:tmp_path/'db.sqlite')
    release=threading.Event();entered1=threading.Event();entered2=threading.Event()
    def hold(started):started.set();assert release.wait(3)
    def run():
        a=module._SINT_POOL.submit(hold,entered1);b=module._SCREEN_POOL.submit(hold,entered2)
        try:
            assert entered1.wait(2) and entered2.wait(2)
            assert module.VEXX_RUNTIME.active==2 and not module.VEXX_RUNTIME.drain()
        finally:release.set();a.result(3);b.result(3)
        assert module.VEXX_RUNTIME.active==0
    module.run=run
    try:
        ar.launch(module)
        assert sint.submit==originals[0] and screen.submit==originals[1]
    finally: release.set();sint.shutdown();screen.shutdown()
