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
import remoto
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

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


def open_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
        created_at TEXT NOT NULL, received_at TEXT NOT NULL
    )""")
    try:
        db.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe (migração idempotente)
    db.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
        user_message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        model TEXT NOT NULL, state TEXT NOT NULL,
        reply_id TEXT, response_text TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_created ON messages(origin, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mobile_messages_conv ON messages(origin, conversation_id, created_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS memories (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS memory_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'chat', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memfacts_key ON memory_facts(key, updated_at)")
    docs_agent.criar_tabelas(db)
    db.execute("""CREATE TABLE IF NOT EXISTS ui_state (
        k TEXT PRIMARY KEY, message_id TEXT NOT NULL, slot TEXT NOT NULL,
        state TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_uistate_msg ON ui_state(message_id)")
    db.commit()
    return db


def persist_messages(db, rows):
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
                (id, conversation_id, origin, role, text, created_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (mid, conv, "mobile", m["role"], txt, created,
                 datetime.now(timezone.utc).isoformat()))
            confirmed.append(mid)
    return confirmed


def list_messages(db, limit=200):
    rows = db.execute("""SELECT id, conversation_id, origin, role, text, created_at,
                                COALESCE(model, '')
                         FROM messages WHERE origin=? ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", min(max(int(limit), 1), 200))).fetchall()
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
def salvar_fatos(db, texto: str) -> None:
    """Heurística simples: 'lembre-se que ...', 'meu nome é ...' etc viram memories."""
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
                    db.execute("""INSERT INTO memories (key, value, updated_at)
                        VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value, updated_at=excluded.updated_at""",
                        (chave, valor, agora_iso()))
                    achou = True
    if achou:
        log.info("memória atualizada a partir da conversa")


def ler_memorias(db) -> list:
    try:
        rows = db.execute("SELECT key, value FROM memories ORDER BY updated_at DESC LIMIT 20").fetchall()
    except Exception:
        return []
    return [{"key": k, "value": v} for k, v in rows if v]


def memoria_global(db, conversation_id: str, limite_outras: int = 8) -> list:
    """Últimas mensagens de OUTRAS conversas + fatos salvos, para injetar no prompt."""
    try:
        rows = db.execute("""SELECT conversation_id, role, text FROM messages
                             WHERE origin='mobile' AND conversation_id != ?
                             ORDER BY created_at DESC, id DESC LIMIT ?""",
                          (conversation_id, limite_outras)).fetchall()
    except Exception:
        rows = []
    blocos = []
    for conv, role, text in reversed(rows):
        if role in ("user", "assistant") and text:
            blocos.append(f"[{conv[-6:]}|{role}]: {(text or '')[:300]}")
    fatos = ler_memorias(db)
    if fatos:
        blocos.append("FATOS SALVOS: " + "; ".join(f"{f['key']}={f['value'][:150]}" for f in fatos))
    return blocos


def guardar_fato(db, chave: str, valor: str, origem: str = "chat") -> None:
    """Guarda fato aprendido: chave resumida + histórico para evolução."""
    chave = re.sub(r"\s+", "_", (chave or "").strip().lower())[:60].strip("_") or "fato"
    valor = (valor or "").strip()[:500]
    if not valor:
        return
    with db:
        db.execute("""INSERT INTO memories (key, value, updated_at)
            VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET
            value=excluded.value, updated_at=excluded.updated_at""",
            (chave, valor, agora_iso()))
        db.execute("""INSERT INTO memory_facts (key, value, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)""",
            (chave, valor, origem, agora_iso(), agora_iso()))
    log.info("memória aprendeu: %s", chave)


def memorias_relevantes(db, pergunta: str, k: int = 8) -> list:
    """Fatos ordenados por relevância (palavras em comum) + recência."""
    try:
        rows = db.execute("SELECT key, value, updated_at FROM memories").fetchall()
    except Exception:
        return []
    toks_q = set(re.findall(r"[a-zà-ú0-9]{3,}", (pergunta or "").lower()))
    scored = []
    for chave, valor, upd in rows:
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", f"{chave} {valor}".lower()))
        inter = toks_q & toks if toks_q else set()
        scored.append((len(inter) * 2 + (1 if chave in ("nome", "foco") else 0), upd or "", chave, valor))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    if toks_q:
        relevantes = [s for s in scored if s[0] > 0][:k] or scored[:2]
    else:
        relevantes = scored[:k]
    return [{"key": c, "value": v} for _, _, c, v in relevantes]


def interpretar_comando_memoria(db, texto: str):
    """Comandos diretos de memória. Retorna resposta pronta ou None."""
    t = (texto or "").strip().lower()
    if re.search(r"o que (você|voce) (sabe|lembra|conhece) sobre mim", t) or \
       re.search(r"(mostre|mostra|liste|lista).{0,20}mem[óo]ria", t) or \
       t in ("o que você sabe?", "o que voce sabe?"):
        fatos = ler_memorias(db)
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
        rows = db.execute("SELECT key, value FROM memories").fetchall()
        melhor, melhor_n = None, 0
        for chave, valor in rows:
            n = len(toks & set(re.findall(r"[a-zà-ú0-9]{3,}", f"{chave} {valor}".lower())))
            if n > melhor_n:
                melhor, melhor_n = chave, n
        if melhor and melhor_n > 0:
            with db:
                db.execute("DELETE FROM memories WHERE key=?", (melhor,))
            return (f"Esqueci **{melhor}**. 🧹", "mem_esquecer")
        return ("Não encontrei isso na minha memória. Diga \"o que você sabe sobre mim\" para ver a lista.", "mem_nada")
    return None


def aprender_com_conversa(db_path: Path, cfg: dict, texto_usuario: str, texto_resposta: str) -> None:
    """Thread em 2º plano: pede ao LLM fatos novos (JSON) e guarda. Nunca bloqueia o chat."""
    try:
        if len(texto_usuario or "") < 20:
            return
        import json as _json
        prompt = ("Extraia FATOS duradouros sobre o usuário desta conversa "
                  "(nome, profissão, projetos, preferências, metas, contexto de vida). "
                  "Ignore o assunto pontual da pergunta. Responda SÓ com JSON: "
                  "[{\"key\": \"curta_em_snake\", \"value\": \"...\"}] ou [].\n\n"
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
                if isinstance(f, dict) and f.get("value"):
                    guardar_fato(db, str(f.get("key", "fato"))[:60], str(f.get("value"))[:500], "llm")
            n = db.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            if n > 60:
                _consolidar_memorias(db, cfg)
        finally:
            db.close()
    except Exception as exc:
        log.warning("aprendizado em 2º plano falhou: %s", exc)


def _consolidar_memorias(db, cfg: dict) -> None:
    """Junta fatos antigos/duplicados num conjunto enxuto (evolução da memória)."""
    try:
        rows = db.execute("SELECT key, value FROM memory_facts ORDER BY created_at DESC LIMIT 60").fetchall()
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
            db.execute("DELETE FROM memories")
            db.execute("DELETE FROM memory_facts")
            for f in novos[:25]:
                if isinstance(f, dict) and f.get("value"):
                    chave = re.sub(r"\s+", "_", str(f.get("key", "fato")).strip().lower())[:60] or "fato"
                    db.execute("INSERT INTO memories (key, value, updated_at) VALUES (?, ?, ?)",
                               (chave, str(f["value"])[:500], agora_iso()))
        log.info("memória consolidada: %d fatos", len(novos))
    except Exception as exc:
        log.warning("consolidação falhou: %s", exc)


def doc_mencionado(db, texto: str, conversation_id: str) -> str:
    """Acha documento citado pelo nome ou o mais recente da conversa."""
    t = (texto or "").lower()
    try:
        docs = docs_agent.listar_documentos(db, 50)
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


def listar_conversas(db, limite: int = 100) -> list:
    try:
        rows = db.execute("""SELECT conversation_id, COUNT(*), MAX(created_at),
                             substr(MAX(created_at || ' ' || text), 22, 80)
                             FROM messages WHERE origin='mobile'
                             GROUP BY conversation_id
                             ORDER BY MAX(created_at) DESC LIMIT ?""",
                          (min(max(int(limite), 1), 200),)).fetchall()
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


def ai_montar_mensagens(db, conversation_id: str, cfg: dict, texto_usuario: str) -> tuple:
    """Monta o prompt com contexto local + memória global + pesquisa. Retorna (messages, extras)."""
    memoria_on = cfg.get("memoria_global", True)
    historico = contexto_conversa(db, conversation_id, cfg["context"])
    extras = {"fontes": [], "memoria_usada": False, "doc_id": ""}
    partes_sistema = [cfg["system"]]
    if memoria_on:
        rel = memorias_relevantes(db, texto_usuario)
        recentes = []
        if not rel:
            # sem pergunta específica: leva um resumo do que sabe (nome/foco primeiro)
            rel = memorias_relevantes(db, "", k=4)
        if rel:
            extras["memoria_usada"] = True
            partes_sistema.append("O QUE VOCÊ SABE SOBRE O USUÁRIO (use naturalmente, sem citar que é memória):\n" +
                                  "\n".join(f"- {f['key']}: {f['value'][:200]}" for f in rel))
        blocos = memoria_global(db, conversation_id, 6)
        if blocos:
            partes_sistema.append("CONTEXTO RECENTE DE OUTRAS CONVERSAS (só se for relevante):\n" + "\n".join(blocos[-6:]))
    # JDUI: impõe interface declarativa quando pedida ou muito útil.
    comp_sugerido = JuliaPresentationEngine.sugerir(texto_usuario)
    if comp_sugerido:
        partes_sistema.append(
            "PEDIDO DE INTERFACE INTERATIVA (componente: " + comp_sugerido + "). " + JDUI_CATALOGO)
    # Documentos: se a pergunta cita um doc ou fala de documento, injeta trechos
    doc_id = doc_mencionado(db, texto_usuario, conversation_id)
    if doc_id:
        extras["doc_id"] = doc_id
        trechos = docs_agent.trechos_relevantes(db, texto_usuario, doc_id, k=4)
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


def contexto_conversa(db, conversation_id: str, limite: int) -> list:
    rows = db.execute("""SELECT role, text FROM messages
                         WHERE origin=? AND conversation_id=?
                         ORDER BY created_at DESC, id DESC LIMIT ?""",
                      ("mobile", conversation_id, limite)).fetchall()
    limpos = []
    for role, text in reversed(rows):
        if role not in ("user", "assistant"):
            continue
        t = re.sub(r"```jdui[\s\S]*?(```|$)", "[interface]", text or "", flags=re.IGNORECASE)
        limpos.append({"role": role, "content": t[:2000]})
    return limpos


def ai_estado(db, user_message_id: str):
    row = db.execute("SELECT state, reply_id, response_text, error, model FROM ai_requests "
                     "WHERE user_message_id=?", (user_message_id,)).fetchone()
    if not row:
        return None
    return {"state": row[0], "reply_id": row[1], "response_text": row[2],
            "error": row[3], "model": row[4]}


def ai_marcar(db, user_message_id, conversation_id, model, state,
              reply_id=None, response_text=None, error=None):
    with db:
        db.execute("""INSERT INTO ai_requests
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_message_id) DO UPDATE SET state=excluded.state,
             reply_id=excluded.reply_id, response_text=excluded.response_text,
             error=excluded.error, updated_at=excluded.updated_at""",
            (user_message_id, conversation_id, model, state, reply_id,
             response_text, error, agora_iso(), agora_iso()))


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
    previo = ai_estado(db, mid)
    if previo and previo["state"] == "completed":
        return {"replay": True, "reply_id": previo["reply_id"],
                "response_text": previo["response_text"], "model": previo["model"]}
    if previo and previo["state"] == "processing":
        return {"busy": True}
    row = db.execute("SELECT text FROM messages WHERE id=? AND origin='mobile' "
                     "AND role='user' AND conversation_id=?", (mid, conv)).fetchone()
    if not row:
        return {"error": "Mensagem do usuário não encontrada. Sincronize primeiro.",
                "codigo": "sem_mensagem"}
    try:
        salvar_fatos(db, row[0])
    except Exception:
        pass
    mem_flag = payload.get("memory", payload.get("memoria_global", None))
    memoria_on = cfg.get("memoria_global", True) if mem_flag is None else (str(mem_flag) == "1")
    ai_marcar(db, mid, conv, modelo, "queued")
    return {"user_text": row[0], "model": modelo,
            "reply_id": f"{mid}-r1", "conversation_id": conv,
            "memoria_global": memoria_on}


def ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto) -> None:
    with db:
        db.execute("""INSERT OR IGNORE INTO messages
            (id, conversation_id, origin, role, text, created_at, received_at, model)
            VALUES (?, ?, 'mobile', 'assistant', ?, ?, ?, ?)""",
            (reply_id, conv, texto, agora_iso(), agora_iso(), modelo))
    ai_marcar(db, mid, conv, modelo, "completed",
              reply_id=reply_id, response_text=texto)


def ai_resposta_direta(db, mid, conv, modelo, reply_id, texto) -> dict:
    """Resposta sem LLM (comandos de memória). Salva e marca como completa."""
    ai_marcar(db, mid, conv, modelo, "processing")
    ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto)
    return {"reply_id": reply_id, "response_text": texto, "model": modelo}


def ai_completa(db, payload: dict, cfg: dict) -> dict:
    prep = ai_preparar(db, payload, cfg)
    if "error" in prep or "replay" in prep or "busy" in prep:
        return prep
    mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
    cmd = interpretar_comando_memoria(db, prep.get("user_text", ""))
    if cmd:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0])
    ai_marcar(db, mid, conv, modelo, "processing")
    cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
    messages, extras = ai_montar_mensagens(db, conv, cfg_eff, prep.get("user_text", ""))
    try:
        res = hermes_bridge.chat_complete(cfg["proxy"], modelo, messages,
                                          max_tokens=cfg["max_tokens"])
    except hermes_bridge.BridgeErro as exc:
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc))
        return {"error": str(exc), "codigo": exc.codigo}
    texto = anexar_fontes(res["texto"], extras["fontes"], intencao_imagem(prep.get("user_text", "")))
    texto, blocos_jdui, erros_jdui = jdui.normalizar(texto)
    if erros_jdui:
        log.warning("JDUI descartado na msg %s: %s", mid, "; ".join(erros_jdui[:3]))
    ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto)
    if len(prep.get("user_text", "")) >= 20:
        threading.Thread(target=aprender_com_conversa,
                         args=(database_path(), dict(cfg), prep["user_text"], texto),
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
        cmd = interpretar_comando_memoria(db, prep.get("user_text", ""))
        if cmd:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0])
            try:
                with sessao.lock_envio:
                    websocket.send(json.dumps({"request_id": request_id, "type": "ai_done",
                                               "reply_id": direta["reply_id"],
                                               "response_text": direta["response_text"],
                                               "model": modelo}, ensure_ascii=False))
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        ai_marcar(db, mid, conv, modelo, "processing")
        cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
        messages, extras = ai_montar_mensagens(db, conv, cfg_eff, prep.get("user_text", ""))

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
            ai_marcar(db, mid, conv, modelo, "failed", error=str(exc))
            try:
                enviar({"request_id": request_id, "type": "ai_error",
                        "error": str(exc), "codigo": exc.codigo})
            except hermes_bridge.BridgeErro:
                pass  # relay fora do ar: celular verá timeout + retry
            return
        if res.get("cancelada"):
            ai_marcar(db, mid, conv, modelo, "cancelled",
                      reply_id=prep["reply_id"], response_text=res["texto"])
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
        if texto_final != res["texto"]:
            # envia o complemento (fontes/imagem) como deltas finais para TTFT não degradar
            try:
                emitir(res.get("seq", 9999) if isinstance(res.get("seq"), int) else 9999,
                       texto_final[len(res["texto"]):])
            except Exception:
                pass
        ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto_final)
        if len(prep.get("user_text", "")) >= 20:
            threading.Thread(target=aprender_com_conversa,
                             args=(db_path, dict(cfg_eff), prep["user_text"], texto_final),
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
                    if req.get("type") == "sync":
                        confirmed_ids = persist_messages(db, req.get("messages", []))
                        reply = {"request_id": request_id, "type": "ack", "confirmed_ids": confirmed_ids}
                    elif req.get("type") == "list":
                        reply = {"request_id": request_id, "type": "history", "messages": list_messages(db, req.get("limit", 200))}
                    elif req.get("type") == "conversations":
                        reply = {"request_id": request_id, "type": "conversations",
                                 "conversations": listar_conversas(db, req.get("limit", 100))}
                    elif req.get("type") == "doc_upload":
                        try:
                            import base64 as _b64
                            raw = _b64.b64decode(req.get("data_b64", ""), validate=True)
                            meta = docs_agent.salvar_documento(
                                db, req.get("name", "arquivo"),
                                raw, req.get("conversation_id", "geral"))
                            reply = {"request_id": request_id, "type": "doc_uploaded", **meta}
                        except Exception as exc:
                            codigo = getattr(exc, "codigo", "erro")
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300], "codigo": codigo}
                    elif req.get("type") == "doc_list":
                        reply = {"request_id": request_id, "type": "doc_list",
                                 "documents": docs_agent.listar_documentos(db, req.get("limit", 50))}
                    elif req.get("type") == "doc_resumo":
                        try:
                            texto = docs_agent.resumir_documento(db, cfg, req.get("doc_id", ""))
                            reply = {"request_id": request_id, "type": "doc_resumo",
                                     "doc_id": req.get("doc_id", ""), "resumo": texto}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "doc_topicos":
                        try:
                            texto = docs_agent.topicos_documento(db, cfg, req.get("doc_id", ""))
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
                                    db.execute("""INSERT INTO ui_state
                                        (k, message_id, slot, state, updated_at)
                                        VALUES (?, ?, ?, ?, ?)
                                        ON CONFLICT(k) DO UPDATE SET
                                        state=excluded.state, updated_at=excluded.updated_at""",
                                        (k, str(s.get("message_id", ""))[:100],
                                         str(s.get("slot", ""))[:40], s["state"],
                                         str(s.get("updated_at", agora_iso()))[:48]))
                                    salvos += 1
                                except Exception:
                                    continue
                        reply = {"request_id": request_id, "type": "ui_state_saved",
                                 "saved": salvos}
                    elif req.get("type") == "ui_state_list":
                        rows = db.execute("SELECT k, message_id, slot, state, updated_at "
                                          "FROM ui_state ORDER BY updated_at DESC LIMIT 500").fetchall()
                        reply = {"request_id": request_id, "type": "ui_state_list",
                                 "states": [{"k": k, "message_id": m, "slot": s,
                                             "state": st, "updated_at": u}
                                            for k, m, s, st, u in rows]}
                    elif req.get("type") == "mem_list":
                        rows = db.execute("SELECT key, value, updated_at FROM memories "
                                          "ORDER BY updated_at DESC LIMIT 100").fetchall()
                        reply = {"request_id": request_id, "type": "mem_list",
                                 "memories": [{"key": k, "value": v, "updated_at": u}
                                              for k, v, u in rows]}
                    elif req.get("type") == "mem_forget":
                        with db:
                            db.execute("DELETE FROM memories WHERE key=?", (req.get("key", ""),))
                        reply = {"request_id": request_id, "type": "mem_forgotten",
                                 "key": req.get("key", "")}
                    elif req.get("type") == "ai":
                        res = ai_completa(db, req, cfg)
                        reply = {"request_id": request_id, "type": "ai_done", **res}
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
        except (ConnectionClosed, ConnectionError, OSError, TimeoutError, ValueError) as exc:
            log.warning("Conexão interrompida (%s). Reconectando em %ss", type(exc).__name__, pause)
        except KeyboardInterrupt:
            break
        time.sleep(pause)
        pause = min(60, pause * 2)
    db.close()


if __name__ == "__main__":
    run()
