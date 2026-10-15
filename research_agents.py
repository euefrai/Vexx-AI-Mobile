"""JuliaResearchAgentSystem (V4.5) — orquestração determinística de pesquisa.

Papéis como FUNÇÕES reutilizáveis sobre estado persistido (não instâncias
de modelo): planejador, buscadores, analista, verificador, sintetizador e
auditor. Tudo auditável: cada passo emite evento, persiste e respeita
orçamento. LLM só redige (indisponível hoje → síntese extrativa honesta);
nunca decide fatos.

Tabelas (owner em tudo; PC é o definitivo):
- research_jobs: o plano + estado (checkpoint = a própria linha).
- research_events: telemetria real (seq por job).
- evidence: registros de evidência com status de verificação.
"""
import hashlib
import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

import research

MODOS = {
    "rapida": {"buscas": 2, "paginas": 3, "timeout_s": 30, "subs": 1, "profundidade": 1},
    "pro": {"buscas": 4, "paginas": 6, "timeout_s": 60, "subs": 3, "profundidade": 2},
    "profunda": {"buscas": 8, "paginas": 12, "timeout_s": 120, "subs": 4, "profundidade": 2},
    "investigativa": {"buscas": 12, "paginas": 20, "timeout_s": 300, "subs": 6,
                      "profundidade": 3},
}

STATUS_JOB = ("criada", "em_andamento", "pausada", "concluida", "interrompida",
              "falhou", "cancelada")
STATUS_EVIDENCIA = ("recuperada", "encontrada", "inacessivel", "nao_sustenta",
                    "contradiz", "parcial")
ESTADOS_CLAIM = ("SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED",
                 "INSUFFICIENT_EVIDENCE")

MODO_AUTO = (
    (("investiga", "hipótese", "hipotese", "a fundo", "tese"), "investigativa"),
    (("aprofundad", "dossiê", "dossie", "relatório completo", "relatorio completo",
       "verifique se", "é verdade", "e verdade"), "profunda"),
    (("compare", "comparar", "prós e contras", "pros e contras",
       "qual melhor", "versus"), "pro"),
)


class AgentErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS research_jobs (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        conv TEXT NOT NULL DEFAULT '', modo TEXT NOT NULL DEFAULT 'pro',
        objetivo TEXT NOT NULL DEFAULT '', plano TEXT NOT NULL DEFAULT '[]',
        plano_versao INT NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'criada',
        orcamento TEXT NOT NULL DEFAULT '{}', usados TEXT NOT NULL DEFAULT '{}',
        achados TEXT NOT NULL DEFAULT '[]', pendencias TEXT NOT NULL DEFAULT '[]',
        erros TEXT NOT NULL DEFAULT '[]', criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS research_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', seq INT NOT NULL DEFAULT 0,
        ts TEXT NOT NULL, agente TEXT NOT NULL DEFAULT '',
        tipo TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
        descricao TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL DEFAULT '{}',
        UNIQUE (job_id, seq))""")
    db.execute("""CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', fonte_id TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '', titulo TEXT NOT NULL DEFAULT '',
        dominio TEXT NOT NULL DEFAULT '', acessado_em TEXT NOT NULL DEFAULT '',
        publicado_em TEXT NOT NULL DEFAULT '', trecho TEXT NOT NULL DEFAULT '',
        localizacao TEXT NOT NULL DEFAULT '', afirmacao TEXT NOT NULL DEFAULT '',
        relacao TEXT NOT NULL DEFAULT 'cita', status TEXT NOT NULL DEFAULT 'recuperada',
        original TEXT NOT NULL DEFAULT '')""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner ON research_jobs(owner_id, criado_em)")
    for _col, _ddl in (("investigacoes", "TEXT NOT NULL DEFAULT '[]'"),
                       ("auditoria", "TEXT NOT NULL DEFAULT '{}'"),
                       ("ajustes", "TEXT NOT NULL DEFAULT '{}'")):
        try:
            cols = [c[1] for c in db.execute("PRAGMA table_info(research_jobs)").fetchall()]
            if _col not in cols:
                db.execute(f"ALTER TABLE research_jobs ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_job ON research_events(job_id, seq)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ev_job ON evidence(job_id, status)")
    db.commit()


def selecionar_modo(texto: str, manual: str = "") -> str:
    manual = (manual or "").lower()
    if manual in MODOS:
        return manual
    t = (texto or "").lower()
    for chaves, modo in MODO_AUTO:
        if any(k in t for k in chaves):
            return modo
    return "rapida" if len(t) < 120 else "pro"


# ── Eventos (telemetria real: só o que de fato aconteceu) ────────────
def emitir(db, job_id: str, owner: str, agente: str, tipo: str, status: str = "ok",
           descricao: str = "", meta: dict = None) -> dict:
    row = db.execute("SELECT COALESCE(MAX(seq), 0) FROM research_events WHERE job_id=?",
                     (job_id,)).fetchone()
    ev = {"job_id": job_id, "seq": (row[0] or 0) + 1, "ts": agora_iso(),
          "agente": agente[:40], "tipo": tipo[:40], "status": status[:20],
          "descricao": descricao[:280], "meta": meta or {}}
    with db:
        db.execute("INSERT INTO research_events (job_id, owner_id, seq, ts, agente, tipo,"
                   " status, descricao, meta) VALUES (?,?,?,?,?,?,?,?,?)",
                   (job_id, owner, ev["seq"], ev["ts"], ev["agente"], ev["tipo"],
                    ev["status"], ev["descricao"],
                    json.dumps(ev["meta"], ensure_ascii=False)[:4000]))
    return ev


def eventos_desde(db, owner: str, job_id: str, apos_seq: int = 0, limite: int = 200) -> list:
    rows = db.execute("SELECT seq, ts, agente, tipo, status, descricao, meta FROM research_events "
                      "WHERE job_id=? AND owner_id=? AND seq>? ORDER BY seq LIMIT ?",
                      (job_id, owner, apos_seq, max(1, min(limite, 500)))).fetchall()
    return [{"seq": r[0], "ts": r[1], "agente": r[2], "tipo": r[3], "status": r[4],
             "descricao": r[5], "meta": json.loads(r[6] or "{}")} for r in rows]


# ── Jobs (checkpoint = a linha; sobrevive a reinício) ───────────────
def _nid(prefixo: str) -> str:
    import secrets as _s
    return f"{prefixo}-{_s.token_hex(6)}"


