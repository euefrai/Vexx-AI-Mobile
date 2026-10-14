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
