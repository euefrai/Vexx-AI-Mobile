"""JULIALearningEngine — dados (FASE 2, V4.2).

Tabelas, validação e algoritmo de repetição espaçada. Stdlib pura.
Tudo com owner_id (isolamento) e IDs client-side estáveis (idempotência:
reenvio do mesmo id não duplica). Sem LLM aqui: geração de conteúdo
vem do Hermes via PresentationEngine; este módulo guarda, corrige
(deterministicamente) e mede.
"""
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

DONO_PADRAO = "local"
TIPOS_QUESTAO = ("multipla", "vf", "curta", "discursiva")
TIPOS_ITEM = ("conteudo", "exercicio", "revisao", "quiz")


class LearnErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS learning_plans (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        titulo TEXT NOT NULL, objetivo TEXT NOT NULL DEFAULT '',
        assunto TEXT NOT NULL DEFAULT '', prazo_iso TEXT NOT NULL DEFAULT '',
        min_dia INT NOT NULL DEFAULT 30, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS plan_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', titulo TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'conteudo', ordem INT NOT NULL DEFAULT 0,
        feito INT NOT NULL DEFAULT 0, feito_em TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        titulo TEXT NOT NULL, assunto TEXT NOT NULL DEFAULT '',
        origem TEXT NOT NULL DEFAULT 'ia', created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', enunciado TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'multipla', opcoes TEXT NOT NULL DEFAULT '[]',
        gabarito TEXT NOT NULL DEFAULT '', explicacao TEXT NOT NULL DEFAULT '',
        dificuldade TEXT NOT NULL DEFAULT 'media', assunto TEXT NOT NULL DEFAULT '',
        ordem INT NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS attempts (
        id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', iniciada_em TEXT NOT NULL,
        finalizada_em TEXT NOT NULL DEFAULT '', nota REAL NOT NULL DEFAULT 0,
        total INT NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS answers (
        attempt_id TEXT NOT NULL, question_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', resposta TEXT NOT NULL DEFAULT '',
        correta INT NOT NULL DEFAULT 0, corrigida_em TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (attempt_id, question_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS flashcards (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        frente TEXT NOT NULL, verso TEXT NOT NULL, assunto TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS reviews (
        flashcard_id TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'local',
        proxima_iso TEXT NOT NULL, intervalo_d INT NOT NULL DEFAULT 1,
        facilidade REAL NOT NULL DEFAULT 2.5, acertos INT NOT NULL DEFAULT 0,
        erros INT NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
        PRIMARY KEY (flashcard_id, owner_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS study_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL DEFAULT 'local',
        tipo TEXT NOT NULL, ref_id TEXT NOT NULL DEFAULT '',
        detalhe TEXT NOT NULL DEFAULT '', ts TEXT NOT NULL)""")
    for _tabela, _col in (("learning_plans", "owner_id"), ("plan_items", "owner_id"),
                          ("assessments", "owner_id"), ("questions", "owner_id"),
                          ("attempts", "owner_id"), ("answers", "owner_id"),
                          ("flashcards", "owner_id"), ("reviews", "owner_id"),
                          ("study_events", "owner_id")):
        try:
            cols = [c[1] for c in db.execute(f"PRAGMA table_info({_tabela})").fetchall()]
            if "owner_id" not in cols:
                db.execute(f"ALTER TABLE {_tabela} ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'")
        except sqlite3.OperationalError:
            pass
    try:
        cols = [c[1] for c in db.execute("PRAGMA table_info(questions)").fetchall()]
        if "assunto" not in cols:
            db.execute("ALTER TABLE questions ADD COLUMN assunto TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    db.execute("CREATE INDEX IF NOT EXISTS idx_learn_owner ON assessments(owner_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_quest_ass ON questions(assessment_id, ordem)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_att_ass ON attempts(assessment_id, finalizada_em)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_rev_due ON reviews(owner_id, proxima_iso)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_items_plan ON plan_items(plan_id, ordem)")
    db.commit()


# ── Validação ─────────────────────────────────────────────────────────
def _txt(v, limite=2000) -> str:
    return str(v or "")[:limite] if isinstance(v, (str, int, float)) else ""


def validar_questao(q: dict) -> dict:
    if not isinstance(q, dict):
        raise LearnErro("questão deve ser objeto", "formato")
    tipo = str(q.get("tipo", "multipla"))
    if tipo not in TIPOS_QUESTAO:
        raise LearnErro("tipo de questão inválido", "tipo")
    enunciado = _txt(q.get("enunciado"), 2000)
    if len(enunciado) < 5:
        raise LearnErro("enunciado curto demais", "enunciado")
    out = {"id": _txt(q.get("id"), 64) or None, "enunciado": enunciado, "tipo": tipo,
           "explicacao": _txt(q.get("explicacao"), 1000),
           "dificuldade": _txt(q.get("dificuldade"), 20) or "media",
           "assunto": _txt(q.get("assunto"), 120)}
    if tipo in ("multipla", "vf"):
        ops = q.get("opcoes")
        n_min, n_max = (2, 6) if tipo == "multipla" else (2, 2)
        if not isinstance(ops, list) or not (n_min <= len(ops) <= n_max):
            raise LearnErro(f"opções: {n_min}..{n_max}", "opcoes")
        out["opcoes"] = [_txt(o, 300) for o in ops]
        try:
            gab = int(q.get("gabarito", -1))
        except (TypeError, ValueError):
            raise LearnErro("gabarito deve ser índice", "gabarito") from None
        if not (0 <= gab < len(out["opcoes"])):
            raise LearnErro("gabarito fora das opções", "gabarito")
        out["gabarito"] = str(gab)
    elif tipo == "curta":
        gab = _txt(q.get("gabarito"), 300)
        if not gab:
            raise LearnErro("resposta curta exige gabarito", "gabarito")
        out["opcoes"] = []
        out["gabarito"] = gab
    else:  # discursiva: critérios explícitos, avaliação assistida
        crit = _txt(q.get("criterios", q.get("gabarito", "")), 1000)
        if len(crit) < 10:
            raise LearnErro("discursiva exige critérios (10+ chars)", "criterios")
        out["opcoes"] = []
        out["gabarito"] = crit
    return out


def norm_resposta(resposta) -> str:
    return re.sub(r"\s+", " ", str(resposta or "")).strip().lower()[:500]


def corrigir_objetiva(questao: dict, resposta) -> bool:
    """Determinística. multipla/vf por índice (aceita letra a-d ou número);
    curta por igualdade normalizada. Discursiva NUNCA aqui."""
    tipo = questao.get("tipo")
    if tipo in ("multipla", "vf"):
        r = norm_resposta(resposta)
        if re.fullmatch(r"[a-d]", r):
            r = str(ord(r) - ord("a"))
        try:
            return int(float(r)) == int(questao.get("gabarito", -1))
        except (TypeError, ValueError):
            return False
    if tipo == "curta":
        return norm_resposta(resposta) == norm_resposta(questao.get("gabarito", ""))
    raise LearnErro("discursiva: avaliação assistida, não automática", "discursiva")


# ── Repetição espaçada (SM-2 simplificado, determinístico) ─────────────
def proxima_revisao(facilidade: float, intervalo_d: int, acertou: bool, hoje=None) -> tuple:
    fac = max(1.3, float(facilidade or 2.5) + (0.1 if acertou else -0.3))
    if not acertou:
        intervalo = 1
    elif intervalo_d <= 0:
        intervalo = 1
    elif intervalo_d == 1:
        intervalo = 6
    else:
        intervalo = max(1, round(intervalo_d * fac))
    hoje = hoje or date.today()
    return round(fac, 2), intervalo, (hoje + timedelta(days=intervalo)).isoformat()


# ── Operações (tentativas, respostas, importação) ───────────────────
def novo_id(prefixo: str = "id") -> str:
    import secrets as _s
    return f"{prefixo}-{_s.token_hex(6)}"


def criar_assessment(db, owner: str, titulo: str, assunto: str, questões: list,
                     origem: str = "ia", assessment_id: str = "") -> dict:
    """Valida e persiste prova + questões. Idempotente por id."""
    if not isinstance(questões, list) or not (1 <= len(questões) <= 30):
        raise LearnErro("questões: 1..30", "questoes")
    norm = [validar_questao(q) for q in questões]
    aid = (assessment_id or "")[:64] or novo_id("av")
    with db:
        db.execute("INSERT OR IGNORE INTO assessments (id, owner_id, titulo, assunto, origem, created_at)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (aid, owner, str(titulo or "")[:160], str(assunto or "")[:120],
                    str(origem or "ia")[:20], agora_iso()))
        for i, q in enumerate(norm):
            qid = q["id"] or f"{aid}-q{i}"
            db.execute("INSERT OR IGNORE INTO questions (id, assessment_id, owner_id, enunciado, tipo,"
                       " opcoes, gabarito, explicacao, dificuldade, assunto, ordem)"
                       " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (qid, aid, owner, q["enunciado"], q["tipo"],
                        json.dumps(q["opcoes"], ensure_ascii=False), q["gabarito"],
                        q["explicacao"], q.get("dificuldade", "media"), q.get("assunto", ""),
                        i))
    return {"id": aid, "total": len(norm)}


def obter_assessment(db, owner: str, assessment_id: str, com_gabarito: bool = False) -> dict:
    row = db.execute("SELECT id, titulo, assunto, origem FROM assessments "
                     "WHERE id=? AND owner_id=?", (assessment_id, owner)).fetchone()
    if not row:
        raise LearnErro("avaliação não encontrada", "ausente")
    qs = db.execute("SELECT id, enunciado, tipo, opcoes, gabarito, explicacao, dificuldade, assunto"
                    " FROM questions WHERE assessment_id=? AND owner_id=? ORDER BY ordem",
                    (assessment_id, owner)).fetchall()
    out = []
    for qid, en, tipo, ops, gab, exp, dif, ass in qs:
        item = {"id": qid, "enunciado": en, "tipo": tipo,
                "opcoes": json.loads(ops or "[]"), "dificuldade": dif, "assunto": ass}
        if com_gabarito:
            item["gabarito"] = gab
            item["explicacao"] = exp
        out.append(item)
    return {"id": row[0], "titulo": row[1], "assunto": row[2], "origem": row[3], "questions": out}


def iniciar_tentativa(db, owner: str, assessment_id: str, attempt_id: str = "") -> dict:
    row = db.execute("SELECT id FROM assessments WHERE id=? AND owner_id=?",
                     (assessment_id, owner)).fetchone()
    if not row:
        raise LearnErro("avaliação não encontrada", "ausente")
    aid = (attempt_id or "")[:64] or novo_id("att")
    with db:
        db.execute("INSERT OR IGNORE INTO attempts (id, assessment_id, owner_id, iniciada_em)"
                   " VALUES (?,?,?,?)", (aid, assessment_id, owner, agora_iso()))
    return {"id": aid, "assessment_id": assessment_id}


def responder(db, owner: str, attempt_id: str, question_id: str, resposta) -> dict:
    att = db.execute("SELECT assessment_id, finalizada_em FROM attempts "
                     "WHERE id=? AND owner_id=?", (attempt_id, owner)).fetchone()
    if not att:
        raise LearnErro("tentativa não encontrada", "ausente")
    if att[1]:
        raise LearnErro("tentativa já finalizada", "finalizada")
    q = db.execute("SELECT enunciado, tipo, opcoes, gabarito, explicacao FROM questions "
                   "WHERE id=? AND assessment_id=? AND owner_id=?",
                   (question_id, att[0], owner)).fetchone()
    if not q:
        raise LearnErro("questão não encontrada", "ausente")
    questao = {"tipo": q[1], "gabarito": q[3]}
    if q[1] == "discursiva":
        with db:
            db.execute("INSERT OR REPLACE INTO answers (attempt_id, question_id, owner_id,"
                       " resposta, correta, corrigida_em) VALUES (?,?,?,?,?,?)",
                       (attempt_id, question_id, owner, str(resposta or "")[:2000],
                        -1, agora_iso()))
        return {"correta": None, "avaliacao": "assistida",
                "aviso": "Discursiva: avaliação assistida por IA, não gabarito final."}
    certa = corrigir_objetiva(questao, resposta)
    with db:
        db.execute("INSERT OR REPLACE INTO answers (attempt_id, question_id, owner_id,"
                   " resposta, correta, corrigida_em) VALUES (?,?,?,?,?,?)",
                   (attempt_id, question_id, owner, str(resposta or "")[:500],
                    1 if certa else 0, agora_iso()))
    return {"correta": bool(certa)}


def finalizar_tentativa(db, owner: str, attempt_id: str) -> dict:
    att = db.execute("SELECT assessment_id FROM attempts WHERE id=? AND owner_id=?",
                     (attempt_id, owner)).fetchone()
    if not att:
        raise LearnErro("tentativa não encontrada", "ausente")
    rows = db.execute("SELECT q.id, q.tipo, q.gabarito, q.explicacao, a.resposta, a.correta,"
                      " q.enunciado, q.opcoes FROM answers a JOIN questions q ON q.id=a.question_id "
                      "WHERE a.attempt_id=? AND a.owner_id=?", (attempt_id, owner)).fetchall()
    certas = sum(1 for r in rows if r[5] == 1)
    total = sum(1 for r in rows if r[5] in (0, 1))
    pendentes = sum(1 for r in rows if r[5] == -1)
    nota = round(certas / total, 3) if total else 0.0
    with db:
        db.execute("UPDATE attempts SET finalizada_em=?, nota=?, total=? WHERE id=? AND owner_id=?",
                   (agora_iso(), nota, total, attempt_id, owner))
        db.execute("INSERT INTO study_events (owner_id, tipo, ref_id, detalhe, ts) VALUES (?,?,?,?,?)",
                   (owner, "prova_finalizada", attempt_id,
                    f"{certas}/{total}" + (f" +{pendentes} discursiva(s)" if pendentes else ""),
                    agora_iso()))
    def _texto_opcao(r):
        try:
            ops = json.loads(r[7] or "[]")
            return ops[int(r[2])] if r[2].lstrip("-").isdigit() and 0 <= int(r[2]) < len(ops) else r[2]
        except (ValueError, IndexError, TypeError):
            return r[2]
    erradas = [{"question_id": r[0], "enunciado": r[6], "sua": r[4], "gabarito": r[2],
                "gabarito_texto": _texto_opcao(r), "explicacao": r[3]}
               for r in rows if r[5] == 0]
    return {"id": attempt_id, "nota": nota, "certas": certas, "total": total,
            "pendentes_avaliacao": pendentes, "erradas": erradas[:10]}


def historico_avulso(db, owner: str, titulo: str, assunto: str, certas: int,
                     total: int) -> dict:
    """Registra resultado de quiz inline (autodeclarado, origem marcada)."""
    aid = novo_id("av")
    with db:
        db.execute("INSERT INTO assessments (id, owner_id, titulo, assunto, origem, created_at)"
                   " VALUES (?,?,?,?,?,?)",
                   (aid, owner, str(titulo or "Quiz")[:160], str(assunto or "")[:120],
                    "quiz-inline", agora_iso()))
        tid = novo_id("att")
        db.execute("INSERT INTO attempts (id, assessment_id, owner_id, iniciada_em,"
                   " finalizada_em, nota, total) VALUES (?,?,?,?,?,?,?)",
                   (tid, aid, owner, agora_iso(), agora_iso(),
                    round((certas or 0) / max(total or 1, 1), 3), int(total or 0)))
        db.execute("INSERT INTO study_events (owner_id, tipo, ref_id, detalhe, ts) VALUES (?,?,?,?,?)",
                   (owner, "quiz_inline", tid, f"{certas}/{total}", agora_iso()))
    return {"assessment_id": aid, "attempt_id": tid}


# ── Estatísticas (só dados reais; vazio útil sem dados) ───────────────
def desempenho_por_assunto(db, owner: str) -> list:
    rows = db.execute("""SELECT q.assunto, SUM(a.correta), COUNT(*)
                         FROM answers a JOIN questions q ON q.id = a.question_id
                         WHERE a.owner_id=? GROUP BY q.assunto
                         ORDER BY COUNT(*) DESC""", (owner,)).fetchall()
    out = []
    for assunto, acertos, total in rows:
        total = total or 1
        out.append({"assunto": assunto or "geral", "acertos": acertos or 0,
                    "total": total, "taxa": round((acertos or 0) / total, 3)})
    return sorted(out, key=lambda r: (r["taxa"], -r["total"]))


def resumo_progresso(db, owner: str) -> dict:
    att = db.execute("SELECT COUNT(*), SUM(CASE WHEN finalizada_em != '' THEN 1 ELSE 0 END) "
                     "FROM attempts WHERE owner_id=?", (owner,)).fetchone()
    acc = db.execute("SELECT COUNT(*) FROM answers WHERE owner_id=? AND correta=1",
                     (owner,)).fetchone()[0]
    tot = db.execute("SELECT COUNT(*) FROM answers WHERE owner_id=?", (owner,)).fetchone()[0]
    plan = db.execute("SELECT COUNT(*), SUM(feito) FROM plan_items WHERE owner_id=?",
                      (owner,)).fetchone()
    hoje = date.today().isoformat()
    rev = db.execute("SELECT COUNT(*) FROM reviews WHERE owner_id=? AND proxima_iso<=?",
                     (owner, hoje)).fetchone()[0]
    return {"avaliacoes": att[0] or 0, "concluidas": att[1] or 0,
            "acertos": acc or 0, "respostas": tot or 0,
            "itens_plano": plan[0] or 0, "itens_feitos": plan[1] or 0,
            "revisoes_pendentes": rev or 0}
