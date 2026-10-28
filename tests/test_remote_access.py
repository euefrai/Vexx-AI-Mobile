"""Local consent, account isolation, revocation, expiry and UI device geometry."""
import shutil
import sqlite3
import subprocess
import threading
from collections import deque
from pathlib import Path

import pytest

import julia_auth
import pc_agent
import remote_access as access
import remoto
import server
from fastapi.testclient import TestClient


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(access, '_pending', None)
    monkeypatch.setattr(access, '_worker_open', False)
    monkeypatch.setattr(access, '_attempts', deque())
    db = pc_agent.open_db(tmp_path / 'remote.sqlite3')
    for name in ('alice', 'bob'):
        julia_auth.criar_usuario(db, name, name, 'qa-only-password-long', criado_por='test')
    yield db
    db.close()


def uid(db, name='alice'):
    return julia_auth.buscar_usuario(db, name)['uid']


def pending(db, monkeypatch, owner=None):
    class HeldThread:
        def __init__(self, **kw): pass
        def start(self): pass
    monkeypatch.setattr(access.threading, 'Thread', HeldThread)
    monkeypatch.setattr(access.sys, 'platform', 'win32')
    monkeypatch.setattr(access.importlib.util, 'find_spec', lambda _: object())
    state = access.request_access(db, owner or uid(db))
    assert state['pending'] and not state['approved'] and not state['view_allowed']
    return access._pending


def complete(db, monkeypatch, req, answer=True):
    monkeypatch.setattr(access, 'confirm_locally', lambda *args: answer)
    access._confirm_worker(db.execute('PRAGMA database_list').fetchone()[2], req, 'alice')


def test_request_never_grants_without_local_confirmation(db, monkeypatch):
    req = pending(db, monkeypatch)
    assert not access.allowed(db, uid(db))
    assert len(req['code']) == 6 and req['code'].isdigit()
    other = access.status(db, uid(db, 'bob'))
    assert not other['pending'] and other['code'] == ''
    assert access.request_access(db, uid(db, 'bob'))['codigo'] == 'ocupado'


def test_local_confirmation_persists_only_for_correct_account(db, monkeypatch):
    req = pending(db, monkeypatch)
    complete(db, monkeypatch, req)
    assert access.status(db, uid(db))['approved']
    assert access.allowed(db, uid(db)) and not access.allowed(db, uid(db, 'bob'))
    with sqlite3.connect(db.execute('PRAGMA database_list').fetchone()[2]) as reopened:
        assert access.binding(reopened, uid(db)) is True
    assert not access.input_blocked()


@pytest.mark.parametrize('reason', ['decline', 'expire', 'revoke', 'blocked', 'deleted', 'error'])
def test_late_or_invalid_confirmation_cannot_grant(db, monkeypatch, reason):
    owner = uid(db)
    req = pending(db, monkeypatch)
    if reason == 'expire': req['expires'] = 0
    if reason == 'revoke': access.revoke(db, owner)
    if reason == 'blocked': julia_auth.definir_status(db, 'local', owner, 'bloqueado')
    if reason == 'deleted':
        db.execute('DELETE FROM users WHERE uid=?', (owner,)); db.commit()
    if reason == 'error':
        monkeypatch.setattr(access, 'confirm_locally', lambda *a: (_ for _ in ()).throw(OSError('desktop missing')))
        access._confirm_worker(db.execute('PRAGMA database_list').fetchone()[2], req, 'alice')
    else:
        complete(db, monkeypatch, req, answer=reason != 'decline')
    assert access.binding(db, owner) is not True
    assert not access.input_blocked()


def test_revoke_overrides_legacy_grant_and_invalidates_pending(db, monkeypatch):
    owner = uid(db)
    julia_auth.update_limits(db, 'local', owner, 0, 0, True)
    assert access.allowed(db, owner)
    access.revoke(db, owner)
    assert not access.allowed(db, owner)
    assert not access.allowed(db, uid(db, 'bob'))
    assert pc_agent.resposta_screen(db, {}, owner, 'r')['codigo'] == 'sem_permissao'
    assert pc_agent.resposta_input(db, {'cmd':{'kind':'click','x':.5,'y':.5}}, owner, 'r')['codigo'] == 'sem_permissao'


def test_native_dialog_blocks_even_legacy_input(db, monkeypatch):
    pending(db, monkeypatch)
    monkeypatch.setenv('JULIA_REMOTE', '1')
    monkeypatch.setattr(remoto, 'executar', lambda *a, **kw: pytest.fail('Dialog approved remotely'))
    assert pc_agent.resposta_input(db, {'cmd':{'kind':'key','key':'enter'}}, 'local', 'r')['codigo'] == 'sem_permissao'