def criar_job(db, owner: str, objetivo: str, conv: str = "", modo: str = "",
              manual: str = "") -> dict:
    objetivo = str(objetivo or "")[:500]
    if len(objetivo) < 3:
        raise AgentErro("objetivo curto demais", "objetivo")
    modo = selecionar_modo(objetivo, manual or modo)
    job = {"id": _nid("rj"), "owner": owner, "conv": conv or "", "modo": modo,
           "objetivo": objetivo, "plano": [], "plano_versao": 1, "status": "criada",
           "orcamento": dict(MODOS[modo]), "usados": {"buscas": 0, "paginas": 0},
           "achados": [], "pendencias": [], "erros": [], "investigacoes": [],
           "auditoria": {}, "ajustes": {"restricoes": [], "prioridades": [], "metricas": []}}
    with db:
        db.execute("INSERT INTO research_jobs (id, owner_id, conv, modo, objetivo, plano,"
                   " plano_versao, status, orcamento, usados, achados, pendencias, erros,"
                   " criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job["id"], owner, job["conv"], modo, objetivo, "[]", 1, "criada",
                    json.dumps(job["orcamento"]), json.dumps(job["usados"]), "[]", "[]", "[]",
                    agora_iso(), agora_iso()))
    emitir(db, job["id"], owner, "orchestrator", "research_created", "ok",
           f"Pesquisa criada (modo {modo}).", {"modo": modo})
    return job


def carregar_job(db, owner: str, job_id: str) -> dict:
    row = db.execute("SELECT id, conv, modo, objetivo, plano, plano_versao, status, orcamento,"
                     " usados, achados, pendencias, erros, criado_em, atualizado_em,"
                     " COALESCE(investigacoes, '[]'), COALESCE(auditoria, '{}'),"
                     " COALESCE(ajustes, '{}')"
                     " FROM research_jobs WHERE id=? AND owner_id=?", (job_id, owner)).fetchone()
    if not row:
        raise AgentErro("pesquisa não encontrada", "ausente")
    try:
        return {"id": row[0], "owner": owner, "conv": row[1], "modo": row[2], "objetivo": row[3],
                "plano": json.loads(row[4] or "[]"), "plano_versao": row[5],
                "status": row[6], "orcamento": json.loads(row[7] or "{}"),
                "usados": json.loads(row[8] or "{}"), "achados": json.loads(row[9] or "[]"),
                "pendencias": json.loads(row[10] or "[]"), "erros": json.loads(row[11] or "[]"),
                "criado_em": row[12], "atualizado_em": row[13],
                "investigacoes": json.loads(row[14] or "[]"),
                "auditoria": json.loads(row[15] or "{}"),
                "ajustes": json.loads(row[16] or "{}")}
    except (TypeError, ValueError, IndexError) as exc:
        raise AgentErro("pesquisa corrompida", "corrompida") from exc


def salvar_job(db, job: dict) -> None:
    plano_limpo = []
    for s in job["plano"]:
        plano_limpo.append({k: v for k, v in s.items() if not k.startswith("_")})
    with db:
        db.execute("UPDATE research_jobs SET plano=?, plano_versao=?, status=?, orcamento=?,"
                   " usados=?, achados=?, pendencias=?, erros=?, atualizado_em=?,"
                   " investigacoes=?, auditoria=?, ajustes=? WHERE id=? AND owner_id=?",
                   (json.dumps(plano_limpo, ensure_ascii=False)[:60000], job["plano_versao"],
                    job["status"], json.dumps(job["orcamento"], ensure_ascii=False),
                    json.dumps(job["usados"], ensure_ascii=False),
                    json.dumps(job["achados"], ensure_ascii=False)[:60000],
                    json.dumps(job["pendencias"], ensure_ascii=False)[:20000],
                    json.dumps(job["erros"], ensure_ascii=False)[:20000],
                    agora_iso(),
                    json.dumps(job.get("investigacoes", []), ensure_ascii=False)[:20000],
                    json.dumps(job.get("auditoria", {}), ensure_ascii=False)[:8000],
                    json.dumps(job.get("ajustes", {}), ensure_ascii=False)[:8000],
                    job["id"], job["owner"]))


def listar_jobs(db, owner: str, limite: int = 20) -> list:
    rows = db.execute("SELECT id, conv, modo, objetivo, status, criado_em, atualizado_em"
                      " FROM research_jobs WHERE owner_id=? ORDER BY criado_em DESC LIMIT ?",
                      (owner, max(1, min(limite, 100)))).fetchall()
    return [{"id": r[0], "conv": r[1], "modo": r[2], "objetivo": r[3][:120],
             "status": r[4], "criado_em": r[5], "atualizado_em": r[6]} for r in rows]


def job_ativo(db, owner: str):
    row = db.execute("SELECT id FROM research_jobs WHERE owner_id=? AND status='em_andamento'"
                     " ORDER BY criado_em DESC LIMIT 1", (owner,)).fetchone()
    return row[0] if row else None


# ── Planejador (determinístico; replaneja sem repetir concluídas) ────
def montar_plano(db, job: dict) -> dict:
    """Etapas por subpergunta: busca → ler → analisar; depois verificar →
    sintetizar → auditar. Idempotente: preserva feitas."""
    subs = research.dividir_subconsultas(job["objetivo"],
                                         job["orcamento"].get("subs", 3)) or [job["objetivo"][:120]]
    feitas = { (s.get("tipo"), s.get("alvo")) for s in job["plano"] if s.get("status") == "feita" }
    plano, n = [], 0
    for sub in subs:
        for tipo in ("busca", "ler", "analisar"):
            n += 1
            chave = (tipo, sub)
            plano.append({"id": f"p{n}", "tipo": tipo, "alvo": sub,
                          "status": "feita" if chave in feitas else "pendente",
                          "tentativas": 0})
    for tipo in ("verificar", "sintetizar", "auditar"):
        n += 1
        chave = (tipo, "")
        plano.append({"id": f"p{n}", "tipo": tipo, "alvo": "",
                      "status": "feita" if chave in feitas else "pendente", "tentativas": 0})
    job["plano"] = plano
    job["plano_versao"] += 1
    salvar_job(db, job)
    emitir(db, job["id"], job["owner"], "orchestrator", "plan_created", "ok",
           f"Plano v{job['plano_versao']}: {len(subs)} frentes, {len(plano)} etapas.",
           {"subs": subs})
    return job


