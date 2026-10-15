"""V4.2 FASE 2: schemas educacionais, correção determinística, SM-2, stats."""
import sys
from datetime import date
from pathlib import Path

import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import learning
import pc_agent


def _db(nome='learn.sqlite3'):
    import sqlite3
    caminho = Path(tempfile.mkdtemp()) / nome
    db = sqlite3.connect(caminho)
    learning.criar_tabelas(db)
    return db


def test_validar_questoes_tipos():
    q = learning.validar_questao({"enunciado": "Quanto é 2+2?", "tipo": "multipla",
                                  "opcoes": ["3", "4"], "gabarito": 1,
                                  "explicacao": "Soma.", "assunto": "mat"})
    assert q["gabarito"] == "1" and q["assunto"] == "mat"
    vf = learning.validar_questao({"enunciado": "Python é linguagem?", "tipo": "vf",
                                   "opcoes": ["V", "F"], "gabarito": 0})
    assert vf["tipo"] == "vf"
    curta = learning.validar_questao({"enunciado": "Capital do BR?", "tipo": "curta",
                                      "gabarito": "Brasília"})
    assert curta["gabarito"] == "Brasília"
    disc = learning.validar_questao({"enunciado": "Explique fotossíntese", "tipo": "discursiva",
                                     "gabarito": "Citar luz, clorofila e glicose como critérios."})
    assert disc["tipo"] == "discursiva"
    for ruim in ({"enunciado": "x", "tipo": "multipla", "opcoes": ["a"], "gabarito": 0},
                 {"enunciado": "Pergunta válida aqui?", "tipo": "multipla",
                  "opcoes": ["a", "b"], "gabarito": 5},
                 {"enunciado": "Pergunta válida aqui?", "tipo": "nuclear",
                  "opcoes": ["a", "b"], "gabarito": 0},
                 {"enunciado": "Explique X", "tipo": "discursiva", "gabarito": "curto"}):
        try:
            learning.validar_questao(ruim)
            raise AssertionError('deveria falhar')
        except learning.LearnErro:
            pass


def test_correcao_objetiva_deterministica():
    m = {"tipo": "multipla", "gabarito": "1"}
    assert learning.corrigir_objetiva(m, 1) is True
    assert learning.corrigir_objetiva(m, "b") is True
    assert learning.corrigir_objetiva(m, "B") is True
    assert learning.corrigir_objetiva(m, "a") is False
    assert learning.corrigir_objetiva(m, "chute") is False
    c = {"tipo": "curta", "gabarito": "Brasília"}
    assert learning.corrigir_objetiva(c, "  brasília ") is True
    assert learning.corrigir_objetiva(c, "São Paulo") is False
    try:
        learning.corrigir_objetiva({"tipo": "discursiva"}, "texto")
        raise AssertionError('discursiva não auto-corrige')
    except learning.LearnErro as exc:
        assert exc.codigo == "discursiva"


def test_sm2_deterministico():
    f, i, _ = learning.proxima_revisao(2.5, 0, True, hoje=date(2026, 1, 1))
    assert (f, i) == (2.6, 1)
    f, i, d = learning.proxima_revisao(2.6, 1, True, hoje=date(2026, 1, 1))
    assert (f, i, d) == (2.7, 6, "2026-01-07")
    f, i, d = learning.proxima_revisao(2.7, 6, False, hoje=date(2026, 1, 1))
    assert (f, i, d) == (2.4, 1, "2026-01-02")
    # mesma entrada, mesma saída (determinismo puro)
    assert learning.proxima_revisao(2.5, 6, True, hoje=date(2026, 1, 1)) == \
        learning.proxima_revisao(2.5, 6, True, hoje=date(2026, 1, 1))


