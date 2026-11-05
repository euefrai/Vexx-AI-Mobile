"""Public distribution, account isolation, local consent and real filename indexing."""
import asyncio
import io
import json
import sqlite3
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import companion_api
import companion_registry
import julia_auth
import server
from pc_companion.app import create_app
from pc_companion.connection import Connection, relay_url
from pc_companion.indexer import FileIndex


@pytest.fixture
def relay_client(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / 'accounts.sqlite3', check_same_thread=False)
    julia_auth.criar_tabelas(db)
    users = {name: julia_auth.criar_usuario(db, name, name.title(), 'qa-companion-password', criado_por='local')['uid']
             for name in ('alice', 'bruno')}
    monkeypatch.setenv('JULIA_SESSION_SECRET', 'qa-companion-only-secret-' * 3)
    async def owner(request):
        return users[request.headers.get('x-account', 'alice')]
    def csrf(request):
        if request.headers.get('x-csrf-token') != 'qa-local':
            from fastapi import HTTPException
            raise HTTPException(403)
    async def exchange(req, **kwargs):
        assert req['type'] == 'companion_registry', 'Public PC must not dispatch to central desktop'
        return companion_registry.handle(db, req)
    monkeypatch.setattr(server, 'revogacao_ok', owner)
    monkeypatch.setattr(server, 'require_csrf', csrf)
    monkeypatch.setattr(server.relay, 'exchange', exchange)
    hub = server.companion_hub
    hub.codes.clear(); hub.cache.clear(); hub.connections.clear()
    with TestClient(server.app) as client:
        yield client, users, db
    hub.codes.clear(); hub.cache.clear(); hub.connections.clear()
    db.close()


HEADERS = {'X-CSRF-Token': 'qa-local'}


def test_persistent_nick_pin_connect_rotate_delete_and_unlink(relay_client):
    client, users, db = relay_client
    identity = {'nick':'Alice-PC', 'pin':'672938'}
    assert client.post('/api/companion/identity', json=identity).status_code == 403
    assert client.post('/api/companion/identity', headers=HEADERS, json=identity).status_code == 200
    state = client.get('/api/companion/identity', headers=HEADERS).json()
    assert state == {'configured':True, 'nick':'alice-pc'}
    stored = db.execute('SELECT pin_hash FROM companion_identities WHERE owner=?', (users['alice'],)).fetchone()[0]
    assert stored != identity['pin'] and stored.startswith('scrypt$')
    claim = {'nick':'ALICE-PC','pin':identity['pin'],'name':'QA Windows'}
    response = client.post('/api/companion/connect',json=claim)
    assert response.status_code == 200
    token = response.json()['token'];device=response.json()['device_id']
    assert companion_registry.handle(db, {'owner':users['alice'],'action':'validate','device_id':device,'token':token})['allowed']
    assert client.post('/api/companion/unlink',headers=HEADERS).status_code == 200
    assert client.get('/api/companion/identity',headers=HEADERS).json()==state
    assert client.post('/api/companion/connect',json=claim).status_code == 200
    assert client.post('/api/companion/identity',headers=HEADERS,json={'nick':'alice-new','pin':'481926'}).status_code == 200
    assert client.post('/api/companion/connect',json=claim).status_code == 403
    assert not companion_registry.handle(db, {'owner':users['alice'],'action':'validate','device_id':device,'token':token})['allowed']
    claim.update(nick='alice-new',pin='481926')
    assert client.post('/api/companion/connect',json=claim).status_code == 200
    assert client.delete('/api/companion/identity',headers=HEADERS).status_code == 200
    assert client.get('/api/companion/identity',headers=HEADERS).json()=={'configured':False,'nick':''}
    assert client.post('/api/companion/connect',json=claim).status_code == 403


def test_nick_uniqueness_owner_isolation_and_stale_generation(relay_client):
    client, users, db = relay_client
    identity={'nick':'shared-name','pin':'987652'}
    assert client.post('/api/companion/identity',headers=HEADERS,json=identity).status_code==200
    assert client.post('/api/companion/identity',headers={**HEADERS,'x-account':'bruno'},json=identity).status_code==409
    assert client.get('/api/companion/identity',headers={**HEADERS,'x-account':'bruno'}).json()['configured'] is False
    authenticated=companion_registry.handle(db,{'action':'authenticate_identity',**identity})
    assert authenticated['owner']==users['alice']
    client.delete('/api/companion/identity',headers=HEADERS)
    stale=companion_registry.handle(db,{'action':'enroll','owner':users['alice'],'generation':authenticated['generation'],'device_id':'a'*32,'token_hash':'b'*64})
    assert stale['denied']


def test_pin_throttle_survives_registry_calls_and_rejects_inactive_account(relay_client):
    client, users, db=relay_client
    identity={'nick':'locked-pc','pin':'238194'}
    client.post('/api/companion/identity',headers=HEADERS,json=identity)
    for _ in range(5):
        assert companion_registry.handle(db,{'action':'authenticate_identity',**identity,'pin':'000000'})['denied']
    assert companion_registry.handle(db,{'action':'authenticate_identity',**identity})['denied']
    db.execute('UPDATE companion_identities SET locked_until=0');db.commit()
    assert companion_registry.handle(db,{'action':'authenticate_identity',**identity})['owner']==users['alice']
    db.execute("UPDATE users SET status='bloqueado' WHERE uid=?",(users['alice'],));db.commit()
    assert companion_registry.handle(db,{'action':'authenticate_identity',**identity})['denied']