def replanejar(db, job: dict, lacunas: list) -> dict:
    """1 rodada extra: nova busca por lacuna + releitura (sem repetir feitas)."""
    if job["usados"].get("replans", 0) >= 1:
        return job
    feitas = {(s.get("tipo"), s.get("alvo")) for s in job["plano"] if s.get("status") != "pendente"}
    novas = 0
    feitos_fu = set(job["usados"].get("follow_ups", []))
    for inv in job.get("investigacoes") or []:
        for q in (inv.get("follow_up") or [])[:2]:
            alvo = str(q)[:120]
            if ("busca", alvo) in feitas or alvo in feitos_fu:
                continue
            job["plano"].append({"id": f"p{len(job['plano']) + 1}", "tipo": "busca",
                                 "alvo": alvo, "status": "pendente", "tentativas": 0,
                                 "motivo": "lacuna de investigação"})
            feitas.add(("busca", alvo))
            feitos_fu.add(alvo)
            novas += 1
            emitir(db, job["id"], job["owner"], "orchestrator", "step_started", "ok",
                   f"Busca motivada por lacuna: {alvo[:80]}", {})
    job["usados"]["follow_ups"] = sorted(feitos_fu)
    for lac in (lacunas or [])[:4]:
        alvo = str(lac)[:120]
        if ("busca", alvo) in feitas:
            continue
        job["plano"].append({"id": f"p{len(job['plano']) + 1}", "tipo": "busca",
                             "alvo": alvo, "status": "pendente", "tentativas": 0})
        for s in job["plano"]:
            if s.get("tipo") == "ler" and s.get("alvo") == alvo and s.get("status") == "feita":
                s["status"] = "pendente"  # relê com os novos achados
        feitas.add(("busca", alvo))
        novas += 1
    if novas:
        job["usados"]["replans"] = job["usados"].get("replans", 0) + 1
        job["plano_versao"] += 1
        salvar_job(db, job)
        emitir(db, job["id"], job["owner"], "orchestrator", "plan_updated", "ok",
               f"Replanejamento v{job['plano_versao']}: +{novas} buscas.", {})
    return job


# ── Provedores (interface + fallback; DDG preservado) ───────────────
class ProvedorBusca:
    nome = "base"

    def buscar(self, consulta: str, limite: int = 6) -> list:
        raise NotImplementedError


class ProvedorDDG(ProvedorBusca):
    nome = "ddg"

    def buscar(self, consulta: str, limite: int = 6) -> list:
        return research.buscar_ddg(consulta, max_resultados=limite) or \
            research.buscar_ddg(consulta, base=research.DDG_LITE, max_resultados=limite)


class ProvedorSearXNG(ProvedorBusca):
    """Instância própria (JULIA_SEARXNG_URL). Sem URL → indisponível (nunca finge)."""
    nome = "searxng"

    def __init__(self, base: str = ""):
        self.base = (base or "").strip().rstrip("/")

    def buscar(self, consulta: str, limite: int = 6) -> list:
        if not self.base:
            raise research.ResearchErro("SearXNG não configurado (JULIA_SEARXNG_URL).",
                                       "indisponivel")
        url = self.base + "/search?" + urllib.parse.urlencode(
            {"q": (consulta or "")[:200], "format": "json", "language": "pt-BR"})
        _, corpo = research.baixar(url, timeout=10.0, max_bytes=512 * 1024)
        try:
            dados = json.loads(corpo)
        except ValueError as exc:
            raise research.ResearchErro("SearXNG fora do formato.", "formato") from exc
        out = []
        for r in (dados.get("results") or [])[:limite]:
            titulo, link = str(r.get("title", ""))[:160], str(r.get("url", ""))[:500]
            if link.startswith("http") and titulo:
                out.append({"titulo": titulo, "url": link,
                            "trecho": str(r.get("content", ""))[:280]})
        return out


def buscar_com_fallback(provedores: list, consulta: str, limite: int = 6) -> tuple:
    """Tenta provedores em ordem; registra falhas; nunca inventa resultado."""
    erros = []
    for p in provedores or []:
        try:
            achados = p.buscar(consulta, limite) or []
            return achados, {"provedor": p.nome, "erros": erros}
        except Exception as exc:
            erros.append({"provedor": getattr(p, "nome", "?"),
                          "codigo": getattr(exc, "codigo", type(exc).__name__)})
    return [], {"provedor": "", "erros": erros}


# ── Evidence Store ──────────────────────────────────────────────────
def registrar_evidencia(db, job: dict, fonte: dict, trecho: str, afirmacao: str = "",
                        relacao: str = "cita", status: str = "recuperada") -> dict:
    if status not in STATUS_EVIDENCIA:
        raise AgentErro("status de evidência inválido", "status")
    eid = _nid("ev")
    row = {"id": eid, "job_id": job["id"], "fonte_id": fonte.get("id", ""),
           "url": (fonte.get("url") or "")[:500], "titulo": (fonte.get("titulo") or "")[:160],
           "dominio": (fonte.get("dominio") or "")[:120],
           "acessado_em": fonte.get("acessado_em") or agora_iso(),
           "publicado_em": (fonte.get("publicado_em") or "")[:32],
           "trecho": (trecho or "")[:2000],
           "localizacao": (fonte.get("localizacao") or "")[:120],
           "afirmacao": (afirmacao or "")[:500], "relacao": relacao[:20], "status": status,
           "original": json.dumps(fonte, ensure_ascii=False)[:8000]}
    with db:
        db.execute("INSERT INTO evidence (id, job_id, owner_id, fonte_id, url, titulo, dominio,"
                   " acessado_em, publicado_em, trecho, localizacao, afirmacao, relacao,"
                   " status, original) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (eid, job["id"], job["owner"], row["fonte_id"], row["url"], row["titulo"],
                    row["dominio"], row["acessado_em"], row["publicado_em"], row["trecho"],
                    row["localizacao"], row["afirmacao"], row["relacao"], status, row["original"]))
    emitir(db, job["id"], job["owner"], "analyst", "evidence_registered", "ok",
           f"Evidência {eid[:11]} de {row['dominio'] or 'fonte'}.", {"status": status})
    return row


def listar_evidencias(db, owner: str, job_id: str, status: str = "") -> list:
    sql = ("SELECT id, fonte_id, url, titulo, dominio, acessado_em, publicado_em, trecho,"
           " afirmacao, relacao, status FROM evidence WHERE job_id=? AND owner_id=?")
    args = [job_id, owner]
    if status:
        sql += " AND status=?"
        args.append(status)
    rows = db.execute(sql + " ORDER BY id", args).fetchall()
    return [{"id": r[0], "fonte_id": r[1], "url": r[2], "titulo": r[3], "dominio": r[4],
             "acessado_em": r[5], "publicado_em": r[6] or "", "trecho": r[7],
             "afirmacao": r[8], "relacao": r[9], "status": r[10]} for r in rows]


def marcar_evidencia(db, job: dict, evidencia_id: str, status: str, afirmacao: str = "") -> None:
    if status not in STATUS_EVIDENCIA:
        raise AgentErro("status de evidência inválido", "status")
    with db:
        n = db.execute("UPDATE evidence SET status=?, afirmacao=? WHERE id=? AND job_id=?"
                       " AND owner_id=?",
                       (status, afirmacao[:500], evidencia_id, job["id"], job["owner"])).rowcount
    if not n:
        raise AgentErro("evidência não encontrada", "ausente")