def test_tabelas_isoladas_e_idempotentes(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnfull.sqlite3')
    cols = [c[1] for c in db.execute("PRAGMA table_info(questions)").fetchall()]
    assert "owner_id" in cols and "gabarito" in cols
    db.execute("INSERT INTO assessments (id, owner_id, titulo, created_at) VALUES ('a1','u-x','T','t')")
    db.execute("INSERT INTO questions (id, assessment_id, owner_id, enunciado) VALUES ('q1','a1','u-x','E?')")
    db.execute("INSERT OR IGNORE INTO questions (id, assessment_id, owner_id, enunciado) VALUES ('q1','a1','u-x','E2')")
    n = db.execute("SELECT COUNT(*) FROM questions WHERE owner_id='u-x'").fetchone()[0]
    assert n == 1  # reenvio do mesmo id não duplica (idempotência)
    assert db.execute("SELECT enunciado FROM questions WHERE id='q1'").fetchone()[0] == 'E?'
    assert db.execute("SELECT COUNT(*) FROM questions WHERE owner_id='u-y'").fetchone()[0] == 0
    # stats vazias: estado vazio útil, sem invenção
    r = learning.resumo_progresso(db, 'u-x')
    assert r == {"avaliacoes": 0, "concluidas": 0, "acertos": 0, "respostas": 0,
                 "itens_plano": 0, "itens_feitos": 0, "revisoes_pendentes": 0}
    assert learning.desempenho_por_assunto(db, 'u-x') == []
    db.close()


def test_stats_reais_por_assunto(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnstats.sqlite3')
    db.execute("INSERT INTO questions (id, assessment_id, owner_id, enunciado, assunto) VALUES "
               "('q1','a','u-x','E1','mat'), ('q2','a','u-x','E2','mat'), ('q3','a','u-x','E3','port')")
    db.execute("INSERT INTO answers (attempt_id, question_id, owner_id, resposta, correta) VALUES "
               "('t','q1','u-x','1',1), ('t','q2','u-x','0',0), ('t','q3','u-x','x',1)")
    db.commit()
    perf = {p["assunto"]: p for p in learning.desempenho_por_assunto(db, 'u-x')}
    assert perf["mat"]["taxa"] == 0.5 and perf["port"]["taxa"] == 1.0
    assert learning.desempenho_por_assunto(db, 'u-y') == []
    db.close()


def test_criar_assessment_idempotente_e_fluxo(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnfluxo.sqlite3')
    qs = [{"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
           "opcoes": ["3", "4"], "gabarito": 1, "assunto": "mat"},
          {"id": "q2", "enunciado": "Disserte sobre soma", "tipo": "discursiva",
           "gabarito": "Citar parcelas, total e exemplo como critérios."}]
    r1 = learning.criar_assessment(db, 'u-x', 'P1', 'mat', qs, assessment_id='av-1')
    r2 = learning.criar_assessment(db, 'u-x', 'P1', 'mat', qs, assessment_id='av-1')
    assert (r1, r2) == ({"id": "av-1", "total": 2}, {"id": "av-1", "total": 2})
    assert db.execute("SELECT COUNT(*) FROM questions WHERE assessment_id='av-1'").fetchone()[0] == 2
    pub = learning.obter_assessment(db, 'u-x', 'av-1')
    assert all('gabarito' not in q for q in pub['questions'])  # sem gabarito p/ o aluno
    full = learning.obter_assessment(db, 'u-x', 'av-1', com_gabarito=True)
    assert full['questions'][0]['gabarito'] == '1'
    try:
        learning.obter_assessment(db, 'u-y', 'av-1')
        raise AssertionError('outro dono não lê')
    except learning.LearnErro as exc:
        assert exc.codigo == 'ausente'
    att = learning.iniciar_tentativa(db, 'u-x', 'av-1', 'att-1')['id']
    assert learning.responder(db, 'u-x', att, 'q1', 'b') == {"correta": True}
    d = learning.responder(db, 'u-x', att, 'q2', 'texto livre')
    assert d['correta'] is None and d['avaliacao'] == 'assistida'
    fim = learning.finalizar_tentativa(db, 'u-x', att)
    assert (fim['certas'], fim['total'], fim['pendentes_avaliacao']) == (1, 1, 1)
    try:
        learning.responder(db, 'u-x', att, 'q1', 'a')
        raise AssertionError('finalizada não aceita resposta')
    except learning.LearnErro as exc:
        assert exc.codigo == 'finalizada'
    db.close()


def test_planos_crud_e_atualizacao_preserva_feitos(tmp_path):
    from datetime import date
    db = pc_agent.open_db(tmp_path / 'learnplanos.sqlite3')
    itens = [{"titulo": "Frações", "tipo": "conteudo"}, {"titulo": "Quiz 1", "tipo": "quiz"}]
    p = learning.criar_plano(db, 'u-x', 'Mat até nov', 'Passar', 'mat',
                             prazo_iso='2026-11-30', min_dia=30, itens=itens, plan_id='pl-1')
    assert p == {"id": "pl-1", "itens": 2}
    pl = learning.obter_plano(db, 'u-x', 'pl-1')
    assert pl['progresso'] == {"feitos": 0, "total": 2, "taxa": 0.0}
    assert learning.listar_planos(db, 'u-x')[0]['total'] == 2
    assert learning.listar_planos(db, 'u-y') == []
    prog = learning.concluir_item(db, 'u-x', 'pl-1', pl['itens'][0]['id'])
    assert prog == {"feitos": 1, "total": 2, "taxa": 0.5}
    # atualização compatível preserva concluído (match por título)
    novo = learning.atualizar_plano(db, 'u-x', 'pl-1',
                                   {"min_dia": 45, "itens": [{"titulo": "Frações"}, {"titulo": "Geometria"}]})
    assert novo['min_dia'] == 45 and novo['progresso'] == {"feitos": 1, "total": 2, "taxa": 0.5}
    try:
        learning.obter_plano(db, 'u-y', 'pl-1')
        raise AssertionError('outro dono não lê plano')
    except learning.LearnErro as exc:
        assert exc.codigo == 'ausente'
    try:
        learning.criar_plano(db, 'u-x', 'X', itens=[])
        raise AssertionError('plano sem itens deveria falhar')
    except learning.LearnErro:
        pass
    db.close()


def test_flashcards_revisao_e_pendentes(tmp_path):
    from datetime import date, timedelta
    db = pc_agent.open_db(tmp_path / 'learncards.sqlite3')
    hoje = date.today()
    r = learning.criar_flashcards(db, 'u-x', [
        {"id": "fc-1", "frente": "2+2?", "verso": "4", "assunto": "mat"},
        {"frente": "Capital do BR?", "verso": "Brasília"}])
    assert r['total'] == 2 and r['ids'][0] == 'fc-1'
    assert len(learning.revisoes_pendentes(db, 'u-x', hoje=hoje)) == 2
    assert learning.revisoes_pendentes(db, 'u-y', hoje=hoje) == []
    out = learning.revisar_flashcard(db, 'u-x', 'fc-1', True, hoje=hoje)
    assert (out['intervalo_d'], out['proxima_iso']) == (1, (hoje + timedelta(days=1)).isoformat())
    assert len(learning.revisoes_pendentes(db, 'u-x', hoje=hoje)) == 1
    out = learning.revisar_flashcard(db, 'u-x', 'fc-1', False, hoje=hoje)
    assert (out['intervalo_d'], out['proxima_iso']) == (1, (hoje + timedelta(days=1)).isoformat())
    assert learning.resumo_progresso(db, 'u-x')['revisoes_pendentes'] >= 1
    db.close()


def test_recomendar_regras_e_sem_dados(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnrec.sqlite3')
    vazio = learning.recomendar(db, 'u-x')
    assert vazio == {"recomendacoes": [], "motivo": "sem_dados",
                     "aviso": "Ainda não há respostas suficientes para recomendar."}
    db.execute("INSERT INTO questions (id, assessment_id, owner_id, enunciado, assunto) VALUES "
               "('q1','a','u-x','E1','mat'), ('q2','a','u-x','E2','mat'), ('q3','a','u-x','E3','mat'),"
               " ('q4','a','u-x','E4','port'), ('q5','a','u-x','E5','port'), ('q6','a','u-x','E6','port')")
    db.execute("INSERT INTO answers (attempt_id, question_id, owner_id, resposta, correta) VALUES "
               "('t','q1','u-x','0',0), ('t','q2','u-x','0',0), ('t','q3','u-x','1',1),"
               " ('t','q4','u-x','1',1), ('t','q5','u-x','1',1), ('t','q6','u-x','1',1)")
    db.commit()
    rec = learning.recomendar(db, 'u-x')
    assert rec['motivo'] == 'dados_reais'
    tipos = {x['tipo']: x for x in rec['recomendacoes']}
    assert tipos['revisar']['assunto'] == 'mat'  # 1/3 < 60%
    assert tipos['avancar']['assunto'] == 'port'  # 3/3
    assert all('base' in x for x in rec['recomendacoes'])
    assert learning.recomendar(db, 'u-y')['motivo'] == 'sem_dados'  # isolamento
    db.close()


def test_sinalizar_e_erradas(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnflag.sqlite3')
    learning.criar_assessment(db, 'u-x', 'P', 'mat', [
        {"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
         "opcoes": ["3", "4"], "gabarito": 1}], assessment_id='av-f')
    att = learning.iniciar_tentativa(db, 'u-x', 'av-f', 'att-f')['id']
    learning.responder(db, 'u-x', att, 'q1', '0')
    learning.finalizar_tentativa(db, 'u-x', att)
    assert learning.sinalizar_questao(db, 'u-x', 'q1', 'gabarito parece trocado') == {"ok": True, "question_id": "q1"}
    ev = db.execute("SELECT tipo FROM study_events WHERE owner_id='u-x'").fetchall()
    tipos = {e[0] for e in ev}
    assert 'questao_sinalizada' in tipos and 'prova_finalizada' in tipos  # história preservada
    err = learning.questoes_erradas(db, 'u-x')
    assert len(err) == 1 and err[0]['question_id'] == 'q1' and err[0]['assunto'] == 'mat'
    assert learning.questoes_erradas(db, 'u-y') == []
    db.close()


def test_criar_reforco_das_erradas(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnreforco.sqlite3')
    try:
        learning.criar_reforco(db, 'u-x')
        raise AssertionError('sem erros deveria falhar')
    except learning.LearnErro as exc:
        assert exc.codigo == 'sem_dados'
    learning.criar_assessment(db, 'u-x', 'P', 'mat', [
        {"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
         "opcoes": ["3", "4"], "gabarito": 1, "explicacao": "Soma."},
        {"id": "q2", "enunciado": "Quanto é 3+3?", "tipo": "multipla",
         "opcoes": ["5", "6"], "gabarito": 1, "explicacao": "Soma."}], assessment_id='av-r')
    att = learning.iniciar_tentativa(db, 'u-x', 'av-r', 'att-r')['id']
    learning.responder(db, 'u-x', att, 'q1', '0')  # errou
    learning.responder(db, 'u-x', att, 'q2', '1')  # acertou
    learning.finalizar_tentativa(db, 'u-x', att)
    ref = learning.criar_reforco(db, 'u-x')
    av = learning.obter_assessment(db, 'u-x', ref['id'], com_gabarito=True)
    assert len(av['questions']) == 1  # só a errada
    assert av['questions'][0]['enunciado'] == 'Quanto é 2+2?'
    assert av['questions'][0]['gabarito'] == '1'  # gabarito original preservado
    row = db.execute("SELECT origem FROM assessments WHERE id=?", (ref['id'],)).fetchone()
    assert row[0] == 'reforco'
    try:
        learning.criar_reforco(db, 'u-y')
        raise AssertionError('outro dono não tem erros')
    except learning.LearnErro as exc:
        assert exc.codigo == 'sem_dados'
    db.close()


def test_reforco_intencao_e_fence(tmp_path):
    assert pc_agent.intencao_reforco("faz outro simulado só com o que eu errei ontem")
    assert pc_agent.intencao_reforco("crie um simulado de reforço do que errei")
    assert not pc_agent.intencao_reforco("cria uma prova de matemática")
    assert not pc_agent.intencao_reforco("me ensina python")
    db = pc_agent.open_db(tmp_path / 'learnrefchat.sqlite3')
    sem = pc_agent.sintetizar_reforco(db, 'u-x', "simulado com o que errei")
    assert "```jdui" not in sem and "erradas" in sem  # informa, não inventa
    learning.criar_assessment(db, 'u-x', 'P', 'mat', [
        {"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
         "opcoes": ["3", "4"], "gabarito": 1}], assessment_id='av-rc')
    att = learning.iniciar_tentativa(db, 'u-x', 'av-rc', 'att-rc')['id']
    learning.responder(db, 'u-x', att, 'q1', '0')
    learning.finalizar_tentativa(db, 'u-x', att)
    fence = pc_agent.sintetizar_reforco(db, 'u-x', "outro simulado com o que errei")
    assert '"component": "exam"' in fence
    import json as _json
    bloco = _json.loads(fence.split("```jdui\n")[1].split("\n```")[0])
    aid = bloco["blocks"][1]["props"]["assessment_id"]
    row = db.execute("SELECT origem FROM assessments WHERE id=?", (aid,)).fetchone()
    assert row[0] == 'reforco'
    db.close()


def test_desempenho_real_entra_no_prompt(tmp_path):
    db = pc_agent.open_db(tmp_path / 'learnprompt.sqlite3')
    cfg = {'proxy': 'x', 'model': 'm', 'system': 'S', 'context': 5, 'max_tokens': 50,
           'memoria_global': True, 'pesquisa_web': False}
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv', cfg, 'Em que assuntos estou errando mais?', 'u-x')
    assert 'DESEMPENHO REAL' not in msgs[0]['content']  # sem dados: nada inventado
    db.execute("INSERT INTO questions (id, assessment_id, owner_id, enunciado, assunto) VALUES "
               "('q1','a','u-x','E1','mat'), ('q2','a','u-x','E2','mat'), ('q3','a','u-x','E3','mat')")
    db.execute("INSERT INTO answers (attempt_id, question_id, owner_id, resposta, correta) VALUES "
               "('t','q1','u-x','0',0), ('t','q2','u-x','0',0), ('t','q3','u-x','1',1)")
    db.commit()
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv', cfg, 'Em que assuntos estou errando mais?', 'u-x')
    sistema = msgs[0]['content']
    assert 'DESEMPENHO REAL' in sistema and 'mat 33% (1/3)' in sistema
    msgs2, _ = pc_agent.ai_montar_mensagens(db, 'conv', cfg, 'Qual a capital do Peru?', 'u-x')
    assert 'DESEMPENHO REAL' not in msgs2[0]['content']  # fora de contexto de estudo
    msgs3, _ = pc_agent.ai_montar_mensagens(db, 'conv', cfg, 'Em que assuntos estou errando mais?', 'u-y')
    assert 'DESEMPENHO REAL' not in msgs3[0]['content']  # outro dono: nada vaza
    db.close()
