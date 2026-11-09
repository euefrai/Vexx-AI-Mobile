"""PC-side durable SQLite agent. Run only on a trusted Windows computer."""
import json
import logging
import logging.handlers
import os
import random
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import docs_agent
import files_agent
import model3d
import model3d_research
import env_local
env_local.carregar_env_local()  # .env local do PC (nunca sobrescreve o sistema)
from assistant_identity import (CONVERSATION_NAME, OFFICIAL_NAME,
                                limitar_afirmacoes_nao_suportadas,
                                pergunta_identidade_produto,
                                resposta_identidade_produto,
                                system_with_identity)
import hermes_bridge
import intent
import jdui
import providers
import inference_status
import tool_protocol
import julia_auth as JULIA_auth
import learning
import remoto
import remote_access
import research
import query_intelligence
import research_agents
import shopping
import live_data
import conversation_followups
import evidence_graph as evgraph
import workspace_store
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("JULIA-pc")
_BOOT_MONO = time.monotonic()
_BOOT_ISO = datetime.now(timezone.utc).isoformat(timespec="seconds")
_REVISAO_CACHE = ""


def revisao_agente() -> str:
    """Commit que este processo esta executando (env ou git do checkout)."""
    global _REVISAO_CACHE
    if _REVISAO_CACHE:
        return _REVISAO_CACHE
    candidato = os.environ.get("JULIA_AGENT_COMMIT", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{7,40}", candidato):
        try:
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
                      "text": True, "timeout": 5, "check": False}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            saida = subprocess.run(
                ["git", "-C", str(Path(__file__).resolve().parent),
                 "rev-parse", "HEAD"], **kwargs)
            candidato = (saida.stdout or "").strip().lower()
        except (OSError, subprocess.SubprocessError):
            candidato = ""
    _REVISAO_CACHE = candidato[:12] if re.fullmatch(
        r"[0-9a-f]{7,40}", candidato) else "desconhecido"
    return _REVISAO_CACHE


def sqlite_integro(db) -> bool:
    """Prova rapida de integridade para o hello de readiness."""
    try:
        return str(db.execute("PRAGMA quick_check").fetchone()[0]).lower() == "ok"
    except Exception:
        return False


def hello_agente(db) -> dict:
    """Metadata tecnica enviada ao relay ao conectar (sem dados de usuario)."""
    return {
        "type": "agent_hello",
        "commit": revisao_agente(),
        "pid": os.getpid(),
        "uptime_s": max(0, int(time.monotonic() - _BOOT_MONO)),
        "started_at": _BOOT_ISO,
        "db_ok": sqlite_integro(db),
        "python": "%d.%d.%d" % sys.version_info[:3],
    }


def configurar_log_persistente() -> None:
    """Log rotativo em ~/.julia-mobile/logs para sobreviver ao console."""
    try:
        destino = Path(os.environ.get(
            "JULIA_LOG_DIR", str(Path.home() / ".julia-mobile" / "logs")))
        destino.mkdir(parents=True, exist_ok=True)
        alvo = destino / "agent.log"
        raiz = logging.getLogger()
        if any(getattr(h, "baseFilename", "") == str(alvo.resolve())
               for h in raiz.handlers):
            return
        handler = logging.handlers.RotatingFileHandler(
            alvo, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        raiz.addHandler(handler)
        log.info("Log persistente: %s", alvo)
    except OSError as exc:
        log.warning("Nao foi possivel abrir log persistente: %s", exc)

# Síntese de UI em paralelo com a geração principal (conexão própria por
# thread; SQLite não compartilha conexão entre threads).
_SINT_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="juliarsint")
_SCREEN_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vexxscreen")
_SCREEN_SLOT = threading.BoundedSemaphore(1)


def _sintetizar_isolado(fn, owner: str, *args):
    db = open_db(database_path())
    try:
        return fn(db, *args)
    except Exception as exc:
        log.warning("síntese paralela falhou (%s)", type(exc).__name__)
        return ""
    finally:
        try:
            db.close()
        except Exception:
            pass