def test_identity_profile_survives_sqlite_reopen(tmp_path):
    path=tmp_path/'accounts.sqlite3'
    db=sqlite3.connect(path);julia_auth.criar_tabelas(db)
    user=julia_auth.criar_usuario(db,'persist-user','QA','fixture-password',criado_por='local')['uid']
    assert companion_registry.handle(db,{'owner':user,'action':'identity_set','nick':'persist-pc','pin':'112738'})['ok']
    db.close();db=sqlite3.connect(path)
    assert companion_registry.handle(db,{'action':'authenticate_identity','nick':'persist-pc','pin':'112738'})['owner']==user
    db.close()


def enroll(client, name='Alice-PC', account='alice'):
    code = client.post('/api/companion/pair', headers={**HEADERS, 'x-account': account}).json()['code']
    r = client.post('/api/companion/claim', json={'code': code, 'name': name})
    assert r.status_code == 200, r.text
    return code, r.json()['token']


def test_bundle_is_complete_allowlist_without_private_files():
    with zipfile.ZipFile(io.BytesIO(companion_api.bundle())) as archive:
        names = archive.namelist()
        assert len(names) == len(companion_api.BUNDLE_FILES) + 2
        assert 'Vexx-PC/Instalar.cmd' in names
        assert 'Vexx-PC/remoto.py' in names
        assert not any(name.endswith(('.db', '.sqlite3', '.log', '.env')) for name in names)
        for name in names:
            assert not name.startswith('/') and '..' not in Path(name).parts
        assert 'JULIA_AGENT_TOKEN' not in archive.read('Vexx-PC/pc_companion/app.py').decode()


def test_public_routes_require_account_and_csrf():
    with TestClient(server.app) as client:
        for path in ('pair', 'unlink'):
            assert client.post('/api/companion/' + path).status_code == 401
        assert client.get('/api/companion/status').status_code == 401
        assert client.get('/api/companion/screen').status_code == 401
        assert client.post('/api/companion/input', json={'kind':'key','key':'enter'}).status_code == 401
        assert client.get('/downloads/vexx-pc-agent-windows.zip').status_code == 200


def test_pairing_single_use_expiry_account_and_persistent_revocation(relay_client):
    client, users, db = relay_client
    assert client.post('/api/companion/pair').status_code == 403
    code, token = enroll(client)
    assert client.post('/api/companion/claim', json={'code': code, 'name': 'Replay'}).status_code == 400
    assert client.get('/api/companion/status', headers=HEADERS).json()['name'] == 'Alice-PC'
    assert not client.get('/api/companion/status', headers={**HEADERS, 'x-account': 'bruno'}).json()['linked']
    assert client.get('/api/companion/screen', headers=HEADERS).status_code == 503
    assert client.get('/api/companion/screen', headers={**HEADERS, 'x-account': 'bruno'}).status_code == 403
    expiring = client.post('/api/companion/pair', headers=HEADERS).json()['code']
    server.companion_hub.codes[expiring]['until'] = 0
    assert client.post('/api/companion/claim', json={'code': expiring, 'name': 'Expired'}).status_code == 400
    assert client.post('/api/companion/unlink', headers=HEADERS).status_code == 200
    server.companion_hub.cache.clear()  # restart loses cache, not revocation
    state = companion_registry.handle(db, {'owner': users['alice'], 'action': 'status'})
    assert state['linked'] and not state['active']
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/companion/ws', headers={'Authorization':'Bearer '+token}):
            pass


def test_outbound_socket_routes_only_owners_and_device_revoke(relay_client):
    client, users, db = relay_client
    _, token = enroll(client)
    with client.websocket_connect('/api/companion/ws', headers={'Authorization': 'Bearer '+token}) as ws:
        assert client.get('/api/companion/status', headers=HEADERS).json()['online']
        with ThreadPoolExecutor() as pool:
            response = pool.submit(client.get, '/api/companion/screen', headers=HEADERS)
            req = ws.receive_json()
            assert req['type'] == 'screen' and 'owner' not in req
            ws.send_json({'request_id':req['request_id'], 'type':'screen_error', 'error':'Local permission required'})
            assert response.result(timeout=5).status_code == 403
        assert client.get('/api/companion/remote/status', headers={**HEADERS, 'x-account':'bruno'}).json()['offline']
    assert client.post('/api/companion/device-revoke', headers={'Authorization':'Bearer '+token}).status_code == 200
    assert client.post('/api/companion/device-revoke', headers={'Authorization':'Bearer '+token}).status_code == 401


def test_pair_limits_and_forged_credentials(relay_client):
    client, _, _ = relay_client
    for _ in range(5):
        assert client.post('/api/companion/pair', headers=HEADERS).status_code == 200
    assert client.post('/api/companion/pair', headers=HEADERS).status_code == 429
    assert client.post('/api/companion/device-revoke', headers={'Authorization':'Bearer forged'}).status_code == 401