# ── Agentes (funções puras sobre o estado; sem LLM aqui) ────────────
def _relevancia(alvo: str, trecho: str) -> float:
    def _toks(s):
        return set(re.findall(r"[a-zà-ú]{3,}", (s or "").lower()))
    a, b = _toks(alvo), _toks(trecho)
    if not a:
        return 0.0
    return round(len(a & b) / len(a), 3)


def agente_busca(db, job: dict, etapa: dict, provedores: list, vistas: set) -> list:
    """Search Agent: consultas adaptativas (original + variação sem stopwords)."""
    base = etapa["alvo"]
    variacao = " ".join(w for w in base.split() if len(w) > 4 and w not in ("sobre", "para"))
    consultas = [base] + ([variacao] if variacao and variacao != base else [])
    achados, falhas = [], []
    for q in consultas[:2]:
        if q in vistas:
            continue
        vistas.add(q)
        t0 = time.monotonic()
        encontrados, info = buscar_com_fallback(provedores, q, 6)
        provs = job["usados"].setdefault("provedores", {})
        pm = provs.setdefault(info["provedor"] or "nenhum", {"ok": 0, "falhas": 0, "ms": 0})
        pm["ms"] += int((time.monotonic() - t0) * 1000)
        if encontrados:
            pm["ok"] += 1
        else:
            pm["falhas"] += 1
        emitir(db, job["id"], job["owner"], "search", "search_completed", "ok",
               f"Busca '{q[:60]}': {len(encontrados)} achados.",
               {"provedor": info["provedor"], "falhas": info["erros"]})
        falhas.extend(info["erros"])
        for a in encontrados:
            if a["url"] not in {x["url"] for x in achados}:
                achados.append(a)
    job["usados"]["buscas"] = job["usados"].get("buscas", 0) + len(consultas[:2])
    prios = (job.get("ajustes") or {}).get("prioridades", [])
    if prios:
        achados.sort(key=lambda a: 0 if any(p in (a.get("url", "") or "").lower()
                                            for p in prios) else 1)
    if not achados:
        job["erros"].append(f"busca '{base[:60]}': sem resultados" +
                            (f" ({len(falhas)} falhas de provedor)" if falhas else ""))
        emitir(db, job["id"], job["owner"], "search", "search_completed", "alerta",
               f"Busca '{base[:60]}' sem resultados.", {})
    return achados


def agente_analista(db, job: dict, etapa: dict, achados: list, recuperar_fn=None,
                    teto_paginas: int = 3) -> list:
    """Source Analyst: abre (em paralelo), extrai, pontua, registra (sequencial)."""
    import evidence_graph as _eg
    from concurrent.futures import ThreadPoolExecutor

    def _ler(a):
        if recuperar_fn is not None:
            rec = recuperar_fn(a["url"])
            return {"titulo": rec.get("titulo") or a["titulo"],
                    "texto": (rec.get("texto") or "").strip(), "final": rec.get("final", "")}
        final, pagina = research.baixar(a["url"], timeout=8.0)
        titulo, texto = research.extrair_texto_html(pagina)
        return {"titulo": titulo or a["titulo"], "texto": texto.strip(), "final": final}

    alvos = achados[:teto_paginas]
    baixados: dict = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="julialer") as pool:
        futs = {pool.submit(_ler, a): a for a in alvos}
        for fut, a in futs.items():
            try:
                baixados[a["url"]] = fut.result()
            except research.ResearchErro as exc:
                emitir(db, job["id"], job["owner"], "analyst", "source_opened", "falha",
                       f"Ignorada ({exc.codigo}): {a['url'][:60]}.", {})
            except Exception as exc:
                emitir(db, job["id"], job["owner"], "analyst", "source_opened", "falha",
                       f"Ignorada ({type(exc).__name__}): {a['url'][:60]}.", {})
    evidencias = []
    for a in alvos:
        rec = baixados.get(a["url"])
        if rec is None:
            continue
        texto = rec["texto"]
        if not texto and not a.get("trecho"):
            emitir(db, job["id"], job["owner"], "analyst", "source_opened",
                   "vazia", f"Sem texto: {a['url'][:60]}.", {})
            continue
        fonte = {"id": a.get("id", ""), "url": a["url"], "titulo": rec.get("titulo") or a["titulo"],
                 "dominio": research._dominio(a["url"]), "acessado_em": research.agora_iso()}
        ev = registrar_evidencia(db, job, fonte, texto[:1500] or a.get("trecho", ""))
        ev["score"] = _relevancia(etapa["alvo"], ev["trecho"])
        evidencias.append(ev)
        job["usados"]["paginas"] = job["usados"].get("paginas", 0) + 1
        emitir(db, job["id"], job["owner"], "analyst", "extraction_completed", "ok",
               f"Lida {ev['dominio']} (relevância {ev['score']}).", {})
        try:
            nsrc = _eg.criar_no(db, job["owner"], job["id"], "source",
                                _eg.canonical_url(a["url"]),
                                {"url": a["url"][:500], "dominio": ev["dominio"]})
            ndoc = _eg.criar_no(db, job["owner"], job["id"], "document",
                                _eg.hash_conteudo(texto[:1500]),
                                {"titulo": ev["titulo"], "url": a["url"][:500],
                                 "hash": _eg.hash_conteudo(texto[:1500])})
            nev = _eg.criar_no(db, job["owner"], job["id"], "evidence", ev["id"],
                               {"evidence_id": ev["id"], "titulo": ev["titulo"]})
            _eg.ligar(db, job["owner"], job["id"], ndoc, nsrc, "DERIVED_FROM",
                      "ingestao", "documento veio desta fonte")
            _eg.ligar(db, job["owner"], job["id"], nev, ndoc, "MENTIONS",
                      "ingestao", "trecho extraído deste documento")
            emitir(db, job["id"], job["owner"], "analyst", "evidence_linked", "ok",
                   f"Evidência ligada ao documento ({ev['dominio']}).",
                   {"evidencia_id": ev["id"], "dominio": ev["dominio"],
                    "trecho": ev["trecho"][:300], "url": ev["url"][:200]})
        except Exception:
            pass
    return sorted(evidencias, key=lambda e: e.get("score", 0), reverse=True)


