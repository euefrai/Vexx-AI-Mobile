"""Documentos + memória que aprende: extração, relevância, comandos e relay."""
import base64
import io
import os
import sys
import threading
from pathlib import Path

import pytest

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


def mem_db(tmp_path):
    db = pc_agent.open_db(tmp_path / 'mem.sqlite3')
    cols = [c[1] for c in db.execute("PRAGMA table_info(documents)").fetchall()]
    assert 'summary' in cols
    return db


# ── Extração ──────────────────────────────────────────────────────────
def test_txt_csv_html(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(db, 'notas.txt', ('Olá mundo. ' * 500).encode('utf-8'), 'conv-1')
    assert m['chunks'] >= 1 and m['chars'] > 100
    assert docs_agent.obter_texto(db, m['doc_id'])[:9] == 'Olá mundo'
    m2 = docs_agent.salvar_documento(db, 'dados.csv', b'nome,idade\nana,30\nbob,25\n', 'conv-1')
    assert 'ana | 30' in docs_agent.obter_texto(db, m2['doc_id'])
    m3 = docs_agent.salvar_documento(db, 'pag.html', b'<html><body><h1>Titulo</h1><script>x()</script><p>Corpo aqui.</p>', 'conv-1')
    txt = docs_agent.obter_texto(db, m3['doc_id'])
    assert 'Titulo' in txt and 'x()' not in txt
    assert len(docs_agent.listar_documentos(db)) == 3
    db.close()


def test_docx_xlsx(tmp_path):
    docx = pytest.importorskip('docx')
    oxl = pytest.importorskip('openpyxl')
    db = mem_db(tmp_path)
    buf = io.BytesIO()
    d = docx.Document()
    d.add_paragraph('Contrato de teste da Júlia')
    d.save(buf)
    m = docs_agent.salvar_documento(db, 'contrato.docx', buf.getvalue(), 'conv-2')
    assert 'Júlia' in docs_agent.obter_texto(db, m['doc_id'])
    wb = oxl.Workbook()
    ws = wb.active
    ws.append(['item', 'valor'])
    ws.append(['caneta', 5])
    buf2 = io.BytesIO()
    wb.save(buf2)
    m2 = docs_agent.salvar_documento(db, 'plan.xlsx', buf2.getvalue(), 'conv-2')
    assert 'caneta | 5' in docs_agent.obter_texto(db, m2['doc_id'])
    db.close()


def test_rejeita_formato_e_tamanho(tmp_path):
    db = mem_db(tmp_path)
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'foto.png', b'\x89PNG' + b'0' * 100, 'c')
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'vazio.txt', b'   ', 'c')
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'grande.txt', b'x' * (docs_agent.MAX_BYTES + 1), 'c')
    db.close()


def test_trechos_relevantes(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(
        db, 'manual.txt',
        ('O reembolso de viagens precisa de nota fiscal. O prazo do reembolso é 30 dias. '
         'O estacionamento é pago à parte.' * 20).encode('utf-8'), 'conv-9')
    got = docs_agent.trechos_relevantes(db, 'qual o prazo do reembolso?', m['doc_id'])
    assert got and 'reembolso' in got[0]['trecho'].lower()
    db.close()


# ── Memória que aprende ───────────────────────────────────────────────
def test_fatos_e_relevancia(tmp_path):
    db = mem_db(tmp_path)
    pc_agent.guardar_fato(db, 'nome', 'Efrain Silva', 'chat')
    pc_agent.guardar_fato(db, 'projeto_alpha', 'app de finanças em Python', 'llm')
    assert any(f['key'] == 'nome' for f in pc_agent.ler_memorias(db))
    rel = pc_agent.memorias_relevantes(db, 'qual é o meu nome?')
    assert rel and rel[0]['key'] == 'nome'
    rel2 = pc_agent.memorias_relevantes(db, 'me conta do projeto de finanças')
    assert any(f['key'] == 'projeto_alpha' for f in rel2)
    db.close()


def test_comandos_de_memoria(tmp_path):
    db = mem_db(tmp_path)
    vazio = pc_agent.interpretar_comando_memoria(db, 'o que você sabe sobre mim?')
    assert vazio and vazio[1] == 'mem_vazia'
    pc_agent.guardar_fato(db, 'foco', 'produtividade')
    lista = pc_agent.interpretar_comando_memoria(db, 'mostre sua memória')
    assert lista and 'produtividade' in lista[0]
    esquecer = pc_agent.interpretar_comando_memoria(db, 'esqueça produtividade')
    assert esquecer and esquecer[1] == 'mem_esquecer'
    assert pc_agent.interpretar_comando_memoria(db, 'qual a capital do Brasil?') is None
    db.close()


def test_ai_responde_memoria_sem_llm(tmp_path, monkeypatch):
    db = mem_db(tmp_path)
    pc_agent.persist_messages(db, [{
        'id': 'mem-user-001', 'origin': 'mobile', 'role': 'user',
        'text': 'o que você sabe sobre mim? Por favor me diga tudo.',
        'created_at': '2026-10-12T12:00:00.000Z', 'conversation_id': 'conv-mem'}])
    pc_agent.guardar_fato(db, 'nome', 'Efrain')
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'fake', 'system': 's',
           'context': 5, 'max_tokens': 50}

    def _boom(*a, **k):
        raise AssertionError('LLM não deveria ser chamado para comando de memória')

    monkeypatch.setattr('hermes_bridge.chat_complete', _boom)
    r = pc_agent.ai_completa(db, {'message_id': 'mem-user-001', 'conversation_id': 'conv-mem'}, cfg)
    assert 'Efrain' in r['response_text']
    assert r['reply_id'] == 'mem-user-001-r1'
    db.close()


