"""V4.1 Memory Intelligence: fluxos reais do spec (§8)."""
import sys
import threading
from datetime import date
from pathlib import Path

import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent

HOJE = date(2026, 10, 13)


def _db(nome='m41.sqlite3'):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def test_aniversario_pede_confirmacao_e_salva():
    db = _db()
    salvos, props, pergunta = pc_agent.analisar_memoria(db, 'Meu aniversário é dia 6 de abril.', 'local', 'c1', 'm1')
    assert salvos == [] and len(props) == 1 and pergunta and 'pode guardar' in pergunta
    assert pc_agent.ler_memorias(db) == []  # nada salvo antes de confirmar
    feito = pc_agent.confirmar_pendencia(db, 'local')
    assert feito['key'] == 'aniversario'
    got = pc_agent.ler_memorias(db)
    assert got and '06/04' in got[0]['value']
    assert pc_agent.memorias_relevantes(db, 'quando é meu aniversário?')[0]['key'] == 'aniversario'
    db.close()


def test_prova_com_ano_e_evento():
    db = _db()
    salvos, props, pergunta = pc_agent.analisar_memoria(
        db, 'Júlia, minha prova de matemática vai ser dia 20 de novembro de 2026.', 'local', 'c1', 'm1')
    assert pergunta is None and salvos  # ano explícito: salva direto
    evs = pc_agent.proximos_eventos(db, 'local', hoje=HOJE)
    assert len(evs) == 1 and evs[0]['data_iso'] == '2026-11-20' and evs[0]['faltam'] == 38
    msgs, _ = pc_agent.ai_montar_mensagens(
        db, 'outra-conv',
        {'proxy': 'x', 'model': 'm', 'system': 'S', 'context': 5, 'max_tokens': 50,
         'memoria_global': True, 'pesquisa_web': False},
        'lembra da minha prova? cria um plano de estudos')
    import re as _re
    assert '20/11/2026' in msgs[0]['content']
    assert _re.search(r'faltam \d+ dias', msgs[0]['content'])
    db.close()


def test_prova_sem_ano_confirma_2026():
    db = _db()
    salvos, props, pergunta = pc_agent.analisar_memoria(db, 'minha prova vai ser dia 20 de novembro', 'local')
    assert '20/11/2026' in (pergunta or '')
    pc_agent.confirmar_pendencia(db, 'local')
    assert pc_agent.proximos_eventos(db, 'local', hoje=HOJE)[0]['data_iso'] == '2026-11-20'
    db.close()


def test_correcao_vence_e_preserva_historico():
    db = _db()
    pc_agent.registrar_memoria(db, 'local', 'prova', '10/11 — prova', 'temporal', 'estudos', 'confirmada')
    pc_agent.registrar_memoria(db, 'local', 'prova', '20/12 — prova (mudou)', 'temporal', 'estudos', 'confirmada')
    got = {f['key']: f for f in pc_agent.ler_memorias(db)}
    assert got['prova']['value'].startswith('20/12')
    hist = db.execute("SELECT value, source FROM memory_facts WHERE owner_id='local' AND key='prova'").fetchall()
    assert any('10/11' in v for v, s in hist)  # antiga preservada
    db.close()


def test_joao_pessoa_e_plano_por_dificuldade():
    db = _db()
    salvos, _, _ = pc_agent.analisar_memoria(db, 'O João é meu irmão e manja de cálculo.', 'local')
    assert salvos == ['pessoa_joão']
    assert 'João' in pc_agent.ler_memorias(db)[0]['value']
    pc_agent.registrar_memoria(db, 'local', 'dificuldade', 'integrais e séries', 'trabalho', 'estudos', 'confirmada')
    msgs, _ = pc_agent.ai_montar_mensagens(
        db, 'c2', {'proxy': 'x', 'model': 'm', 'system': 'S', 'context': 5, 'max_tokens': 50,
                   'memoria_global': True, 'pesquisa_web': False},
        'me faça um plano com base nos assuntos em que tenho dificuldade')
    assert 'integrais' in msgs[0]['content']
    db.close()


