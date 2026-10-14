"""Isolamento por dono (§9, §11, teste 6 do spec): B nunca vê nem apaga nada de A."""
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import docs_agent
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


def msg(i, conv, texto='oi'):
    return {'id': i, 'origin': 'mobile', 'role': 'user', 'text': texto,
            'created_at': '2026-10-13T10:00:00.000Z', 'conversation_id': conv}


def test_mensagens_isoladas(tmp_path):
    db = pc_agent.open_db(tmp_path / 'iso.sqlite3')
    assert pc_agent.persist_messages(db, [msg('a-user-001', 'conv-a', 'segredo de A')], owner='alice') == ['a-user-001']
    assert pc_agent.list_messages(db, owner='alice')[0]['text'] == 'segredo de A'
    assert pc_agent.list_messages(db, owner='bob') == []
    assert pc_agent.list_messages(db) == []  # padrão local não vaza
    assert pc_agent.listar_conversas(db, owner='bob') == []
    assert len(pc_agent.listar_conversas(db, owner='alice')) == 1
    assert pc_agent.contexto_conversa(db, 'conv-a', 10, owner='bob') == []
    db.close()


def test_memorias_isoladas(tmp_path):
    db = pc_agent.open_db(tmp_path / 'iso2.sqlite3')
    pc_agent.guardar_fato(db, 'nome', 'Alice', owner='alice')
    assert pc_agent.ler_memorias(db, owner='bob') == []
    assert pc_agent.memorias_relevantes(db, 'qual meu nome', owner='bob') == []
    assert pc_agent.memoria_global(db, 'x', owner='bob') == []
    assert pc_agent.interpretar_comando_memoria(db, 'o que você sabe sobre mim?', owner='bob')[1] == 'mem_vazia'
    db.close()


