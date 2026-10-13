"""Chat profissional: regenerar e continuar (agente + relay)."""
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import pc_agent
import server


def setup_module():
    os.environ['JULIA_USERNAME'] = 'efrai'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    server.login_failures.clear()


def login(client):
    r = client.post('/api/login', json={'username': 'efrai', 'password': 'strong-example-password'})
    assert r.status_code == 200, r.text
    return r.json()['csrf']


def umsg(i, texto='oi'):
    return {'id': i, 'origin': 'mobile', 'role': 'user', 'text': texto,
            'created_at': '2026-10-13T10:00:00.000Z', 'conversation_id': 'conv-pro'}


def test_reset_limpa_pedido_e_resposta(tmp_path):
    db = pc_agent.open_db(tmp_path / 'pro.sqlite3')
    pc_agent.persist_messages(db, [umsg('pro-user-01')])
    pc_agent.ai_marcar(db, 'pro-user-01', 'conv-pro', 'm', 'completed',
                       reply_id='pro-user-01-r1', response_text='velha')
    pc_agent.ai_guardar_resposta(db, 'pro-user-01', 'conv-pro', 'm', 'pro-user-01-r1', 'velha')
    r = pc_agent.ai_resetar(db, {'message_id': 'pro-user-01', 'conversation_id': 'conv-pro'})
    assert r.get('ok') is True
    assert pc_agent.ai_estado(db, 'pro-user-01') is None
    assert pc_agent.ai_resetar(db, {'message_id': 'curto', 'conversation_id': 'conv-pro'})['codigo'] == 'invalido'
    assert pc_agent.ai_resetar(db, {'message_id': 'pro-user-99', 'conversation_id': 'conv-pro'})['codigo'] == 'sem_mensagem'
    db.close()


def test_continue_anexa_mesmo_reply(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / 'pro2.sqlite3')
    pc_agent.persist_messages(db, [umsg('pro-user-02')])
    pc_agent.ai_marcar(db, 'pro-user-02', 'conv-pro', 'm', 'completed',
                       reply_id='pro-user-02-r1', response_text='Era uma vez')
    pc_agent.ai_guardar_resposta(db, 'pro-user-02', 'conv-pro', 'm', 'pro-user-02-r1', 'Era uma vez')
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 's',
           'context': 5, 'max_tokens': 50}
    monkeypatch.setattr('hermes_bridge.chat_complete',
                        lambda *a, **k: {"texto": "um reino distante.", "latencia_s": 0.1})
    r = pc_agent.ai_continuar(db, {'message_id': 'pro-user-02', 'conversation_id': 'conv-pro'}, cfg)
    assert r['reply_id'] == 'pro-user-02-r1'
    assert r['response_text'] == 'Era uma vez um reino distante.'
    rows = {m['id']: m for m in pc_agent.list_messages(db)}
    assert rows['pro-user-02-r1']['text'] == 'Era uma vez um reino distante.'
    assert pc_agent.ai_continuar(db, {'message_id': 'pro-user-99', 'conversation_id': 'conv-pro'}, cfg)['codigo'] == 'sem_resposta'
    db.close()


def test_orcamento_corta_antigas():
    hist = [{'role': 'user', 'content': 'x' * 5000} for _ in range(5)]
    out = pc_agent.aplicar_orcamento(hist, teto=12000)
    assert sum(len(m['content']) for m in out) <= 12000
    assert out[-1]['content'] == hist[-1]['content']  # recente preservada
    assert 'CONFIABILIDADE' in pc_agent.REGRAS_CONFIANCA and 'não sei' in pc_agent.REGRAS_CONFIANCA


def test_relay_regenerate_continue():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            out = {}

            def regen():
                out['r'] = client.post('/api/ai/regenerate',
                                       json={'message_id': 'pro-user-01', 'conversation_id': 'conv-pro'},
                                       headers={'X-CSRF-Token': csrf})

            def cont():
                out['c'] = client.post('/api/ai/continue',
                                       json={'message_id': 'pro-user-01', 'conversation_id': 'conv-pro'},
                                       headers={'X-CSRF-Token': csrf})

            t = threading.Thread(target=regen)
            t.start()
            req = ws.receive_json()
            assert req['type'] == 'ai_reset' and req['owner'] == 'efrai'
            ws.send_json({'request_id': req['request_id'], 'type': 'ai_reset_ok', 'reply_id': 'pro-user-01-r1'})
            t.join(timeout=8)
            assert out['r'].json() == {'ok': True, 'reply_id': 'pro-user-01-r1'}

            t = threading.Thread(target=cont)
            t.start()
            req = ws.receive_json()
            assert req['type'] == 'ai_continue' and req['owner'] == 'efrai'
            ws.send_json({'request_id': req['request_id'], 'type': 'ai_done', 'reply_id': 'pro-user-01-r1',
                          'response_text': 'completo', 'model': 'm'})
            t.join(timeout=8)
            assert out['c'].json()['response_text'] == 'completo'

            bad = client.post('/api/ai/regenerate', json={'message_id': 'x', 'conversation_id': 'conv-pro'},
                              headers={'X-CSRF-Token': csrf})
            assert bad.status_code == 422
