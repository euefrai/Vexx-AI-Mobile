"""PC-side durable SQLite agent. Run only on a trusted Windows computer."""
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import docs_agent
import hermes_bridge
import jdui
import julia_auth
import remoto
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("julia-pc")

SYSTEM_PADRAO = ("Você é a Júlia, assistente pessoal do usuário. "
                 "Responda em português, de forma direta e útil. "
                 "Use markdown leve: títulos curtos, listas, **negrito**, `código`, tabelas quando útil. "
                 "Se navegar/pesquisar, cite ao final uma seção 'Fontes:' com os links usados. "
                 "Se pedirem imagem, responda com ![descrição](https://...) em markdown além do texto. "
                 "RECURSOS VISUAIS (use quando pedirem desenho, diagrama, mapa ou foto): "
                 "1) Desenho/diagrama/mapa/ícone: bloco ```svg com o SVG (formas, setas, textos, cores). "
                 "2) Arte com caracteres (banner, mapa simples): bloco de código. "
                 "3) Para foto/ilustração: ![descrição](https://...) em markdown. "
                 "INTERFACES INTERATIVAS (quiz, checklist, calculadora, cards, diagrama, tabela, formulário): "
                 "NUNCA JavaScript, CSS ou código executável — descreva em blocos ```jdui "
                 "(JSON {version:'julia-ui-message/v1',blocks:[{type:'ui',component,props}]}). "
                 "Pergunta simples → só texto, sem interface.")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def database_path() -> Path:
    return Path(os.environ.get("JULIA_SQLITE_PATH", str(Path.home() / ".julia-mobile" / "memory.sqlite3")))


DONO_PADRAO = "local"


def dono_valido(v) -> str:
    """Sanitiza o dono vindo do relay (autenticado). Padrão: 'local'."""
    s = str(v or "").strip().lower()[:40]
    if re.fullmatch(r"[a-z0-9_-]{1,40}", s):
        return s
    return DONO_PADRAO


def _ensure_owner_coluna(db, tabela: str) -> None:
    cols = [c[1] for c in db.execute(f"PRAGMA table_info({tabela})").fetchall()]
    if "owner_id" not in cols:
        db.execute(f"ALTER TABLE {tabela} ADD COLUMN owner_id TEXT NOT NULL DEFAULT '{DONO_PADRAO}'")


def _colunas(db, tabela: str) -> list:
    try:
        return [c[1] for c in db.execute(f"PRAGMA table_info({tabela})").fetchall()]
    except Exception:
        return []


def _migrar_memories_por_dono(db) -> None:
    """memories passa de PK(key) para PK(owner_id, key), preservando dados locais."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='memories'").fetchone()
    if not sql or not sql[0]:
        db.execute("""CREATE TABLE memories (
            owner_id TEXT NOT NULL DEFAULT 'local', key TEXT NOT NULL,
            value TEXT NOT NULL, updated_at TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'semantica', assunto TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmada',
            origem_conv TEXT NOT NULL DEFAULT '', origem_msg TEXT NOT NULL DEFAULT '',
            valido_ate TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (owner_id, key)
        )""")
        return
    if "owner_id" in sql[0]:
        return
    db.execute("ALTER TABLE memories RENAME TO memories_antiga")
    db.execute("""CREATE TABLE memories (
        owner_id TEXT NOT NULL DEFAULT 'local', key TEXT NOT NULL,
        value TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (owner_id, key)
    )""")
    db.execute("""INSERT INTO memories (owner_id, key, value, updated_at)
                  SELECT 'local', key, value, updated_at FROM memories_antiga""")
    db.execute("DROP TABLE memories_antiga")
    log.info("memories migrada para isolamento por dono")


def _memoria_v41(db) -> None:
    """Colunas tipadas + eventos + settings + FTS (idempotente, preserva dados)."""
    for _col, _ddl in (("tipo", "TEXT NOT NULL DEFAULT 'semantica'"),
                       ("assunto", "TEXT NOT NULL DEFAULT ''"),
                       ("status", "TEXT NOT NULL DEFAULT 'confirmada'"),
                       ("origem_conv", "TEXT NOT NULL DEFAULT ''"),
                       ("origem_msg", "TEXT NOT NULL DEFAULT ''"),
                       ("valido_ate", "TEXT NOT NULL DEFAULT ''")):
        try:
            if _col not in _colunas(db, "memories"):
                db.execute(f"ALTER TABLE memories ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass
    db.execute("""CREATE TABLE IF NOT EXISTS memory_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL DEFAULT 'local',
        titulo TEXT NOT NULL, data_iso TEXT NOT NULL DEFAULT '', data_raw TEXT NOT NULL DEFAULT '',
        assunto TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ativo',
        origem_conv TEXT NOT NULL DEFAULT '', origem_msg TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mevents_owner ON memory_events(owner_id, status, data_iso)")
    db.execute("""CREATE TABLE IF NOT EXISTS memory_settings (
        owner_id TEXT PRIMARY KEY, learning INT NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""")
    _criar_fts_memorias(db)


