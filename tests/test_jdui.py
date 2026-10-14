"""JDUI schema: válidos, inválidos, limites e segurança (§18)."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import pc_agent
import server
from argon2 import PasswordHasher
from fastapi.testclient import TestClient


def _login(client):
    os.environ['JULIA_USERNAME'] = 'efrai'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    server.login_failures.clear()
    r = client.post('/api/login', json={'username': 'efrai', 'password': 'strong-example-password'})
    assert r.status_code == 200, r.text
    return r.json()['csrf']


def quiz_ok():
    return {"version": "JULIA-ui-message/v1", "blocks": [
        {"type": "text", "content": "Teste seus conhecimentos:"},
        {"type": "ui", "component": "quiz", "props": {
            "title": "Python",
            "questions": [
                {"q": "2+2?", "options": ["3", "4"], "answer": 1, "explain": "Soma."},
                {"q": "Tipo de []?", "options": ["list", "dict", "tupla"], "answer": 0},
            ]}}]}


def test_valido_quiz():
    ok, norm, erros = jdui.validar_mensagem(quiz_ok())
    assert ok and norm['blocks'][1]['props']['questions'][0]['answer'] == 1


def test_todos_componentes_validos():
    msg = {"version": "JULIA-ui-message/v1", "blocks": [
        {"type": "ui", "component": "checklist",
         "props": {"title": "Estudos", "items": ["Ler cap.1", {"label": "Exercícios", "checked": True}]}},
        {"type": "ui", "component": "calculator", "props": {"kind": "imc"}},
        {"type": "ui", "component": "cards", "props": {"items": [
            {"title": "Python", "desc": "Linguagem", "value": "9.5", "badge": "top",
             "url": "https://python.org", "action": {"chat": "Detalhe Python"}}]}},
        {"type": "ui", "component": "diagram", "props": {
            "direction": "v",
            "nodes": [{"id": "a", "label": "Celular"}, {"id": "b", "label": "PC"}],
            "edges": [{"from": "a", "to": "b", "label": "sync"}]}},
        {"type": "ui", "component": "table", "props": {
            "columns": ["Lang", "Nota"], "rows": [["Python", "9"], ["JS", "8"]]}},
        {"type": "ui", "component": "form", "props": {
            "title": "IMC", "calc": "imc",
            "fields": [{"name": "peso", "label": "Peso", "type": "number", "required": True},
                       {"name": "sexo", "label": "Sexo", "type": "select", "options": ["F", "M"]}]}},
        {"type": "ui", "component": "progress", "props": {"label": "Curso", "value": 30, "max": 100}},
        {"type": "ui", "component": "tabs", "props": {"tabs": [
            {"title": "A", "markdown": "x"}, {"title": "B", "markdown": "y"}]}},
        {"type": "ui", "component": "accordion", "props": {"items": [
            {"title": "Q?", "markdown": "R"}]}},
    ]}
    ok, norm, erros = jdui.validar_mensagem(msg)
    assert ok, erros
    assert len(norm['blocks']) == 8  # 9 enviados, teto trunca
    assert any('teto' in e for e in erros)


def test_invalidos():
    base = {"version": "JULIA-ui-message/v1", "blocks": []}
    assert jdui.validar_mensagem({"version": "x", "blocks": []})[0] is False
    assert jdui.validar_mensagem(dict(base, blocks=[]))[0] is False
    # componente desconhecido → fallback (rejeitado, erro registrado)
    ok, norm, erros = jdui.validar_mensagem(
        dict(base, blocks=[{"type": "ui", "component": "grafico3d", "props": {}}]))
    assert ok is False and any('desconhecido' in e for e in erros)
    # answer fora do intervalo → bloco cai, texto sobrevive (fallback)
    q = quiz_ok()
    q['blocks'][1]['props']['questions'][0]['answer'] = 9
    ok, norm, erros = jdui.validar_mensagem(q)
    assert ok and len(norm['blocks']) == 1 and norm['blocks'][0]['type'] == 'text'
    assert any('answer' in e for e in erros)
    # props ausentes
    assert jdui.validar_mensagem(
        dict(base, blocks=[{"type": "ui", "component": "quiz"}]))[0] is False
    # calculator.kind inválido
    assert jdui.validar_mensagem(
        dict(base, blocks=[{"type": "ui", "component": "calculator",
                            "props": {"kind": "nuclear"}}]))[0] is False
    # form.calc não registrado
    assert jdui.validar_mensagem(
        dict(base, blocks=[{"type": "ui", "component": "form",
                            "props": {"calc": "eval", "fields": [
                                {"name": "x", "label": "X", "type": "text"}]}}]))[0] is False
    # URL perigosa removida
    ok, norm, _ = jdui.validar_mensagem(
        dict(base, blocks=[{"type": "ui", "component": "cards", "props": {"items": [
            {"title": "T", "url": "javascript:alert(1)"}]}}]))
    assert ok and norm['blocks'][0]['props']['items'][0]['url'] == ''


def test_limites_e_profundidade():
    grande = {"version": "JULIA-ui-message/v1",
              "blocks": [{"type": "text", "content": "x"}] * 30}
    ok, norm, erros = jdui.validar_mensagem(grande)
    assert ok and len(norm['blocks']) == 8 and any('teto' in e for e in erros)
    fundo = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": "x"}}}}}}}}}
    assert jdui._profundidade(fundo) > jdui.MAX_DEPTH
    # 14 perguntas > teto 12 → bloco cai, texto sobrevive
    q = quiz_ok()
    q['blocks'][1]['props']['questions'] *= 7
    ok, norm, erros = jdui.validar_mensagem(q)
    assert ok and len(norm['blocks']) == 1


def test_normalizar_mantem_valido_remove_invalido():
    corpo = json.dumps(quiz_ok(), ensure_ascii=False)
    texto = f"Olá!\n\n```jdui\n{corpo}\n```\n\n```jdui\n{{nao json\n```\n\nFim."
    limpo, blocos, erros = jdui.normalizar(texto)
    assert len(blocos) == 1
    assert '```jdui' in limpo  # válido permanece (fonte canônica)
    assert 'nao json' not in limpo
    assert 'Olá!' in limpo and 'Fim.' in limpo
    assert erros


def test_normalizar_preserva_stream_parcial():
    texto = "Gerando...\n\n```jdui\n{\"version\": \"JULIA-ui-message/v1\", \"blocks\": ["
    limpo, blocos, _ = jdui.normalizar(texto)
    assert blocos == [] and '```jdui' in limpo


def test_ui_state_no_agente_idempotente(tmp_path):
    db = pc_agent.open_db(tmp_path / 'ui.sqlite3')
    with db:
        db.execute("INSERT INTO ui_state (k, message_id, slot, state, updated_at)"
                   " VALUES ('m1#0:quiz', 'm1', '0:quiz', '{\"a\":1}', 't1')"
                   " ON CONFLICT(k) DO UPDATE SET state=excluded.state")
        db.execute("INSERT INTO ui_state (k, message_id, slot, state, updated_at)"
                   " VALUES ('m1#0:quiz', 'm1', '0:quiz', '{\"a\":2}', 't2')"
                   " ON CONFLICT(k) DO UPDATE SET state=excluded.state")
    row = db.execute("SELECT state FROM ui_state WHERE k='m1#0:quiz'").fetchone()
    assert row[0] == '{"a":2}'
    db.close()


def test_relay_ui_state_via_agente_fake():
    with TestClient(server.app) as client:
        csrf = _login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            out = {}

            def salva():
                out['s'] = client.post('/api/ui-state',
                                       json={'states': [{'k': 'mid-0001#0:quiz', 'message_id': 'mid-0001',
                                                         'slot': '0:quiz', 'state': {'answers': {'0': 1}},
                                                         'updated_at': '2026-10-13T00:00:00Z'}]},
                                       headers={'X-CSRF-Token': csrf})

            def lista():
                out['l'] = client.get('/api/ui-state')

            def pega(tipo):
                for _ in range(3):
                    req = ws.receive_json()
                    if req['type'] == 'sess_revogados':
                        ws.send_json({'request_id': req['request_id'],
                                      'type': 'sess_revogados', 'sids': []})
                        continue
                    assert req['type'] == tipo, req
                    return req
                raise AssertionError('sem ' + tipo)

            t = threading.Thread(target=salva)
            t.start()
            req = pega('ui_state_save')
            ws.send_json({'request_id': req['request_id'], 'type': 'ui_state_saved', 'saved': 1})
            t.join(timeout=8)
            assert out['s'].json() == {'saved': 1}

            t = threading.Thread(target=lista)
            t.start()
            req = pega('ui_state_list')
            ws.send_json({'request_id': req['request_id'], 'type': 'ui_state_list', 'states': []})
            t.join(timeout=8)
            assert out['l'].json() == {'states': []}

            bad = client.post('/api/ui-state', json={'states': []}, headers={'X-CSRF-Token': csrf})
            assert bad.status_code == 422
            sem_auth = client.post('/api/ui-state', json={'states': [
                {'k': 'mid-0001#0:quiz', 'message_id': 'mid-0001', 'slot': '0:quiz',
                 'state': {}, 'updated_at': '2026-10-13T00:00:00Z'}]})
            assert sem_auth.status_code in (401, 403)


def test_conv_forget_no_agente(tmp_path):
    db = pc_agent.open_db(tmp_path / 'fg.sqlite3')
    pc_agent.persist_messages(db, [
        {'id': 'fg-user-01', 'origin': 'mobile', 'role': 'user', 'text': 'oi',
         'created_at': '2026-10-13T10:00:00.000Z', 'conversation_id': 'conv-esquecer'},
        {'id': 'fg-user-02', 'origin': 'mobile', 'role': 'user', 'text': 'outra',
         'created_at': '2026-10-13T10:01:00.000Z', 'conversation_id': 'conv-fica'}])
    with db:
        cur = db.execute("DELETE FROM messages WHERE origin='mobile' AND conversation_id=?",
                         ('conv-esquecer',))
        assert cur.rowcount == 1
    restam = [m['conversation_id'] for m in pc_agent.list_messages(db)]
    assert restam == ['conv-fica']
    db.close()


def test_relay_conversation_forget():
    import threading as _th
    with TestClient(server.app) as client:
        csrf = _login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            out = {}

            def deleta():
                out['d'] = client.delete('/api/conversations/conv-esquecer',
                                         headers={'X-CSRF-Token': csrf})

            t = _th.Thread(target=deleta)
            t.start()
            for _ in range(3):
                req = ws.receive_json()
                if req['type'] == 'sess_revogados':
                    ws.send_json({'request_id': req['request_id'],
                                  'type': 'sess_revogados', 'sids': []})
                    continue
                break
            assert req['type'] == 'conv_forget' and req['conversation_id'] == 'conv-esquecer'
            ws.send_json({'request_id': req['request_id'], 'type': 'conv_forgotten', 'deleted': 3})
            t.join(timeout=8)
            assert out['d'].json() == {'ok': True, 'deleted': 3}
            ruim = client.delete('/api/conversations/!!!', headers={'X-CSRF-Token': csrf})
            assert ruim.status_code == 422
            curto = client.delete('/api/conversations/ab', headers={'X-CSRF-Token': csrf})
            assert curto.status_code == 422
            sem = client.delete('/api/conversations/conv-esquecer')
            assert sem.status_code in (401, 403)


def test_xss_em_strings_nao_executa():
    msg = {"version": "JULIA-ui-message/v1", "blocks": [
        {"type": "ui", "component": "cards", "props": {"items": [
            {"title": "<script>alert(1)</script>", "desc": "<img src=x onerror=y>"}]}}]}
    ok, norm, _ = jdui.validar_mensagem(msg)
    assert ok  # validação aceita texto; o escape acontece no renderer
    assert norm['blocks'][0]['props']['items'][0]['title'] == "<script>alert(1)</script>"