def test_paired_input_does_not_require_global_remote_env(db, monkeypatch):
    req = pending(db, monkeypatch)
    complete(db, monkeypatch, req)
    monkeypatch.delenv('JULIA_REMOTE', raising=False)
    seen = []
    monkeypatch.setattr(remoto, 'executar', lambda cmd, **kw: seen.append((cmd,kw)) or {'ok':True,'kind':cmd['kind']})
    result = pc_agent.resposta_input(db, {'cmd':{'kind':'click','x':.5,'y':.5}}, uid(db), 'r')
    assert result['type'] == 'input_done'
    assert seen[0][1] == {'autorizado':True}
    assert pc_agent.resposta_input(db, {'cmd':seen[0][0]}, uid(db,'bob'), 'r')['codigo'] == 'sem_permissao'


def test_missing_account_and_platform_fail_closed(db, monkeypatch):
    assert not access._active(db, 'u-does-not-exist')
    monkeypatch.setattr(access.sys, 'platform', 'linux')
    assert access.request_access(db, uid(db))['codigo'] == 'dependencia'
    monkeypatch.setattr(access.sys, 'platform', 'win32')
    monkeypatch.setattr(access.importlib.util, 'find_spec', lambda _: None)
    assert access.request_access(db, uid(db))['codigo'] == 'dependencia'


def test_requests_are_bounded_across_accounts(db, monkeypatch):
    for _ in range(3):
        req = pending(db, monkeypatch)
        complete(db, monkeypatch, req, False)
    assert access.request_access(db, uid(db, 'bob'))['codigo'] == 'ritmo'


def test_administrator_can_still_revoke_a_locally_paired_account(db, monkeypatch):
    req = pending(db, monkeypatch)
    complete(db, monkeypatch, req)
    assert access.allowed(db, uid(db))
    julia_auth.update_limits(db, 'local', uid(db), 0, 0, False)
    assert not access.allowed(db, uid(db))
    assert not access.status(db, uid(db))['approved']


@pytest.mark.parametrize('kind,expected', [('click',[2,4]), ('right',[8,16]), ('double',[2,4,2,4])])
def test_native_mouse_button_mapping(monkeypatch, kind, expected):
    import ctypes
    from types import SimpleNamespace
    calls = []
    user = SimpleNamespace(SetCursorPos=lambda *a: None, mouse_event=lambda flag,*a: calls.append(flag))
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user), raising=False)
    monkeypatch.setattr(remoto.sys, 'platform', 'win32')
    monkeypatch.setattr(remoto, 'checar_ritmo', lambda: None)
    monkeypatch.setattr(remoto, '_para_px', lambda *a: (50,50))
    remoto.executar({'kind':kind,'x':.5,'y':.5}, autorizado=True)
    assert calls == expected


def test_unicode_input_preserves_utf16_surrogate_pairs_and_checks_windows_result(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    seen=[]
    def accept(count, array, size):
        seen.extend((array[i].u.ki.wScan,array[i].u.ki.dwFlags) for i in range(count))
        return count
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(SendInput=accept)),raising=False)
    remoto._digitar_unicode('á🚀')
    assert seen==[(0xe1,4),(0xe1,6),(0xd83d,4),(0xd83d,6),(0xde80,4),(0xde80,6)]
    monkeypatch.setattr(ctypes.windll.user32,'SendInput',lambda *a:0)
    with pytest.raises(remoto.RemotoErro,match='Windows'):
        remoto._digitar_unicode('x')
    with pytest.raises(remoto.RemotoErro,match='Unicode'):
        remoto._digitar_unicode('\ud800')


def test_device_detection_and_letterbox_coordinates():
    if not shutil.which('node'): pytest.skip('Node unavailable')
    script = r"""
    require('./public/remote.js'); const {isMobile:m,imagePosition:p}=VexxRemote;
    const assert=require('node:assert/strict');
    assert.equal(m({userAgent:'Windows Chrome',maxTouchPoints:10}),false);
    assert.equal(m({userAgent:'Android Chrome',userAgentData:{mobile:true}}),true);
    assert.equal(m({userAgent:'iPhone'}),true);
    assert.equal(m({userAgent:'Macintosh Safari',maxTouchPoints:5}),true);
    assert.equal(m({userAgent:'Macintosh Safari',maxTouchPoints:0}),false);
    const r={left:0,top:0,width:400,height:400};
    assert.equal(p(r,1600,900,200,10),null);
    assert.deepEqual(p(r,1600,900,200,200),{x:.5,y:.5});
    assert.equal(p(r,0,0,200,200),null);
    """
    subprocess.run(['node','-e',script], cwd=Path(__file__).resolve().parents[1],check=True)