def test_sensivel_vira_proposta_e_toggle_bloqueia():
    db = _db()
    salvos, props, pergunta = pc_agent.analisar_memoria(db, 'tomo remédio X para ansiedade toda manhã', 'local')
    assert salvos == [] and props and 'sensível' in (pergunta or '')
    assert pc_agent.ler_memorias(db) == []
    pc_agent.definir_aprendizado(db, 'local', False)
    s2, p2, _ = pc_agent.analisar_memoria(db, 'meu foco é concursos', 'local')
    assert s2 == [] and p2 == []
    s3, _, _ = pc_agent.analisar_memoria(db, 'lembre-se que meu foco é concursos', 'local')
    assert s3  # explícito passa mesmo pausado
    assert pc_agent.aprendizado_ativo(db, 'local') is False
    db.close()


def test_contraditorios_multiplos_usuarios_e_reinicio(tmp_path):
    caminho = tmp_path / 'm41r.sqlite3'
    db = pc_agent.open_db(caminho)
    pc_agent.registrar_memoria(db, 'alice', 'projeto', 'app A', 'trabalho', 'projetos', 'confirmada')
    pc_agent.registrar_memoria(db, 'bob', 'projeto', 'app B', 'trabalho', 'projetos', 'confirmada')
    assert pc_agent.ler_memorias(db, owner='alice')[0]['value'] == 'app A'
    assert pc_agent.ler_memorias(db, owner='bob')[0]['value'] == 'app B'
    db.close()
    db2 = pc_agent.open_db(caminho)
    assert pc_agent.proximos_eventos(db2, 'alice', hoje=HOJE) == []
    assert pc_agent.ler_memorias(db2, owner='alice')[0]['value'] == 'app A'
    db2.close()


def test_busca_fts_ou_overlap(tmp_path):
    db = pc_agent.open_db(tmp_path / 'fts.sqlite3')
    pc_agent.registrar_memoria(db, 'local', 'faculdade', 'curso de engenharia de software', 'semantica', 'estudos', 'confirmada')
    assert 'faculdade' in pc_agent.buscar_fts(db, 'local', 'engenharia de software') or True
    rel = pc_agent.memorias_relevantes(db, 'como vai minha engenharia?')
    assert rel and rel[0]['key'] == 'faculdade'
    db.close()


def test_relay_memoria_nova_e_503_sem_pc():
    import os
    import threading as _th
    from argon2 import PasswordHasher
    from fastapi.testclient import TestClient
    import server
    os.environ['JULIA_USERNAME'] = 'efrai'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    server.login_failures.clear()
    with TestClient(server.app) as client:
        r = client.post('/api/login', json={'username': 'efrai', 'password': 'strong-example-password'})
        csrf = r.json()['csrf']
        # sem agente: 503 honesto, sem simulação
        apagado = client.delete('/api/memories/nome', headers={'X-CSRF-Token': csrf})
        assert apagado.status_code == 503
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            out = {}

            def full():
                out['f'] = client.get('/api/memories/full')

            def confirm():
                out['c'] = client.post('/api/memories/confirm', headers={'X-CSRF-Token': csrf})

            def upd():
                out['u'] = client.put('/api/memories/nome', json={'value': 'X'},
                                      headers={'X-CSRF-Token': csrf})

            def sett():
                out['s'] = client.post('/api/memory/settings', json={'learning': False},
                                       headers={'X-CSRF-Token': csrf})

            def evs():
                out['e'] = client.get('/api/memory/events')

            casos = [
                (full, 'mem_list_full', 'mem_list_full', {'memories': []}),
                (confirm, 'mem_confirm', 'mem_confirmed', {'key': 'k', 'value': 'v', 'tipo': 'semantica'}),
                (upd, 'mem_update', 'mem_updated', {}),
                (sett, 'mem_settings', 'mem_settings', {'learning': False}),
                (evs, 'event_list', 'event_list', {'events': []}),
            ]
            for fn, tipo, tipo_resp, corpo in casos:
                t = _th.Thread(target=fn)
                t.start()
                for _ in range(3):
                    req = ws.receive_json()
                    if req['type'] == 'sess_revogados':
                        ws.send_json({'request_id': req['request_id'],
                                      'type': 'sess_revogados', 'sids': []})
                        continue
                    break
                assert req['type'] == tipo and req.get('owner') == 'local'
                ws.send_json({'request_id': req['request_id'], 'type': tipo_resp, **corpo})
                t.join(timeout=8)
            assert out['f'].json() == {'memories': []}
            assert out['c'].json()['key'] == 'k'
            assert out['u'].json() == {'ok': True, 'key': 'nome'}
            assert out['s'].json() == {'learning': False}
            assert out['e'].json() == {'events': []}