def _criar_fts_memorias(db) -> None:
    """Índice FTS5 para busca textual (opcional: sem ele, cai no overlap)."""
    try:
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                      USING fts5(key, value, assunto, owner_id, tokenize='unicode61')""")
    except Exception as exc:
        log.warning("FTS5 indisponível (%s); busca usa overlap", type(exc).__name__)


def _fts_sync(db, owner: str, chave: str, valor: str, assunto: str) -> None:
    try:
        db.execute("DELETE FROM memories_fts WHERE owner_id=? AND key=?", (owner, chave))
        if valor:
            db.execute("INSERT INTO memories_fts (key, value, assunto, owner_id) VALUES (?,?,?,?)",
                       (chave, valor, assunto, owner))
    except Exception:
        pass


def open_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        created_at TEXT NOT NULL, received_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    try:
        db.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe (migração idempotente)
    _ensure_owner_coluna(db, "messages")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
        user_message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL,
        reply_id TEXT, response_text TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    _ensure_owner_coluna(db, "ai_requests")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_created ON messages(origin, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_conv ON messages(origin, conversation_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id, origin, created_at)")
    _migrar_memories_por_dono(db)
    _memoria_v41(db)
    julia_auth.criar_tabelas(db)
    julia_auth.migrar_legado(db)
    db.execute("""CREATE TABLE IF NOT EXISTS memory_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'chat', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    _ensure_owner_coluna(db, "memory_facts")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memfacts_key ON memory_facts(key, updated_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memfacts_owner ON memory_facts(owner_id, updated_at)")
    docs_agent.criar_tabelas(db)
    for _tabela in ("documents", "doc_chunks"):
        _ensure_owner_coluna(db, _tabela)
    db.execute("CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(owner_id, created_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS ui_state (
        k TEXT PRIMARY KEY, message_id TEXT NOT NULL, slot TEXT NOT NULL,
        state TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    _ensure_owner_coluna(db, "ui_state")
    db.execute("CREATE INDEX IF NOT EXISTS idx_uistate_msg ON ui_state(message_id)")
    db.commit()
    return db


def persist_messages(db, rows, owner=DONO_PADRAO):
    owner = dono_valido(owner)
    confirmed = []
    with db:
        for m in rows:
            # The relay validates payloads, but the agent independently limits data.
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            txt = m.get("text")
            conv = m.get("conversation_id")
            created = m.get("created_at")
            if not (isinstance(mid, str) and 8 <= len(mid) <= 100 and
                    isinstance(txt, str) and 1 <= len(txt) <= 10000 and
                    isinstance(conv, str) and 3 <= len(conv) <= 100 and
                    isinstance(created, str) and 10 <= len(created) <= 48 and
                    m.get("origin") == "mobile" and m.get("role") in ("user", "assistant")):
                continue
            db.execute("""INSERT OR IGNORE INTO messages
                (id, conversation_id, origin, role, text, created_at, received_at, owner_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (mid, conv, "mobile", m["role"], txt, created,
                 datetime.now(timezone.utc).isoformat(), owner))
            confirmed.append(mid)
    return confirmed


def list_messages(db, limit=200, owner=DONO_PADRAO):
    owner = dono_valido(owner)
    rows = db.execute("""SELECT id, conversation_id, origin, role, text, created_at,
                                COALESCE(model, '')
                         FROM messages WHERE origin=? AND owner_id=?
                         ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", owner, min(max(int(limit), 1), 200))).fetchall()
    cols = ["id", "conversation_id", "origin", "role", "text", "created_at", "model"]
    return [dict(zip(cols, row)) for row in reversed(rows)]


def ai_config() -> dict:
    return {
        "proxy": os.environ.get("HERMES_PROXY_URL", hermes_bridge.DEFAULT_PROXY_URL),
        "model": os.environ.get("JULIA_AI_MODEL", hermes_bridge.DEFAULT_MODEL),
        "system": os.environ.get("JULIA_SYSTEM_PROMPT", SYSTEM_PADRAO)[:2000],
        "context": min(max(int(os.environ.get("JULIA_AI_CONTEXT", "12")), 1), 50),
        "max_tokens": min(max(int(os.environ.get("JULIA_AI_MAX_TOKENS", "1500")), 1), 8000),
        "memoria_global": os.environ.get("JULIA_SHARED_MEMORY", "1") == "1",
        "pesquisa_web": os.environ.get("JULIA_WEB_SEARCH", "1") == "1",
    }


# ── Memória compartilhada entre sessões ──────────────────────────────
def salvar_fatos(db, texto: str, owner=DONO_PADRAO) -> None:
    """Heurística de fundo (respeita 'desativar armazenamento'; explícito passa direto)."""
    owner = dono_valido(owner)
    if not aprendizado_ativo(db, owner):
        return
    import re
    if not isinstance(texto, str):
        return
    t = texto.strip()
    padroes = [
        (r"(?i)lembre-?se (?:que |de que |disso:?\s?)(.{3,300})", "fato"),
        (r"(?i)(?:meu nome é|me chamo|sou o|sou a)\s+(.{2,80})", "nome"),
        (r"(?i)(?:meu foco é|minha meta é|estou trabalhando (?:em|com))\s+(.{3,200})", "foco"),
        (r"(?i)(?:prefiro|gosto de|não gosto de)\s+(.{3,200})", "preferencia"),
    ]
    achou = False
    with db:
        for rx, chave in padroes:
            m = re.search(rx, t)
            if m:
                valor = re.sub(r"\s+", " ", m.group(1)).strip(" .;:")[:300]
                if valor:
                    db.execute("""INSERT INTO memories (owner_id, key, value, updated_at)
                        VALUES (?, ?, ?, ?) ON CONFLICT(owner_id, key) DO UPDATE SET
                        value=excluded.value, updated_at=excluded.updated_at""",
                        (owner, chave, valor, agora_iso()))
                    achou = True
    if achou:
        log.info("memória atualizada a partir da conversa")


def ler_memorias(db, owner=DONO_PADRAO, status: str = "confirmada") -> list:
    try:
        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, origem_msg, "
                          "valido_ate, updated_at FROM memories WHERE owner_id=? AND status=? "
                          "ORDER BY updated_at DESC LIMIT 40", (dono_valido(owner), status)).fetchall()
    except Exception:
        return []
    return [{"key": k, "value": v, "tipo": t, "assunto": a, "status": s,
             "origem_conv": oc, "origem_msg": om, "valido_ate": va, "updated_at": u}
            for k, v, t, a, s, oc, om, va, u in rows if v]


def buscar_fts(db, owner: str, consulta: str, limite: int = 10) -> set:
    """Busca textual FTS5 (vazia se indisponível). Retorna chaves ranqueadas."""
    try:
        toks = [t for t in re.findall(r"[a-zà-ú0-9]{2,}", (consulta or "").lower()) if len(t) > 2][:8]
        if not toks:
            return set()
        q = " OR ".join(f'"{t}"*' for t in toks)
        rows = db.execute("SELECT key FROM memories_fts WHERE memories_fts MATCH ? "
                          "AND owner_id=? LIMIT ?", (q, owner, limite)).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def data_curta(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (iso or "")[:10])
    return f"{m.group(3)}/{m.group(2)}" if m else ""


def proveniencia(f: dict) -> str:
    """Selo de origem para o prompt: '(guardado em 12/10)'."""
    d = data_curta(f.get("updated_at", ""))
    return f" (guardado em {d})" if d else ""


def memoria_global(db, conversation_id: str, limite_outras: int = 8, owner=DONO_PADRAO) -> list:
    """Últimas mensagens de OUTRAS conversas + fatos salvos, para injetar no prompt."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("""SELECT conversation_id, role, text FROM messages
                             WHERE origin='mobile' AND owner_id=? AND conversation_id != ?
                             ORDER BY created_at DESC, id DESC LIMIT ?""",
                          (owner, conversation_id, limite_outras)).fetchall()
    except Exception:
        rows = []
    blocos = []
    for conv, role, text in reversed(rows):
        if role in ("user", "assistant") and text:
            blocos.append(f"[{conv[-6:]}|{role}]: {(text or '')[:300]}")
    fatos = ler_memorias(db, owner)
    if fatos:
        blocos.append("FATOS SALVOS: " + "; ".join(f"{f['key']}={f['value'][:150]}" for f in fatos))
    return blocos


TIPOS_MEMORIA = ("semantica", "temporal", "episodica", "trabalho")
STATUS_MEMORIA = ("confirmada", "pendente", "contraditoria", "arquivada")

SENSIVEIS = ("saude", "saúde", "doenca", "doença", "remedio", "remédio", "medicamento",
             "exame", "hospital", "depressao", "depressão", "ansiedade", "terapia",
             "salario", "salário", "cpf", "rg", "endereco", "endereço", "telefone",
             "senha", "religiao", "religião", "gravidez", "cancer", "câncer", "hiv",
             "soropositivo", "deficiencia", "deficiência", "processo judicial",
             "divida", "dívida", "emprestimo", "empréstimo")


def aprendizado_ativo(db, owner=DONO_PADRAO) -> bool:
    """Toggle 'desativar armazenamento' (painel). Comandos explícitos passam direto."""
    try:
        row = db.execute("SELECT learning FROM memory_settings WHERE owner_id=?",
                         (dono_valido(owner),)).fetchone()
        return (row[0] if row else 1) != 0
    except Exception:
        return True


def definir_aprendizado(db, owner, ativo: bool) -> None:
    with db:
        db.execute("""INSERT INTO memory_settings (owner_id, learning, updated_at)
            VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET
            learning=excluded.learning, updated_at=excluded.updated_at""",
            (dono_valido(owner), 1 if ativo else 0, agora_iso()))


def registrar_memoria(db, owner, chave: str, valor: str, tipo: str = "semantica",
                      assunto: str = "", status: str = "confirmada",
                      origem_conv: str = "", origem_msg: str = "", valido_ate: str = "") -> str:
    """Núcleo V4.1: salva fato tipado com proveniência; contradição preserva histórico."""
    owner = dono_valido(owner)
    chave = re.sub(r"\s+", "_", (chave or "").strip().lower())[:60].strip("_") or "fato"
    valor = (valor or "").strip()[:500]
    if not valor:
        return ""
    if tipo not in TIPOS_MEMORIA:
        tipo = "semantica"
    if status not in STATUS_MEMORIA:
        status = "confirmada"
    anterior = db.execute("SELECT value FROM memories WHERE owner_id=? AND key=?",
                          (owner, chave)).fetchone()
    with db:
        db.execute("""INSERT INTO memories
            (owner_id, key, value, updated_at, tipo, assunto, status, origem_conv, origem_msg, valido_ate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, key) DO UPDATE SET value=excluded.value,
             updated_at=excluded.updated_at, tipo=excluded.tipo, assunto=excluded.assunto,
             status=excluded.status, origem_conv=excluded.origem_conv,
             origem_msg=excluded.origem_msg, valido_ate=excluded.valido_ate""",
            (owner, chave, valor, agora_iso(), tipo, (assunto or "")[:80], status,
             (origem_conv or "")[:100], (origem_msg or "")[:100], (valido_ate or "")[:20]))
        if anterior and anterior[0] != valor:
            db.execute("""INSERT INTO memory_facts (key, value, source, created_at, updated_at, owner_id)
                VALUES (?, ?, 'substituida', ?, ?, ?)""",
                (chave, anterior[0], agora_iso(), agora_iso(), owner))
        db.execute("""INSERT INTO memory_facts (key, value, source, created_at, updated_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (chave, valor, "chat" if status == "confirmada" else "proposta",
             agora_iso(), agora_iso(), owner))
        _fts_sync(db, owner, chave, valor, assunto or "")
    if anterior and anterior[0] != valor:
        log.info("memória corrigida: %s (antiga preservada no histórico)", chave)
    else:
        log.info("memória aprendeu: %s [%s]", chave, tipo)
    return chave


def guardar_fato(db, chave: str, valor: str, origem: str = "chat", owner=DONO_PADRAO) -> None:
    """Compat: delega ao registro tipado V4.1."""
    registrar_memoria(db, owner, chave, valor, origem_conv="", origem_msg="")


def memorias_relevantes(db, pergunta: str, k: int = 8, owner=DONO_PADRAO) -> list:
    """Híbrido FTS5 + overlap + recência. Só confirmadas. Nunca inventa."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, origem_msg, "
                          "valido_ate, updated_at FROM memories "
                          "WHERE owner_id=? AND status='confirmada'", (owner,)).fetchall()
    except Exception:
        return []
    boost = buscar_fts(db, owner, pergunta)
    toks_q = set(re.findall(r"[a-zà-ú0-9]{3,}", (pergunta or "").lower()))
    scored = []
    for (chave, valor, tipo, assunto, status, oc, om, va, upd) in rows:
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", f"{chave} {valor} {assunto}".lower()))
        inter = toks_q & toks if toks_q else set()
        nota = len(inter) * 2 + (1 if chave in ("nome", "foco") else 0)
        if chave in boost:
            nota += 3
        scored.append((nota, upd or "", {"key": chave, "value": valor, "tipo": tipo,
                                         "assunto": assunto, "origem_conv": oc,
                                         "origem_msg": om, "updated_at": upd}))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    if toks_q:
        relevantes = [s for s in scored if s[0] > 0][:k] or scored[:2]
    else:
        relevantes = scored[:k]
    return [f for _, _, f in relevantes]


def interpretar_comando_memoria(db, texto: str, owner=DONO_PADRAO):
    """Comandos diretos de memória. Retorna resposta pronta ou None."""
    owner = dono_valido(owner)
    t = (texto or "").strip().lower()
    if CONFIRM_RE.search(t) and pendencias(db, owner):
        feito = confirmar_pendencia(db, owner)
        if feito:
            return (f"Guardado! ✅ **{feito['key']}**: {feito['value'][:200]}", "mem_confirmar")
    m_nc = re.search(r"(?i)(?:não (?:guard|salv|anot)|descart|esquece(?:r| isso)|não quero)[a-z ]{0,30}$", t)
    if m_nc and pendencias(db, owner):
        feito = descartar_pendencia(db, owner)
        if feito:
            return (f"Tudo bem, descartei **{feito['key']}** — não guardei nada. 🧹", "mem_descartar")
    if re.search(r"(pend[eê]ncia|pendente|aguardando confirma|para confirmar|confirma[rçã])", t):
        pend = pendencias(db, owner)
        if not pend:
            return ("Nada aguardando confirmação. 🌱", "mem_pend_vazia")
        linhas = "\n".join(f"- **{p['key']}**: {p['value'][:150]}" for p in pend)
        return (f"Aguardando sua confirmação:\n\n{linhas}\n\n"
                "Diga \"pode guardar\" para confirmar ou \"descarta\" para recusar.", "mem_pend_listar")
    m_ev = re.search(r"(?i)(cancela(?:r|ndo)?|desmarca(?:r)?|conclu(?:ir|[ií])(?:da|do)?|marcar como feit)[a-z ]{0,20}(.+)", t)
    if m_ev and ("cancel" in t or "desmarc" in t or "conclu" in t or "feit" in t):
        alvo = (m_ev.group(2) or "").strip(" .;:")[:120]
        feito = atualizar_evento(db, owner, alvo, "concluido" if "conclu" in t or "feit" in t else "cancelado")
        if feito:
            return (f"Pronto: **{feito}** atualizado. ✅", "mem_evento")
        return ("Não encontrei esse evento nos próximos. Veja seus eventos perguntando \"meus eventos\".", "mem_evento_nada")
    if re.search(r"(meus eventos|pr[óo]ximos eventos|minha agenda|compromissos)", t):
        evs = proximos_eventos(db, owner)
        if not evs:
            return ("Nenhum evento futuro guardado. Me diga datas como \"minha prova é dia 20/11\". 📅", "mem_eventos_vazios")
        linhas = "\n".join(f"- **{e['data_br']}** (faltam {e['faltam']} dias): {e['titulo'][:150]}" for e in evs)
        return (f"Seus próximos eventos:\n\n{linhas}", "mem_eventos")
    if re.search(r"o que (você|voce) (sabe|lembra|conhece) sobre mim", t) or \
       re.search(r"(mostre|mostra|liste|lista).{0,20}mem[óo]ria", t) or \
       t in ("o que você sabe?", "o que voce sabe?"):
        fatos = ler_memorias(db, owner)
        if not fatos:
            return ("Ainda não guardei nada sobre você. Me diga coisas como "
                    "\"lembre-se que meu foco é X\" e eu aprendo. 🌱", "mem_vazia")
        linhas = "\n".join(f"- **{f['key']}**: {f['value']}" for f in fatos)
        return (f"O que sei sobre você até agora:\n\n{linhas}\n\n"
                "Quer que eu esqueça algo? Diga \"esqueça <assunto>\".", "mem_listar")
    m = re.search(r"(?:esqueça|esqueca|apague|remova|delete)\s+(?:o|a|os|as|de|do|da|que)?\s*(.{2,120})", t)
    if m and ("esque" in t or "apag" in t or "remov" in t or "delet" in t):
        alvo = m.group(1).strip(" .;:")[:120]
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", alvo))
        rows = db.execute("SELECT key, value FROM memories WHERE owner_id=?", (owner,)).fetchall()
        melhor, melhor_n = None, 0
        for chave, valor in rows:
            n = len(toks & set(re.findall(r"[a-zà-ú0-9]{3,}", f"{chave} {valor}".lower())))
            if n > melhor_n:
                melhor, melhor_n = chave, n
        if melhor and melhor_n > 0:
            with db:
                db.execute("DELETE FROM memories WHERE owner_id=? AND key=?", (owner, melhor))
            return (f"Esqueci **{melhor}**. 🧹", "mem_esquecer")
        return ("Não encontrei isso na minha memória. Diga \"o que você sabe sobre mim\" para ver a lista.", "mem_nada")
    return None


MESES_PT = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
            "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
            "outubro": 10, "novembro": 11, "dezembro": 12}
DIAS_PT = {"segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
           "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6}

CONFIRM_RE = re.compile(r"(?i)(pode guardar|pode salvar|pode anotar|confirma|confirmo|isso mesmo|est[áa] certo|correto|t[áa] certo|guarda (isso|a[ií])|salva (isso|a[ií]))")


def parse_data(texto: str, hoje=None):
    """Datas em PT-BR. Retorna (iso|None, raw, precisa_confirmacao).

    Ano explícito ou data relativa = sem ambiguidade. Mês/dia sem ano =
    sempre pede confirmação (nunca presume o ano).
    """
    from datetime import date as _date, timedelta as _td
    hoje = hoje or _date.today()
    t = (texto or "").lower()
    m = re.search(r"\b(\d{1,2})[\/\.](\d{1,2})(?:[\/\.](\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        ano = m.group(3)
        if ano:
            ano = int(ano) + (2000 if len(ano) == 2 and int(ano) < 50 else 0)
            try:
                return _date(ano, mo, d).isoformat(), m.group(0), False
            except ValueError:
                return None, m.group(0), True
        try:
            cand = _date(hoje.year, mo, d)
        except ValueError:
            return None, m.group(0), True
        iso = cand.isoformat() if cand >= hoje else _date(hoje.year + 1, mo, d).isoformat()
        return iso, m.group(0), True
    m = re.search(r"(?:dia\s+)?(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{4}))?", t)
    if m and m.group(2) in MESES_PT:
        d, mo, ano = int(m.group(1)), MESES_PT[m.group(2)], m.group(3)
        if ano:
            try:
                return _date(int(ano), mo, d).isoformat(), m.group(0), False
            except ValueError:
                return None, m.group(0), True
        try:
            cand = _date(hoje.year, mo, d)
        except ValueError:
            return None, m.group(0), True
        iso = cand.isoformat() if cand >= hoje else _date(hoje.year + 1, mo, d).isoformat()
        return iso, m.group(0), True
    if "depois de amanh" in t:
        return (hoje + _td(days=2)).isoformat(), "depois de amanhã", False
    if "amanh" in t:
        return (hoje + _td(days=1)).isoformat(), "amanhã", False
    if "semana que vem" in t or "próxima semana" in t or "proxima semana" in t:
        return (hoje + _td(days=7)).isoformat(), "semana que vem", False
    if "mês que vem" in t or "mes que vem" in t:
        mes = hoje.month % 12 + 1
        ano = hoje.year + (1 if mes == 1 else 0)
        try:
            return _date(ano, mes, min(hoje.day, 28)).isoformat(), "mês que vem", False
        except ValueError:
            return None, "mês que vem", True
    m = re.search(r"(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)(?:-feira)?", t)
    if m:
        alvo = DIAS_PT[m.group(1)]
        delta = (alvo - hoje.weekday()) % 7 or 7
        return (hoje + _td(days=delta)).isoformat(), m.group(0), False
    return None, "", True


def data_br(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else (iso or "")


def registrar_evento(db, owner, titulo: str, data_iso: str = "", data_raw: str = "",
                     assunto: str = "", conv: str = "", msg: str = "", status: str = "ativo") -> int:
    owner = dono_valido(owner)
    titulo = (titulo or "").strip()[:200]
    if not titulo:
        return 0
    with db:
        ex = db.execute("SELECT id FROM memory_events WHERE owner_id=? AND titulo=? AND data_iso=?",
                        (owner, titulo, data_iso or "")).fetchone()
        if ex:
            db.execute("UPDATE memory_events SET status=?, assunto=?, updated_at=? WHERE id=?",
                       (status, (assunto or "")[:80], agora_iso(), ex[0]))
            return ex[0]
        cur = db.execute("""INSERT INTO memory_events
            (owner_id, titulo, data_iso, data_raw, assunto, status, origem_conv, origem_msg,
             created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (owner, titulo, data_iso or "", (data_raw or "")[:120], (assunto or "")[:80],
             status, (conv or "")[:100], (msg or "")[:100], agora_iso(), agora_iso()))
        return cur.lastrowid or 0


def proximos_eventos(db, owner, limite: int = 6, hoje=None) -> list:
    from datetime import date as _date
    owner = dono_valido(owner)
    hoje = hoje or _date.today()
    try:
        rows = db.execute("""SELECT id, titulo, data_iso, assunto FROM memory_events
                             WHERE owner_id=? AND status='ativo' AND data_iso>=?
                             ORDER BY data_iso LIMIT ?""",
                          (owner, (hoje.isoformat()), limite)).fetchall()
    except Exception:
        return []
    out = []
    for i, titulo, iso, assunto in rows:
        try:
            d = _date.fromisoformat(iso)
            out.append({"id": i, "titulo": titulo, "data_iso": iso, "data_br": data_br(iso),
                        "faltam": (d - hoje).days, "assunto": assunto})
        except ValueError:
            continue
    return out


def atualizar_evento(db, owner, ref: str, status: str = "cancelado") -> str:
    """Cancela/conclui por id ou trecho do título. Retorna título ou ''."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT id, titulo FROM memory_events WHERE owner_id=? AND status='ativo'",
                          (owner,)).fetchall()
    except Exception:
        return ""
    alvo = None
    if str(ref).isdigit():
        alvo = next((r for r in rows if str(r[0]) == str(ref)), None)
    if alvo is None:
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", str(ref).lower()))
        melhor, n = None, 0
        for i, titulo in rows:
            inter = len(toks & set(re.findall(r"[a-zà-ú0-9]{3,}", titulo.lower())))
            if inter > n:
                melhor, n = (i, titulo), inter
        alvo = melhor
    if alvo is None:
        return ""
    with db:
        db.execute("UPDATE memory_events SET status=?, updated_at=? WHERE id=? AND owner_id=?",
                   (status, agora_iso(), alvo[0], owner))
    return alvo[1]


def eh_sensivel(texto: str) -> bool:
    t = (texto or "").lower()
    if re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", t):
        return True  # padrão CPF
    return any(s in t for s in SENSIVEIS)


def extrair_candidatos(texto: str) -> list:
    """Candidatos tipados (fato vs hipótese separados pelo chamador)."""
    t = (texto or "").strip()
    out = []
    for rx, chave, tipo, assunto in [
        (r"(?i)(?:meu nome é|me chamo|sou o|sou a)\s+(.{2,80})", "nome", "semantica", "identidade"),
        (r"(?i)(?:meu foco é|minha meta é|estou trabalhando (?:em|com))\s+(.{3,200})", "foco", "trabalho", "objetivos"),
        (r"(?i)(?:prefiro|gosto de|não gosto de)\s+(.{3,200})", "preferencia", "semantica", "gostos"),
        (r"(?i)(?:lembre-?se (?:que |de que |disso:?\s?))(.{3,300})", "fato", "semantica", "geral"),
        (r"(?i)(?:aniversário|aniversario) (?:é |eh |dia )?(.{2,60})", "aniversario", "temporal", "datas"),
        (r"(?i)(?:minha prova|prova) (?:de \w+ )?(?:é|será|vai ser|dia) (.{2,80})", "prova", "temporal", "estudos"),
        (r"(?i)(?:reunião|reuniao|consulta|compromisso|viagem|entrega|prazo)[^.]{0,10}(.{2,80})", "evento", "temporal", "agenda"),
        (r"\b([A-ZÀ-Ú][a-zà-ú]{2,30}) é (?:meu|minha) ([a-zà-ú ]{2,40}?)(?:[.,;]| e |$)", "pessoa", "semantica", "pessoas"),
    ]:
        m = re.search(rx, t)
        if not m:
            continue
        if chave == "pessoa":
            nome = m.group(1).strip()
            rel = m.group(2).strip()
            out.append({"chave": "pessoa_" + nome.lower(), "valor": f"{nome} é meu/minha {rel}",
                        "tipo": tipo, "assunto": assunto,
                        "sensivel": eh_sensivel(t)})
            continue
        valor = re.sub(r"\s+", " ", m.group(1)).strip(" .;:")[:300]
        if valor:
            out.append({"chave": chave, "valor": valor, "tipo": tipo, "assunto": assunto,
                        "sensivel": eh_sensivel(valor) or eh_sensivel(t)})
    if not out and eh_sensivel(t) and re.search(
            r"(?i)\b(eu|meu|minha|tomo|tenho|sou|fa[çc]o|estou|uso|tive|preciso)\b", t):
        slug = "_".join(re.findall(r"[a-zà-ú]{4,}", t.lower())[:4])[:40] or "nota"
        out.append({"chave": "sensivel_" + slug, "valor": t[:300], "tipo": "semantica",
                    "assunto": "sensivel", "sensivel": True})
    return out


def pendencias(db, owner) -> list:
    return ler_memorias(db, owner, status="pendente")


def confirmar_pendencia(db, owner) -> dict:
    """Confirma a pendência mais antiga. Retorna {} se não houver."""
    owner = dono_valido(owner)
    rows = db.execute("SELECT key, value, tipo, assunto, origem_conv, origem_msg FROM memories "
                      "WHERE owner_id=? AND status='pendente' ORDER BY updated_at LIMIT 1",
                      (owner,)).fetchone()
    if not rows:
        return {}
    chave, valor, tipo, assunto, oc, om = rows
    with db:
        db.execute("UPDATE memories SET status='confirmada', updated_at=? "
                   "WHERE owner_id=? AND key=?", (agora_iso(), owner, chave))
        _fts_sync(db, owner, chave, valor, assunto)
    if tipo == "temporal":
        iso, _, _ = parse_data(valor)
        if iso:
            titulo = f"{chave} · {assunto}" if assunto else chave
            registrar_evento(db, owner, titulo[:200], iso, valor[:120], assunto, oc, om)
    return {"key": chave, "value": valor, "tipo": tipo}


def descartar_pendencia(db, owner) -> dict:
    owner = dono_valido(owner)
    row = db.execute("SELECT key FROM memories WHERE owner_id=? AND status='pendente' "
                     "ORDER BY updated_at LIMIT 1", (owner,)).fetchone()
    if not row:
        return {}
    with db:
        db.execute("DELETE FROM memories WHERE owner_id=? AND key=?", (owner, row[0]))
        try:
            db.execute("DELETE FROM memories_fts WHERE owner_id=? AND key=?", (owner, row[0]))
        except Exception:
            pass
    return {"key": row[0]}


def analisar_memoria(db, texto: str, owner, conv: str = "", msg_id: str = "") -> tuple:
    """V4.1: extrai candidatos; sensível/temporal-ambíguo vira PROPOSTA + pergunta.

    Retorna (salvos[], propostas[], pergunta|None). Explícito ('lembre-se',
    'guarde') passa mesmo com aprendizado pausado.
    """
    owner = dono_valido(owner)
    explicito = bool(re.search(r"(?i)(lembre-?se|guarde|guardar|anote|anotar|salve|salvar|registre)", texto or ""))
    if not aprendizado_ativo(db, owner) and not explicito:
        return [], [], None
    salvos, propostas, pergunta = [], [], None
    for c in extrair_candidatos(texto):
        if c["tipo"] == "temporal":
            iso, raw, confirma = parse_data(c["valor"])
            rotulo = (data_br(iso) + " — " + c["valor"]) if iso else c["valor"]
            if iso and not confirma:
                chave = registrar_memoria(db, owner, c["chave"], rotulo, "temporal", c["assunto"],
                                          "confirmada", conv, msg_id)
                titulo = f"{c['chave']} · {c['assunto']}" if c["assunto"] else c["chave"]
                registrar_evento(db, owner, titulo[:200], iso, c["valor"][:120],
                                 c["assunto"], conv, msg_id)
                if chave:
                    salvos.append(chave)
                continue
            chave = registrar_memoria(db, owner, c["chave"], rotulo, "temporal", c["assunto"],
                                      "pendente", conv, msg_id)
            propostas.append(chave)
            if confirma and iso and pergunta is None:
                pergunta = (f"Posso guardar essa data para te ajudar? É {data_br(iso)}? "
                            "Responda \"pode guardar\" para confirmar.")
            elif pergunta is None:
                pergunta = (f"Posso guardar \"{c['valor'][:100]}\"? "
                            "Responda \"pode guardar\" para confirmar.")
        elif c["sensivel"]:
            chave = registrar_memoria(db, owner, c["chave"], c["valor"], c["tipo"], c["assunto"],
                                      "pendente", conv, msg_id)
            propostas.append(chave)
            if pergunta is None:
                pergunta = ("Isso parece sensível, então não guardei ainda. "
                            "Posso guardar? Responda \"pode guardar\" para confirmar.")
        else:
            chave = registrar_memoria(db, owner, c["chave"], c["valor"], c["tipo"], c["assunto"],
                                      "confirmada", conv, msg_id)
            if chave:
                salvos.append(chave)
    return salvos, propostas, pergunta


def aprender_com_conversa(db_path: Path, cfg: dict, texto_usuario: str, texto_resposta: str,
                          owner=DONO_PADRAO) -> None:
    """Thread em 2º plano: pede ao LLM fatos novos (JSON) e guarda. Nunca bloqueia o chat."""
    try:
        if len(texto_usuario or "") < 20:
            return
        _db_chk = open_db(db_path)
        try:
            if not aprendizado_ativo(_db_chk, owner):
                return
        finally:
            _db_chk.close()
        import json as _json
        prompt = ("Extraia FATOS duradouros sobre o usuário desta conversa "
                  "(nome, profissão, projetos, preferências, metas, contexto de vida). "
                  "NÃO extraia hipóteses, exemplos citados ou palpites — só o que o usuário "
                  "afirmou sobre si. Responda SÓ com JSON: "
                  "[{\"key\": \"curta_em_snake\", \"value\": \"...\", \"tipo\": \"semantica|temporal|episodica|trabalho\", "
                  "\"assunto\": \"...\", \"sensivel\": false, \"confianca\": 0.0-1.0}] ou [].\n\n"
                  f"USUÁRIO: {(texto_usuario or '')[:1500]}\nASSISTENTE: {(texto_resposta or '')[:1500]}")
        res = hermes_bridge.chat_complete(
            cfg["proxy"], cfg["model"],
            [{"role": "system", "content": "Você extrai fatos. Responda só JSON válido."},
             {"role": "user", "content": prompt}], max_tokens=300)
        try:
            fatos = _json.loads(res["texto"].strip().strip("`").replace("json", "", 1).strip())
        except Exception:
            m = re.search(r"\[.*\]", res["texto"], re.S)
            fatos = _json.loads(m.group(0)) if m else []
        db = open_db(db_path)
        try:
            for f in fatos if isinstance(fatos, list) else []:
                if not (isinstance(f, dict) and f.get("value")):
                    continue
                chave = str(f.get("key", "fato"))[:60]
                valor = str(f.get("value"))[:500]
                tipo = str(f.get("tipo", "semantica"))[:20]
                assunto = str(f.get("assunto", ""))[:80]
                try:
                    conf = float(f.get("confianca", 0.8))
                except (TypeError, ValueError):
                    conf = 0.8
                if f.get("sensivel") or eh_sensivel(valor) or conf < 0.6:
                    registrar_memoria(db, owner, chave, valor, tipo, assunto, "pendente")
                else:
                    registrar_memoria(db, owner, chave, valor, tipo, assunto, "confirmada")
            n = db.execute("SELECT COUNT(*) FROM memory_facts WHERE owner_id=?",
                           (dono_valido(owner),)).fetchone()[0]
            if n > 60:
                _consolidar_memorias(db, cfg, owner)
        finally:
            db.close()
    except Exception as exc:
        log.warning("aprendizado em 2º plano falhou: %s", exc)


def _consolidar_memorias(db, cfg: dict, owner=DONO_PADRAO) -> None:
    """Junta fatos antigos/duplicados num conjunto enxuto (evolução da memória)."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT key, value FROM memory_facts WHERE owner_id=? "
                          "ORDER BY created_at DESC LIMIT 60", (owner,)).fetchall()
        bloco = "\n".join(f"- {k}: {v[:200]}" for k, v in rows)
        res = hermes_bridge.chat_complete(
            cfg["proxy"], cfg["model"],
            [{"role": "system", "content": "Você consolida memórias. Responda só JSON válido."},
             {"role": "user", "content": "Junte estes fatos, removendo duplicados e o que for passageiro. "
              "Responda SÓ JSON: [{\"key\": \"...\", \"value\": \"...\"}] (máx 25 itens).\n\n" + bloco}],
            max_tokens=1200)
        import json as _json
        try:
            novos = _json.loads(res["texto"].strip().strip("`").replace("json", "", 1).strip())
        except Exception:
            return
        if not isinstance(novos, list) or not novos:
            return
        with db:
            db.execute("DELETE FROM memories WHERE owner_id=?", (owner,))
            db.execute("DELETE FROM memory_facts WHERE owner_id=?", (owner,))
            for f in novos[:25]:
                if isinstance(f, dict) and f.get("value"):
                    chave = re.sub(r"\s+", "_", str(f.get("key", "fato")).strip().lower())[:60] or "fato"
                    db.execute("INSERT INTO memories (owner_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                               (owner, chave, str(f["value"])[:500], agora_iso()))
        log.info("memória consolidada: %d fatos", len(novos))
    except Exception as exc:
        log.warning("consolidação falhou: %s", exc)


def doc_mencionado(db, texto: str, conversation_id: str, owner=DONO_PADRAO) -> str:
    """Acha documento citado pelo nome ou o mais recente da conversa."""
    t = (texto or "").lower()
    try:
        docs = docs_agent.listar_documentos(db, 50, owner)
    except Exception:
        return ""
    for d in docs:
        nome = (d["name"] or "").lower()
        base = re.sub(r"\.[a-z0-9]+$", "", nome)
        if len(base) >= 4 and base in t:
            return d["doc_id"]
    if re.search(r"(documento|arquivo|pdf|texto|contrato|relat[óo]rio|planilha|resum)", t):
        mesmos = [d for d in docs if d["conversation_id"] == conversation_id] or docs
        if mesmos:
            return mesmos[0]["doc_id"]
    return ""


def listar_conversas(db, limite: int = 100, owner=DONO_PADRAO) -> list:
    try:
        rows = db.execute("""SELECT conversation_id, COUNT(*), MAX(created_at),
                             substr(MAX(created_at || ' ' || text), 22, 80)
                             FROM messages WHERE origin='mobile' AND owner_id=?
                             GROUP BY conversation_id
                             ORDER BY MAX(created_at) DESC LIMIT ?""",
                          (dono_valido(owner), min(max(int(limite), 1), 200))).fetchall()
    except Exception:
        return []
    return [{"conversation_id": c, "total": n, "ultima": u, "previa": (p or "")[:80]}
            for c, n, u, p in rows]


# ── Pesquisa web opcional (stdlib, sem dependências) ─────────────────
TERMOS_PESQUISA = ("pesquise", "pesquisar", "busque", "buscar", "google",
                   "últimas notícias", "ultimas noticias", "notícia", "noticia",
                   "fontes", "referências", "referencias", "atualizado", "hoje",
                   "preço", "preco", "clima", "placar", "resultado")


def intencao_pesquisa(texto: str) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in TERMOS_PESQUISA)


def intencao_imagem(texto: str) -> str:
    """Retorna o termo da imagem pedida ou ''."""
    import re
    t = texto or ""
    m = re.search(r"(?i)(?:mostre|mostra|mande|envie|quero|gere?)?\s*(?:uma?|a)?\s*(?:imagem|foto|figura|picture|image)\s*(?:de|do|da|sobre)?\s*(.{2,80})", t)
    if m:
        termo = re.sub(r"[.?!]+$", "", m.group(1).strip())[:80]
        if len(termo) >= 2 and "imagem" not in termo.lower():
            return termo
        return termo or "paisagem"
    if re.search(r"(?i)\b(imagem|foto|figura)\b", t):
        return "paisagem"
    return ""


_CACHE_PESQUISA: dict = {}


def _baixar_resultados(base: str, q: str, timeout: float) -> str:
    import urllib.parse
    import urllib.request
    url = base + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Júlia Mobile)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _extrair_resultados(pagina: str, max_resultados: int) -> list:
    import urllib.parse
    import html as ihtml
    resultados = []
    padroes = [
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:class="result__snippet"[^>]*>(.*?)</(?:a|div|td))?',
        r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    ]
    for rx in padroes:
        for m in re.finditer(rx, pagina, re.S):
            try:
                link, titulo = m.group(1), m.group(2)
                trecho = m.group(3) if m.lastindex and m.lastindex >= 3 and m.group(3) else ""
                titulo = ihtml.unescape(re.sub(r"<.*?>", "", titulo)).strip()[:160]
                trecho = ihtml.unescape(re.sub(r"<.*?>", "", trecho or "")).strip()[:280]
                if link.startswith("//"):
                    link = "https:" + link
                if link.startswith("/") and "uddg=" in link:
                    link = urllib.parse.unquote(link.split("uddg=", 1)[1].split("&", 1)[0])
                if link.startswith("http") and titulo and all(f["url"] != link[:500] for f in resultados):
                    resultados.append({"titulo": titulo, "url": link[:500], "trecho": trecho})
                if len(resultados) >= max_resultados:
                    return resultados
            except Exception:
                continue
        if resultados:
            break
    return resultados