def test_docs_e_uistate_isolados(tmp_path):
    db = pc_agent.open_db(tmp_path / 'iso3.sqlite3')
    m = docs_agent.salvar_documento(db, 'segredo.txt', b'dados de alice', 'conv-a', owner='alice')
    assert docs_agent.listar_documentos(db, owner='bob') == []
    assert docs_agent.obter_texto(db, m['doc_id'], owner='bob') == ''
    assert docs_agent.trechos_relevantes(db, 'dados', m['doc_id'], owner='bob') == []
    try:
        docs_agent.resumir_documento(db, {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm'}, m['doc_id'], owner='bob')
        raise AssertionError('deveria negar')
    except docs_agent.DocErro as exc:
        assert exc.codigo == 'nao_encontrado'
    with db:
        db.execute("INSERT INTO ui_state (k, message_id, slot, state, updated_at, owner_id)"
                   " VALUES ('k1','m','s','{}','t','alice')")
    rows = db.execute("SELECT k FROM ui_state WHERE owner_id='bob'").fetchall()
    assert rows == []
    db.close()


def test_ai_replay_nao_vaza_entre_donos(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / 'iso4.sqlite3')
    pc_agent.persist_messages(db, [msg('r-user-001', 'conv-a')], owner='alice')
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 's',
           'context': 5, 'max_tokens': 50}
    monkeypatch.setattr('hermes_bridge.chat_complete',
                        lambda *a, **k: {"texto": "RESP", "latencia_s": 0.1})
    monkeypatch.setattr('pc_agent.aprender_com_conversa', lambda *a, **k: None)
    r = pc_agent.ai_completa(db, {'message_id': 'r-user-001', 'conversation_id': 'conv-a',
                                  'owner': 'alice'}, cfg)
    assert r['response_text'] == 'RESP'
    # bob pedindo o MESMO id: mensagem não encontrada (não replay de alice)
    r2 = pc_agent.ai_completa(db, {'message_id': 'r-user-001', 'conversation_id': 'conv-a',
                                   'owner': 'bob'}, cfg)
    assert r2.get('codigo') == 'sem_mensagem'
    # com contas existindo, desconhecido é barrado na porta
    import julia_auth as _ja
    _ja.criar_usuario(db, 'carol', 'Carol', 'senha-forte-1', criado_por='t')
    r3 = pc_agent.ai_completa(db, {'message_id': 'r-user-001', 'conversation_id': 'conv-a',
                                   'owner': 'dave'}, cfg)
    assert r3.get('codigo') == 'bloqueada'
    db.close()


def test_dono_legado_vale_mesmo_com_usuarios(tmp_path):
    from pathlib import Path as _P
    import tempfile as _t
    import julia_auth as _ja
    db = pc_agent.open_db(_P(_t.mkdtemp()) / 'leg.sqlite3')
    pc_agent.guardar_fato(db, 'nome', 'Amigo', owner='u-abc123')
    # sem contas: legado vale, desconhecido passa mas nada vaza (leituras filtram)
    assert pc_agent.dono_bloqueado(db, 'local') is False
    assert pc_agent.dono_bloqueado(db, 'u-xyz') is False
    _ja.criar_usuario(db, 'carol', 'Carol', 'senha-forte-1', criado_por='t')
    # com contas: desconhecido barra, legado continua valendo
    assert pc_agent.dono_bloqueado(db, 'local') is False
    assert pc_agent.dono_bloqueado(db, 'u-xyz') is True
    # linha local bloqueada pelo admin: bloqueia de verdade
    _ja.vincular_proprietario(db, 'dono', 'Dono', 'senha-forte-1')
    _ja.definir_status(db, 'u-abc123', 'local', 'bloqueado')
    assert pc_agent.dono_bloqueado(db, 'local') is True
    db.close()


def test_conv_forget_limitado_ao_dono(tmp_path):
    db = pc_agent.open_db(tmp_path / 'iso5.sqlite3')
    pc_agent.persist_messages(db, [msg('d-user-01', 'conv-a')], owner='alice')
    with db:
        cur = db.execute("DELETE FROM messages WHERE origin='mobile' AND owner_id='bob' "
                         "AND conversation_id='conv-a'")
        assert (cur.rowcount or 0) == 0
    assert len(pc_agent.list_messages(db, owner='alice')) == 1
    db.close()


def test_relay_repasse_owner_e_isolamento():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            vistos = {}

            def agente():
                for _ in range(4):
                    req = ws.receive_json()
                    vistos[req['type']] = req.get('owner')
                    if req['type'] == 'sess_revogados':
                        ws.send_json({'request_id': req['request_id'],
                                      'type': 'sess_revogados', 'sids': []})
                    elif req['type'] == 'sync':
                        ws.send_json({'request_id': req['request_id'], 'type': 'ack', 'confirmed_ids': []})
                    elif req['type'] == 'list':
                        ws.send_json({'request_id': req['request_id'], 'type': 'history',
                                      'messages': [{'id': 'x-user-001', 'conversation_id': 'c',
                                                    'origin': 'mobile', 'role': 'user', 'text': 'de outro?',
                                                    'created_at': '2026-10-13T10:00:00Z'}]})
                    elif req['type'] == 'mem_list':
                        ws.send_json({'request_id': req['request_id'], 'type': 'mem_list', 'memories': []})

            t = threading.Thread(target=agente, daemon=True)
            t.start()
            client.post('/api/sync', json={'messages': [msg('s-user-01', 'conv-x')]},
                        headers={'X-CSRF-Token': csrf})
            client.get('/api/messages', headers={'X-CSRF-Token': csrf})
            client.get('/api/memories', headers={'X-CSRF-Token': csrf})
            t.join(timeout=8)
            # relay sempre informa o dono autenticado; agente filtra por ele
            # (login legado = dono 'local')
            assert vistos.get('sync') == 'local', vistos
            assert vistos.get('list') == 'local', vistos
            assert vistos.get('mem_list') == 'local', vistos
