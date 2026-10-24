"""Real auth/SQLite and HTTP guards with an in-process relay adapter; not production E2E."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

import admin_console as console
import admin_http
import admin_migration as migration
import julia_auth as auth
import pc_agent
import server

PASSWORD='qa-password-long-5981'


@pytest.fixture
def env(tmp_path,monkeypatch):
    for key,value in {'JULIA_USERNAME':'ownerqa','JULIA_PASSWORD_HASH':PasswordHasher().hash(PASSWORD),
                      'JULIA_SESSION_SECRET':'q'*64,'JULIA_AGENT_TOKEN':'r'*64,'JULIA_ENV':'test',
                      'JULIA_RATE_ADMIN_USER':'1000'}.items():
        monkeypatch.setenv(key,value)
    server.login_failures.clear(); server.revogados['sids']=set();server.revogados['ts']=0
    path=tmp_path/'qa.sqlite';pc_agent.open_db(path).close()
    db=sqlite3.connect(path,check_same_thread=False)
    auth.vincular_proprietario(db,'ownerqa','Owner QA',PASSWORD)
    admin=auth.criar_usuario(db,'alice','Alice Human',PASSWORD,papel='admin',criado_por='local')['uid']
    user=auth.criar_usuario(db,'bob','Bob Human',PASSWORD,criado_por='local')['uid']
    agent=SimpleNamespace(ai_config=lambda:{'model':'qa:free'},VEXX_RUNTIME=None)
    calls=[]
    async def exchange(req,timeout=12):
        calls.append({k:v for k,v in req.items() if k!='password'})
        try:
            kind=req['type']
            if kind in console.TYPES:
                return console.handle(db,req,agent)
            if kind=='auth_whoami':
                u=auth.sessao_valida(db,req.get('sid',''))
                return {'type':'auth_user','user':u} if u else {'type':'op_error'}
            if kind=='auth_login':
                u=auth.login_conta(db,req['username'],req['password'])
                return {'type':'auth_ok',**u,**auth.criar_sessao(db,u['uid'])}
            if kind=='sess_revogados':
                return {'type':kind,'sids':auth.sids_revogados(db)}
            if kind=='admin_users':
                return {'type':kind,'users':[dict(zip(('uid','username','display','role','status','aprovado'),r)) for r in db.execute('select uid,username,display,role,status,aprovado from users')]}
            if kind=='conversations':
                assert req['owner']==admin
                return {'type':kind,'conversations':[]}
            return {'type':'op_error','codigo':'permissao'}
        except auth.AuthErro as exc:
            return {'type':'op_error','codigo':exc.codigo}
    monkeypatch.setattr(server.relay,'ws',object());monkeypatch.setattr(server.relay,'exchange',exchange)
    yield SimpleNamespace(db=db,admin=admin,user=user,calls=calls,path=path)
    db.close()


def login(client,username='alice'):
    result=client.post('/api/login',json={'username':username,'password':PASSWORD})
    assert result.status_code==200,result.text
    return {'X-CSRF-Token':result.json()['csrf']}


def authorize(client,username='alice'):
    headers=login(client,username)
    assert client.post('/api/admin/reauth',json={'password':PASSWORD},headers=headers).status_code==200
    return headers


def test_anonymous_shell_has_no_operational_data_and_api_denied(env):
    with TestClient(server.app) as client:
        assert client.get('/admin').status_code==200
        assert client.get('/api/admin/overview').status_code==401
        assert client.get('/api/admin/users').status_code==401
        assert env.admin not in client.get('/admin').text


def test_user_cannot_forge_role_or_access_admin_api(env):
    with TestClient(server.app) as c:
        h=login(c,'bob')
        assert c.get('/api/admin/overview').status_code==403
        assert c.post('/api/admin/reauth',json={'password':PASSWORD,'role':'admin'},headers=h).status_code==403
        assert auth.buscar_uid(env.db,env.user)['role']=='user'


def test_admin_needs_recent_reauth_and_reload_keeps_valid_grant(env):
    with TestClient(server.app) as c:
        h=login(c)
        assert c.get('/api/admin/overview').status_code==403
        r=c.post('/api/admin/reauth',json={'password':PASSWORD},headers=h)
        assert r.status_code==200,r.text
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
        first=c.get('/api/admin/overview');assert first.status_code==200,first.text
        assert 0 < first.json()['admin_expires_in'] <= 600
        assert c.get('/admin').status_code==200
        assert c.get('/api/admin/users').status_code==200


def test_expired_authorization_rejected(env,monkeypatch):
    with TestClient(server.app) as c:
        authorize(c);monkeypatch.setattr(admin_http,'SECONDS',-1)
        assert c.get('/api/admin/overview').status_code==403


def test_grant_is_bound_to_exact_session_not_only_uid(env):
    with TestClient(server.app) as c:
        authorize(c)
        login(c) # Same human, a new session nonce/sid.
        assert c.get('/api/admin/overview').status_code==403


@pytest.mark.parametrize('change',['revoke','block','demote','unapprove','revision'])
def test_live_account_and_session_changes_invalidate_access(env,change):
    with TestClient(server.app) as c:
        authorize(c)
        if change=='revoke':auth.revogar_sessoes(env.db,'local',env.admin)
        if change=='block':auth.definir_status(env.db,'local',env.admin,'bloqueado')
        if change=='demote':auth.definir_papel(env.db,'local',env.admin,'user')
        if change=='unapprove':env.db.execute('update users set aprovado=0 where uid=?',(env.admin,));env.db.commit()
        if change=='revision':auth.definir_papel(env.db,'local',env.admin,'admin')
        assert c.get('/api/admin/overview').status_code in (401,403)


def test_csrf_and_cross_origin_denied(env):
    with TestClient(server.app) as c:
        h=login(c)
        assert c.post('/api/admin/reauth',json={'password':PASSWORD}).status_code==403
        assert c.post('/api/admin/reauth',json={'password':PASSWORD},headers={**h,'Origin':'https://evil.invalid'}).status_code==403
        assert not any(r['type']=='admin_verify_password' for r in env.calls)


def test_wrong_password_rate_limited_and_audited(env):
    with TestClient(server.app) as c:
        h=login(c)
        statuses=[c.post('/api/admin/reauth',json={'password':'bad'},headers=h).status_code for _ in range(6)]
        assert statuses[:5]==[401]*5 and statuses[5]==429
        assert env.db.execute("select count(*) from audit_log where acao='admin_reauth_failed'").fetchone()[0]==5


def test_legacy_argon2_reauth_and_revocation(env):
    with TestClient(server.app) as c:
        authorize(c,'ownerqa')
        assert c.get('/api/admin/overview').status_code==200
        assert not any('password' in r for r in env.calls if r['type']=='admin_verify_password')
        auth.revogar_sessoes(env.db,'local','local')
        assert c.get('/api/admin/overview').status_code in (401,403)


def test_secure_cookie_and_explicit_lock(env,monkeypatch):
    monkeypatch.setenv('JULIA_ENV','production')
    with TestClient(server.app,base_url='https://testserver') as c:
        h=login(c);r=c.post('/api/admin/reauth',json={'password':PASSWORD},headers=h)
        assert r.status_code==200 and 'Secure' in r.headers['set-cookie']
        assert c.post('/api/admin/leave',json={},headers=h).status_code==200
        assert c.get('/api/admin/overview').status_code==403


def test_aggregate_diagnostics_do_not_include_private_content_or_hashes(env):
    with TestClient(server.app) as c:
        authorize(c)
        payload=c.get('/api/admin/overview').json()
        assert payload['research']['read_rate'] is None
        assert payload['model']['availability'] is None
        raw=json.dumps(payload)
        for forbidden in ('response_text','objective','password','control.key','hash','conversation_id'):
            assert forbidden not in raw
        assert payload['agent']['cpu_percent'] is None


def test_non_admin_relay_identity_cannot_impersonate_another_session(env):
    sid=auth.criar_sessao(env.db,env.user)['sid']
    with pytest.raises(auth.AuthErro):
        console.identity(env.db,env.admin,sid,True)


def test_admin_status_does_not_enable_remote_permission(env):
    assert not auth.pode_remoto(env.db,env.admin)
    auth.definir_papel(env.db,'local',env.user,'admin')
    assert not auth.pode_remoto(env.db,env.user)


def test_migration_snapshot_idempotent_excludes_pending_service_fixture_future(env):
    for name,status,approved,actor in [('carol','ativo',True,'aberto'),('pending','pendente',False,'local'),
            ('test-fixture','ativo',True,'local'),('svc-agent','ativo',True,'local'),('unknown','ativo',True,'unverified')]:
        created=auth.criar_usuario(env.db,name,'Display '+name,PASSWORD,aprovado=approved,criado_por=actor)
        env.db.execute('update users set status=? where uid=?',(status,created['uid']));env.db.commit()
    plan=migration.plan(env.db);before=env.db.execute('select uid,hash,status,aprovado,remote_ok from users order by uid').fetchall()
    result=migration.apply(env.db,plan)
    assert result['promoted']==2 # Bob and Carol
    after=env.db.execute('select uid,hash,status,aprovado,remote_ok from users order by uid').fetchall()
    assert before==after
    assert migration.apply(env.db,plan)['promoted']==0
    newcomer=auth.criar_usuario(env.db,'future','Future Human',PASSWORD,criado_por='local')['uid']
    assert migration.apply(env.db,migration.plan(env.db))['promoted']==0
    assert auth.buscar_uid(env.db,newcomer)['role']=='user'
    assert len(migration.reverse(env.db))==2
    assert auth.buscar_uid(env.db,env.user)['role']=='user'


def test_migration_detects_changed_snapshot(env):
    snapshot=migration.plan(env.db)
    auth.criar_usuario(env.db,'later','Later Human',PASSWORD,criado_por='local')
    with pytest.raises(ValueError):migration.apply(env.db,snapshot)
    assert auth.buscar_uid(env.db,env.user)['role']=='user'


def test_last_active_approved_admin_cannot_be_removed_demoted_or_blocked(env):
    env.db.execute("update users set role='user' where uid!='local'");env.db.commit()
    for fn,args in [(auth.definir_papel,('user',)),(auth.definir_status,('bloqueado',)),(auth.excluir_usuario,())]:
        with pytest.raises(auth.AuthErro):fn(env.db,'external-actor','local',*args)
    assert auth.buscar_uid(env.db,'local')['role']=='admin'


def test_public_registration_still_user(env):
    auth.config_set(env.db,'modo_cadastro','aberto');auth.config_set(env.db,'exigir_aprovacao','0')
    result=auth.registrar(env.db,'New Human','newhuman',PASSWORD)
    assert auth.buscar_uid(env.db,result['uid'])['role']=='user'


@pytest.mark.parametrize('action',['demote','block','delete'])
def test_concurrent_admin_mutations_preserve_one_active_admin(env,action):
    import threading
    env.db.execute("update users set role='user' where uid='local'")
    env.db.execute("update users set role='admin' where uid=?",(env.user,));env.db.commit()
    barrier=threading.Barrier(2);results=[]
    def change(actor,target):
        db=sqlite3.connect(env.path,timeout=5)
        try:
            barrier.wait(timeout=5)
            if action=='demote':auth.definir_papel(db,actor,target,'user')
            if action=='block':auth.definir_status(db,actor,target,'bloqueado')
            if action=='delete':auth.excluir_usuario(db,actor,target)
            results.append('ok')
        except auth.AuthErro as exc:
            results.append(exc.codigo)
        finally:db.close()
    threads=[threading.Thread(target=change,args=(env.admin,env.user)),threading.Thread(target=change,args=(env.user,env.admin))]
    for t in threads:t.start()
    for t in threads:t.join(8);assert not t.is_alive()
    assert results.count('ok')==1 and results.count('ultimo_admin')==1
    assert env.db.execute("select count(*) from users where role='admin' and status='ativo' and aprovado=1").fetchone()[0]==1


def test_invite_audit_does_not_store_code_fragments(env):
    invite=auth.gerar_convite(env.db,'local')
    result=auth.registrar(env.db,'Invited Human','invited',PASSWORD,invite['codigo'])
    log=' '.join(str(r) for r in env.db.execute("select ator,detalhe from audit_log where alvo='invited'"))
    assert invite['codigo'][:12] not in log


def test_admin_does_not_bypass_message_ownership(env):
    # Administrator remains an ordinary owner for conversational data.
    for owner,mid in ((env.admin,'admin-msg'),(env.user,'other-msg')):
        env.db.execute("INSERT INTO messages(id,conversation_id,origin,role,text,created_at,received_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",
                       (mid,'shared-name','mobile','user','private-'+owner,auth.agora_iso(),auth.agora_iso(),owner))
    env.db.commit()
    rows=pc_agent.list_messages(env.db,owner=env.admin,conversation_id='shared-name')
    assert [r['id'] for r in rows]==['admin-msg']


def test_admin_frontend_uses_safe_dom_no_model_or_remote_execution():
    source=Path('public/admin.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in source and 'eval(' not in source
    import jdui
    from test_v58_deep_research import _msg
    safe={'files':[{'name':'Evidence','url':'https://example.org/a.pdf','kind':'pdf'}]}
    assert jdui.validar_mensagem(_msg('filecard',safe))[0]
    unsafe={'files':[{'name':'Admin','url':'/api/admin/users','kind':'pdf'}]}
    assert not jdui.validar_mensagem(_msg('filecard',unsafe))[0]