def pesquisa_web(consulta: str, max_resultados: int = 6, timeout: float = 8.0) -> list:
    """Pesquisa em tempo real (DuckDuckGo via stdlib) com cache de 10 min.

    Tenta o endpoint HTML e cai para o lite. Falha silenciosa → lista vazia
    (offline-first: o chat nunca trava por causa da pesquisa).
    """
    q = (consulta or "").strip()[:200]
    if not q:
        return []
    chave = q.lower()
    agora = time.monotonic()
    if chave in _CACHE_PESQUISA and agora - _CACHE_PESQUISA[chave][0] < 600:
        return _CACHE_PESQUISA[chave][1]
    for base in ("https://html.duckduckgo.com/html/?q=",
                 "https://lite.duckduckgo.com/lite/?q="):
        try:
            pagina = _baixar_resultados(base, q, timeout)
            resultados = _extrair_resultados(pagina, max_resultados)
            if resultados:
                _CACHE_PESQUISA[chave] = (agora, resultados)
                return resultados
        except Exception as exc:
            log.warning("pesquisa %s falhou (%s)", base.split("//")[1].split("/")[0], type(exc).__name__)
    return []


class JuliaPresentationEngine:
    """Decide quando a resposta merece interface declarativa JDUI (sem JS do modelo)."""

    REGRAS = [
        (("quiz", "quizz", "questionário", "questionario", "teste de conhecimento",
          "perguntas e respostas", "simulado"), "quiz"),
        (("checklist", "check-list", "lista de tarefas", "rotina de estudos",
          "plano de estudos", "hábitos"), "checklist"),
        (("calculadora", "calcule meu imc", "índice de massa", "indice de massa",
          "porcentagem", "juros compostos", "quanto rende"), "calculator"),
        (("compare", "comparação", "comparacao", "diferenças entre", "diferencas entre",
          "prós e contras", "pros e contras", "qual melhor"), "cards"),
        (("diagrama", "fluxograma", "fluxo de", "arquitetura", "como funciona o",
          "como se conecta", "etapas do", "mapa do sistema"), "diagram"),
        (("em tabela", "tabela com", "liste em colunas", "cronograma"), "table"),
        (("formulário", "formulario", "cadastro", "inscrição", "inscricao"), "form"),
    ]

    @classmethod
    def sugerir(cls, texto: str) -> str:
        t = (texto or "").lower()
        for chaves, comp in cls.REGRAS:
            if any(k in t for k in chaves):
                return comp
        return ""


