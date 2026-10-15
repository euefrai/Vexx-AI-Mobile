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
    norm = []
    for q in questões:
        qq = dict(q) if isinstance(q, dict) else {}
        qq.setdefault("assunto", assunto or "")
        norm.append(validar_questao(qq))
    aid = (assessment_id or "")[:64] or novo_id("av")
    with db:
        db.execute("INSERT OR IGNORE INTO assessments (id, owner_id, titulo, assunto, origem, created_at)"
                   " VALUES (?,?,?,?,?,?)",
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
    rows = db.execute("""SELECT q.assunto,
                                SUM(CASE WHEN a.correta=1 THEN 1 ELSE 0 END),
                                SUM(CASE WHEN a.correta IN (0,1) THEN 1 ELSE 0 END)
                         FROM answers a JOIN questions q ON q.id = a.question_id
                         WHERE a.owner_id=? GROUP BY q.assunto""", (owner,)).fetchall()
    out = []
    for assunto, acertos, total in rows:
        total = total or 0
        if not total:
            continue  # só discursiva pendente: sem taxa, sem invenção
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


# ── Planos de estudo ────────────────────────────────────────────────
def _validar_itens(itens) -> list:
    if not isinstance(itens, list) or not (1 <= len(itens) <= 50):
        raise LearnErro("itens: 1..50", "itens")
    out = []
    for i, it in enumerate(itens):
        if not isinstance(it, dict):
            raise LearnErro(f"item {i} inválido", "itens")
        titulo = _txt(it.get("titulo"), 200)
        if len(titulo) < 3:
            raise LearnErro(f"item {i} sem título", "itens")
        tipo = str(it.get("tipo", "conteudo"))
        if tipo not in TIPOS_ITEM:
            raise LearnErro(f"item {i}: tipo inválido", "itens")
        out.append({"titulo": titulo, "tipo": tipo})
    return out


def criar_plano(db, owner: str, titulo: str, objetivo: str = "", assunto: str = "",
               prazo_iso: str = "", min_dia: int = 30, itens: list = None,
               plan_id: str = "") -> dict:
    """Cria plano + itens. Idempotente por plan_id (reenvio não duplica)."""
    if len(_txt(titulo, 160)) < 3:
        raise LearnErro("plano exige título", "titulo")
    norm = _validar_itens(itens or [])
    pid = (plan_id or "")[:64] or novo_id("pl")
    try:
        min_d = max(5, min(int(min_dia or 30), 480))
    except (TypeError, ValueError):
        min_d = 30
    with db:
        db.execute("INSERT OR IGNORE INTO learning_plans (id, owner_id, titulo, objetivo,"
                   " assunto, prazo_iso, min_dia, created_at, updated_at)"
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (pid, owner, str(titulo)[:160], str(objetivo or "")[:500],
                    str(assunto or "")[:120], str(prazo_iso or "")[:32], min_d, agora_iso(), agora_iso()))
        for i, it in enumerate(norm):
            db.execute("INSERT INTO plan_items (plan_id, owner_id, titulo, tipo, ordem, created_at)"
                       " SELECT ?,?,?,?,?,? WHERE NOT EXISTS"
                       " (SELECT 1 FROM plan_items WHERE plan_id=? AND owner_id=? AND titulo=? AND ordem=?)",
                       (pid, owner, it["titulo"], it["tipo"], i, agora_iso(),
                        pid, owner, it["titulo"], i))
    return {"id": pid, "itens": len(norm)}


def obter_plano(db, owner: str, plan_id: str) -> dict:
    row = db.execute("SELECT id, titulo, objetivo, assunto, prazo_iso, min_dia FROM learning_plans "
                     "WHERE id=? AND owner_id=?", (plan_id, owner)).fetchone()
    if not row:
        raise LearnErro("plano não encontrado", "ausente")
    itens = db.execute("SELECT id, titulo, tipo, ordem, feito, feito_em FROM plan_items "
                       "WHERE plan_id=? AND owner_id=? ORDER BY ordem",
                       (plan_id, owner)).fetchall()
    lista = [{"id": i[0], "titulo": i[1], "tipo": i[2], "ordem": i[3],
              "feito": bool(i[4]), "feito_em": i[5]} for i in itens]
    feitos = sum(1 for i in lista if i["feito"])
    return {"id": row[0], "titulo": row[1], "objetivo": row[2], "assunto": row[3],
            "prazo_iso": row[4], "min_dia": row[5], "itens": lista,
            "progresso": {"feitos": feitos, "total": len(lista),
                          "taxa": round(feitos / len(lista), 3) if lista else 0.0}}


def concluir_item(db, owner: str, plan_id: str, item_id: int, feito: bool = True) -> dict:
    row = db.execute("SELECT id FROM plan_items WHERE id=? AND plan_id=? AND owner_id=?",
                     (item_id, plan_id, owner)).fetchone()
    if not row:
        raise LearnErro("item não encontrado", "ausente")
    with db:
        db.execute("UPDATE plan_items SET feito=?, feito_em=? WHERE id=? AND owner_id=?",
                   (1 if feito else 0, agora_iso() if feito else "", item_id, owner))
        db.execute("UPDATE learning_plans SET updated_at=? WHERE id=? AND owner_id=?",
                   (agora_iso(), plan_id, owner))
        db.execute("INSERT INTO study_events (owner_id, tipo, ref_id, detalhe, ts) VALUES (?,?,?,?,?)",
                   (owner, "item_concluido" if feito else "item_reaberto",
                    str(item_id), plan_id, agora_iso()))
    return obter_plano(db, owner, plan_id)["progresso"]


def atualizar_plano(db, owner: str, plan_id: str, mudancas: dict) -> dict:
    """Atualiza campos/itens preservando concluídos compatíveis (match por título).

    Nunca inventa disponibilidade: só aplica o que foi informado.
    """
    plano = obter_plano(db, owner, plan_id)  # 404 se de outro dono
    if not isinstance(mudancas, dict):
        raise LearnErro("mudanças inválidas", "formato")
    with db:
        if any(k in mudancas for k in ("titulo", "objetivo", "assunto", "prazo_iso", "min_dia")):
            try:
                min_d = max(5, min(int(mudancas.get("min_dia", plano["min_dia"]) or 30), 480))
            except (TypeError, ValueError):
                min_d = plano["min_dia"]
            db.execute("UPDATE learning_plans SET titulo=?, objetivo=?, assunto=?, prazo_iso=?,"
                       " min_dia=?, updated_at=? WHERE id=? AND owner_id=?",
                       (str(mudancas.get("titulo", plano["titulo"]))[:160],
                        str(mudancas.get("objetivo", plano["objetivo"]))[:500],
                        str(mudancas.get("assunto", plano["assunto"]))[:120],
                        str(mudancas.get("prazo_iso", plano["prazo_iso"]))[:32],
                        min_d, agora_iso(), plan_id, owner))
        if "itens" in mudancas:
            norm = _validar_itens(mudancas["itens"])
            feitos_antes = {norm_resposta(i["titulo"]): i for i in plano["itens"] if i["feito"]}
            db.execute("DELETE FROM plan_items WHERE plan_id=? AND owner_id=?", (plan_id, owner))
            for i, it in enumerate(norm):
                antes = feitos_antes.get(norm_resposta(it["titulo"]))
                db.execute("INSERT INTO plan_items (plan_id, owner_id, titulo, tipo, ordem,"
                           " feito, feito_em, created_at) VALUES (?,?,?,?,?,?,?,?)",
                           (plan_id, owner, it["titulo"], it["tipo"], i,
                            1 if antes else 0, antes["feito_em"] if antes else "",
                            agora_iso()))
            db.execute("UPDATE learning_plans SET updated_at=? WHERE id=? AND owner_id=?",
                       (agora_iso(), plan_id, owner))
    return obter_plano(db, owner, plan_id)


def listar_planos(db, owner: str) -> list:
    rows = db.execute("SELECT id, titulo, assunto, prazo_iso, min_dia, updated_at FROM learning_plans "
                      "WHERE owner_id=? ORDER BY updated_at DESC LIMIT 50", (owner,)).fetchall()
    out = []
    for pid, titulo, assunto, prazo, min_d, upd in rows:
        n = db.execute("SELECT COUNT(*), SUM(feito) FROM plan_items WHERE plan_id=? AND owner_id=?",
                       (pid, owner)).fetchone()
        out.append({"id": pid, "titulo": titulo, "assunto": assunto or "", "prazo_iso": prazo or "",
                    "min_dia": min_d, "feitos": n[1] or 0, "total": n[0] or 0})
    return out


# ── Flashcards e revisão ────────────────────────────────────────────
def _validar_cards(cards) -> list:
    if not isinstance(cards, list) or not (1 <= len(cards) <= 100):
        raise LearnErro("cards: 1..100", "cards")
    out = []
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            raise LearnErro(f"card {i} inválido", "cards")
        frente, verso = _txt(c.get("frente"), 500), _txt(c.get("verso"), 1000)
        if len(frente) < 2 or len(verso) < 1:
            raise LearnErro(f"card {i} incompleto", "cards")
        out.append({"id": _txt(c.get("id"), 64) or None, "frente": frente, "verso": verso,
                    "assunto": _txt(c.get("assunto"), 120)})
    return out


def criar_flashcards(db, owner: str, cards: list) -> dict:
    """Cria cartões + agenda inicial (vencem hoje). Idempotente por id."""
    norm = _validar_cards(cards)
    ids = []
    hoje = date.today().isoformat()
    with db:
        for c in norm:
            fid = c["id"] or novo_id("fc")
            db.execute("INSERT OR IGNORE INTO flashcards (id, owner_id, frente, verso, assunto, created_at)"
                       " VALUES (?,?,?,?,?,?)",
                       (fid, owner, c["frente"], c["verso"], c["assunto"], agora_iso()))
            db.execute("INSERT OR IGNORE INTO reviews (flashcard_id, owner_id, proxima_iso,"
                       " intervalo_d, facilidade, acertos, erros, updated_at)"
                       " VALUES (?,?,?,?,?,?,?,?)",
                       (fid, owner, hoje, 0, 2.5, 0, 0, agora_iso()))
            ids.append(fid)
    return {"ids": ids, "total": len(ids)}


def revisoes_pendentes(db, owner: str, hoje=None, limite: int = 50) -> list:
    dia = (hoje or date.today()).isoformat() if hasattr((hoje or date.today()), "isoformat") else str(hoje)
    rows = db.execute("SELECT f.id, f.frente, f.verso, f.assunto, r.proxima_iso, r.intervalo_d,"
                      " r.facilidade FROM reviews r JOIN flashcards f ON f.id=r.flashcard_id"
                      " AND f.owner_id=r.owner_id WHERE r.owner_id=? AND r.proxima_iso<=?"
                      " ORDER BY r.proxima_iso LIMIT ?",
                      (owner, dia, max(1, min(int(limite or 50), 200)))).fetchall()
    return [{"id": r[0], "frente": r[1], "verso": r[2], "assunto": r[3] or "",
             "proxima_iso": r[4], "intervalo_d": r[5], "facilidade": r[6]} for r in rows]


def revisar_flashcard(db, owner: str, flashcard_id: str, acertou: bool, hoje=None) -> dict:
    """Aplica SM-2 e reagenda. Datas determinísticas; sem promessa de notificação."""
    row = db.execute("SELECT facilidade, intervalo_d FROM reviews "
                     "WHERE flashcard_id=? AND owner_id=?", (flashcard_id, owner)).fetchone()
    if not row:
        raise LearnErro("cartão não encontrado", "ausente")
    dia = hoje or date.today()
    fac, intervalo, proxima = proxima_revisao(row[0], row[1], bool(acertou), hoje=dia)
    with db:
        db.execute("UPDATE reviews SET proxima_iso=?, intervalo_d=?, facilidade=?,"
                   " acertos=acertos+?, erros=erros+?, updated_at=? WHERE flashcard_id=? AND owner_id=?",
                   (proxima, intervalo, fac, 1 if acertou else 0, 0 if acertou else 1,
                    agora_iso(), flashcard_id, owner))
        db.execute("INSERT INTO study_events (owner_id, tipo, ref_id, detalhe, ts) VALUES (?,?,?,?,?)",
                   (owner, "revisao_flashcard", flashcard_id,
                    "acerto" if acertou else "erro", agora_iso()))
    return {"id": flashcard_id, "acertou": bool(acertou), "facilidade": fac,
            "intervalo_d": intervalo, "proxima_iso": proxima}


# ── Qualidade (§13): sinalizar gabarito duvidoso, sem reescrever história ──
def sinalizar_questao(db, owner: str, question_id: str, motivo: str) -> dict:
    q = db.execute("SELECT assessment_id, enunciado FROM questions WHERE id=? AND owner_id=?",
                   (question_id, owner)).fetchone()
    if not q:
        raise LearnErro("questão não encontrada", "ausente")
    if len(_txt(motivo, 500)) < 5:
        raise LearnErro("descreva o problema (5+ caracteres)", "motivo")
    with db:
        db.execute("INSERT INTO study_events (owner_id, tipo, ref_id, detalhe, ts) VALUES (?,?,?,?,?)",
                   (owner, "questao_sinalizada", question_id,
                    str(motivo)[:500], agora_iso()))
    return {"ok": True, "question_id": question_id}


def questoes_erradas(db, owner: str, limite: int = 20) -> list:
    """Erros recentes (base p/ 'refazer as que errei' e simulados de reforço)."""
    rows = db.execute("SELECT q.id, q.enunciado, q.assunto, q.tipo, a.resposta, a.corrigida_em"
                      " FROM answers a JOIN questions q ON q.id=a.question_id"
                      " WHERE a.owner_id=? AND a.correta=0 ORDER BY a.corrigida_em DESC LIMIT ?",
                      (owner, max(1, min(int(limite or 20), 100)))).fetchall()
    return [{"question_id": r[0], "enunciado": r[1], "assunto": r[2] or "",
             "tipo": r[3], "sua_resposta": r[4], "em": r[5]} for r in rows]


def criar_reforco(db, owner: str, limite: int = 10) -> dict:
    """Simulado de reforço com as questões que o dono errou (dados reais).

    Reutiliza enunciado/gabarito/explicação originais — nunca reescreve nem
    inventa questões. Origem marcada como 'reforco'. Sem erros recentes:
    LearnErro 'sem_dados' (o chat informa, em vez de inventar).
    """
    erradas = questoes_erradas(db, owner, limite)
    if not erradas:
        raise LearnErro("sem erros recentes para reforçar", "sem_dados")
    ids = [e["question_id"] for e in erradas]
    qs = []
    for qid in ids:
        row = db.execute("SELECT enunciado, tipo, opcoes, gabarito, explicacao, dificuldade, assunto"
                         " FROM questions WHERE id=? AND owner_id=?", (qid, owner)).fetchone()
        if not row:
            continue
        try:
            ops = json.loads(row[2] or "[]")
        except (TypeError, ValueError):
            ops = []
        q = {"id": f"{qid}-r", "enunciado": row[0], "tipo": row[1], "opcoes": ops,
             "explicacao": row[4], "dificuldade": row[5] or "media", "assunto": row[6] or ""}
        if row[1] in ("multipla", "vf"):
            try:
                q["gabarito"] = int(row[3])
            except (TypeError, ValueError):
                continue  # gabarito corrompido: pula, não inventa
        else:
            q["gabarito"] = row[3]
        try:
            validar_questao(q)
        except LearnErro:
            continue
        qs.append(q)
    if not qs:
        raise LearnErro("sem erros recentes para reforçar", "sem_dados")
    assuntos = sorted({q["assunto"] for q in qs if q["assunto"]})
    return criar_assessment(db, owner, "Reforço: " + (", ".join(assuntos[:3]) or "geral"),
                           assuntos[0] if assuntos else "", qs, origem="reforco")


# ── Aprendizado adaptativo (regras transparentes, §9) ─────────────
def recomendar(db, owner: str, hoje=None) -> dict:
    """Recomendações determinísticas a partir de dados reais.

    Sem dados suficientes: lista vazia + motivo explícito (nunca inventa
    dificuldade). Sem diagnósticos pessoais: só tópicos e ritmo.
    """
    recs = []
    perf = desempenho_por_assunto(db, owner)
    for p in perf:
        if p["total"] >= 3 and p["taxa"] < 0.6:
            recs.append({"tipo": "revisar", "assunto": p["assunto"],
                         "detalhe": f"{p['acertos']}/{p['total']} ({p['taxa']:.0%}) — refazer questões",
                         "base": "respostas_reais"})
    for p in perf:
        if p["total"] >= 3 and p["taxa"] >= 0.8 and len(recs) < 5:
            recs.append({"tipo": "avancar", "assunto": p["assunto"],
                         "detalhe": f"{p['taxa']:.0%} de acerto — pode subir o nível",
                         "base": "respostas_reais"})
    dia = (hoje or date.today()).isoformat()
    pend = db.execute("SELECT COUNT(*) FROM reviews WHERE owner_id=? AND proxima_iso<=?",
                      (owner, dia)).fetchone()[0]
    if pend:
        recs.insert(0, {"tipo": "revisoes_pendentes", "assunto": "",
                        "detalhe": f"{pend} cartão(ões) vencendo — revise hoje",
                        "base": "agenda_real"})
    erradas = questoes_erradas(db, owner, 1)
    if erradas and not any(r["tipo"] == "revisar" for r in recs):
        recs.append({"tipo": "refazer_erradas", "assunto": erradas[0]["assunto"],
                     "detalhe": "há questões erradas recentes para refazer",
                     "base": "respostas_reais"})
    if not recs:
        return {"recomendacoes": [], "motivo": "sem_dados",
                "aviso": "Ainda não há respostas suficientes para recomendar."}
    return {"recomendacoes": recs[:5], "motivo": "dados_reais"}