SYSTEM_PADRAO = ("Você é o assistente pessoal do usuário no Vexx AI. "
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
                 "(JSON {version:'JULIA-ui-message/v1',blocks:[{type:'ui',component,props}]}). "
                 "Pergunta simples → só texto, sem interface.")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def database_path() -> Path:
    return Path(os.environ.get("JULIA_SQLITE_PATH", str(Path.home() / ".JULIA-mobile" / "memory.sqlite3")))


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


def _migrar_ai_requests_por_dono(db) -> None:
    """ai_requests passa de PK(user_message_id) global para PK(owner_id,
    user_message_id): sem isso, um dono sobrescreve o estado de IA do outro
    (busy/replay vazam entre contas). Preserva dados existentes."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='ai_requests'").fetchone()
    if not sql or not sql[0]:
        return
    if "PRIMARY KEY (owner_id, user_message_id)" in sql[0]:
        return
    db.execute("ALTER TABLE ai_requests RENAME TO ai_requests_antiga")
    db.execute("""CREATE TABLE ai_requests (
        user_message_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL,
        reply_id TEXT, response_text TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local',
        PRIMARY KEY (owner_id, user_message_id)
    )""")
    db.execute("""INSERT OR IGNORE INTO ai_requests
        (user_message_id, conversation_id, model, state, reply_id,
         response_text, error, created_at, updated_at, owner_id)
        SELECT user_message_id, conversation_id, model, state, reply_id,
         response_text, error, created_at, updated_at, owner_id
        FROM ai_requests_antiga""")
    db.execute("DROP TABLE ai_requests_antiga")
    log.info("ai_requests migrada para PK por dono")


def _migrar_messages_por_dono(db) -> None:
    """messages passa de PK(id) global para PK(owner_id, id): sem isso, dois
    donos não podem ter a mesma mensagem (INSERT OR IGNORE descarta a do
    segundo) e o histórico vaza entre contas. Preserva colunas e dados."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='messages'").fetchone()
    if not sql or not sql[0]:
        return
    if "PRIMARY KEY (owner_id, id)" in sql[0]:
        return
    pragma = db.execute("PRAGMA table_info(messages)").fetchall()
    defs, nomes = [], []
    for cid, nome, tipo, nn, dflt, pk in pragma:
        nomes.append(nome)
        pedaco = f"{nome} {tipo or 'TEXT'}"
        if nn and nome != "id":
            pedaco += " NOT NULL"
        if dflt is not None:
            pedaco += f" DEFAULT {dflt}"
        defs.append(pedaco)
    defs.append("PRIMARY KEY (owner_id, id)")
    db.execute("ALTER TABLE messages RENAME TO messages_antiga")
    db.execute(f"CREATE TABLE messages ({', '.join(defs)})")
    cols = ", ".join(nomes)
    db.execute(f"INSERT OR IGNORE INTO messages ({cols}) SELECT {cols} FROM messages_antiga")
    db.execute("DROP TABLE messages_antiga")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_created ON messages(origin, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_conv ON messages(origin, conversation_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id, origin, created_at)")
    log.info("messages migrada para PK por dono")


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
        id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        created_at TEXT NOT NULL, received_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local',
        PRIMARY KEY (owner_id, id)
    )""")
    try:
        db.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe (migração idempotente)
    _ensure_owner_coluna(db, "messages")
    _migrar_messages_por_dono(db)
    db.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
        user_message_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL,
        reply_id TEXT, response_text TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local',
        PRIMARY KEY (owner_id, user_message_id)
    )""")
    _ensure_owner_coluna(db, "ai_requests")
    _migrar_ai_requests_por_dono(db)
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_created ON messages(origin, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_conv ON messages(origin, conversation_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id, origin, created_at)")
    _migrar_memories_por_dono(db)
    _memoria_v41(db)
    JULIA_auth.criar_tabelas(db)
    remote_access.create_tables(db)
    JULIA_auth.migrar_legado(db)
    learning.criar_tabelas(db)
    research.criar_tabelas(db)
    research_agents.criar_tabelas(db)
    shopping.criar_tabelas(db)
    evgraph.criar_tabelas(db)
    workspace_store.create_tables(db)
    db.execute("""CREATE TABLE IF NOT EXISTS memory_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'chat', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    _ensure_owner_coluna(db, "memory_facts")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memfacts_key ON memory_facts(key, updated_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memfacts_owner ON memory_facts(owner_id, updated_at)")
    docs_agent.criar_tabelas(db)
    files_agent.criar_tabelas(db)
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
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
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
            if workspace_store.chat_deleted(db, owner, conv):
                continue
            existing = db.execute("SELECT conversation_id,role,text,created_at FROM messages "
                                  "WHERE id=? AND owner_id=? AND origin='mobile'", (mid, owner)).fetchone()
            if existing and tuple(existing) != (conv, m["role"], txt, created):
                continue
            db.execute("""INSERT OR IGNORE INTO messages
                (id, conversation_id, origin, role, text, created_at, received_at, owner_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (mid, conv, "mobile", m["role"], txt, created,
                 datetime.now(timezone.utc).isoformat(), owner))
            confirmed.append(mid)
    return confirmed


def list_messages(db, limit=200, owner=DONO_PADRAO, conversation_id="", before=None):
    owner = dono_valido(owner)
    filters, params = "", ["mobile", owner]
    if conversation_id:
        filters += " AND conversation_id=?"
        params.append(conversation_id)
    if before:
        filters += " AND (created_at,id)<(?,?)"
        params.extend(before)
    params.append(min(max(int(limit), 1), 200))
    rows = db.execute("""SELECT id, conversation_id, origin, role, text, created_at,
                                COALESCE(model, '')
                         FROM messages WHERE origin=? AND owner_id=?
                         """ + filters + " ORDER BY created_at DESC, id DESC LIMIT ?", params).fetchall()
    cols = ["id", "conversation_id", "origin", "role", "text", "created_at", "model"]
    return [dict(zip(cols, row)) for row in reversed(rows)]


def ai_config() -> dict:
    return {
        "proxy": os.environ.get("HERMES_PROXY_URL", hermes_bridge.DEFAULT_PROXY_URL),
        "model": os.environ.get("JULIA_AI_MODEL", "qwen2.5-1.5b-instruct"),
        "model_implicit": not bool(os.environ.get("JULIA_AI_MODEL")),
        "fallbacks": _lista_fallbacks(os.environ.get("JULIA_AI_FALLBACKS", "")),
        "system": system_with_identity((os.environ.get("JULIA_SYSTEM_PROMPT", "").strip()
                                        or SYSTEM_PADRAO)[:2000]),
        "context": min(max(int(os.environ.get("JULIA_AI_CONTEXT", "12")), 1), 50),
        "max_tokens": min(max(int(os.environ.get("JULIA_AI_MAX_TOKENS", "1500")), 1), 8000),
        "memoria_global": os.environ.get("JULIA_SHARED_MEMORY", "1") == "1",
        "pesquisa_web": os.environ.get("JULIA_WEB_SEARCH", "1") == "1",
    }


def _lista_fallbacks(valor: str) -> list:
    """Modelos alternativos explícitos (máx 4; slugs validados, sem varredura)."""
    out = []
    for parte in (valor or "").split(","):
        slug = parte.strip()[:120]
        if slug and re.fullmatch(r"[A-Za-z0-9_~.][A-Za-z0-9_~.:/-]*", slug) and slug not in out:
            out.append(slug)
    return out[:4]


FALLBACKS_GRATIS_PADRAO = [
    "qwen2.5-1.5b-instruct",
    "vexx-qwen-2.5-3b",
    "meituan/longcat-2.5:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
]

_MODELOS_COOLDOWN = {}


def registrar_cooldown_modelo(model: str, segundos: float = 180.0):
    if model:
        _MODELOS_COOLDOWN[model] = time.monotonic() + segundos


def modelos_tentativa(cfg: dict, preferido: str = "") -> list:
    """[preferido, *fallbacks_configurados, *fallbacks_gratis_padrao] sem duplicar.

    Quando um modelo preferido atinge limite (429) ou fica indisponível,
    ele é colocado em cooldown temporário e o sistema alterna sozinho
    para outro modelo gratuito saudável."""
    agora = time.monotonic()
    primario = (preferido or cfg.get("model", "")).strip()
    candidatos = []
    if primario:
        candidatos.append(primario)
    for fb in cfg.get("fallbacks", []) or []:
        if fb and fb not in candidatos:
            candidatos.append(fb)
    for fb in FALLBACKS_GRATIS_PADRAO:
        if fb and fb not in candidatos:
            candidatos.append(fb)

    if preferido and preferido in candidatos:
        resto = [m for m in candidatos if m != preferido]
        resto_saudaveis = [m for m in resto if _MODELOS_COOLDOWN.get(m, 0) < agora]
        resto_espera = [m for m in resto if _MODELOS_COOLDOWN.get(m, 0) >= agora]
        fila = [preferido] + resto_saudaveis + resto_espera
    else:
        saudaveis = [m for m in candidatos if _MODELOS_COOLDOWN.get(m, 0) < agora]
        em_espera = [m for m in candidatos if _MODELOS_COOLDOWN.get(m, 0) >= agora]
        fila = saudaveis + em_espera if saudaveis else candidatos
    return [m for m in fila if m][:6]


def gerar_texto(cfg: dict, messages: list, preferido: str = "",
                max_tokens: int = 0, timeout: float = 60.0) -> dict:
    """Chamada LLM com fallback (leitura sem efeitos; mesma reply_id fora daqui).

    Modelos "provedor/modelo" roteiam para providers.py; IDs simples usam o
    Hermes (legado)."""
    fila = modelos_tentativa(cfg, preferido)
    lookup_started = time.monotonic()
    fila = inference_status.effective_models(cfg, fila, timeout=min(2, timeout))
    timeout = max(.1, timeout - (time.monotonic() - lookup_started))
    if any(providers.dividir(m)[0] != "hermes" for m in fila):
        return providers.tentar_modelos(
            fila, messages, timeout_por_tentativa=timeout,
            max_tokens=max_tokens or cfg["max_tokens"],
            proxy=cfg.get("proxy") or "")
    structured = {}
    if cfg.get('_research_response_format') and len(fila) == 1:
        import research_output
        started = time.monotonic()
        if research_output.supported(cfg['proxy'], fila[0], timeout=timeout):
            structured['response_format'] = cfg['_research_response_format']
            effort = research_output.reasoning_effort(cfg['proxy'], fila[0])
            if effort:structured['reasoning_effort'] = effort
        timeout = max(.1, timeout-(time.monotonic()-started))
    attempt_started=time.monotonic()
    try:
        result = hermes_bridge.tentar_modelos(
            cfg["proxy"], fila, messages,
            timeout_por_tentativa=timeout, max_tokens=max_tokens or cfg["max_tokens"], **structured)
    except hermes_bridge.BridgeErro as exc:
        metadata=getattr(exc,'response_metadata',{})
        remaining=timeout-(time.monotonic()-attempt_started)
        if not (structured and exc.codigo=='vazia' and metadata.get('finish_reason')=='stop'
                and remaining>=5):
            raise
        # Some gateways advertise strict JSON but return null content. Retry
        # once on the same model, retaining declared reasoning effort and all
        # downstream JSON/evidence validation, within the original deadline.
        result=hermes_bridge.tentar_modelos(cfg['proxy'],fila,messages,
            timeout_por_tentativa=remaining,max_tokens=max_tokens or cfg['max_tokens'],
            **({'reasoning_effort':structured['reasoning_effort']} if structured.get('reasoning_effort') else {}))
        result['structured_output_fallback']='empty_content'
    if structured:result['structured_output_requested'] = True
    return result


def gerar_stream(cfg: dict, modelos: list, messages: list, emitir,
                 deve_parar=None, max_tokens: int = 0) -> dict:
    """Stream com fallback; roteia multi-provedor quando houver prefixo."""
    if not (deve_parar and deve_parar()):
        modelos = inference_status.effective_models(cfg, modelos)
    if any(providers.dividir(m)[0] != "hermes" for m in modelos):
        return providers.chat_stream_fb(
            modelos, messages, emitir, deve_parar,
            max_tokens=max_tokens or cfg["max_tokens"],
            proxy=cfg.get("proxy") or "")
    return hermes_bridge.chat_stream_fb(
        cfg["proxy"], modelos, messages, emitir,
        deve_parar=deve_parar, max_tokens=max_tokens or cfg["max_tokens"])