JDUI_CATALOGO = (
    "INTERFACE DECLARATIVA (use quando pedida ou muito útil; texto simples prefere texto): "
    "responda com texto normal + blocos ```jdui com JSON {version:'julia-ui-message/v1',"
    "blocks:[{type:'text',content},{type:'ui',component,props}]}. Componentes: "
    "quiz{title,questions[{q,options[2..6],answer(índice),explain}]}; "
    "checklist{title,items[]}; calculator{kind:basic|imc|porcentagem|juros}; "
    "cards{items[{title,desc,value,badge,url,action{chat}}]}; "
    "diagram{direction:v|h,nodes[{id,label,desc}],edges[{from,to,label}]}; "
    "table{columns[],rows[[]]}; form{title,fields[{name,label,type:text|number|select,options}],calc:imc|juros|porcentagem|soma}; "
    "progress{label,value,max}; tabs{tabs[{title,markdown}]}; accordion{items[{title,markdown}]}. "
    "REGRAS: JSON válido e pequeno (máx 6 blocos, 12 perguntas, 30 linhas); sem JavaScript, sem CSS, "
    "sem perguntas de volta quando pedirem app; quiz/calculadora/checklist NUNCA em texto corrido."
)


def intencao_widget(texto: str) -> str:
    """Legado: agora redireciona para o componente JDUI equivalente."""
    comp = JuliaPresentationEngine.sugerir(texto)
    return comp or ""


PEDIDO_CODIGO_RE = re.compile(
    r"(?i)(quero|manda|mande|mostra|mostre|pode mostrar|me d[áa]|quero ver).{0,40}(c[óo]digo|fonte)"
    r"|^(sim|quero|manda|pode ser|claro|ok|yes)\W*$")


def ultimos_blocos_jdui(db, conversation_id: str, limite: int = 2, owner=DONO_PADRAO) -> list:
    """Últimos blocos JDUI válidos do assistente nesta conversa (p/ gerar código-fonte)."""
    try:
        rows = db.execute(
            """SELECT text FROM messages WHERE origin='mobile' AND owner_id=? AND conversation_id=?
               AND role='assistant' AND text LIKE '%```jdui%' ORDER BY created_at DESC LIMIT 5""",
            (dono_valido(owner), conversation_id)).fetchall()
    except Exception:
        return []
    out = []
    for (txt,) in rows:
        for corpo in jdui.extrair_fences(txt or ""):
            try:
                obj = json.loads(corpo)
            except ValueError:
                continue
            ok, norm, _ = jdui.validar_mensagem(obj)
            if ok:
                out.append(norm)
                if len(out) >= limite:
                    return out
    return out


JDUI_SINTETIZAR = {
    "quiz": ("Converta o quiz abaixo para JSON JDUI. Responda SÓ com o JSON, sem cercas e sem texto: "
             '{"version":"julia-ui-message/v1","blocks":[{"type":"ui","component":"quiz",'
             '"props":{"title":"...","questions":[{"q":"...","options":["...","..."],"answer":0,"explain":"..."}]}}]}. '
             "Regras: use as perguntas e opções do conteúdo (em código Python, a certa está no `if`); "
             "máximo 6 perguntas, 4 opções cada, answer é o índice; explain curta."),
    "checklist": ("Converta a lista abaixo para JSON JDUI. Responda SÓ com o JSON: "
                  '{"version":"julia-ui-message/v1","blocks":[{"type":"ui","component":"checklist",'
                  '"props":{"title":"...","items":["..."]}}]}. Máximo 20 itens curtos.'),
    "calculator": ("O usuário quer uma calculadora. Responda SÓ com o JSON JDUI: "
                   '{"version":"julia-ui-message/v1","blocks":[{"type":"ui","component":"calculator",'
                   '"props":{"kind":"basic"}}]}. kind: basic (padrão), imc (peso/altura), '
                   "porcentagem (valor/percentual) ou juros (capital/taxa/meses) conforme o pedido."),
}