def test_doc_mencionado_e_intencoes(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(db, 'contrato-aluguel.txt', 'cláusula sobre multa de aluguel'.encode('utf-8'), 'conv-d')
    assert pc_agent.doc_mencionado(db, 'qual a multa no contrato-aluguel?', 'conv-d') == m['doc_id']
    assert pc_agent.doc_mencionado(db, 'resuma o documento pra mim', 'conv-d') == m['doc_id']
    assert pc_agent.doc_mencionado(db, 'qual a capital do Peru?', 'conv-d') == ''
    assert pc_agent.intencao_pesquisa('pesquise o preço do dólar hoje com fontes')
    assert not pc_agent.intencao_pesquisa('me conta uma piada')
    assert pc_agent.intencao_imagem('mostre uma imagem de um gato astronauta')
    db.close()


# ── Relay: docs + memories via agente fake ────────────────────────────
def _agent_loop(ws, handlers):
    while True:
        try:
            req = ws.receive_json()
        except Exception:
            return
        fn = handlers.get(req.get('type'))
        if fn is None:
            continue
        ws.send_json({'request_id': req['request_id'], **fn(req)})


def test_relay_docs_e_memories():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            handlers = {
                'doc_upload': lambda r: {'type': 'doc_uploaded', 'doc_id': 'doc-abc123',
                                         'name': 'a.txt', 'ext': '.txt', 'chars': 10,
                                         'chunks': 1, 'paginas_aprox': 1},
                'doc_list': lambda r: {'type': 'doc_list', 'documents': []},
                'doc_resumo': lambda r: {'type': 'doc_resumo', 'doc_id': r['doc_id'], 'resumo': 'RES'},
                'mem_list': lambda r: {'type': 'mem_list',
                                       'memories': [{'key': 'nome', 'value': 'X', 'updated_at': 't'}]},
                'mem_forget': lambda r: {'type': 'mem_forgotten', 'key': r['key']},
            }
            t = threading.Thread(target=_agent_loop, args=(ws, handlers), daemon=True)
            t.start()

            up = client.post('/api/docs/upload', files={'file': ('a.txt', b'conteudo aqui')},
                             data={'conversation_id': 'conv-001'},
                             headers={'X-CSRF-Token': csrf})
            assert up.status_code == 200, up.text
            assert up.json()['doc_id'] == 'doc-abc123'

            docs = client.get('/api/docs')
            assert docs.status_code == 200, docs.text

            bad = client.post('/api/docs/resumo', json={'doc_id': '!!'},
                              headers={'X-CSRF-Token': csrf})
            assert bad.status_code == 422

            ok = client.post('/api/docs/resumo', json={'doc_id': 'doc-abc123'},
                             headers={'X-CSRF-Token': csrf})
            assert ok.json() == {'doc_id': 'doc-abc123', 'resumo': 'RES'}

            mem = client.get('/api/memories')
            assert mem.json()['memories'][0]['key'] == 'nome'
            forg = client.delete('/api/memories/nome', headers={'X-CSRF-Token': csrf})
            assert forg.json() == {'ok': True, 'key': 'nome'}
            assert client.delete('/api/memories/IN-VÁLIDA!', headers={'X-CSRF-Token': csrf}).status_code == 422

            empty = client.post('/api/docs/upload', files={'file': ('e.txt', b'')},
                                data={'conversation_id': 'conv-001'},
                                headers={'X-CSRF-Token': csrf})
            assert empty.status_code == 422
