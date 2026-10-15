"""Avaliação conversacional V4.0 (§16): os 8 testes do spec, automatizados.

T1 nome salvo→recuperado em outra conversa · T2 correção de data vence a
antiga · T3 sem memória inventada · T4 quiz renderizável · T5 sem ferramenta,
limitação declarada · T6 isolamento entre donos · T7 falha de ferramenta não
vira conclusão · T8 recuperação após reinicialização.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import pc_agent


def _db(nome='av.sqlite3'):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _cfg():
    return {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
            'context': 12, 'max_tokens': 500, 'memoria_global': True, 'pesquisa_web': True}


def _umsg(i, conv, texto):
    return {'id': i, 'origin': 'mobile', 'role': 'user', 'text': texto,
            'created_at': '2026-10-13T10:00:00.000Z', 'conversation_id': conv}


def test_t1_nome_recuperado_outra_conversa():
    db = _db()
    pc_agent.persist_messages(db, [_umsg('t1-user-01', 'conv-a', 'meu nome é Marina e sou médica')])
    pc_agent.guardar_fato(db, 'nome', 'Marina (médica)')
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-b', _cfg(), 'qual é o meu nome?')
    assert 'Marina' in msgs[0]['content']
    db.close()


def test_t2_correcao_substitui_antiga():
    db = _db()
    pc_agent.guardar_fato(db, 'prova', 'dia 10 de novembro')
    pc_agent.guardar_fato(db, 'prova', 'dia 20 de novembro (corrigido)')
    got = pc_agent.ler_memorias(db)
    assert [f for f in got if f['key'] == 'prova'][0]['value'].startswith('dia 20')
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-a', _cfg(), 'quando é minha prova?')
    assert 'dia 20' in msgs[0]['content'] and 'dia 10' not in msgs[0]['content']
    db.close()


def test_t3_nada_inventado_sem_memoria():
    db = _db()
    resp, codigo = pc_agent.interpretar_comando_memoria(db, 'o que você sabe sobre mim?')
    assert codigo == 'mem_vazia'
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-a', _cfg(), 'qual é o meu nome?')
    assert 'O QUE VOCÊ SABE' not in msgs[0]['content']
    db.close()


def test_t4_quiz_renderizavel():
    import json as _json
    quiz = {"version": "JULIA-ui-message/v1", "blocks": [
        {"type": "ui", "component": "quiz", "props": {"title": "CF", "questions": [
            {"q": "Artigo 5?", "options": ["Direitos", "Deveres"], "answer": 0, "explain": "Caput."}]}}]}
    texto = 'Aqui vai:\n\n```jdui\n' + _json.dumps(quiz) + '\n```'
    limpo, blocos, erros = jdui.normalizar(texto)
    assert len(blocos) == 1 and not erros and '```jdui' in limpo
    assert blocos[0]['blocks'][0]['props']['questions'][0]['answer'] == 0  # gabarito determinístico


def test_t5_sem_pesquisa_declara_limitacao(monkeypatch):
    import research
    db = _db()
    monkeypatch.setattr(research, 'pesquisa_rapida',
                        lambda *a, **k: {"fontes": [], "etapas": [], "divergencias": [],
                                         "de_cache": False, "erro": "provedor_indisponivel"})
    msgs, extras = pc_agent.ai_montar_mensagens(db, 'conv-a', _cfg(), 'pesquise o preço do dólar hoje')
    assert extras['fontes'] == []
    assert 'sem inventar links' in msgs[0]['content']
    db.close()


def test_t6_isolamento_entre_donos():
    db = _db()
    pc_agent.guardar_fato(db, 'nome', 'Alice', owner='alice')
    assert pc_agent.ler_memorias(db, owner='bob') == []
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-x', _cfg(), 'qual meu nome?', owner='bob')
    assert 'Alice' not in msgs[0]['content']
    db.close()


def test_t7_falha_nao_vira_conclusao(monkeypatch):
    import hermes_bridge
    db = _db()
    pc_agent.persist_messages(db, [_umsg('t7-user-01', 'conv-a', 'resuma este texto longo para mim, por favor')])

    def _boom(*a, **k):
        raise hermes_bridge.BridgeErro('Proxy fora do ar', 'indisponivel')

    monkeypatch.setattr(hermes_bridge, 'chat_complete', _boom)
    monkeypatch.setattr(hermes_bridge, 'chat_stream', _boom)
    r = pc_agent.ai_completa(db, {'message_id': 't7-user-01', 'conversation_id': 'conv-a'}, _cfg())
    assert r.get('codigo') == 'indisponivel'
    assert pc_agent.ai_estado(db, 't7-user-01')['state'] == 'failed'
    assert all(m['role'] != 'assistant' or 'Proxy fora' not in m['text']
               for m in pc_agent.list_messages(db))
    db.close()


def test_t8_recuperacao_apos_reinicio(tmp_path):
    caminho = tmp_path / 'restart.sqlite3'
    db = pc_agent.open_db(caminho)
    pc_agent.persist_messages(db, [_umsg('t8-user-01', 'conv-a', 'lembre-se que meu foco é concursos')])
    pc_agent.ai_guardar_resposta(db, 't8-user-01', 'conv-a', 'm', 't8-user-01-r1', 'Anotado!')
    db.close()
    db2 = pc_agent.open_db(caminho)  # "reinicia" o processo
    textos = {m['id']: m['text'] for m in pc_agent.list_messages(db2)}
    assert textos['t8-user-01'] == 'lembre-se que meu foco é concursos'
    assert textos['t8-user-01-r1'] == 'Anotado!'
    db2.close()