def _limpa_opcao(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").replace("\\n", " ").strip(" \t\"'")).strip()
    return s[:120]


def _indice_resposta(letras: list, letra) -> int:
    try:
        return letras.index((letra or "").lower())
    except ValueError:
        return -1


def _opcoes_inline(t: str) -> list:
    """Opções 'a) x  b) y' na mesma linha. Retorna [(letra, texto)]."""
    return [(l.lower(), _limpa_opcao(x))
            for l, x in re.findall(r"\b([a-dA-D])[.)]\s*(.+?)(?=\s*\b[a-dA-D][.)]\s*|\s*$)", t)]


def _fence_quiz(questions: list) -> str:
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "quiz",
             "props": {"title": "Quiz", "questions": questions[:6]}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def extrair_quiz_codigo(texto: str) -> str:
    """Quiz em código Python terminal (print pergunta/opções + if resposta)."""
    segmentos = re.split(r"#\s*[Pp]ergunta\s*\d+", texto or "")
    questions = []
    for seg in segmentos[1:]:
        prints = re.findall(r'print\(\s*"((?:[^"\\]|\\.)*)"\s*\)', seg)
        if not prints:
            prints = re.findall(r"print\(\s*'((?:[^'\\]|\\.)*)'\s*\)", seg)
        corte = re.search(r"\bresposta\s*=\s*input|\binput\s*\(|if\s+\w+\s*==", seg)
        regiao = seg[:corte.start()] if corte else seg
        prints_reg = re.findall(r'print\(\s*"((?:[^"\\]|\\.)*)"\s*\)', regiao) or \
            re.findall(r"print\(\s*'((?:[^'\\]|\\.)*)'\s*\)", regiao)
        q, pares = "", []
        for p in prints_reg:
            p = p.replace("\\n", " ").replace('\\"', '"')
            if not q:
                m = re.match(r"\s*\d+[.)]\s*(.+)", p, re.S)
                cand = _limpa_opcao(m.group(1) if m else p)
                if len(cand) >= 8 and "===" not in cand:
                    q = cand
                    continue
            pares.extend(_opcoes_inline(p))
        if len(pares) < 2:  # opções podem estar no mesmo print da pergunta
            juntos = " ".join(prints_reg)
            pares = _opcoes_inline(juntos)
        letras = [l for l, _ in pares]
        textos = [_limpa_opcao(t) or t.strip() for _, t in pares][:6]
        m = re.search(r'if\s+\w+\s*==\s*["\']([a-dA-D])["\']', seg)
        ans = _indice_resposta(letras, m.group(1) if m else "")
        if q and len(textos) >= 2 and 0 <= ans < len(textos):
            questions.append({"q": q[:300], "options": textos,
                              "answer": ans, "explain": ""})
        if len(questions) >= 6:
            break
    return _fence_quiz(questions) if questions else ""


def extrair_quiz_texto(texto: str) -> str:
    """Quiz em texto corrido (Pergunta N + a) b) c) d) + Resposta: x)."""
    partes = re.split(r"(?im)^\s*(?:\*\*?)?\s*pergunta\s*\d+\s*[:.\-]?\s*(?:\*\*?)?", texto or "")
    questions = []
    for seg in partes[1:]:
        seg = seg.strip()
        if "print(" in seg and "input(" in seg:
            continue  # código Python: trabalho do extrair_quiz_codigo
        corpo = re.sub(r"(?s)```.*?```", " ", seg)
        pares = []
        for linha in corpo.split("\n"):
            m = re.match(r"\s*([a-dA-D])[.)]\s*(.+?)\s*$", linha)
            if m and len(_limpa_opcao(m.group(2))) >= 1:
                pares.append((m.group(1).lower(), _limpa_opcao(m.group(2))))
        if len(pares) < 2:
            pares = [(l, t) for l, t in _opcoes_inline(" " + corpo) if t]
        # pergunta = texto antes da primeira opção (sem code fence)
        mq = re.search(r"\b[a-dA-D][.)]\s", seg)
        qpart = re.sub(r"(?s)```.*?```", " ", seg[:mq.start()] if mq else seg)
        q = _limpa_opcao(re.sub(r"^[\s*#:\-–—]+", "", qpart))[:300]
        letras = [l for l, _ in pares]
        textos = [t for _, t in pares][:6]
        m = re.search(r"(?i)(?:resposta\s*(?:certa|correta)?|certa|gabarito)\s*[:\-]?\s*\(?([a-dA-D])\)?",
                      seg)
        ans = _indice_resposta(letras, m.group(1) if m else "")
        if q and len(textos) >= 2 and 0 <= ans < len(textos):
            questions.append({"q": q, "options": textos, "answer": ans, "explain": ""})
        if len(questions) >= 6:
            break
    return _fence_quiz(questions) if questions else ""


def sintetizar_calculadora(texto_usuario: str) -> str:
    """Calculadora não precisa de LLM: o kind sai do pedido. 100% confiável."""
    t = (texto_usuario or "").lower()
    if any(k in t for k in ("imc", "massa corporal", "peso", "altura")):
        kind = "imc"
    elif any(k in t for k in ("porcent", "%", "desconto", "aumento", "taxa")):
        kind = "porcentagem"
    elif any(k in t for k in ("juros", "montante", "rende", "compost")):
        kind = "juros"
    else:
        kind = "basic"
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "calculator", "props": {"kind": kind}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def extrair_checklist(texto_resposta: str) -> str:
    """Itens em bullets da resposta viram checklist (sem LLM)."""
    itens = []
    for linha in (texto_resposta or "").split("\n"):
        if re.match(r"\s*([a-dA-D])[.)]\s", linha):
            continue  # opção de quiz, não item
        m = re.match(r"\s*(?:[-*•‣]|(?:\d+[.)]))\s+(.{3,120}?)\s*$", linha)
        if m:
            txt = _limpa_opcao(m.group(1))
            if txt and txt not in itens:
                itens.append(txt)
        if len(itens) >= 20:
            break
    if len(itens) < 2:
        return ""
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "checklist",
             "props": {"title": "Checklist", "items": itens}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def sintetizar_jdui(cfg: dict, componente: str, texto_usuario: str, texto_resposta: str) -> str:
    """Garante a interface quando a IA não emitiu o fence.

    Ordem: determinístico (grátis, instantâneo) → conversão via LLM.
    Retorna o fence pronto ou ''. Nunca levanta exceção.
    """
    try:
        if componente == "calculator":
            fence = sintetizar_calculadora(texto_usuario)
            if fence:
                return fence
        elif componente == "quiz":
            fence = extrair_quiz_codigo(texto_resposta) or extrair_quiz_texto(texto_resposta)
            if fence:
                log.info("quiz extraído deterministicamente")
                return fence
        elif componente == "checklist":
            fence = extrair_checklist(texto_resposta)
            if fence:
                return fence
    except Exception as exc:
        log.warning("extração determinística falhou (%s)", type(exc).__name__)
    return _sintetizar_jdui_llm(cfg, componente, texto_usuario, texto_resposta)


def _sintetizar_jdui_llm(cfg: dict, componente: str, texto_usuario: str, texto_resposta: str) -> str:
    """Último recurso: quando a IA não emitiu o fence, converte a resposta em JDUI.

    Retorna o fence pronto (com \\n\\n) ou ''. Nunca levanta exceção.
    """
    prompt = JDUI_SINTETIZAR.get(componente or "")
    if not prompt or len(texto_resposta or "") < 50:
        return ""
    try:
        res = hermes_bridge.chat_complete(
            cfg["proxy"], cfg["model"],
            [{"role": "system", "content": "Você converte conteúdo para JSON. Responda SÓ JSON válido."},
             {"role": "user", "content": prompt + "\n\nPEDIDO: " + (texto_usuario or "")[:400]
              + "\n\nCONTEÚDO:\n" + (texto_resposta or "")[:6000]}],
            max_tokens=1500)
        corpo = (res.get("texto") or "").strip()
        m = re.search(r"```(?:jdui|json)?\s*\n?([\s\S]*?)```", corpo)
        if m:
            corpo = m.group(1).strip()
        obj = json.loads(corpo)
        ok, norm, _ = jdui.validar_mensagem(obj)
        if not ok:
            return ""
        return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
    except Exception as exc:
        log.warning("síntese JDUI falhou (%s); mantendo só texto", type(exc).__name__)
        return ""


REGRAS_CONFIANCA = (
    "CONFIABILIDADE: distinga (a) o que o usuário disse, (b) MEMÓRIA salva, "
    "(c) RESULTADO DE PESQUISA com data, (d) seu conhecimento geral, (e) palpite. "
    "Se não souber, admita ('não sei' / 'não encontrei'). "
    "NUNCA invente: links, fontes, preços, datas, eventos, estatísticas ou memórias. "
    "Sem resultado de ferramenta, diga que respondeu pelo conhecimento geral."
)

ORCAMENTO_CHARS = 12000


def aplicar_orcamento(historico: list, teto: int = ORCAMENTO_CHARS) -> list:
    """Corta as mensagens MAIS ANTIGAS até caber no teto (as recentes valem mais)."""
    total, mantidas = 0, []
    for m in reversed(historico):
        total += len(m.get("content", ""))
        if total > teto and mantidas:
            break
        mantidas.append(m)
    return list(reversed(mantidas))


def ai_montar_mensagens(db, conversation_id: str, cfg: dict, texto_usuario: str,
                        owner=DONO_PADRAO) -> tuple:
    """Monta o prompt com contexto local + memória global + pesquisa. Retorna (messages, extras)."""
    owner = dono_valido(owner)
    memoria_on = cfg.get("memoria_global", True)
    historico = aplicar_orcamento(contexto_conversa(db, conversation_id, cfg["context"], owner))
    extras = {"fontes": [], "memoria_usada": False, "doc_id": ""}
    partes_sistema = [cfg["system"], REGRAS_CONFIANCA]
    if memoria_on:
        rel = memorias_relevantes(db, texto_usuario, owner=owner)
        if not rel:
            # sem pergunta específica: leva um resumo do que sabe (nome/foco primeiro)
            rel = memorias_relevantes(db, "", k=4, owner=owner)
        if rel:
            extras["memoria_usada"] = True
            partes_sistema.append("O QUE VOCÊ SABE SOBRE O USUÁRIO (memórias confirmadas; "
                                  "use naturalmente; o que não está aqui você NÃO sabe):\n" +
                                  "\n".join(f"- {f['key']}: {f['value'][:200]}{proveniencia(f)}"
                                            for f in rel))
        blocos = memoria_global(db, conversation_id, 6, owner)
        if blocos:
            partes_sistema.append("CONTEXTO RECENTE DE OUTRAS CONVERSAS (só se for relevante):\n" + "\n".join(blocos[-6:]))
        from datetime import date as _d
        evs = proximos_eventos(db, owner)
        if evs:
            hoje_br = _d.today().strftime("%d/%m/%Y")
            partes_sistema.append(
                f"PRÓXIMOS EVENTOS (hoje é {hoje_br}; use para planos e contagens, sem inventar):\n" +
                "\n".join(f"- {e['data_br']} (faltam {e['faltam']} dias): {e['titulo'][:150]}"
                          for e in evs))
        pend = pendencias(db, owner)[:2]
        if pend:
            partes_sistema.append(
                "AGUARDANDO CONFIRMAÇÃO (não afirme que guardou; pergunte de forma natural):\n" +
                "\n".join(f"- {p['value'][:150]}" for p in pend))
    # Follow-up de código: "quero o código" após uma interface → gera fonte (sem jdui).
    if PEDIDO_CODIGO_RE.search(texto_usuario or ""):
        blocos_prev = ultimos_blocos_jdui(db, conversation_id, owner=owner)
        if blocos_prev:
            partes_sistema.append(
                "GERAR CÓDIGO-FONTE: o usuário pediu o código da interface anterior. "
                "Gere o código-fonte equivalente em bloco de código "
                "(Python para quiz/checklist/calculadora, usando os dados do JSON). "
                "PROIBIDO usar ```jdui aqui — é código-fonte, não interface. "
                "JSON da interface:\n" + json.dumps(blocos_prev[0], ensure_ascii=False)[:4000])
    # JDUI: impõe interface declarativa quando pedida ou muito útil.
    comp_sugerido = JuliaPresentationEngine.sugerir(texto_usuario)
    extras["comp_sugerido"] = comp_sugerido or ""
    if comp_sugerido:
        diretiva = "PEDIDO DE INTERFACE INTERATIVA (componente: " + comp_sugerido + "). " + JDUI_CATALOGO
        if comp_sugerido == "quiz":
            diretiva += (" REGRA DURA DO QUIZ: responda com 1-2 linhas de apresentação + "
                         "UM bloco ```jdui quiz com 5 perguntas (cada uma: q, options[4], answer, explain). "
                         "PROIBIDO despejar código Python/terminal na resposta — a interface JÁ É o quiz jogável. "
                         "Depois do bloco, termine com: 'Quer ver o código-fonte desse quiz em Python?' "
                         "Só envie código se o usuário disser sim.")
        elif comp_sugerido in ("calculator", "checklist"):
            diretiva += (" PROIBIDO código Python/terminal ou perguntas de volta — "
                         "a interface pronta JÁ É a entrega.")
        partes_sistema.append(diretiva)
    # Documentos: se a pergunta cita um doc ou fala de documento, injeta trechos
    doc_id = doc_mencionado(db, texto_usuario, conversation_id, owner)
    if doc_id:
        extras["doc_id"] = doc_id
        trechos = docs_agent.trechos_relevantes(db, texto_usuario, doc_id, k=4, owner=owner)
        if trechos:
            nome = trechos[0]["doc"]
            partes_sistema.append(f"TRECHOS DO DOCUMENTO '{nome}' (responda com base neles e cite a fonte):\n" +
                                  "\n---\n".join(t["trecho"][:1200] for t in trechos))
    termo_img = intencao_imagem(texto_usuario)
    if termo_img:
        import urllib.parse
        slug = urllib.parse.quote(termo_img.strip() or "paisagem")
        partes_sistema.append(f"O usuário pediu uma IMAGEM sobre '{termo_img}'. "
                              f"Além de descrever, inclua no final: ![{{descricao}}](https://loremflickr.com/800/500/{slug}) "
                              "para exibir a imagem no chat.")
    if cfg.get("pesquisa_web", True) and intencao_pesquisa(texto_usuario):
        hoje = datetime.now().strftime("%d/%m/%Y")
        fontes = pesquisa_web(texto_usuario)
        extras["fontes"] = fontes
        if fontes:
            bloco = "\n".join(f"- {f['titulo']}: {f['trecho']} ({f['url']})" for f in fontes)
            partes_sistema.append(f"RESULTADOS DA PESQUISA WEB EM TEMPO REAL (hoje é {hoje}; "
                                  "cite ao final em 'Fontes:' com os links):\n" + bloco)
        else:
            partes_sistema.append(f"O usuário pediu pesquisa em tempo real (hoje é {hoje}), "
                                  "mas a busca falhou. Avise a data e responda com seu conhecimento, sem inventar links.")
    messages = [{"role": "system", "content": "\n\n".join(partes_sistema)}] + historico
    return messages, extras