def test_remote_endpoints_require_auth_csrf_and_derive_owner(monkeypatch):
    from argon2 import PasswordHasher
    monkeypatch.setenv('JULIA_USERNAME','remote-qa')
    monkeypatch.setenv('JULIA_PASSWORD_HASH',PasswordHasher().hash('qa-password-long'))
    monkeypatch.setenv('JULIA_SESSION_SECRET','r'*64)
    monkeypatch.setenv('JULIA_AGENT_TOKEN','s'*64)
    monkeypatch.setenv('JULIA_ENV','development')
    calls = []
    async def exchange(req,**kwargs):
        calls.append(req)
        return {'type':'remote_status','approved':False,'request_id':'private'}
    async def validated(request):
        return 'u-authenticated-account'
    monkeypatch.setattr(server.relay,'exchange',exchange)
    monkeypatch.setattr(server,'revogacao_ok',validated)
    with TestClient(server.app) as client:
        for method,route in [('GET','status'),('POST','request'),('POST','revoke')]:
            assert client.request(method,'/api/remote/'+route).status_code == 401
        result=client.post('/api/login',json={'username':'remote-qa','password':'qa-password-long'})
        assert result.status_code == 200
        csrf=result.json()['csrf']
        calls.clear()
        assert client.post('/api/remote/request').status_code == 403
        for method,route in [('GET','status'),('POST','request'),('POST','revoke')]:
            response=client.request(method,'/api/remote/'+route,headers={'X-CSRF-Token':csrf},
                                    json={'owner':'u-victim','approved':True})
            assert response.status_code == 200, response.text
            assert 'request_id' not in response.json()
        assert [r['type'] for r in calls] == ['remote_status','remote_request','remote_revoke']
        assert all(r['owner']=='u-authenticated-account' and 'approved' not in r for r in calls)


def test_two_sessions_share_account_access_over_real_relay(db, monkeypatch):
    """Real ASGI/WebSocket/SQLite handlers; native consent/capture/input simulated."""
    from argon2 import PasswordHasher
    monkeypatch.setenv('JULIA_USERNAME','qa-owner')
    monkeypatch.setenv('JULIA_PASSWORD_HASH',PasswordHasher().hash('qa-owner-password'))
    monkeypatch.setenv('JULIA_SESSION_SECRET','t'*64)
    monkeypatch.setenv('JULIA_AGENT_TOKEN','v'*64)
    monkeypatch.setenv('JULIA_ENV','development')
    monkeypatch.setattr(server,'revogados',{'sids':set(),'ts':0,'suportado':True,'falhas':0})
    monkeypatch.setattr(access,'confirm_locally',lambda *a: True)
    monkeypatch.setattr(remoto,'capturar',lambda *a:{'imagem':'simulated','largura':960,'altura':540,'ms':1})
    commands=[]
    monkeypatch.setattr(remoto,'executar',lambda cmd,**kw: commands.append(cmd) or {'ok':True,'kind':cmd['kind']})
    path=db.execute('PRAGMA database_list').fetchone()[2]
    errors=[]
    def agent(ws):
        store=pc_agent.open_db(Path(path))
        try:
            while True:
                try: req=ws.receive_json()
                except Exception: break
                kind=req['type'];owner=req.get('owner','local')
                if kind=='auth_login':
                    user=julia_auth.login_conta(store,req['username'],req['password'])
                    reply={'type':'auth_ok',**user,**julia_auth.criar_sessao(store,user['uid'])}
                elif kind=='sess_revogados': reply={'type':kind,'sids':[]}
                elif kind=='remote_status': reply=access.status(store,owner)
                elif kind=='remote_request': reply=access.request_access(store,owner)
                elif kind=='remote_revoke': reply=access.revoke(store,owner)
                elif kind=='screen': reply=pc_agent.resposta_screen(store,req,owner,req['request_id'])
                elif kind=='input': reply=pc_agent.resposta_input(store,req,owner,req['request_id'])
                else: raise AssertionError(kind)
                ws.send_json({**reply,'request_id':req['request_id']})
        except Exception as exc: errors.append(str(exc))
        finally: store.close()
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',headers={'Authorization':'Bearer '+'v'*64}) as ws:
            worker=threading.Thread(target=agent,args=(ws,),daemon=True);worker.start()
            sessions=[]
            for name in ('alice','alice','bob'):
                response=client.post('/api/login',json={'username':name,'password':'qa-only-password-long'})
                assert response.status_code==200,response.text
                sessions.append({'Cookie':'JULIA_session='+client.cookies.get('JULIA_session'),
                                 'X-CSRF-Token':response.json()['csrf']})
                client.cookies.clear()
            assert sessions[0]['Cookie']!=sessions[1]['Cookie']
            first,second,other=sessions
            assert client.get('/api/screen',headers=second).status_code==403
            response=client.post('/api/remote/request',headers=first)
            assert response.status_code==200,response.text
            for _ in range(20):
                state=client.get('/api/remote/status',headers=second)
                if state.json().get('approved'): break
                threading.Event().wait(.05)
            assert state.json()['approved'] is True
            assert client.get('/api/screen',headers=second).json()['imagem']=='simulated'
            assert client.get('/api/screen',headers=other).status_code==403
            assert client.post('/api/input',headers=second,json={'kind':'text','text':'Olá'}).status_code==200
            assert commands==[{'kind':'text','text':'Olá'}]
            assert client.post('/api/remote/revoke',headers=first).status_code==200
            assert client.get('/api/screen',headers=second).status_code==403
            assert client.post('/api/input',headers=second,json={'kind':'key','key':'enter'}).status_code==403
        worker.join(5)
        assert not worker.is_alive()
    assert not errors,errors
