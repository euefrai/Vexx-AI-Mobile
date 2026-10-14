import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import pc_agent
import server


def setup_module():
    os.environ['fajulto_USERNAME'] = 'efrai'
    os.environ['fajulto_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['fajulto_SESSION_SECRET'] = 'a' * 64
    os.environ['fajulto_AGENT_TOKEN'] = 'b' * 64


def authenticate(client):
    r = client.post('/api/login', json={'username': 'efrai', 'password': 'strong-example-password'})
    assert r.status_code == 200, r.text
    assert r.cookies.get('fajulto_session')
    assert 'httponly' in r.headers.get('set-cookie', '').lower()
    return r.json()['csrf']


def msg(i='message001'):
    return {'id': i, 'origin': 'mobile', 'role': 'user', 'text': 'testando offline',
            'created_at': '2026-10-10T20:00:00.000Z', 'conversation_id': 'conversation-001'}


def test_pc_sqlite_durable_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'local' / 'memory.sqlite3'
        db = pc_agent.open_db(path)
        assert pc_agent.persist_messages(db, [msg()]) == ['message001']
        assert pc_agent.persist_messages(db, [msg()]) == ['message001']
        db.close()
        assert path.exists()
        db = pc_agent.open_db(path)
        rows = pc_agent.list_messages(db)
        assert len(rows) == 1
        assert rows[0]['text'] == 'testando offline'
        db.close()


def test_no_persistence_on_render_and_auth_required():
    with TestClient(server.app) as client:
        assert client.get('/api/status').status_code == 401
        assert client.get('/api/messages').status_code == 401
        assert client.post('/api/sync', json={'messages': [msg()]}).status_code == 401
        assert client.post('/api/login', json={'username': 'efrai', 'password': 'incorrect'}).status_code == 401
        assert client.get('/server.py').status_code == 404  # private agent/backend code never served
        assert client.get('/pc_agent.py').status_code == 404
        assert client.get('/api/health').json()['configured'] is True
        csrf = authenticate(client)
        assert client.get('/api/status').json()['pc_online'] is False
        assert client.post('/api/sync', json={'messages': [msg()]}).status_code == 403
        r = client.post('/api/sync', json={'messages': [msg()]}, headers={'X-CSRF-Token': csrf})
        assert r.status_code == 503  # PC offline: browser must RETAIN its IndexedDB messages


def test_real_relay_ack_only_after_agent_message():
    with TestClient(server.app) as client:
        csrf = authenticate(client)
        with client.websocket_connect('/api/agent/ws', headers={'Authorization': 'Bearer ' + os.environ['fajulto_AGENT_TOKEN']}) as ws:
            assert client.get('/api/status').json()['pc_online'] is True
            result = {}
            def submit():
                result['response'] = client.post('/api/sync', json={'messages': [msg()]}, headers={'X-CSRF-Token': csrf})
            thread = threading.Thread(target=submit)
            thread.start()
            for _ in range(3):
                req = ws.receive_json()
                if req['type'] == 'sess_revogados':
                    ws.send_json({'request_id': req['request_id'],
                                  'type': 'sess_revogados', 'sids': []})
                    continue
                break
            assert req['type'] == 'sync'
            assert req['messages'][0]['id'] == 'message001'
            ws.send_json({'request_id': req['request_id'], 'type': 'ack', 'confirmed_ids': ['message001']})
            thread.join(timeout=6)
            assert not thread.is_alive()
            assert result['response'].status_code == 200, result['response'].text
            assert result['response'].json()['confirmed_ids'] == ['message001']
        assert client.get('/api/status').json()['pc_online'] is False


def test_agent_auth_rejected():
    with TestClient(server.app) as client:
        try:
            with client.websocket_connect('/api/agent/ws', headers={'Authorization': 'Bearer wrong'}) as ws:
                ws.receive_text()
        except Exception:
            pass
        else:
            raise AssertionError('Unauthorized websocket should close')


def test_diag_publico_sem_auth_e_status_com_idade():
    import json as _json
    with TestClient(server.app) as client:
        d = client.get('/api/diag')
        assert d.status_code == 200
        corpo = d.json()
        assert corpo['pc_online'] is False and corpo['agente_ha'] == -1
        assert isinstance(corpo.get('commit'), str)
        assert isinstance(corpo.get('instance'), str) and len(corpo['instance']) == 8
        csrf = authenticate(client)
        st = client.get('/api/status')
        assert st.json()['pc_online'] is False and st.json()['agente_ha'] == -1
        with client.websocket_connect('/api/agent/ws', headers={'Authorization': 'Bearer ' + os.environ['fajulto_AGENT_TOKEN']}) as ws:
            assert client.get('/api/status').json()['pc_online'] is True
            assert client.get('/api/diag').json()['pc_online'] is True


def test_bloqueio_vira_403_explicavel_nao_503():
    """Regressão do apagão: conta bloqueada gerava 503 'conectividade'.
    Agora o relay traduz codigo=bloqueada em 403 com mensagem clara."""
    with TestClient(server.app) as client:
        csrf = authenticate(client)
        with client.websocket_connect('/api/agent/ws', headers={'Authorization': 'Bearer ' + os.environ['fajulto_AGENT_TOKEN']}) as ws:
            result = {}

            def submit():
                result['response'] = client.post('/api/sync', json={'messages': [msg()]}, headers={'X-CSRF-Token': csrf})

            thread = threading.Thread(target=submit)
            thread.start()
            req = ws.receive_json()
            assert req['type'] == 'sync'
            ws.send_json({'request_id': req['request_id'], 'type': 'op_error',
                          'error': 'Conta indisponível.', 'codigo': 'bloqueada'})
            thread.join(timeout=6)
            assert result['response'].status_code == 403, result['response'].text
            assert 'Conta indispon' in result['response'].json()['detail']


def test_wrong_origin_rejected():
    with TestClient(server.app) as client:
        csrf = authenticate(client)
        r = client.post('/api/sync', json={'messages': [msg()]}, headers={
            'X-CSRF-Token': csrf, 'Origin': 'https://attacker.invalid'})
        assert r.status_code == 403