def anexar_fontes(texto: str, fontes: list, termo_img: str = "") -> str:
    if termo_img and "![" not in (texto or ""):
        import urllib.parse
        slug = urllib.parse.quote(termo_img.strip() or "paisagem")
        texto = (texto or "") + f"\n\n![{termo_img}](https://loremflickr.com/800/500/{slug})"
    if fontes and "Fontes:" not in (texto or ""):
        linhas = "\n".join(f"- [{f['titulo']}]({f['url']})" for f in fontes)
        texto = (texto or "") + "\n\nFontes:\n" + linhas
    return texto


def contexto_conversa(db, conversation_id: str, limite: int, owner=DONO_PADRAO) -> list:
    rows = db.execute("""SELECT role, text FROM messages
                         WHERE origin=? AND owner_id=? AND conversation_id=?
                         ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", dono_valido(owner), conversation_id, limite)).fetchall()
    limpos = []
    for role, text in reversed(rows):
        if role not in ("user", "assistant"):
            continue
        t = re.sub(r"```jdui[\s\S]*?(```|$)", "[interface]", text or "", flags=re.IGNORECASE)
        limpos.append({"role": role, "content": t[:2000]})
    return limpos


def ai_estado(db, user_message_id: str, owner=DONO_PADRAO):
    row = db.execute("SELECT state, reply_id, response_text, error, model FROM ai_requests "
                     "WHERE user_message_id=? AND owner_id=?", (user_message_id, dono_valido(owner),)).fetchone()
    if not row:
        return None
    return {"state": row[0], "reply_id": row[1], "response_text": row[2],
            "error": row[3], "model": row[4]}


def ai_marcar(db, user_message_id, conversation_id, model, state,
              reply_id=None, response_text=None, error=None, owner=DONO_PADRAO):
    with db:
        db.execute("""INSERT INTO ai_requests
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, created_at, updated_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_message_id) DO UPDATE SET state=excluded.state,
             reply_id=excluded.reply_id, response_text=excluded.response_text,
             error=excluded.error, updated_at=excluded.updated_at""",
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, agora_iso(), agora_iso(), dono_valido(owner)))


def _apagar_todos_dados(db, owner: str) -> int:
    """Apaga conta + todos os dados do dono. Retorna registros removidos."""
    total = 0
    with db:
        for tabela, col in (("messages", "owner_id"), ("ai_requests", "owner_id"),
                            ("memories", "owner_id"), ("memory_facts", "owner_id"),
                            ("documents", "owner_id"), ("doc_chunks", "owner_id"),
                            ("ui_state", "owner_id"), ("memory_events", "owner_id")):
            try:
                cur = db.execute(f"DELETE FROM {tabela} WHERE {col}=?", (owner,))
                total += cur.rowcount or 0
            except Exception:
                continue
        try:
            db.execute("DELETE FROM memories_fts WHERE owner_id=?", (owner,))
        except Exception:
            pass
        db.execute("DELETE FROM user_sessions WHERE uid=?", (owner,))
        db.execute("DELETE FROM users WHERE uid=?", (owner,))
    return total


def dono_bloqueado(db, owner: str) -> bool:
    """Conta bloqueada/inexistente não usa dados nem IA (verificação por RPC)."""
    owner = dono_valido(owner)
    try:
        total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if not total:
            return False  # modo legado: conta única do .env, sem tabela de usuários
        user = julia_auth.buscar_uid(db, owner)
        return user is None or user.get("status") != "ativo"
    except Exception:
        return True


def ai_preparar(db, payload: dict, cfg: dict) -> dict:
    """Valida e aplica idempotência. Retorna {user_text, model, reply_id} ou {replay|busy|error}."""
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    if not (isinstance(conv, str) and 3 <= len(conv) <= 100):
        return {"error": "conversation_id inválido.", "codigo": "invalido"}
    modelo = payload.get("model") or cfg["model"]
    if not (isinstance(modelo, str) and 1 <= len(modelo) <= 120):
        return {"error": "Modelo inválido.", "codigo": "invalido"}
    owner = dono_valido(payload.get("owner"))
    if dono_bloqueado(db, owner):
        return {"error": "Conta indisponível.", "codigo": "bloqueada"}
    lim = julia_auth.limites_usuario(db, owner)
    if julia_auth.simultaneas_ia(db, owner) >= lim["max_ia_simult"]:
        return {"error": "Muitas gerações ao mesmo tempo; aguarde.", "codigo": "limite"}
    if julia_auth.uso_ia_hora(db, owner) >= lim["max_ai_hora"]:
        return {"error": "Limite de uso da IA por hora atingido.", "codigo": "limite"}
    previo = ai_estado(db, mid, owner)
    if previo and previo["state"] == "completed":
        return {"replay": True, "reply_id": previo["reply_id"],
                "response_text": previo["response_text"], "model": previo["model"]}
    if previo and previo["state"] == "processing":
        return {"busy": True}
    row = db.execute("SELECT text FROM messages WHERE id=? AND origin='mobile' "
                     "AND owner_id=? AND role='user' AND conversation_id=?", (mid, owner, conv)).fetchone()
    if not row:
        return {"error": "Mensagem do usuário não encontrada. Sincronize primeiro.",
                "codigo": "sem_mensagem"}
    try:
        analisar_memoria(db, row[0], owner, conv, mid)
    except Exception:
        pass
    mem_flag = payload.get("memory", payload.get("memoria_global", None))
    memoria_on = cfg.get("memoria_global", True) if mem_flag is None else (str(mem_flag) == "1")
    ai_marcar(db, mid, conv, modelo, "queued", owner=owner)
    return {"user_text": row[0], "model": modelo,
            "reply_id": f"{mid}-r1", "conversation_id": conv,
            "memoria_global": memoria_on, "owner": owner}


def ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto, owner=DONO_PADRAO) -> None:
    owner = dono_valido(owner)
    with db:
        db.execute("""INSERT OR IGNORE INTO messages
            (id, conversation_id, origin, role, text, created_at, received_at, model, owner_id)
            VALUES (?, ?, 'mobile', 'assistant', ?, ?, ?, ?, ?)""",
            (reply_id, conv, texto, agora_iso(), agora_iso(), modelo, owner))
        db.execute("""UPDATE messages SET text=?, received_at=? WHERE id=?
                      AND origin='mobile' AND owner_id=?""",
                   (texto, agora_iso(), reply_id, owner))
    ai_marcar(db, mid, conv, modelo, "completed",
              reply_id=reply_id, response_text=texto, owner=owner)


def ai_resetar(db, payload: dict) -> dict:
    """Regenerar: apaga pedido anterior + resposta para recomputar do zero."""
    owner = dono_valido(payload.get("owner"))
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    row = db.execute("SELECT 1 FROM messages WHERE id=? AND origin='mobile' AND owner_id=? "
                     "AND role='user' AND conversation_id=?", (mid, owner, conv)).fetchone()
    if not row:
        return {"error": "Mensagem não encontrada.", "codigo": "sem_mensagem"}
    with db:
        db.execute("DELETE FROM ai_requests WHERE user_message_id=? AND owner_id=?", (mid, owner))
        db.execute("DELETE FROM messages WHERE id=? AND origin='mobile' AND owner_id=?",
                   (f"{mid}-r1", owner))
    return {"ok": True, "reply_id": f"{mid}-r1"}


def ai_continuar(db, payload: dict, cfg: dict) -> dict:
    """Continuar: gera a continuação e ANEXA à mesma resposta (mesmo reply_id)."""
    owner = dono_valido(payload.get("owner"))
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    est = ai_estado(db, mid, owner)
    if not est or not (est.get("response_text") or "").strip():
        return {"error": "Nada para continuar.", "codigo": "sem_resposta"}
    modelo = payload.get("model") or est.get("model") or cfg["model"]
    cfg_eff = dict(cfg, memoria_global=True)
    historico = contexto_conversa(db, conv, min(cfg["context"], 8), owner)
    messages = ([{"role": "system", "content": cfg["system"]}] + historico
                + [{"role": "assistant", "content": (est["response_text"] or "")[-4000:]},
                   {"role": "user", "content": "Continue exatamente de onde parou, sem repetir o que já disse."}])
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    try:
        res = hermes_bridge.chat_complete(cfg["proxy"], modelo, messages, max_tokens=cfg["max_tokens"])
    except hermes_bridge.BridgeErro as exc:
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner)
        return {"error": str(exc), "codigo": exc.codigo}
    trecho = (res.get("texto") or "").strip()
    if not trecho:
        return {"error": "Modelo não continuou.", "codigo": "vazia"}
    anterior = (est["response_text"] or "").rstrip()
    combinado = anterior + ("" if anterior.endswith((" ", "\n")) else " ") + trecho
    ai_guardar_resposta(db, mid, conv, modelo, est["reply_id"] or f"{mid}-r1", combinado, owner)
    return {"reply_id": est["reply_id"], "response_text": combinado, "model": modelo}


def ai_resposta_direta(db, mid, conv, modelo, reply_id, texto, owner=DONO_PADRAO) -> dict:
    """Resposta sem LLM (comandos de memória). Salva e marca como completa."""
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto, owner)
    return {"reply_id": reply_id, "response_text": texto, "model": modelo}


def ai_completa(db, payload: dict, cfg: dict) -> dict:
    prep = ai_preparar(db, payload, cfg)
    if "error" in prep or "replay" in prep or "busy" in prep:
        return prep
    mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
    owner = prep.get("owner", DONO_PADRAO)
    cmd = interpretar_comando_memoria(db, prep.get("user_text", ""), owner)
    if cmd:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0], owner)
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
    messages, extras = ai_montar_mensagens(db, conv, cfg_eff, prep.get("user_text", ""), owner)
    try:
        res = hermes_bridge.chat_complete(cfg["proxy"], modelo, messages,
                                          max_tokens=cfg["max_tokens"])
    except hermes_bridge.BridgeErro as exc:
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner)
        return {"error": str(exc), "codigo": exc.codigo}
    texto = anexar_fontes(res["texto"], extras["fontes"], intencao_imagem(prep.get("user_text", "")))
    texto, blocos_jdui, erros_jdui = jdui.normalizar(texto)
    if erros_jdui:
        log.warning("JDUI descartado na msg %s: %s", mid, "; ".join(erros_jdui[:3]))
    if not blocos_jdui and extras.get("comp_sugerido") in JDUI_SINTETIZAR:
        fence = sintetizar_jdui(cfg_eff, extras["comp_sugerido"], prep.get("user_text", ""), texto)
        if fence:
            texto += fence
            log.info("JDUI sintetizado para %s (%s)", mid, extras["comp_sugerido"])
    ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto, owner)
    if len(prep.get("user_text", "")) >= 20:
        threading.Thread(target=aprender_com_conversa,
                         args=(database_path(), dict(cfg), prep["user_text"], texto, owner),
                         daemon=True).start()
    log.info("IA %s respondeu em %ss (msg %s, memoria=%s, fontes=%d)", modelo, res["latencia_s"], mid,
             extras["memoria_usada"], len(extras["fontes"]))
    return {"reply_id": prep["reply_id"], "response_text": texto,
            "model": modelo, "truncada": res.get("truncada", False)}


class SessaoStream:
    def __init__(self):
        self.parar = threading.Event()
        self.lock_envio = threading.Lock()


def ai_stream_worker(db_path: Path, cfg: dict, payload: dict, request_id: str,
                     websocket, sessao: SessaoStream, cancelados: dict) -> None:
    """Roda em thread: deltas saem pelo lock; a thread principal só recebe."""
    db = open_db(db_path)
    try:
        prep = ai_preparar(db, payload, cfg)
        if "error" in prep or "replay" in prep or "busy" in prep:
            try:
                with sessao.lock_envio:
                    websocket.send(json.dumps({"request_id": request_id, "type": "ai_error",
                                               **{k: prep[k] for k in ("error", "codigo", "reply_id",
                                                                       "response_text", "model", "busy")
                                                   if k in prep}},
                                              ensure_ascii=False))
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
        owner = prep.get("owner", DONO_PADRAO)
        cmd = interpretar_comando_memoria(db, prep.get("user_text", ""), owner)
        if cmd:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0], owner)
            try:
                with sessao.lock_envio:
                    websocket.send(json.dumps({"request_id": request_id, "type": "ai_done",
                                               "reply_id": direta["reply_id"],
                                               "response_text": direta["response_text"],
                                               "model": modelo}, ensure_ascii=False))
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
        cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
        messages, extras = ai_montar_mensagens(db, conv, cfg_eff, prep.get("user_text", ""), owner)

        def enviar(obj):
            try:
                with sessao.lock_envio:
                    websocket.send(json.dumps(obj, ensure_ascii=False))
            except (ConnectionClosed, OSError, RuntimeError, ValueError) as exc:
                raise hermes_bridge.BridgeErro(
                    "Conexão com o relay caiu no meio da resposta.", "desconectado") from exc

        def emitir(seq, trecho):
            enviar({"request_id": request_id, "type": "ai_delta",
                    "seq": seq, "trecho": trecho})

        try:
            res = hermes_bridge.chat_stream(cfg["proxy"], modelo, messages, emitir,
                                            deve_parar=sessao.parar.is_set,
                                            max_tokens=cfg["max_tokens"])
        except hermes_bridge.BridgeErro as exc:
            ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner)
            try:
                enviar({"request_id": request_id, "type": "ai_error",
                        "error": str(exc), "codigo": exc.codigo})
            except hermes_bridge.BridgeErro:
                pass  # relay fora do ar: celular verá timeout + retry
            return
        if res.get("cancelada"):
            ai_marcar(db, mid, conv, modelo, "cancelled",
                      reply_id=prep["reply_id"], response_text=res["texto"], owner=owner)
            try:
                enviar({"request_id": request_id, "type": "ai_cancelled",
                        "reply_id": prep["reply_id"], "partial": res["texto"]})
            except hermes_bridge.BridgeErro:
                pass
            return
        texto_final = anexar_fontes(res["texto"], extras["fontes"], intencao_imagem(prep.get("user_text", "")))
        texto_final, blocos_jdui, erros_jdui = jdui.normalizar(texto_final)
        if erros_jdui:
            log.warning("JDUI descartado no stream %s: %s", mid, "; ".join(erros_jdui[:3]))
        if not blocos_jdui and extras.get("comp_sugerido") in JDUI_SINTETIZAR:
            fence = sintetizar_jdui(cfg_eff, extras["comp_sugerido"], prep.get("user_text", ""), texto_final)
            if fence:
                texto_final += fence  # o tail-emit abaixo entrega como deltas finais
                log.info("JDUI sintetizado no stream %s (%s)", mid, extras["comp_sugerido"])
        if texto_final != res["texto"]:
            # envia o complemento (fontes/imagem) como deltas finais para TTFT não degradar
            try:
                emitir(res.get("seq", 9999) if isinstance(res.get("seq"), int) else 9999,
                       texto_final[len(res["texto"]):])
            except Exception:
                pass
        ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto_final, owner)
        if len(prep.get("user_text", "")) >= 20:
            threading.Thread(target=aprender_com_conversa,
                             args=(db_path, dict(cfg_eff), prep["user_text"], texto_final, owner),
                             daemon=True).start()
        log.info("IA %s (stream) em %ss (msg %s, fontes=%d)", modelo, res["latencia_s"], mid, len(extras["fontes"]))
        enviar({"request_id": request_id, "type": "ai_done",
                "reply_id": prep["reply_id"],
                "response_text": texto_final, "model": modelo})
    finally:
        cancelados.pop(request_id, None)
        db.close()


def run():
    relay_url = os.environ.get("JULIA_RELAY_URL", "").strip().rstrip("/")
    token = os.environ.get("JULIA_AGENT_TOKEN", "")
    if not relay_url or not token:
        raise SystemExit("Configure JULIA_RELAY_URL e JULIA_AGENT_TOKEN")
    parsed = urlparse(relay_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise SystemExit("JULIA_RELAY_URL inválida")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("O agente exige HTTPS fora de localhost")
    ws_url = f"{'wss' if parsed.scheme == 'https' else 'ws'}://{parsed.netloc}/api/agent/ws"
    db = open_db(database_path())
    cfg = ai_config()
    try:
        modelos = hermes_bridge.listar_modelos(cfg["proxy"])
        log.info("Hermes proxy OK: %d modelos (padrão %s)", len(modelos), cfg["model"])
    except hermes_bridge.BridgeErro as exc:
        log.warning("Hermes indisponível no boot (%s). Mensagens serão guardadas; IA tenta depois.",
                    exc)
    pause = 2
    log.info("SQLite local preparado: %s", database_path())
    if remoto.entrada_ativada():
        log.warning("CONTROLE REMOTO ATIVO (JULIA_REMOTE=1): cliques/teclas do celular serão executados. Comandos registrados no log.")
    else:
        log.info("Controle remoto desativado (somente visualização). Defina JULIA_REMOTE=1 para ativar.")
    cancelados: dict = {}
    while True:
        try:
            with connect(ws_url, additional_headers={"Authorization": "Bearer " + token},
                          open_timeout=15, ping_interval=25, ping_timeout=20, max_size=25_000_000) as websocket:
                log.info("Conectado ao relay. Nenhuma porta de entrada foi aberta no PC.")
                pause = 2
                for raw in websocket:
                    req = json.loads(raw)
                    request_id = req.get("request_id")
                    if not isinstance(request_id, str):
                        continue
                    dono = dono_valido(req.get("owner"))
                    tipo = req.get("type")

                    def _exige_admin():
                        u = julia_auth.buscar_uid(db, dono)
                        if not u or u.get("role") != "admin" or u.get("status") != "ativo":
                            return None
                        return u

                    def _resp_ok(_tipo, **campos):
                        return {"request_id": request_id, "type": _tipo, **campos}

                    def _resp_erro(msg, codigo="erro"):
                        return {"request_id": request_id, "type": "auth_error"
                                if tipo in ("auth_login", "auth_register") else "op_error",
                                "error": msg, "codigo": codigo}

                    if tipo in ("sync", "list", "conversations", "doc_upload", "doc_list",
                                "doc_resumo", "doc_topicos", "mem_list", "mem_list_full",
                                "mem_forget", "mem_confirm", "mem_update", "ui_state_save",
                                "ui_state_list", "conv_forget", "event_list", "ai", "ai_stream",
                                "ai_reset", "ai_continue") and dono_bloqueado(db, dono):
                        reply = _resp_erro("Conta indisponível.", "bloqueada")
                    elif tipo == "auth_login":
                        try:
                            user = julia_auth.login_conta(db, req.get("username", ""),
                                                          req.get("password", ""))
                            sess = julia_auth.criar_sessao(db, user["uid"])
                            reply = _resp_ok("auth_ok", uid=user["uid"], username=user["username"],
                                             display=user["display"], role=user["role"],
                                             sid=sess["sid"], expira_em=sess["expira_em"])
                        except julia_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "auth_register":
                        try:
                            reg = julia_auth.registrar(db, req.get("display", ""),
                                                       req.get("username", ""),
                                                       req.get("password", ""),
                                                       req.get("invite", ""))
                            out = {"uid": reg["uid"], "username": reg["username"],
                                   "display": reg["display"], "status": reg["status"]}
                            if reg["status"] == "ativo" and reg["uid"]:
                                sess = julia_auth.criar_sessao(db, reg["uid"])
                                out["sid"] = sess["sid"]
                                out["expira_em"] = sess["expira_em"]
                            reply = _resp_ok("auth_registered", **out)
                        except julia_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "auth_config":
                        reply = _resp_ok("auth_config", modo=julia_auth.modo_cadastro(db),
                                         exigir_aprovacao=julia_auth.config_get(
                                             db, "exigir_aprovacao", "1") == "1")
                    elif tipo == "auth_logout":
                        julia_auth.revogar_sessao(db, req.get("sid", ""))
                        reply = _resp_ok("auth_logged_out")
                    elif tipo == "auth_whoami":
                        user = julia_auth.sessao_valida(db, req.get("sid", ""))
                        reply = _resp_ok("auth_user", user=user) if user else \
                            _resp_erro("Sessão inválida.", "sessao")
                    elif tipo == "account_password":
                        if req.get("uid") != dono:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                julia_auth.trocar_senha(db, dono, req.get("atual", ""),
                                                        req.get("nova", ""))
                                reply = _resp_ok("account_ok")
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "account_delete":
                        try:
                            alvo = julia_auth.buscar_uid(db, dono)
                            if not alvo or not julia_auth.confere_senha(
                                    req.get("password", ""),
                                    (julia_auth.buscar_usuario(db, alvo["username"]) or {}).get("hash", "")):
                                raise julia_auth.AuthErro("Senha incorreta.", "senha")
                            n_admin = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' "
                                                 "AND status='ativo'").fetchone()[0]
                            if alvo["role"] == "admin" and n_admin <= 1:
                                raise julia_auth.AuthErro(
                                    "Último admin: transfira antes de excluir.", "ultimo_admin")
                            total = _apagar_todos_dados(db, dono)
                            julia_auth.auditar(db, dono, "conta_autoexcluida", alvo["username"],
                                               f"registros={total}")
                            reply = _resp_ok("account_deleted", apagados=total)
                        except julia_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_users":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            rows = db.execute("SELECT uid, username, display, role, status, "
                                              "aprovado, created_at, last_seen FROM users "
                                              "ORDER BY created_at").fetchall()
                            pend = db.execute("SELECT COUNT(*) FROM reg_requests "
                                              "WHERE status='pendente'").fetchone()[0]
                            reply = _resp_ok("admin_users",
                                             users=[{"uid": u, "username": n, "display": d,
                                                     "role": r, "status": s, "aprovado": bool(a),
                                                     "created_at": c, "last_seen": l}
                                                    for u, n, d, r, s, a, c, l in rows],
                                             pendentes=pend)
                    elif tipo == "admin_user_create":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                papel = req.get("role", "user") if req.get("role") in ("admin", "user") else "user"
                                user = julia_auth.criar_usuario(
                                    db, req.get("username", ""), req.get("display", ""),
                                    req.get("password", ""), papel=papel, criado_por=dono)
                                reply = _resp_ok("admin_user_created", **user)
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_role":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                julia_auth.definir_papel(db, dono, req.get("uid", ""), req.get("role", ""))
                                reply = _resp_ok("admin_ok")
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_status":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                julia_auth.definir_status(db, dono, req.get("uid", ""), req.get("status", ""))
                                reply = _resp_ok("admin_ok")
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_delete":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                n = julia_auth.excluir_usuario(db, dono, req.get("uid", ""))
                                reply = _resp_ok("admin_ok", apagados=n)
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_invite_create":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            conv = julia_auth.gerar_convite(db, dono, req.get("max_usos", 1),
                                                           req.get("dias", 7), req.get("nota", ""))
                            reply = _resp_ok("admin_invite", **conv)
                    elif tipo == "admin_invites":
                        adm = _exige_admin()
                        reply = _resp_ok("admin_invites",
                                         invites=julia_auth.listar_convites(db)) if adm else \
                            _resp_erro("Sem permissão.", "permissao")
                    elif tipo == "admin_invite_revoke":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            julia_auth.revogar_convite(db, dono, req.get("id", 0))
                            reply = _resp_ok("admin_ok")
                    elif tipo == "admin_regs":
                        adm = _exige_admin()
                        reply = _resp_ok("admin_regs",
                                         pedidos=julia_auth.listar_pedidos(db)) if adm else \
                            _resp_erro("Sem permissão.", "permissao")
                    elif tipo == "admin_reg_decide":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                julia_auth.decidir_pedido(db, dono, req.get("id", 0),
                                                          bool(req.get("aprovar")))
                                reply = _resp_ok("admin_ok")
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_config_set":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            modo = str(req.get("modo", ""))
                            if modo and modo not in julia_auth.MODOS:
                                reply = _resp_erro("Modo inválido.", "invalido")
                            else:
                                if modo:
                                    julia_auth.config_set(db, "modo_cadastro", modo)
                                if "exigir_aprovacao" in req:
                                    julia_auth.config_set(
                                        db, "exigir_aprovacao",
                                        "1" if req.get("exigir_aprovacao") else "0")
                                julia_auth.auditar(db, dono, "config_alterada", "",
                                                   f"modo={modo or '-'}")
                                reply = _resp_ok("admin_ok")
                    elif tipo == "admin_audit":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            rows = db.execute("SELECT ts, ator, acao, alvo, detalhe FROM audit_log "
                                              "ORDER BY id DESC LIMIT 200").fetchall()
                            reply = _resp_ok("admin_audit",
                                             eventos=[{"ts": t, "ator": a, "acao": c,
                                                       "alvo": al, "detalhe": d}
                                                      for t, a, c, al, d in rows])
                    elif tipo == "admin_sess_revoke":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            with db:
                                db.execute("UPDATE user_sessions SET revogada=1 WHERE uid=?",
                                           (str(req.get("uid", "")),))
                            julia_auth.auditar(db, dono, "sessoes_revogadas", str(req.get("uid", "")))
                            reply = _resp_ok("admin_ok")
                    elif tipo == "admin_user_limits":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                julia_auth.update_limits(db, dono, str(req.get("uid", "")),
                                                        req.get("max_ai_hora", 0), req.get("max_ia_simult", 0))
                                reply = _resp_ok("admin_ok")
                            except julia_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "sess_revogados":
                        reply = _resp_ok("sess_revogados", sids=julia_auth.sids_revogados(db))
                    elif req.get("type") == "sync":
                        confirmed_ids = persist_messages(db, req.get("messages", []), dono)
                        reply = {"request_id": request_id, "type": "ack", "confirmed_ids": confirmed_ids}
                    elif req.get("type") == "list":
                        reply = {"request_id": request_id, "type": "history",
                                 "messages": list_messages(db, req.get("limit", 200), dono)}
                    elif req.get("type") == "conversations":
                        reply = {"request_id": request_id, "type": "conversations",
                                 "conversations": listar_conversas(db, req.get("limit", 100), dono)}
                    elif req.get("type") == "doc_upload":
                        try:
                            import base64 as _b64
                            raw = _b64.b64decode(req.get("data_b64", ""), validate=True)
                            meta = docs_agent.salvar_documento(
                                db, req.get("name", "arquivo"),
                                raw, req.get("conversation_id", "geral"), dono)
                            reply = {"request_id": request_id, "type": "doc_uploaded", **meta}
                        except Exception as exc:
                            codigo = getattr(exc, "codigo", "erro")
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300], "codigo": codigo}
                    elif req.get("type") == "doc_list":
                        reply = {"request_id": request_id, "type": "doc_list",
                                 "documents": docs_agent.listar_documentos(db, req.get("limit", 50), dono)}
                    elif req.get("type") == "doc_resumo":
                        try:
                            texto = docs_agent.resumir_documento(db, cfg, req.get("doc_id", ""), dono)
                            reply = {"request_id": request_id, "type": "doc_resumo",
                                     "doc_id": req.get("doc_id", ""), "resumo": texto}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "doc_topicos":
                        try:
                            texto = docs_agent.topicos_documento(db, cfg, req.get("doc_id", ""), dono)
                            reply = {"request_id": request_id, "type": "doc_topicos",
                                     "doc_id": req.get("doc_id", ""), "topicos": texto}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "ui_state_save":
                        salvos = 0
                        with db:
                            for s in req.get("states", [])[:300]:
                                try:
                                    k = str(s.get("k", ""))[:200]
                                    if not (k and isinstance(s.get("state"), str)
                                            and len(s["state"]) <= 8000):
                                        continue
                                    ex = db.execute("SELECT owner_id FROM ui_state WHERE k=?",
                                                    (k,)).fetchone()
                                    if ex and ex[0] != dono:
                                        continue  # chave de outro dono: não toca
                                    db.execute("""INSERT INTO ui_state
                                        (k, message_id, slot, state, updated_at, owner_id)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(k) DO UPDATE SET
                                        state=excluded.state, updated_at=excluded.updated_at""",
                                        (k, str(s.get("message_id", ""))[:100],
                                         str(s.get("slot", ""))[:40], s["state"],
                                         str(s.get("updated_at", agora_iso()))[:48], dono))
                                    salvos += 1
                                except Exception:
                                    continue
                        reply = {"request_id": request_id, "type": "ui_state_saved",
                                 "saved": salvos}
                    elif req.get("type") == "ui_state_list":
                        rows = db.execute("SELECT k, message_id, slot, state, updated_at "
                                          "FROM ui_state WHERE owner_id=? "
                                          "ORDER BY updated_at DESC LIMIT 500", (dono,)).fetchall()
                        reply = {"request_id": request_id, "type": "ui_state_list",
                                 "states": [{"k": k, "message_id": m, "slot": s,
                                             "state": st, "updated_at": u}
                                            for k, m, s, st, u in rows]}
                    elif req.get("type") == "conv_forget":
                        conv = req.get("conversation_id", "")
                        n = 0
                        if isinstance(conv, str) and 3 <= len(conv) <= 100:
                            with db:
                                cur = db.execute("DELETE FROM messages WHERE origin='mobile' "
                                                 "AND owner_id=? AND conversation_id=?", (dono, conv))
                                n = cur.rowcount or 0
                                db.execute("DELETE FROM ai_requests WHERE owner_id=? AND conversation_id=?",
                                           (dono, conv))
                        log.info("conversa esquecida no PC: %s (%d msgs)", conv, n)
                        reply = {"request_id": request_id, "type": "conv_forgotten",
                                 "deleted": n}
                    elif req.get("type") == "mem_list":
                        rows = db.execute("SELECT key, value, updated_at FROM memories WHERE owner_id=? "
                                          "ORDER BY updated_at DESC LIMIT 100", (dono,)).fetchall()
                        reply = {"request_id": request_id, "type": "mem_list",
                                 "memories": [{"key": k, "value": v, "updated_at": u}
                                              for k, v, u in rows]}
                    elif req.get("type") == "mem_forget":
                        with db:
                            db.execute("DELETE FROM memories WHERE owner_id=? AND key=?",
                                       (dono, req.get("key", "")))
                            try:
                                db.execute("DELETE FROM memories_fts WHERE owner_id=? AND key=?",
                                           (dono, req.get("key", "")))
                            except Exception:
                                pass
                        reply = {"request_id": request_id, "type": "mem_forgotten",
                                 "key": req.get("key", "")}
                    elif req.get("type") == "mem_list_full":
                        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, "
                                          "origem_msg, valido_ate, updated_at FROM memories "
                                          "WHERE owner_id=? ORDER BY status, updated_at DESC LIMIT 200",
                                          (dono,)).fetchall()
                        reply = {"request_id": request_id, "type": "mem_list_full",
                                 "memories": [{"key": k, "value": v, "tipo": t, "assunto": a,
                                               "status": s, "origem_conv": oc, "origem_msg": om,
                                               "valido_ate": va, "updated_at": u}
                                              for k, v, t, a, s, oc, om, va, u in rows]}
                    elif req.get("type") == "mem_confirm":
                        feito = confirmar_pendencia(db, dono)
                        reply = {"request_id": request_id, "type": "mem_confirmed", **feito}
                    elif req.get("type") == "mem_update":
                        chave = re.sub(r"\s+", "_", str(req.get("key", "")).strip().lower())[:60]
                        valor = str(req.get("value", "")).strip()[:500]
                        if chave and valor:
                            registrar_memoria(db, dono, chave, valor)
                            reply = {"request_id": request_id, "type": "mem_updated", "key": chave}
                        else:
                            reply = {"request_id": request_id, "type": "mem_error",
                                     "error": "Chave ou valor inválido"}
                    elif req.get("type") == "mem_settings":
                        if "learning" in req:
                            definir_aprendizado(db, dono, str(req.get("learning")) == "1")
                        reply = {"request_id": request_id, "type": "mem_settings",
                                 "learning": aprendizado_ativo(db, dono)}
                    elif req.get("type") == "event_list":
                        reply = {"request_id": request_id, "type": "event_list",
                                 "events": proximos_eventos(db, dono)}
                    elif req.get("type") == "ai":
                        res = ai_completa(db, req, cfg)
                        reply = {"request_id": request_id, "type": "ai_done", **res}
                    elif req.get("type") == "ai_reset":
                        res = ai_resetar(db, req)
                        reply = {"request_id": request_id,
                                 **({"type": "ai_reset_ok", **res} if "ok" in res
                                    else {"type": "ai_error", **res})}
                    elif req.get("type") == "ai_continue":
                        res = ai_continuar(db, req, cfg)
                        reply = {"request_id": request_id,
                                 **({"type": "ai_done", **res} if "response_text" in res
                                    else {"type": "ai_error", **res})}
                    elif req.get("type") == "ai_models":
                        try:
                            reply = {"request_id": request_id, "type": "ai_models",
                                     "models": hermes_bridge.listar_modelos(cfg["proxy"]),
                                     "default": cfg["model"]}
                        except hermes_bridge.BridgeErro as exc:
                            reply = {"request_id": request_id, "type": "ai_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "ai_stream":
                        sessao = SessaoStream()
                        cancelados[request_id] = sessao
                        threading.Thread(target=ai_stream_worker,
                                         args=(database_path(), cfg, req, request_id,
                                               websocket, sessao, cancelados),
                                         daemon=True).start()
                        continue
                    elif req.get("type") == "ai_cancel":
                        alvo = req.get("target") if isinstance(req.get("target"), str) else request_id
                        sessao = cancelados.get(alvo)
                        if sessao is not None:
                            sessao.parar.set()
                        continue
                    elif req.get("type") == "screen":
                        try:
                            img = remoto.capturar(req.get("max_w", 800), req.get("q", 55))
                            reply = {"request_id": request_id, "type": "screen", **img,
                                     "remote_enabled": remoto.entrada_ativada()}
                        except remoto.RemotoErro as exc:
                            reply = {"request_id": request_id, "type": "screen_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "input":
                        try:
                            cmd = remoto.validar_comando(req.get("cmd", {}))
                            res = remoto.executar(cmd)
                            log.info("remoto: %s executado", res["kind"])
                            reply = {"request_id": request_id, "type": "input_done", **res}
                        except remoto.RemotoErro as exc:
                            reply = {"request_id": request_id, "type": "input_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    else:
                        continue
                    websocket.send(json.dumps(reply, ensure_ascii=False))
        except InvalidStatus as exc:
            # HTTP 403 no handshake = bloqueio anti-robô/rate-limit na borda
            # (Cloudflare), NÃO problema no agente. Martelar piora: espera longa.
            status = getattr(exc.response, "status_code", "?") if getattr(exc, "response", None) else "?"
            pause = min(1800, max(pause * 2, 120))
            log.warning("Relay recusou o handshake (HTTP %s). Provável bloqueio temporário "
                        "anti-robô/rate-limit na borda — NÃO é erro de token. "
                        "Aguardando %ss antes de tentar (não force reconexões).",
                        status, pause)
        except (ConnectionClosed, ConnectionError, OSError, TimeoutError, ValueError) as exc:
            log.warning("Conexão interrompida (%s). Reconectando em %ss", type(exc).__name__, pause)
            pause = min(60, pause * 2)
        except KeyboardInterrupt:
            break
        time.sleep(pause)
    db.close()


if __name__ == "__main__":
    run()