def extrair_afirmacoes(texto: str, teto: int = 12) -> list:
    """Frases verificáveis: longas o bastante + número ou nome próprio."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", texto or ""):
        s = s.strip()
        if len(s) < 40 or len(s) > 400:
            continue
        if re.search(r"\d", s) or re.search(r"\b[A-ZÀ-Ú][a-zà-ú]{3,}\b", s):
            if s not in out:
                out.append(s)
        if len(out) >= teto:
            break
    return out


def cobertura(afirmacao: str, trechos: list) -> float:
    """Fração de tokens da afirmação coberta pelas evidências (léxico, não verdade)."""
    a = research._tokens_topico(afirmacao)
    if not a:
        return 0.0
    b = set()
    for t in trechos:
        b |= research._tokens_topico(t)
    return round(len(a & b) / len(a), 3)


def agente_verificador(db, job: dict, evidencias: list) -> list:
    """Fact Checker 2.0: claims v2 × evidências (regras válidas; resto UNVERIFIED).

    Mantém chaves {afirmacao, estado, cobertura_lexica} + metodo/relacoes.
    """
    import evidence_graph as _eg
    base = job["objetivo"] + ". " + " ".join(e.get("trecho", "") for e in evidencias)
    claims = _eg.extrair_afirmacoes_v2(base)
    if not claims and evidencias:
        claims = [{"texto": job["objetivo"], "condicoes": {"comparado_a": "", "metrica": "",
                                                           "quantidades": [], "datas": []}}]
    vereditos = []
    for c in claims[:12]:
        emitir(db, job["id"], job["owner"], "checker", "claim_identified", "ok",
               f"Afirmação: {c['texto'][:90]}", {})
        contrad = [e["id"] for e in evidencias if e.get("status") == "contradiz"]
        if contrad:
            res = {"estado": "CONTRADICTED", "metodo": "evidencia-contradiz",
                   "evidencia": contrad[0], "cobertura_lexica": 0.0}
        else:
            res = _eg.verificar_claim(c, [{"id": e["id"], "trecho": e["trecho"]} for e in evidencias])
        try:
            ncl = _eg.criar_no(db, job["owner"], job["id"], "claim", c["texto"][:200],
                               {"texto": c["texto"][:500], "condicoes": c["condicoes"]})
            for e in evidencias:
                nev = _eg.no_id("evidence", job["id"], e["id"])
                if res["estado"] == "SUPPORTED" and res.get("evidencia") == e["id"]:
                    _eg.ligar(db, job["owner"], job["id"], nev, ncl, "SUPPORTS",
                              res["metodo"], "quantidade exata no trecho")
                elif res["estado"] == "CONTRADICTED" and e["id"] in contrad:
                    _eg.ligar(db, job["owner"], job["id"], nev, ncl, "CONTRADICTS",
                              "evidencia-contradiz", "fonte marcada como contraditória")
                elif res["estado"] == "PARTIALLY_SUPPORTED" and \
                        _relevancia(c["texto"], e.get("trecho", "")) >= 0.25:
                    _eg.ligar(db, job["owner"], job["id"], nev, ncl, "PARTIALLY_SUPPORTS",
                              res["metodo"], "cobertura parcial")
                elif _relevancia(c["texto"], e.get("trecho", "")) > 0:
                    _eg.ligar(db, job["owner"], job["id"], nev, ncl, "MENTIONS",
                              "lexico", "citação contextual")
                else:
                    _eg.ligar(db, job["owner"], job["id"], nev, ncl, "REQUIRES_VERIFICATION",
                              "sem-cobertura", "sem relação lexical detectada")
        except Exception:
            pass
        vereditos.append({"afirmacao": c["texto"], "estado": res["estado"],
                          "cobertura_lexica": res.get("cobertura_lexica", 0.0),
                          "metodo": res.get("metodo", ""),
                          "condicoes_ausentes": res.get("condicoes_ausentes", [])})
        emitir(db, job["id"], job["owner"], "checker", "claim_verified", "ok",
               f"{res['estado']} ({res.get('metodo', '?')}): {c['texto'][:90]}",
               {"estado": res["estado"], "afirmacao": c["texto"][:200]})
    emitir(db, job["id"], job["owner"], "checker", "claim_verification_completed", "ok",
           f"{len(vereditos)} afirmações avaliadas.", {})
    return vereditos


def analisar_independencia_job(db, job: dict, evidencias: list) -> list:
    """Source Independence: pares de documentos → laudo + arestas."""
    import evidence_graph as _eg
    docs = [{"url": e.get("url", ""), "texto": e.get("trecho", ""), "id": e.get("id", "")}
            for e in evidencias or []]
    laudos = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            laudo = _eg.analisar_independencia(docs[i], docs[j])
            laudo.update({"a": docs[i]["id"], "b": docs[j]["id"]})
            laudos.append(laudo)
            try:
                na = _eg.no_id("document", job["id"], _eg.hash_conteudo(docs[i]["texto"][:1500]))
                nb = _eg.no_id("document", job["id"], _eg.hash_conteudo(docs[j]["texto"][:1500]))
                _eg.ligar(db, job["owner"], job["id"], na, nb, laudo["relacao"],
                          "independencia", laudo["motivo"][:200])
            except Exception:
                pass
            if laudo["relacao"] in ("DUPLICATES", "DERIVED_FROM"):
                emitir(db, job["id"], job["owner"], "analyst", "source_dependency_detected",
                       "alerta", f"{laudo['relacao']}: {laudo['motivo'][:120]}", {})
    return laudos


def agente_sintetizador(db, job: dict, evidencias: list, vereditos: list) -> dict:
    """Synthesizer extrativo honesto (redação LLM = BLOQUEADA sem provedor)."""
    tops = sorted(evidencias, key=lambda e: e.get("score", 0), reverse=True)[:6]
    resposta = [f"Investigação: {job['objetivo']}"]
    for i, e in enumerate(tops):
        resposta.append(f"[E{i + 1}] {e['titulo']} ({e['dominio']}): {e['trecho'][:300]}")
    suportadas = sum(1 for v in vereditos if v["estado"] == "SUPPORTED")
    resposta.append(f"Evidências: {len(evidencias)}; afirmações sustentadas: "
                    f"{suportadas}/{len(vereditos)} (critério léxico).")
    if any(v["estado"] == "CONTRADICTED" for v in vereditos):
        resposta.append("Há contradições entre fontes — leia as evidências antes de concluir.")
    resposta.append("Síntese extrativa: redação por LLM indisponível (provedor Hermes bloqueado).")
    sintese = {"texto": "\n\n".join(resposta), "llm": False}
    emitir(db, job["id"], job["owner"], "synthesizer", "answer_started", "ok",
           f"Síntese extrativa com {len(tops)} evidências.", {})
    return sintese


def agente_auditor(db, job: dict, sintese: dict, evidencias: list) -> dict:
    """Evidence Auditor: citações existem? afirmações exageram?"""
    ids = [f"E{i + 1}" for i in range(len(evidencias))]
    citadas = sorted({m.group(0) for m in re.finditer(r"\[E\d+\]", sintese.get("texto", ""))})
    fantasmas = [c for c in citadas if c.strip("[]") not in ids]
    problemas = [f"citação sem evidência: {c}" for c in fantasmas]
    ok = not problemas
    emitir(db, job["id"], job["owner"], "auditor", "answer_started" if ok else "answer_started",
           "ok" if ok else "alerta", f"Auditoria: {len(problemas)} problemas.", {"problemas": problemas})
    return {"ok": ok, "problemas": problemas}


# ── Orchestrator ────────────────────────────────────────────────────
def _sincronizar(job: dict, fresco: dict) -> None:
    """Adota plano/status/ajustes persistidos (intervenção, pausa, cancelamento)
    preservando transientes em memória (_achados da etapa atual)."""
    mem = {s["id"]: s for s in job["plano"]}
    for s in fresco["plano"]:
        if s["id"] in mem and mem[s["id"]].get("status") == "pendente":
            mem[s["id"]]["status"] = s.get("status", "pendente")
    for s in fresco["plano"]:
        if s["id"] not in mem:
            job["plano"].append(s)
    job["ajustes"] = fresco.get("ajustes", job.get("ajustes", {}))
    if fresco.get("status") in ("cancelada", "pausada", "em_andamento", "criada"):
        job["status"] = fresco["status"]
    job["usados"]["replans"] = max(job["usados"].get("replans", 0),
                                   fresco.get("usados", {}).get("replans", 0))


def _orcamento_ok(job: dict) -> str:
    orc, uso = job["orcamento"], job["usados"]
    if uso.get("buscas", 0) >= orc.get("buscas", 0) and uso.get("paginas", 0) >= orc.get("paginas", 0):
        return "orçamento esgotado"
    return ""


def executar(db, job_id: str, owner: str, provedores: list, recuperar_fn=None,
             deve_parar=None, t0: float = 0) -> dict:
    """Executa passos pendentes com orçamentos; persiste a cada passo.

    Idempotente por etapa (feitas são puladas) → retomada segura.
    Interrupção/falha: estado persistido, nunca meio-termo.
    """
    job = carregar_job(db, owner, job_id)
    if job["status"] in ("concluida", "cancelada"):
        return _resumo(db, job)
    while job["status"] == "pausada":
        if deve_parar is not None and deve_parar():
            job["status"] = "interrompida"
            salvar_job(db, job)
            return _resumo(db, job)
        time.sleep(1.0)
        job = carregar_job(db, owner, job_id)
        if job["status"] in ("concluida", "cancelada"):
            return _resumo(db, job)
    if job["status"] not in ("em_andamento", "criada", "interrompida"):
        raise AgentErro("pesquisa em estado final", "estado")
    job["status"] = "em_andamento"
    salvar_job(db, job)
    if not job["plano"]:
        montar_plano(db, job)
    t0 = t0 or time.monotonic()
    timeout = job["orcamento"].get("timeout_s", 120)
    vistas, todas_evid, vereditos = set(), [], []
    try:
        for etapa in job["plano"]:
            _sincronizar(job, carregar_job(db, owner, job_id))
            if job["status"] == "cancelada":
                return _resumo(db, job)
            while job["status"] == "pausada":
                time.sleep(1.0)
                if deve_parar is not None and deve_parar():
                    break
                _sincronizar(job, carregar_job(db, owner, job_id))
                if job["status"] in ("cancelada", "concluida"):
                    return _resumo(db, job)
            if etapa.get("status") in ("feita", "removida"):
                continue
            if deve_parar is not None and deve_parar():
                job["status"] = "interrompida"
                salvar_job(db, job)
                emitir(db, job["id"], owner, "orchestrator", "research_cancelled", "ok",
                       "Interrompida pelo usuário; retomável.", {})
                return _resumo(db, job)
            if time.monotonic() - t0 > timeout:
                job["pendencias"].append("tempo esgotado antes de " + etapa["id"])
                break
            msg = _orcamento_ok(job)
            if msg and etapa["tipo"] in ("busca", "ler"):
                job["pendencias"].append(f"{etapa['id']}: {msg}")
                continue
            emitir(db, job["id"], owner, "orchestrator", "step_started", "ok",
                   f"Etapa {etapa['id']} ({etapa['tipo']}): {etapa['alvo'][:80]}", {})
            etapa["tentativas"] = etapa.get("tentativas", 0) + 1
            try:
                if etapa["tipo"] == "busca":
                    etapa["_achados"] = agente_busca(db, job, etapa, provedores, vistas)
                elif etapa["tipo"] == "ler":
                    teto = max(1, job["orcamento"].get("paginas", 3) // max(1, len(
                        [s for s in job["plano"] if s["tipo"] == "ler"])))
                    fonte = _achados_etapa(job, etapa)
                    etapa["_evidencias"] = agente_analista(db, job, etapa, fonte,
                                                          recuperar_fn, teto)
                    todas_evid.extend(etapa["_evidencias"])
                elif etapa["tipo"] == "analisar":
                    etapa["_n"] = len(todas_evid)
                elif etapa["tipo"] == "verificar":
                    base_ev = todas_evid or _evidencias_job(db, job)
                    analisar_independencia_job(db, job, base_ev)
                    vereditos = agente_verificador(db, job, base_ev)
                    job["achados"] = [{"afirmacao": v["afirmacao"], "estado": v["estado"],
                                       "metodo": v.get("metodo", "")} for v in vereditos]
                    job["investigacoes"] = investigar_contradicoes_job(db, job, base_ev)
                elif etapa["tipo"] == "sintetizar":
                    etapa["_sintese"] = agente_sintetizador(
                        db, job, todas_evid or _evidencias_job(db, job), vereditos)
                elif etapa["tipo"] == "auditar":
                    sint = next((s.get("_sintese") for s in job["plano"]
                                 if s.get("_sintese")), {"texto": "", "llm": False})
                    emitir(db, job["id"], owner, "auditor", "audit_started", "ok",
                           "Auditoria final da resposta.", {})
                    etapa["_auditoria"] = agente_auditor(
                        db, job, sint, todas_evid or _evidencias_job(db, job))
                    job["auditoria"] = dict(etapa["_auditoria"])
                    emitir(db, job["id"], owner, "auditor", "audit_completed",
                           "ok" if etapa["_auditoria"].get("ok") else "alerta",
                           f"Auditoria: {len(etapa['_auditoria'].get('problemas', []))} problemas.",
                           {})
                etapa["status"] = "feita"
            except (AgentErro, research.ResearchErro) as exc:
                etapa["status"] = "falhou"
                job["erros"].append(f"{etapa['id']}: {exc}")
                emitir(db, job["id"], owner, "orchestrator", "step_started", "falha",
                       f"Etapa {etapa['id']} falhou ({getattr(exc, 'codigo', '?')}).", {})
            salvar_job(db, job)
        lacunas = _lacunas(job)
        if lacunas and not _orcamento_ok(job) and job["plano"] and \
                job["usados"].get("replans", 0) < 1 and \
                all(s.get("status") != "pendente" for s in job["plano"]):
            v0 = job["plano_versao"]
            replanejar(db, job, lacunas)
            salvar_job(db, job)
            if job["plano_versao"] > v0:
                return executar(db, job_id, owner, provedores, recuperar_fn, deve_parar, t0)
        job["status"] = "concluida" if not job["pendencias"] or todas_evid else \
            ("concluida" if todas_evid else "interrompida")
        if job["status"] == "interrompida" and not job["pendencias"]:
            job["pendencias"].append("sem evidências suficientes")
        salvar_job(db, job)
        emitir(db, job["id"], owner, "orchestrator", "research_completed", "ok",
               f"Pesquisa {job['status']}: {len(todas_evid or _evidencias_job(db, job))} evidências.",
               {})
        return _resumo(db, job)
    except Exception as exc:
        job["status"] = "falhou"
        job["erros"].append(f"orquestrador: {type(exc).__name__}: {exc}"[:300])
        salvar_job(db, job)
        emitir(db, job["id"], owner, "orchestrator", "research_failed", "falha",
               f"Falha: {type(exc).__name__}. Estado preservado.", {})
        return _resumo(db, job)


def _achados_etapa(job: dict, etapa: dict) -> list:
    for s in job["plano"]:
        if s.get("tipo") == "busca" and s.get("alvo") == etapa["alvo"] and "_achados" in s:
            return s["_achados"]
    return []


def _evidencias_job(db, job: dict) -> list:
    return listar_evidencias(db, job["owner"], job["id"])


def _lacunas(job: dict) -> list:
    subs_busca = {s.get("alvo") for s in job["plano"] if s.get("tipo") == "busca"}
    com_evid = set()
    for s in job["plano"]:
        if s.get("tipo") == "ler" and s.get("_evidencias"):
            com_evid.add(s.get("alvo"))
    return sorted(subs_busca - com_evid)


def investigar_contradicoes_job(db, job: dict, evidencias: list) -> list:
    """Contradiction Agent: pares com negação assimétrica → investiga dimensão."""
    import evidence_graph as _eg
    invs = []
    tops = [research._tokens_topico(e.get("titulo", "") + " " + e.get("trecho", ""))
            for e in evidencias or []]
    for i in range(len(evidencias or [])):
        for j in range(i + 1, len(evidencias or [])):
            if not (tops[i] & tops[j]):
                continue
            ti = (evidencias[i].get("trecho", "") or "").lower()
            tj = (evidencias[j].get("trecho", "") or "").lower()
            qi = _eg.extrair_quantidades(ti)
            qj = _eg.extrair_quantidades(tj)
            mesmos = [a for a in qi for b in qj
                      if (a.get("unidade") or "") == (b.get("unidade") or "")
                      and a.get("unidade") and a["valor"] != b["valor"]]
            if mesmos:
                a, b = mesmos[0], [x for x in qj if x.get("unidade") == mesmos[0].get("unidade")
                                   and x["valor"] != mesmos[0]["valor"]][0]
                inv = {"tipo": "valor_divergente", "status": "em_aberto",
                       "explicacao": f"Mesma unidade, valores distintos ({a['valor']} × {b['valor']}). "
                                     "Verificar metodologia, data e condições.",
                       "follow_up": ["metodologia medição", "data atualização dado"],
                       "entre": [evidencias[i]["id"], evidencias[j]["id"]]}
                invs.append(inv)
                try:
                    na = _eg.no_id("evidence", job["id"], evidencias[i]["id"])
                    nb = _eg.no_id("evidence", job["id"], evidencias[j]["id"])
                    _eg.ligar(db, job["owner"], job["id"], na, nb, "CONTRADICTS",
                              "contradicao", inv["tipo"])
                except Exception:
                    pass
                emitir(db, job["id"], job["owner"], "contradiction", "contradiction_investigated",
                       "alerta", f"Divergência valor_divergente: valores distintos.", {})
                continue
            ni = any(n in ti for n in research.NEGACOES)
            nj = any(n in tj for n in research.NEGACOES)
            if ni == nj:
                continue
            ci = {"texto": evidencias[i]["trecho"][:400],
                  "condicoes": {"comparado_a": "", "metrica": "",
                                "quantidades": _eg.extrair_quantidades(ti),
                                "datas": _eg._RX_DATA.findall(ti)[:3]}}
            cj = {"texto": evidencias[j]["trecho"][:400],
                  "condicoes": {"comparado_a": "", "metrica": "",
                                "quantidades": _eg.extrair_quantidades(tj),
                                "datas": _eg._RX_DATA.findall(tj)[:3]}}
            inv = _eg.investigar_divergencia(ci, cj, evidencias[i]["id"], evidencias[j]["id"])
            inv.update({"entre": [evidencias[i]["id"], evidencias[j]["id"]]})
            invs.append(inv)
            try:
                na = _eg.no_id("evidence", job["id"], evidencias[i]["id"])
                nb = _eg.no_id("evidence", job["id"], evidencias[j]["id"])
                _eg.ligar(db, job["owner"], job["id"], na, nb, "CONTRADICTS",
                          "contradicao", inv["tipo"])
            except Exception:
                pass
            emitir(db, job["id"], job["owner"], "contradiction", "contradiction_investigated",
                   "alerta" if inv["tipo"] == "valor_divergente" else "ok",
                   f"Divergência {inv['tipo']}: {inv['explicacao'][:140]}", {})
    return invs


def _resumo(db, job: dict) -> dict:
    evs = _evidencias_job(db, job)
    invs = job.get("investigacoes") or []
    aud = job.get("auditoria") or {}
    return {"id": job["id"], "status": job["status"], "modo": job["modo"],
            "objetivo": job["objetivo"], "plano_versao": job["plano_versao"],
            "etapas": [{"id": s["id"], "tipo": s["tipo"], "status": s.get("status", "pendente")}
                       for s in job["plano"]],
            "evidencias": len(evs), "achados": job["achados"],
            "investigacoes": len(invs),
            "auditoria_ok": aud.get("ok") if aud else None,
            "pendencias": job["pendencias"], "erros": job["erros"],
            "usados": job["usados"], "orcamento": job["orcamento"]}


def cancelar(db, owner: str, job_id: str) -> dict:
    job = carregar_job(db, owner, job_id)
    if job["status"] in ("concluida", "cancelada"):
        return _resumo(db, job)
    job["status"] = "cancelada"
    salvar_job(db, job)
    emitir(db, job["id"], owner, "orchestrator", "research_cancelled", "ok",
           "Cancelada; resultados parciais preservados.", {})
    return _resumo(db, job)


def pausar(db, owner: str, job_id: str, pausar: bool = True) -> dict:
    job = carregar_job(db, owner, job_id)
    if job["status"] not in ("em_andamento", "pausada"):
        raise AgentErro("só pausa job em andamento", "estado")
    job["status"] = "pausada" if pausar else "em_andamento"
    salvar_job(db, job)
    emitir(db, job["id"], owner, "orchestrator",
           "research_cancelled" if pausar else "step_started",
           "ok", "Pausada pelo usuário." if pausar else "Retomada pelo usuário.", {})
    return _resumo(db, job)


OPS_INTERVENCAO = ("escopo_add", "escopo_remove", "priorizar_dominio",
                   "investigar_divergencia", "parar_topico", "adicionar_metrica")


def intervir(db, owner: str, job_id: str, op: str, params: dict = None) -> dict:
    """Alteração estruturada do plano (sem LLM): nova versão, feitas preservadas,
    incompatíveis invalidadas e listadas."""
    params = params or {}
    if op not in OPS_INTERVENCAO:
        raise AgentErro("operação inválida", "op")
    job = carregar_job(db, owner, job_id)
    if job["status"] in ("concluida", "cancelada", "falhou"):
        raise AgentErro("pesquisa em estado final", "estado")
    aj = job.get("ajustes") or {"restricoes": [], "prioridades": [], "metricas": []}
    adicionadas, removidas, invalidadas = [], [], []
    if op in ("escopo_add", "adicionar_metrica"):
        texto = str(params.get("texto", ""))[:120]
        if len(texto) < 3:
            raise AgentErro("texto curto demais", "texto")
        if op == "adicionar_metrica":
            aj["metricas"].append(texto)
        for tipo in ("busca", "ler"):
            job["plano"].append({"id": f"p{len(job['plano']) + 1}", "tipo": tipo,
                                 "alvo": texto, "status": "pendente", "tentativas": 0})
            adicionadas.append(tipo + ":" + texto)
    elif op in ("escopo_remove", "parar_topico"):
        texto = str(params.get("texto", ""))[:120].lower()
        if len(texto) < 3:
            raise AgentErro("texto curto demais", "texto")
        aj["restricoes"].append(texto)
        for s in job["plano"]:
            if s.get("status") == "pendente" and texto in (s.get("alvo", "") or "").lower():
                s["status"] = "removida"
                removidas.append(s["id"])
    elif op == "priorizar_dominio":
        dom = str(params.get("dominio", ""))[:120].lower()
        if len(dom) < 3:
            raise AgentErro("domínio curto demais", "dominio")
        aj["prioridades"].insert(0, dom)
        adicionadas.append("prioridade:" + dom)
    elif op == "investigar_divergencia":
        invs = job.get("investigacoes") or []
        try:
            idx = int(params.get("indice", 0))
        except (TypeError, ValueError):
            raise AgentErro("índice inválido", "indice") from None
        if not (0 <= idx < len(invs)):
            raise AgentErro("divergência inexistente", "indice")
        for q in invs[idx].get("follow_up", [])[:3]:
            job["plano"].append({"id": f"p{len(job['plano']) + 1}", "tipo": "busca",
                                 "alvo": str(q)[:120], "status": "pendente", "tentativas": 0})
            adicionadas.append("busca:" + str(q)[:60])
    for ev in listar_evidencias(db, owner, job_id):
        if any(r in (ev.get("url", "") or "").lower() or r in (ev.get("titulo", "") or "").lower()
               for r in aj["restricoes"]):
            invalidadas.append(ev["id"])
    job["ajustes"] = aj
    job["plano_versao"] += 1
    if job["status"] in ("interrompida", "pausada"):
        job["status"] = "em_andamento"
    salvar_job(db, job)
    emitir(db, job["id"], owner, "orchestrator", "plan_updated", "ok",
           f"Intervenção {op} → plano v{job['plano_versao']}: +{len(adicionadas)}/-{len(removidas)}.",
           {"op": op})
    return {"job_id": job_id, "plano_versao": job["plano_versao"], "adicionadas": adicionadas,
            "removidas": removidas, "invalidadas": invalidadas, "status": job["status"]}


def _segundos(ini: str, fim: str) -> float:
    try:
        from datetime import datetime as _dt
        a = _dt.fromisoformat(ini)
        b = _dt.fromisoformat(fim)
        return max(0.0, (b - a).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def avaliar_job(db, owner: str, job_id: str) -> dict:
    """Métricas determinísticas de qualidade (metodologia documentada, sem
    nota de 'verdade': cobertura é léxica, independência é por domínio)."""
    job = carregar_job(db, owner, job_id)
    evs = listar_evidencias(db, owner, job_id)
    subs = [s.get("alvo", "") for s in job["plano"] if s.get("tipo") == "busca"]
    cobertos = sum(1 for s in subs
                   if any(_relevancia(s, e.get("trecho", "")) >= 0.2 for e in evs))
    dominios = {e["dominio"] for e in evs if e["dominio"]}
    urls = {e["url"] for e in evs if e["url"]}
    ach = job["achados"]
    return {
        "job_id": job_id, "status": job["status"], "modo": job["modo"],
        "cobertura": round(cobertos / len(subs), 3) if subs else 0.0,
        "subs": len(subs), "subs_cobertos": cobertos,
        "evidencias": len(evs), "fontes_unicas": len(urls),
        "fontes_independentes": len(dominios),
        "contradicoes": sum(1 for e in evs if e["status"] == "contradiz"),
        "parciais": sum(1 for e in evs if e["status"] == "parcial"),
        "nao_verificadas": sum(1 for a in ach if a.get("estado") in ("UNVERIFIED",
                                                                     "INSUFFICIENT_EVIDENCE")),
        "sustentadas": sum(1 for a in ach if a.get("estado") == "SUPPORTED"),
        "atualidade": round(sum(1 for e in evs if e["acessado_em"]) / len(evs), 3) if evs else 0.0,
        "latencia_s": round(_segundos(job["criado_em"], job["atualizado_em"]), 1),
        "buscas": job["usados"].get("buscas", 0),
        "paginas": job["usados"].get("paginas", 0),
        "replans": job["usados"].get("replans", 0),
        "erros": len(job["erros"]), "pendencias": len(job["pendencias"]),
        "metodo": "cobertura=overlap léxico sub↔trecho; independência=domínios distintos; "
                  "sem nota de verdade",
    }


# ── Fábrica de provedores (injetável em teste) ──────────────────────
PROVS_FABRICA = None
RECUPERAR_FABRICA = None


def provedores_reais():
    import os as _os
    if PROVS_FABRICA is not None:
        return PROVS_FABRICA()
    return [ProvedorDDG(), ProvedorSearXNG(_os.environ.get("JULIA_SEARXNG_URL", ""))]


def recuperar_real():
    if RECUPERAR_FABRICA is not None:
        return RECUPERAR_FABRICA()
    return None