def test_filename_index_real_scan_metadata_deletion_and_no_query_disk_scan(tmp_path, monkeypatch):
    root = tmp_path / 'documents'; root.mkdir()
    nested = root / 'projects'; nested.mkdir()
    (nested / 'relatório-final.pdf').write_bytes(b'x' * 12345)
    (root / 'photo.jpg').write_bytes(b'abc')
    ignored = root / 'node_modules'; ignored.mkdir(); (ignored / 'hidden.pdf').touch()
    index = FileIndex(tmp_path / 'index.sqlite3', [root])
    index.scan()
    result = index.search('final')
    assert result['items'][0]['size'] == 12345
    assert index.search('projects')['items'][0]['size'] == 12345
    assert not index.search('hidden')['items']
    assert index.search('ab')['hint']
    assert not index.search('" OR *')['items']
    (nested / 'relatório-final.pdf').unlink(); index.scan()
    assert not index.search('final')['items']
    monkeypatch.setattr('os.scandir', lambda *_: pytest.fail('Search must not scan filesystem'))
    assert index.search('photo')['items'][0]['size'] == 3


def test_search_large_index_pagination_and_bounded_latency(tmp_path):
    index = FileIndex(tmp_path / 'large.sqlite3', [])
    with index.db() as db:
        db.executemany('INSERT INTO files VALUES (?,?,?,?,?,?)',
                       ((f'/qa/{n}', f'file-{n:06d}.txt', n, 0, 0, 'qa') for n in range(100000)))
        db.commit()
    result = index.search('.txt')
    assert len(result['items']) == 60 and result['more']
    assert result['ms'] < 500
    second = index.search('.txt', 60)
    assert not set(i['path'] for i in result['items']) & set(i['path'] for i in second['items'])


def test_local_api_host_origin_tokens_copilot_and_pause(tmp_path):
    app = create_app(tmp_path / 'local', [])
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/status').status_code == 401
        assert client.get('/api/bootstrap').status_code == 401
        assert client.get('/').status_code == 200
        token = client.get('/api/bootstrap').json()['token']
        h = {'X-Vexx-Token': token}
        assert client.get('/api/status', headers={**h,'Host':'evil.example'}).status_code == 403
        assert client.post('/api/action', headers={**h,'Origin':'https://evil.example'},json={'action':'allow'}).status_code == 403
        assert client.post('/api/action', headers=h, content=b'x'*8193).status_code == 413
        assert not client.get('/api/status',headers=h).json()['connection']['approved']
        assert client.post('/api/action',headers=h,json={'action':'allow','control':True}).status_code == 200
        assert client.get('/api/status',headers=h).json()['connection']['control_allowed']
        assert client.post('/api/copilot',headers=h,json={'text':'pausar acesso'}).status_code == 200
        assert not client.get('/api/status',headers=h).json()['connection']['approved']
        assert client.post('/api/copilot',headers=h,json={'text':'buscar relatorio.pdf'}).json()['search'] == 'relatorio.pdf'
        assert client.post('/api/action',headers=h,json={'action':'execute','cmd':'anything'}).status_code == 400
        for path in ('/api/action', '/api/copilot', '/api/pair'):
            assert client.post(path, headers=h, json=[]).status_code == 400
            assert client.post(path, headers=h, content='{bad').status_code == 400


def test_replaced_device_cannot_reauthenticate(relay_client):
    client, users, db = relay_client
    _, old = enroll(client)
    _, new = enroll(client, 'Replacement')
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/companion/ws', headers={'Authorization':'Bearer '+old}):
            pass
    with client.websocket_connect('/api/companion/ws', headers={'Authorization':'Bearer '+new}):
        assert client.get('/api/companion/status',headers=HEADERS).json()['online']
    assert client.get('/api/companion/status',headers=HEADERS).json()['name'] == 'Replacement'


def test_connection_local_permission_expiry_revoke_and_no_native_input(monkeypatch):
    import remoto
    async def scenario():
        c = Connection({}, lambda:None, lambda _:None)
        monkeypatch.setattr(remoto, 'executar', lambda *a,**kw: pytest.fail('Native input executed without consent'))
        cmd = {'type':'input','cmd':{'kind':'key','key':'enter'}}
        assert (await c.handle(cmd))['codigo'] == 'sem_permissao'
        await c.permission(True, False)
        assert (await c.handle(cmd))['codigo'] == 'sem_permissao'
        await c.permission(True, True)
        c.grant_until = 0
        assert (await c.handle(cmd))['codigo'] == 'sem_permissao'
        await c.permission(True, True)
        await c.handle({'type':'remote_request'})
        assert (await c.handle(cmd))['codigo'] == 'sem_permissao'
        await c.handle({'type':'remote_revoke'})
        assert not c.status()['approved']
    asyncio.run(scenario())


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com', 'https://example.com/path', 'https://example.com?token=x'])
def test_relay_url_rejects_unsafe_origins(url):
    with pytest.raises(ValueError): relay_url(url)
