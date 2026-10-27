"""JuliaResearchAgentSystem (V4.5) — orquestração determinística de pesquisa.

Papéis como FUNÇÕES reutilizáveis sobre estado persistido (não instâncias
de modelo): planejador, buscadores, analista, verificador, sintetizador e
auditor. Tudo auditável: cada passo emite evento, persiste e respeita
orçamento. LLM só redige (falha/ausência → síntese extrativa honesta);
nunca decide fatos.

Tabelas (owner em tudo; PC é o definitivo):
- research_jobs: o plano + estado (checkpoint = a própria linha).
- research_events: telemetria real (seq por job).
- evidence: registros de evidência com status de verificação.
"""
import hashlib
import json
import json_store
import os
import re
import threading
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from contextvars import copy_context

import academic_research
import continuous_research
import hypothesis_engine
import media_evidence
import research
import research_reports
import research_synthesis
import research_visualizations
import retrieval_trace
import structured_analysis

MODOS = {
    "rapida": {"buscas": 2, "paginas": 3, "timeout_s": 30, "subs": 1,
               "profundidade": 1, "midia": 8, "concorrencia": 3,
               "replans": 1, "max_bytes_pagina": 2_000_000},
    "pro": {"buscas": 4, "paginas": 6, "timeout_s": 60, "subs": 3,
            "profundidade": 2, "midia": 12, "concorrencia": 3,
            "replans": 1, "max_bytes_pagina": 2_000_000},
    "profunda": {"buscas": 8, "paginas": 12, "timeout_s": 120, "subs": 4,
                 "profundidade": 2, "midia": 16, "concorrencia": 3,
                 "replans": 2, "max_bytes_pagina": 2_000_000},
    "investigativa": {"buscas": 12, "paginas": 20, "timeout_s": 300, "subs": 6,
                      "profundidade": 3, "midia": 20, "concorrencia": 3,
                      "replans": 2, "max_bytes_pagina": 2_000_000},
}

ALIAS_MODOS = {
    "rapida": "rapida", "rápida": "rapida", "quick": "rapida", "fast": "rapida",
    "pro": "pro", "professional": "pro",
    "profunda": "profunda", "deep": "profunda", "deep research": "profunda",
    "deep_research": "profunda", "deep search": "profunda",
    "deep_search": "profunda", "pesquisa profunda": "profunda",
    "investigativa": "investigativa", "investigative": "investigativa",
    "investigation": "investigativa",
}

# Environment overrides are read at job creation only, so a running job keeps
# the budget it started with (checkpoint/resume stays reproducible).
_LIMITES_ENV = {
    "buscas": ("JULIA_RESEARCH_MAX_BUSCAS", "JULIA_DEEP_MAX_BUSCAS", 1, 40),
    "paginas": ("JULIA_RESEARCH_MAX_PAGINAS", "JULIA_DEEP_MAX_PAGINAS", 1, 80),
    "timeout_s": ("JULIA_RESEARCH_MAX_SEGUNDOS", "JULIA_DEEP_MAX_SEGUNDOS", 15, 1800),
    "subs": ("JULIA_RESEARCH_MAX_SUBCONSULTAS", "JULIA_DEEP_MAX_SUBCONSULTAS", 1, 12),
    "profundidade": ("JULIA_RESEARCH_MAX_PROFUNDIDADE", "JULIA_DEEP_MAX_PROFUNDIDADE", 1, 4),
    "midia": ("JULIA_RESEARCH_MAX_MIDIA", "JULIA_DEEP_MAX_MIDIA", 0, 40),
    "concorrencia": ("JULIA_RESEARCH_MAX_CONCORRENCIA", "JULIA_DEEP_MAX_CONCORRENCIA",
                     1, 8),
    "replans": ("JULIA_RESEARCH_MAX_REPLANS", "JULIA_DEEP_MAX_REPLANS", 0, 3),
    "max_bytes_pagina": ("JULIA_RESEARCH_MAX_BYTES_PAGINA",
                         "JULIA_DEEP_MAX_BYTES_PAGINA", 65_536, 10_000_000),
}

STATUS_JOB = ("criada", "em_andamento", "pausada", "concluida", "interrompida",
              "falhou", "cancelada")
STATUS_EVIDENCIA = ("recuperada", "encontrada", "inacessivel", "nao_sustenta",
                    "contradiz", "parcial")
ESTADOS_CLAIM = ("SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED",
                 "INSUFFICIENT_EVIDENCE")

MODO_AUTO = (
    (("investiga", "investigative", "hypothesis", "hipótese", "hipotese",
      "a fundo", "tese", "thesis"), "investigativa"),
    (("aprofundad", "dossiê", "dossie", "relatório completo", "relatorio completo",
      "deep research", "deep search", "pesquisa profunda", "pesquise profundo",
      "verifique se", "é verdade", "e verdade", "fact check"), "profunda"),
    (("compare", "comparar", "prós e contras", "pros e contras",
      "qual melhor", "versus", "vs."), "pro"),
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
        atualizado_em TEXT NOT NULL, midia TEXT NOT NULL DEFAULT '[]')""")
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
                       ("ajustes", "TEXT NOT NULL DEFAULT '{}'"),
                       ("structured_analysis", "TEXT NOT NULL DEFAULT '[]'"),
                       ("midia", "TEXT NOT NULL DEFAULT '[]'")):
        try:
            cols = [c[1] for c in db.execute("PRAGMA table_info(research_jobs)").fetchall()]
            if _col not in cols:
                db.execute(f"ALTER TABLE research_jobs ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_job ON research_events(job_id, seq)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ev_job ON evidence(job_id, status)")
    hypothesis_engine.HypothesisStore(db).initialize()
    continuous_research.ResearchContextStore(db).initialize()
    db.commit()


def _orcamento_modo(modo: str) -> dict:
    """Budget for a new job, with bounded environment overrides.

    The same values are persisted in ``research_jobs.orcamento`` and used by
    every step; changing env vars never mutates a job already in progress.
    """
    modo = modo if modo in MODOS else "pro"
    base = dict(MODOS[modo])
    for chave, (env_geral, env_profunda, minimo, maximo) in _LIMITES_ENV.items():
        nomes = (env_profunda, env_geral) if modo in ("profunda", "investigativa") \
            else (env_geral,)
        for nome in nomes:
            bruto = (os.environ.get(nome) or "").strip()
            if not bruto:
                continue
            try:
                base[chave] = max(minimo, min(maximo, int(bruto)))
            except ValueError:
                continue
            break
    return base


def selecionar_modo(texto: str, manual: str = "") -> str:
    manual = (manual or "").strip().lower()
    if manual in ALIAS_MODOS:
        return ALIAS_MODOS[manual]
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
                    json_store.encode(ev["meta"], 4000)))
    terminal={'research_completed','research_failed'}
    if tipo in terminal:
        retrieval_trace.record(job_id,'',{},'JOB_TERMINAL',reason_code=tipo.upper())
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
           "orcamento": _orcamento_modo(modo),
           "usados": {"buscas": 0, "paginas": 0}, "midia": [],
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
                     " COALESCE(ajustes, '{}'), COALESCE(structured_analysis, '[]'),"
                     " COALESCE(midia, '[]')"
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
                "ajustes": json.loads(row[16] or "{}"),
                "structured_analysis": json.loads(row[17] or "[]"),
                "midia": json.loads(row[18] or "[]")}
    except (TypeError, ValueError, IndexError) as exc:
        raise AgentErro("pesquisa corrompida", "corrompida") from exc


def salvar_job(db, job: dict, forcar_status: bool = False) -> None:
    """Persiste o job preservando cancelamento/pausa concorrentes.

    Um passo longo pode terminar depois de o usuário cancelar/pausar. Sem
    `forcar_status`, o estado de controle já gravado no banco vence o
    snapshot antigo do worker (evita "ressuscitar" job cancelado).
    """
    plano_limpo = []
    for s in job["plano"]:
        plano_limpo.append({k: v for k, v in s.items() if not k.startswith("_")})
    # Source excerpts already live in research_evidence. Avoid multiplying them
    # across every claim until an otherwise valid research cannot checkpoint.
    findings = job["achados"]
    if len(json.dumps(findings, ensure_ascii=False)) > 60000:
        findings = [dict(item, fontes=[{k: v for k, v in source.items()
                    if k != "used_excerpt"} for source in item.get("fontes", [])])
                    for item in findings]
        if len(json.dumps(findings, ensure_ascii=False)) > 60000:
            findings = [dict(item, fontes=[{k: source[k] for k in
                        ("evidence_id", "relation", "read", "access_state") if k in source}
                        for source in item.get("fontes", [])]) for item in findings]
        job["usados"]["claim_sources_compacted"] = True
    # CASE atômico: um cancelamento/pausa gravado entre a leitura do snapshot e
    # este UPDATE continua vencendo, sem janela de corrida.
    status_sql = "?" if forcar_status else \
        "CASE WHEN status IN ('cancelada','pausada') THEN status ELSE ? END"
    with db:
        db.execute("UPDATE research_jobs SET plano=?, plano_versao=?,"
                   f" status={status_sql}, orcamento=?,"
                   " usados=?, achados=?, pendencias=?, erros=?, atualizado_em=?,"
                   " investigacoes=?, auditoria=?, ajustes=?, structured_analysis=?, midia=?"
                   " WHERE id=? AND owner_id=?",
                   (json_store.encode(plano_limpo, 60000), job["plano_versao"],
                    job["status"], json.dumps(job["orcamento"], ensure_ascii=False),
                    json.dumps(job["usados"], ensure_ascii=False),
                    json_store.encode(findings, 60000),
                    json_store.encode(job["pendencias"], 20000),
                    json_store.encode(job["erros"], 20000),
                    agora_iso(),
                    json_store.encode(job.get("investigacoes", []), 20000),
                    json_store.encode(job.get("auditoria", {}), 8000),
                    json_store.encode(job.get("ajustes", {}), 8000),
                    json_store.encode(job.get("structured_analysis", []), 60000),
                    json_store.encode(job.get("midia", []), 60000),
                    job["id"], job["owner"]))
    if not forcar_status:
        try:
            atual = db.execute("SELECT status FROM research_jobs WHERE id=? AND owner_id=?",
                               (job["id"], job["owner"])).fetchone()
            if atual:
                job["status"] = atual[0]
        except Exception:
            pass


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
def _chave_consulta(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", str(texto or "").casefold())
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", sem_acento)).strip()


def _subconsultas_unicas(objetivo: str, limite: int) -> list:
    """Prevent the planner from spending budget on the same front twice."""
    import query_intelligence
    request=query_intelligence.analyze(objetivo)
    if request['domain']=='science' and limite>1 and not query_intelligence.retrieval_context(objetivo)['guarded']:
        import search_orchestrator
        import research_gaps
        # Discover the topic first. Methods/results expansion follows observed
        # gaps instead of spending all page slots on blind initial fronts.
        base=research_gaps.science_subject(objetivo)
        fronts=['estudos científicos ' + base]
        translated=search_orchestrator.consulta_cientifica(base)
        if translated.casefold()!=base.casefold(): fronts.append('papers ' + translated)
        return list(dict.fromkeys(fronts))[:max(1,limite)]
    brutas = research.dividir_subconsultas(objetivo, limite) or [objetivo[:120]]
    vistas, saida = set(), []
    for bruta in brutas:
        alvo = re.sub(r"\s+", " ", str(bruta or "")).strip(" .,;:!?-—–")
        chave = _chave_consulta(alvo)
        if len(alvo) < 3 or not chave or chave in vistas:
            continue
        vistas.add(chave)
        saida.append(alvo)
        if len(saida) >= max(1, limite):
            break
    return saida or [objetivo[:240]]


def montar_plano(db, job: dict) -> dict:
    """Etapas com dependências explícitas; preservar etapas e resultados feitos."""
    import query_intelligence
    request_info = job["ajustes"].get("request") or {}
    if request_info.get('original_request') != job['objetivo']:
        request_info = query_intelligence.analyze(job['objetivo'])
        job['ajustes']['request'] = request_info
    # Keep the original temporal expression for the discovery adapter. Re-parsing
    # a rendered date range loses hour windows and can absorb it into the city.
    request_text = job["objetivo"]
    subs = _subconsultas_unicas(request_text, int(job["orcamento"].get("subs", 3) or 3))
    feitas = { (s.get("tipo"), s.get("alvo")) for s in job["plano"] if s.get("status") == "feita" }
    plano, n = [], 0
    for sub_index, sub in enumerate(subs):
        ids = {}
        for tipo in ("busca", "ler", "analisar"):
            n += 1
            chave = (tipo, sub)
            prioridade = {"busca": 10, "ler": 30, "analisar": 50}[tipo] + sub_index
            etapa = {"id": f"p{n}", "tipo": tipo, "alvo": sub,
                     "frente": sub_index + 1,
                     "objetivo_etapa": {
                         "busca": "localizar fontes relevantes e independentes",
                         "ler": "abrir a fonte e extrair trecho com proveniência",
                         "analisar": "registrar evidência sem transformar descoberta em prova",
                     }.get(tipo, ""),
                     "status": "feita" if chave in feitas else "pendente",
                     "tentativas": 0, "prioridade": prioridade,
                     "priority_reason": f"frente {sub_index + 1} do plano explícito",
                     "dependencias": [ids["busca"]] if tipo == "ler" else (
                         [ids["ler"]] if tipo == "analisar" else []),
                     "regra_parada": "etapa concluída ou orçamento/timeout atingido",
                     "criterio_conclusao": {
                         "busca": "resultados únicos; consulta repetida é ignorada",
                         "ler": "fonte aberta e trecho extraído/persistido",
                         "analisar": "achados da etapa disponíveis para verificação",
                     }.get(tipo, "")}
            if chave in feitas:
                etapa["reutilizar_resultado"] = True
            plano.append(etapa)
            ids[tipo] = etapa["id"]
    analizar_ids = [s["id"] for s in plano if s["tipo"] == "analisar"]
    for tipo in ("verificar", "sintetizar", "auditar"):
        n += 1
        chave = (tipo, "")
        dependencias = {
            "verificar": analizar_ids,
            "sintetizar": [f"p{n - 1}"],
            "auditar": [f"p{n - 1}"],
        }
        if tipo == "sintetizar":
            verificar = next((s["id"] for s in plano if s["tipo"] == "verificar"), "")
            dependencias[tipo] = [verificar] if verificar else []
        elif tipo == "auditar":
            sintetizar = next((s["id"] for s in plano if s["tipo"] == "sintetizar"), "")
            dependencias[tipo] = [sintetizar] if sintetizar else []
        plano.append({"id": f"p{n}", "tipo": tipo, "alvo": "",
                      "frente": 0,
                      "objetivo_etapa": {
                          "verificar": "classificar cada afirmação contra as fontes lidas",
                          "sintetizar": "redigir apenas com evidências registradas",
                          "auditar": "checar citações e limitações antes de concluir",
                      }[tipo],
                      "status": "feita" if chave in feitas else "pendente", "tentativas": 0,
                      "prioridade": 100,
                      "priority_reason": "etapa final dependente das frentes de pesquisa",
                      "dependencias": dependencias[tipo],
                      "regra_parada": "etapa concluída ou orçamento/timeout atingido",
                      "criterio_conclusao": {
                          "verificar": "todo veredito tem estado e referências quando aplicável",
                          "sintetizar": "resposta extrativa com citações existentes",
                          "auditar": "nenhuma citação fantasma; limitações explícitas",
                      }[tipo]})
    job["plano"] = plano
    job["plano_versao"] += 1
    salvar_job(db, job)
    emitir(db, job["id"], job["owner"], "orchestrator", "plan_created", "ok",
           f"Plano v{job['plano_versao']}: {len(subs)} frentes, {len(plano)} etapas.",
           {"subs": subs, "dependencies": True, "non_redundant": True,
            "stopping_criteria": "orçamento de buscas/páginas, timeout, uma rodada extra por lacuna",
            "budgets": {k: v for k, v in job["orcamento"].items()
                        if k in ("buscas", "paginas", "timeout_s", "subs", "replans")},
            "max_replans": job["orcamento"].get("replans", 1)})
    _save_context_checkpoint(db, job, "Executar o primeiro passo pendente do plano.")
    return job


def replanejar(db, job: dict, lacunas: list) -> dict:
    """Limited gap-driven round: new searches/readings without repeating fronts."""
    import query_intelligence
    request = (job.get('ajustes') or {}).get('request') or {}
    if request.get('original_request') != job['objetivo']:
        request = query_intelligence.analyze(job['objetivo'])
    max_replans = max(0, int(job["orcamento"].get("replans", 1) or 0))
    if job["usados"].get("replans", 0) >= max_replans:
        return job
    feitas = {(s.get("tipo"), s.get("alvo")) for s in job["plano"] if s.get("status") != "pendente"}
    chaves_feitas = {_chave_consulta(s.get("alvo", "")) for s in job["plano"]
                     if s.get("tipo") == "busca"}
    novas = 0
    limite_novas = min(4, max(0, job["orcamento"].get("buscas", 0) - job["usados"].get("buscas", 0)))
    if not limite_novas:
        return job
    feitos_fu = set(job["usados"].get("follow_ups", []))
    actionable_gaps = any(g.get('status') == 'OPEN' and g.get('query')
                          for g in job['usados'].get('research_gaps', []))
    for inv in ([] if actionable_gaps else job.get("investigacoes") or []):
        for q in (inv.get("follow_up") or [])[:2]:
            if novas >= limite_novas:
                break
            alvo = query_intelligence.constrain_discovery(
                re.sub(r"\s+", " ", str(q or "")).strip(), request, lock_context=True)
            chave = _chave_consulta(alvo)
            if (not chave or ("busca", alvo) in feitas or alvo in feitos_fu
                    or chave in chaves_feitas):
                continue
            chaves_feitas.add(chave)
            search_id = f"p{len(job['plano']) + 1}"
            read_id = f"p{len(job['plano']) + 2}"
            for etapa_id, tipo, deps in (
                (search_id, "busca", []),
                (read_id, "ler", [search_id]),
                (f"p{len(job['plano']) + 3}", "analisar", [read_id]),
            ):
                job["plano"].append({
                    "id": etapa_id, "tipo": tipo, "alvo": alvo,
                    "status": "pendente", "tentativas": 0, "prioridade": 25,
                    "dependencias": deps,
                    "replan_reason": "follow_up gerado por divergência registrada",
                    "regra_parada": "uma única rodada extra, orçamento e timeout originais",
                })
            feitas.add(("busca", alvo))
            feitos_fu.add(alvo)
            novas += 1
            emitir(db, job["id"], job["owner"], "orchestrator", "step_started", "ok",
                   f"Busca motivada por lacuna: {alvo[:80]}", {})
    job["usados"]["follow_ups"] = sorted(feitos_fu)
    for lac in (lacunas or [])[:4]:
        if novas >= limite_novas:
            break
        alvo = query_intelligence.constrain_discovery(
            re.sub(r"\s+", " ", str(lac or "")).strip(), request, lock_context=True)
        chave = _chave_consulta(alvo)
        if not chave or ("busca", alvo) in feitas or chave in chaves_feitas:
            continue
        chaves_feitas.add(chave)
        nova_frente = alvo not in {s.get("alvo") for s in job["plano"]
                                    if s.get("tipo") == "busca"}
        if nova_frente:
            # Lacuna que ainda não é frente do plano (ex.: consulta
            # complementar do orquestrador): cria busca + leitura + análise.
            busca_id = f"p{len(job['plano']) + 1}"
            read_id = f"p{len(job['plano']) + 2}"
            an_id = f"p{len(job['plano']) + 3}"
            for etapa_id, tipo, deps in (
                (busca_id, "busca", []),
                (read_id, "ler", [busca_id]),
                (an_id, "analisar", [read_id]),
            ):
                job["plano"].append({
                    "id": etapa_id, "tipo": tipo, "alvo": alvo, "status": "pendente",
                    "tentativas": 0, "prioridade": 25, "dependencias": deps,
                    "replan_reason": "consulta complementar por lacuna real de busca",
                    "regra_parada": "uma única rodada extra, orçamento e timeout originais",
                })
            feitas.add(("busca", alvo))
            novas += 1
            continue
        busca_id = f"p{len(job['plano']) + 1}"
        job["plano"].append({
            "id": busca_id, "tipo": "busca", "alvo": alvo, "status": "pendente",
            "tentativas": 0, "prioridade": 25, "dependencias": [],
            "replan_reason": "etapa de leitura sem evidência armazenada",
            "regra_parada": "uma única rodada extra, orçamento e timeout originais",
        })
        for s in job["plano"]:
            if s.get("tipo") == "ler" and s.get("alvo") == alvo and s.get("status") == "feita":
                s["status"] = "pendente"  # relê com os novos achados
                s["dependencias"] = [busca_id]
                s["replan_reason"] = "releitura após busca por lacuna"
        feitas.add(("busca", alvo))
        novas += 1
    if novas:
        for item in reversed(job['usados'].get('controller_decisions', [])):
            if item.get('action') == 'REPLAN' and not item.get('executed'):
                item['executed'] = True
                item['new_searches'] = novas
                break
        # New evidence invalidates derived conclusions, not completed retrieval.
        analyses = [step["id"] for step in job["plano"] if step["tipo"] == "analisar"]
        for step in job["plano"]:
            if step["tipo"] in ("verificar", "sintetizar", "auditar"):
                step["status"] = "pendente"
                for key in ("_vereditos", "_sintese", "_auditoria"):
                    step.pop(key, None)
                if step["tipo"] == "verificar":
                    step["dependencias"] = analyses
        job["sintese"] = {}
        job["auditoria"] = {}
        job["usados"]["replans"] = job["usados"].get("replans", 0) + 1
        retrieval_trace.record(job['id'],'',{},'REPLAN_STARTED',budget=job['usados'])
        job["plano_versao"] += 1
        salvar_job(db, job)
        emitir(db, job["id"], job["owner"], "orchestrator", "plan_updated", "ok",
               f"Replanejamento v{job['plano_versao']}: +{novas} buscas.",
               {"reason": "lacunas de evidência", "max_replans": max_replans,
                "round": job["usados"]["replans"], "new_steps": novas})
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


class ProvedorWikipedia(ProvedorBusca):
    """Enciclopédia oficial (opensearch, sem chave). Tipo honestamente marcado;
    nunca usar como preço/oferta."""
    nome = "wikipedia"

    def buscar(self, consulta: str, limite: int = 6) -> list:
        return research.buscar_wikipedia(consulta, max_resultados=limite)


class ProvedorOrquestrado(ProvedorBusca):
    """Busca web real V5.5 (multi-provedor do Research Engine) para os agentes.

    Entra por ÚLTIMO na cadeia (não muda a ordem legada ddg → searxng →
    wikipedia). Não abre páginas: devolve achados ranqueados e guarda o
    `info` da busca (estado honesto, lacunas, consultas de recuperação) para
    o orquestrador decidir o replanejamento por lacuna. Nunca contorna
    bloqueio; vazio/bloqueado viram erro registrado.
    """
    nome = "web"

    def __init__(self, orcamento: dict = None):
        self.orcamento = dict(orcamento) if orcamento else None
        self.info: dict = {}

    def buscar(self, consulta: str, limite: int = 6) -> list:
        achados, info = research._buscar_orquestrado(
            consulta, max_resultados=limite, orcamento=self.orcamento)
        self.info = dict(info or {})
        if achados:
            return achados
        estado = self.info.get("estado", "")
        if estado in ("bloqueado", "rede", "indisponivel"):
            raise research.ResearchErro(f"Busca web indisponível ({estado}).", estado)
        return []


def buscar_com_fallback(provedores: list, consulta: str, limite: int = 6,
                        deve_parar=None) -> tuple:
    """Tenta provedores em ordem; vazio silencioso TAMBÉM alterna (bot-wall
    não para a cadeia); registra falhas; nunca inventa resultado.

    Provedor que guarda diagnóstico (`info`, ex.: ProvedorOrquestrado)
    devolve `detalhe` junto — estados/lacunas reais da busca. `deve_parar`
    é checado antes de cada provedor para cancelar sem esperar a cadeia toda.
    """
    erros = []
    parar = deve_parar or (lambda: False)
    for p in provedores or []:
        if parar():
            return [], {"provedor": "", "erros": erros, "cancelado": True}
        try:
            achados = p.buscar(consulta, limite) or []
        except Exception as exc:
            erros.append({"provedor": getattr(p, "nome", "?"),
                          "codigo": getattr(exc, "codigo", type(exc).__name__)})
            continue
        if achados:
            import query_intelligence as qi
            import search_orchestrator as orch
            usable=[a for a in achados if not orch._context_mismatch(a,consulta)]
            if len(usable)!=len(achados):
                erros.append({'provedor':getattr(p,'nome','?'),'codigo':'context_mismatch',
                              'rejected_candidates':len(achados)-len(usable)})
            achados=usable
        if achados:
            out = {"provedor": p.nome, "erros": erros}
            detalhe = getattr(p, "info", None)
            if isinstance(detalhe, dict) and detalhe:
                out["detalhe"] = dict(detalhe)
            if parar():
                out["cancelado"] = True
            return achados, out
        erros.append({"provedor": getattr(p, "nome", "?"), "codigo": "vazio"})
    return [], {"provedor": "", "erros": erros}


# ── Evidence Store ──────────────────────────────────────────────────
def _merge_provenance(first, second):
    result={**(first or {}),**(second or {})}
    for key in ('query_ids','requirement_ids'):
        result[key]=list(dict.fromkeys((first or {}).get(key,[])+(second or {}).get(key,[])))[:16]
    return result


def _update_reused_provenance(db,job,evidence,candidate):
    provenance=_merge_provenance(evidence.get('retrieval_provenance'),candidate.get('retrieval_provenance'))
    if provenance==evidence.get('retrieval_provenance'):return
    row=db.execute('SELECT original FROM evidence WHERE id=? AND owner_id=? AND job_id=?',
                   (evidence['id'],job['owner'],job['id'])).fetchone()
    if not row:return
    original=json.loads(row[0] or '{}');original['retrieval_provenance']=provenance
    try:serialized=json_store.encode(original,12000)
    except json_store.JSONLimitError:return
    with db:db.execute('UPDATE evidence SET original=? WHERE id=? AND owner_id=? AND job_id=?',
                       (serialized,evidence['id'],job['owner'],job['id']))
    evidence['retrieval_provenance']=provenance


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
           "original": json_store.encode(fonte, 12000)}
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
           " afirmacao, relacao, status, original FROM evidence WHERE job_id=? AND owner_id=?")
    args = [job_id, owner]
    if status:
        sql += " AND status=?"
        args.append(status)
    rows = db.execute(sql + " ORDER BY id", args).fetchall()
    evidencias = []
    for r in rows:
        ev = {"id": r[0], "fonte_id": r[1], "url": r[2], "titulo": r[3], "dominio": r[4],
              "acessado_em": r[5], "publicado_em": r[6] or "", "trecho": r[7],
              "afirmacao": r[8], "relacao": r[9], "status": r[10]}
        try:
            metadata = json.loads(r[11] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        for key in ("doi", "authors", "year", "journal", "repository", "abstract",
                    "landing_url", "pdf_url", "license", "review_status", "publication_type", "publication_date_origin", "provider",
                    "provider_url", "source_url", "fetched_at", "abstract_untrusted",
                    "abstract_kind", "provider_metadata_untrusted", "content_scope",
                    "full_text_fetched", "full_text_url", "full_text_format", "extraction_scope", "full_document_read", "sections", "scientific_sections",
                    "vertical", "structured", "publicador", "imagens", "source_recovery",
                    "citation_count", "citation_count_kind", "doc_id", "chunk_id",
                    "section", "page", "content_hash", "version", "source",
                    "table_hint", "origem_declarada", "texto_lido", "trecho_usado",
                    "access_state", "answer_passages", "answerability", "retrieval_provenance", "document_id", "duplicate_of"):
            if key in metadata:
                ev[key] = metadata[key]
        evidencias.append(ev)
    return evidencias


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


def agente_busca(db, job: dict, etapa: dict, provedores: list, vistas: set,
                 deve_parar=None, prazo: float = 0) -> list:
    """Search Agent: consultas adaptativas (original + variação sem stopwords)."""
    base = etapa["alvo"]
    import query_intelligence as qi
    requirements=qi.requirement_contract(job['objetivo'])['requirements']
    requested={r['attribute'] for r in qi.answer_requirements(base)}
    requirement_ids=[r['id'] for r in requirements if not requested or r['attribute'] in requested]
    import search_orchestrator as orch
    variacao = orch.consulta_conteudo(base)
    if not variacao:
        variacao = re.sub(r"\bvale a pena\b", "", base, flags=re.I).strip(" .?!")
    consultas = [base] + ([variacao] if variacao and variacao != base else [])
    achados, falhas = [], []
    buscas_realizadas = 0
    cancelado = False
    parar = deve_parar or (lambda: False)
    etapas_por_consulta = job["usados"].setdefault("consultas_etapas", {})
    for q in consultas[:2]:
        import query_intelligence
        request = (job.get('ajustes') or {}).get('request') or {}
        if request.get('original_request') != job['objetivo']:
            request = query_intelligence.analyze(job['objetivo'])
        q=query_intelligence.constrain_discovery(q, request, lock_context=True)
        useful = any(orch._util_para_pedido(a, orch._termos_correspondencia(base), base) for a in achados)
        if useful or job["usados"].get("buscas", 0) + buscas_realizadas >= job["orcamento"].get("buscas", 0):
            break
        if parar() or (prazo and time.monotonic() >= prazo):
            cancelado = True
            break
        if q in vistas:
            continue
        chave = _chave_consulta(q)
        anterior = etapas_por_consulta.get(chave, "")
        if anterior and anterior != etapa["id"]:
            emitir(db, job["id"], job["owner"], "search", "search_skipped_duplicate",
                   "alerta", f"Consulta repetida ignorada: {q[:80]}.", {})
            continue
        vistas.add(q)
        etapas_por_consulta[chave] = etapa["id"]
        buscas_realizadas += 1
        t0 = time.monotonic()
        academic = [p for p in provedores if getattr(p, "academic_search", False)]
        general = [p for p in provedores if p not in academic]
        academic_terms = ("artigo", "artigos", "paper", "papers", "estudo", "estudos",
                          "study", "studies", "research", "academic", "scientific",
                          "publication", "publications", "journal", "scholar",
                          "literatura", "cientific", "científic", "doi", "openalex", "crossref")
        if academic and any(term in q.lower() for term in academic_terms):
            providers_for_query = academic + general
        else:
            providers_for_query = general + academic
        import query_intelligence
        if query_intelligence.analyze(q)['domain'] in ('news', 'events', 'air_travel', 'bus_travel', 'science', 'documents'):
            specialized = [p for p in providers_for_query if isinstance(p, ProvedorOrquestrado)]
            providers_for_query = specialized + [p for p in providers_for_query if p not in specialized]
        query_id='Q-'+hashlib.sha256((job['id']+'|'+etapa.get('id','')+'|'+q).encode()).hexdigest()[:20]
        trace_query={'retrieval_provenance':{'query_ids':[query_id],'requirement_ids':requirement_ids}}
        retrieval_trace.record(job['id'],etapa.get('id',''),trace_query,'QUERY_CREATED')
        retrieval_trace.record(job['id'],etapa.get('id',''),trace_query,'QUERY_SENT')
        queries=job.setdefault('ajustes',{}).setdefault('queries',{})
        with query_intelligence.discovery_scope(request,registry=queries,job_id=job['id'],
                                                step_id=etapa.get('id',''),requirement_ids=requirement_ids):
            encontrados, info = buscar_com_fallback(providers_for_query, q, 6,
                                                    deve_parar=parar)
        retrieval_trace.record(job['id'],etapa.get('id',''),trace_query,'PROVIDER_RESPONDED',duration_s=time.monotonic()-t0)
        if len(queries)<120:
            queries[query_id]={**queries.get(query_id,{}),'step_id':etapa.get('id',''),'requirement_ids':requirement_ids,
                               'query':q,'strategy':'replan' if etapa.get('replan_reason') else 'initial',
                               'plan_version':job.get('plano_versao',1)}
        encontrados=[{**a,'retrieval_provenance':_merge_provenance(a.get('retrieval_provenance'),{'query_ids':[query_id],'requirement_ids':requirement_ids,
                        'provider':str(a.get('discovery_provider') or a.get('origem') or (a.get('retrieval_provenance') or {}).get('provider') or info.get('provedor') or '')[:40], 'rank':rank+1,
                        'candidate_id':'C-'+hashlib.sha256((job['id']+'|'+str(a.get('url',''))).encode()).hexdigest()[:20]})}
                      for rank,a in enumerate(encontrados)]
        for candidate in encontrados:
            retrieval_trace.record(job['id'],etapa.get('id',''),candidate,'CANDIDATE_DISCOVERED')
        if info.get("cancelado"):
            for a in encontrados:
                if a["url"] not in {x["url"] for x in achados}:
                    achados.append(a)
            cancelado = True
            break
        if prazo and time.monotonic() >= prazo:
            cancelado = True
            break
        detalhe = info.get("detalhe") or {}
        if detalhe:
            rec = [str(x)[:160] for x in (detalhe.get("recuperacao") or []) if str(x).strip()]
            if rec:
                atuais = job["usados"].setdefault("recuperacao_busca", [])
                job["usados"]["recuperacao_busca"] = sorted(set(atuais) | set(rec))[:4]
            lac = [str(x)[:160] for x in (detalhe.get("lacunas") or []) if str(x).strip()]
            if lac:
                atuais = job["usados"].setdefault("lacunas_busca", [])
                job["usados"]["lacunas_busca"] = sorted(set(atuais) | set(lac))[:4]
        provs = job["usados"].setdefault("provedores", {})
        pm = provs.setdefault(info["provedor"] or "nenhum", {"ok": 0, "falhas": 0, "ms": 0})
        pm["ms"] += int((time.monotonic() - t0) * 1000)
        if encontrados:
            pm["ok"] += 1
        else:
            pm["falhas"] += 1
        emitir(db, job["id"], job["owner"], "search", "search_completed", "ok",
               f"Busca '{q[:60]}': {len(encontrados)} achados.",
               {"provedor": info["provedor"], "falhas": info["erros"],
                "estado": detalhe.get("estado", ""),
                "recovery_steps":(detalhe.get('etapas') or [])[:12]})
        falhas.extend(info["erros"])
        for a in encontrados:
            if a["url"] not in {x["url"] for x in achados}:
                achados.append(a)
            else:
                previous=next(x for x in achados if x['url']==a['url'])
                previous['retrieval_provenance']=_merge_provenance(previous.get('retrieval_provenance'),a.get('retrieval_provenance'))
    job["usados"]["buscas"] = job["usados"].get("buscas", 0) + buscas_realizadas
    if len(etapas_por_consulta) > 120:
        job["usados"]["consultas_etapas"] = dict(list(etapas_por_consulta.items())[-120:])
    prios = (job.get("ajustes") or {}).get("prioridades", [])
    if prios:
        achados.sort(key=lambda a: 0 if any(p in (a.get("url", "") or "").lower()
                                            for p in prios) else 1)
    if not achados and not cancelado:
        job["erros"].append(f"busca '{base[:60]}': sem resultados" +
                            (f" ({len(falhas)} falhas de provedor)" if falhas else ""))
        emitir(db, job["id"], job["owner"], "search", "search_completed", "alerta",
               f"Busca '{base[:60]}' sem resultados.", {})
    if not cancelado and not parar():
        _agregar_midia(db, job, media_evidence.discover_search_media(achados))
    return achados


def _agregar_midia(db, job: dict, itens: list) -> int:
    """Persist discovery metadata only; never promote media to evidence."""
    limite = max(0, int(job["orcamento"].get("midia", 8) or 0))
    if not limite or not itens:
        return 0
    itens = media_evidence.relevant_media(itens, job.get('objetivo') or '')
    import query_intelligence
    if query_intelligence.analyze(job.get('objetivo') or '')['domain']=='documents' and not re.search(r'\b(imagens?|fotos?|v[ií]deos?)\b',job.get('objetivo') or '',re.I):
        itens=[item for item in itens if item.get('type')=='document' and
               not urllib.parse.urlsplit(item.get('url') or '').path.lower().endswith(('.html','.htm'))]
    atuais = [item for item in (job.get("midia") or []) if isinstance(item, dict)]
    chaves = {(item.get("type"), item.get("url")) for item in atuais}
    adicionados = 0
    for item in itens:
        if not isinstance(item, dict) or len(atuais) >= limite:
            continue
        chave = (item.get("type"), item.get("url"))
        if not item.get("url") or chave in chaves:
            continue
        chaves.add(chave)
        atuais.append(item)
        adicionados += 1
    if adicionados:
        job["midia"] = atuais[:limite]
        resumo = media_evidence.resumo_midia(job["midia"])
        emitir(db, job["id"], job["owner"], "analyst", "media_discovered", "ok",
               f"{adicionados} mídia(s) descoberta(s); apenas metadados/links, sem análise.",
               {"added": adicionados, "summary": resumo,
                "claim_evidence": False, "analysis_state": "not_analyzed"})
    return adicionados


def agente_analista(db, job: dict, etapa: dict, achados: list, recuperar_fn=None,
                    teto_paginas: int = 3, deve_parar=None, prazo: float = 0) -> list:
    """Source Analyst: abre (em paralelo), extrai, pontua, registra (sequencial)."""
    import evidence_graph as _eg
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

    parar = deve_parar or (lambda: False)

    def _ler(a):
        if parar() or (prazo and time.monotonic() >= prazo):
            raise research.ResearchErro("Pesquisa cancelada.", "cancelada")
        if a.get("metadata_source") == "academic_provider":
            if recuperar_fn is None:
                rec=research._recuperar_um(a,None,max(0.5,min(8.0,prazo-time.monotonic())) if prazo else 8.0,job['objetivo'])
                if rec.get('full_text_fetched'):
                    return {**rec,'texto_lido':True,'midia':[]}
            return {"titulo": a.get("titulo") or a.get("title") or "",
                    "texto": (a.get("abstract") or "")[:academic_research.MAX_ABSTRACT_CHARS],
                    "final": a.get("landing_url") or a.get("url", ""),
                    "full_text_fetched": False, "midia": [],
                    'content_scope':a.get('content_scope','abstract_only'),
                    "texto_lido": False, "access_state": "metadata_only"}
        if a.get('content_scope')=='feed_metadata':
            return {'titulo':a.get('titulo',''),'texto':'','final':a['url'],'texto_lido':False,'content_scope':'feed_metadata','access_state':'snippet_only'}
        if recuperar_fn is not None:
            rec = recuperar_fn(a["url"])
            return {"titulo": rec.get("titulo") or a["titulo"],
                    "texto": (rec.get("texto") or "").strip(), "final": rec.get("final", ""),
                    "metadados": rec.get('metadados') if isinstance(rec.get('metadados'), dict) else {},
                    "secoes": (rec.get('secoes') or [])[:12],
                    "tabelas": (rec.get('tabelas') or [])[:5],
                    **{k:rec[k] for k in ('answer_passages','document_context','document_scan') if k in rec},
                    "links": (rec.get('links') or [])[:30],
                    "content_scope": rec.get('content_scope') or 'page_text',
                    "midia": rec.get("midia") or [],
                    "texto_lido": bool(rec.get("texto_lido", bool((rec.get("texto") or "").strip()))),
                    "trecho_usado": str(rec.get("trecho_usado") or "")[:1500],
                    "access_state": str(rec.get("access_state") or
                                        ("read" if (rec.get("texto") or "").strip()
                                         else "snippet_only"))[:40]}
        limite_tempo = 8.0
        if prazo:
            restante = prazo - time.monotonic()
            if restante <= 0:
                raise research.ResearchErro("Pesquisa cancelada.", "cancelada")
            limite_tempo = max(0.5, min(limite_tempo, restante))
        if urllib.parse.urlsplit(a["url"]).path.lower().endswith(".pdf"):
            rec = research._recuperar_um(a, None, limite_tempo, etapa["alvo"])
            return {**rec, "midia": [], "texto_lido": bool(rec.get("lida")),
                    "access_state": "read" if rec.get("lida") else "snippet_only"}
        try:
            final, pagina = research.baixar(
                a["url"], timeout=limite_tempo,
                max_bytes=max(65_536, int(job["orcamento"].get(
                    "max_bytes_pagina", research.MAX_PAGINA_BYTES))))
        except TypeError:
            final, pagina = research.baixar(a["url"], timeout=limite_tempo)
        if research.pagina_bloqueada(pagina):
            raise research.ResearchErro("Página bloqueada; conteúdo não usado como evidência.", "bloqueado")
        artigo = research.extrair_artigo(pagina, final, job['objetivo'],
                                         teto=research.MAX_TEXTO_PAGINA)
        texto = (artigo.get("texto") or "").strip()
        return {"titulo": artigo.get("titulo") or a["titulo"],
                "texto": texto, "final": final,
                "content_scope": artigo.get("content_scope", "page_text"),
                "metadados":artigo.get('metadados') or {},
                "secoes": (artigo.get('secoes') or [])[:12],
                "tabelas": (artigo.get('tabelas') or [])[:5],
                **{k:artigo[k] for k in ('answer_passages','document_context','document_scan') if k in artigo},
                "links": (artigo.get('links') or [])[:30],
                "imagens":artigo.get('imagens') or [],
                "midia": media_evidence.extrair_midia(pagina, final, artigo.get("titulo") or ""),
                "texto_lido": bool(texto) and not artigo.get("ilegivel", False),
                "trecho_usado": str(artigo.get("trecho_usado") or texto[:1500])[:1500],
                "access_state": "read" if texto else "snippet_only"}

    import search_orchestrator as orch
    subject = job['objetivo'] if etapa.get('replan_reason') else etapa['alvo']
    import query_intelligence
    import search_verticals
    saved_request = (job.get('ajustes') or {}).get('request') or {}
    request = saved_request if saved_request.get('original_request') == job['objetivo'] else query_intelligence.analyze(job['objetivo'])
    if request['domain'] == 'science':
        import research_gaps
        subject = research_gaps.science_subject(subject)
    termos_pedido = orch._termos_correspondencia(subject)

    def _candidato(a, rec):
        return {**a, 'titulo': rec.get('titulo') or a.get('titulo', ''),
                'trecho': rec.get('texto') or '',
                'content_scope': rec.get('content_scope') or a.get('content_scope', 'page_text'),
                'texto_lido': bool(rec.get('texto_lido')),
                'structured': (rec.get('metadados') or {}).get('structured', []),
                'publicado_em': (rec.get('metadados') or {}).get('publicado_em')
                or a.get('publicado_em') or (a.get('meta') or {}).get('publicado_em')}

    def _corresponde(a, rec):
        candidate = _candidato(a, rec)
        if orch._context_mismatch(candidate,job['objetivo']):
            return False
        if request['domain'] in ('news', 'events', 'air_travel', 'bus_travel', 'documents'):
            if not search_verticals.assess(request, candidate)['eligible']:
                return False
        coverage = _eg.requirement_coverage(job['objetivo'],[{**rec,'url':a['url']}])
        if (coverage['passages'] and not any(r['constraints']['must_preserve'] for r in coverage['requirements'])):
            return True  # Explicit entity/relation, not a loose keyword match.
        return not termos_pedido or orch._util_para_pedido(candidate, termos_pedido, subject)

    def _util(a, rec):
        texto = (rec.get('texto') or '').strip()
        coverage = _eg.requirement_coverage(job['objetivo'], [{**rec,'url':a['url']}])
        return (bool(texto) and _evidencia_lida({**rec, 'trecho': texto}) and _corresponde(a, rec)
                and (not coverage['applicable'] or bool(coverage['passages'])))

    # Preserve ranking, but never spend a page slot on the same canonical URL twice.
    unicos, vistas = [], set()
    for a in achados:
        try:
            chave = orch.canonizar_url(a.get('url', ''))
        except ValueError:
            continue
        if chave and chave not in vistas:
            vistas.add(chave)
            unicos.append(a)
        elif chave:
            retrieval_trace.record(job['id'], etapa.get('id', ''), a, 'SKIPPED_DUPLICATE')
    # RSS is discovery, not a network page read. It must not consume all three
    # quick-mode slots before an original candidate can even reach the reader.
    discovery_only = [a for a in unicos if a.get('content_scope')=='feed_metadata']
    for a in discovery_only:
        retrieval_trace.record(job['id'], etapa.get('id', ''), a, 'SKIPPED_AGGREGATOR')
    achados = [a for a in unicos if a.get('content_scope')!='feed_metadata']
    if request['domain']=='news':
        achados.sort(key=lambda a: not bool(a.get('source_recovery')))
    historico_falhas = job['usados'].get('failed_source_reads', [])
    if not isinstance(historico_falhas, list):
        historico_falhas = []
    falhas_leitura = {key for key in historico_falhas[:80]
                     if isinstance(key, str) and re.fullmatch(r'[0-9a-f]{64}', key)}

    def _chave_fonte(a):
        return hashlib.sha256(orch.canonizar_url(a['url']).encode('utf-8')).hexdigest()

    def _registrar_falha(a):
        # No URL/query string or raw exception is stored in the job counters.
        if not parar() and (not prazo or time.monotonic() < prazo) and len(falhas_leitura) < 80:
            falhas_leitura.add(_chave_fonte(a))
            job['usados']['failed_source_reads'] = sorted(falhas_leitura)

    reader_scope='network'
    if recuperar_fn is not None:
        reader_scope=getattr(recuperar_fn,'document_cache_identity','')
        if not reader_scope:
            reader_scope=_nid('reader')
            try:setattr(recuperar_fn,'document_cache_identity',reader_scope)
            except (AttributeError,TypeError):pass
    cache_job={**job,'document_reader':reader_scope}
    cached_pages, stale_urls = {}, set()
    for candidate in achados:
        state,rec=research.document_cache_get(db,cache_job,candidate['url'])
        retrieval_trace.record(job['id'],etapa.get('id',''),candidate,state)
        if rec is not None:
            cached_pages[candidate['url']]=rec
            retrieval_trace.record(job['id'],etapa.get('id',''),candidate,'CACHE_REUSE',rec=rec)
            retrieval_trace.record(job['id'],etapa.get('id',''),candidate,'DOCUMENT_ALREADY_READ',rec=rec)
        elif state=='CACHE_STALE':
            stale_urls.add(orch.canonizar_url(candidate['url']))
    anteriores = {orch.canonizar_url(e.get("url", "")): e for e in _evidencias_job(db, job)
                  if _evidencia_lida(e) and orch.canonizar_url(e.get('url','')) not in stale_urls}
    reutilizadas = [anteriores[orch.canonizar_url(a.get("url", ""))] for a in achados
                    if orch.canonizar_url(a.get("url", "")) in anteriores][:teto_paginas]
    for candidate in achados:
        ev=anteriores.get(orch.canonizar_url(candidate.get('url','')))
        if ev is not None:_update_reused_provenance(db,job,ev,candidate)
    novas_paginas = [a for a in achados if orch.canonizar_url(a.get("url", "")) not in anteriores]
    cached_candidates=[a for a in novas_paginas if a['url'] in cached_pages]
    novas_paginas=[a for a in novas_paginas if a['url'] not in cached_pages]
    ignoradas = sum(_chave_fonte(a) in falhas_leitura for a in novas_paginas)
    novas_paginas = [a for a in novas_paginas if _chave_fonte(a) not in falhas_leitura]
    if ignoradas:
        emitir(db, job['id'], job['owner'], 'analyst', 'source_failed_read_skipped', 'alerta',
               f'{ignoradas} fonte(s) com falha de download anterior ignorada(s) nesta pesquisa.',
               {'skipped': ignoradas})
    restantes = max(0, job["orcamento"].get("paginas", 0) - job["usados"].get("paginas", 0))
    alvos = novas_paginas[:min(teto_paginas, restantes)]
    limite_tentativas = min(restantes, max(0, teto_paginas) * 2)
    if reutilizadas:
        emitir(db, job["id"], job["owner"], "analyst", "source_reused", "ok",
               f"{len(reutilizadas)} fonte(s) já lida(s) reutilizada(s), sem novo download.", {})
    if parar() or (prazo and time.monotonic() >= prazo):
        return reutilizadas
    job["usados"]["paginas"] = job["usados"].get("paginas", 0) + len(alvos)
    baixados: dict = dict(cached_pages)
    def read_trace(source, state, rec=None, code='', coverage=None):
        rec=rec or {}
        reason = {'extracted': 'CONTENT_EXTRACTED', 'no_readable_content': 'CONTENT_EMPTY',
                  'relevance_rejected': 'RELEVANCE_REJECTED', 'topic_only': 'PASSAGE_NOT_FOUND',
                  'evidence_stored': 'EVIDENCE_STORED', 'discovery_stored': 'DISCOVERY_ONLY',
                  'reader_failed': 'EXTRACTION_FAILED', 'fetch_failed': 'FETCH_FAILED'}.get(state, state)
        if state == 'fetch_failed' and code in ('bloqueado','rate_limit','rate_limited'):
            reason = 'FETCH_BLOCKED'
        elif state == 'fetch_failed' and code == 'redirect':
            reason = 'REDIRECT_INVALID'
        elif state == 'reader_failed' and code == 'TimeoutError':
            reason = 'FETCH_TIMEOUT'
        retrieval_trace.record(job['id'], etapa.get('id', ''), source, reason, rec=rec, coverage=coverage, reason_code=str(code).upper())
        def public_url(value):
            try:
                parts=urllib.parse.urlsplit(value or '')
                return urllib.parse.urlunsplit((parts.scheme,parts.netloc.rsplit('@',1)[-1],parts.path,'',''))[:500]
            except ValueError: return ''
        transitions = {'extracted':'READABLE', 'no_readable_content':'FETCHED',
                       'relevance_rejected':'REJECTED', 'evidence_stored':'EVIDENCE_ELIGIBLE',
                       'discovery_stored':'DISCOVERED', 'reader_failed':'REJECTED',
                       'fetch_failed':'BLOCKED' if code in ('bloqueado','rate_limit','rate_limited') else 'REJECTED'}
        emit_meta={'url':public_url(source.get('url')), 'final_url':public_url(rec.get('final')),
            'source_state': transitions.get(state, 'DISCOVERED'),
            'stage':state,'code':str(code)[:60], 'scope':rec.get('content_scope',''),
            'extracted_chars':len(rec.get('texto') or ''), 'read':bool(rec.get('texto_lido')),
            'published_at':(rec.get('metadados') or {}).get('publicado_em') or source.get('publicado_em') or (source.get('meta') or {}).get('publicado_em',''),
            'excerpt':str(rec.get('trecho_usado') or rec.get('texto') or '')[:400]}
        emitir(db,job['id'],job['owner'],'analyst','source_read_trace','alerta' if code else 'ok',
               'Leitura de fonte: '+state+'.',emit_meta)

    def _ler_cronometrado(a):
        with retrieval_trace.source_scope(job['id'], etapa.get('id',''), a):
            rec = _ler(a)
        return rec, time.monotonic()

    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="julialer")
    for source in alvos:
        retrieval_trace.record(job['id'], etapa.get('id', ''), source, 'SELECTED', charged=True,budget=job['usados'])
    futs = {pool.submit(copy_context().run, _ler_cronometrado, a): a for a in alvos}
    pendentes = set(futs)
    cancelado = False
    expirado = False
    try:
        while pendentes:
            if parar():
                cancelado = True
                break
            restante = prazo - time.monotonic() if prazo else 0.1
            expirado = bool(prazo and restante <= 0)
            prontas, pendentes = wait(pendentes, timeout=max(0, min(0.1, restante)),
                                      return_when=FIRST_COMPLETED)
            for fut in prontas:
                a = futs[fut]
                substituir = True
                concluida = False
                try:
                    rec, concluido_em = fut.result()
                    concluida = True
                    if not prazo or concluido_em <= prazo:
                        baixados[a["url"]] = rec
                        research.document_cache_put(db,cache_job,a['url'],rec)
                        if rec.get('duplicate_of'):
                            retrieval_trace.record(job['id'],etapa.get('id',''),a,'DOCUMENT_DEDUPLICATED',rec=rec,
                                                   reason_code='IDENTICAL_BOUNDED_EXTRACTION')
                        read_trace(a,'extracted' if rec.get('texto') else 'no_readable_content',rec)
                        substituir = not _util(a, rec)
                        coverage_read = _eg.requirement_coverage(job['objetivo'],[{**rec,'url':a['url']}])
                        if rec.get('texto_lido') and coverage_read['applicable'] and not coverage_read['complete']:
                            from web_extract import navigation_candidates
                            links = navigation_candidates(rec.get('links'), job['objetivo'], rec.get('final') or a['url'],
                                a.get('_navigation_depth',0), min(2,job['orcamento'].get('profundidade',1)))
                            for link in reversed(links):
                                canonical = orch.canonizar_url(link['url'])
                                if canonical and canonical not in vistas:
                                    vistas.add(canonical)
                                    novas_paginas.insert(len(alvos),link)
                                    substituir = True
                                    emitir(db,job['id'],job['owner'],'analyst','navigation_candidate','ok',
                                           'Link específico realmente encontrado; leitura sujeita ao mesmo orçamento.',
                                           {'action':'FOLLOW_LINK','url':link['url'],'parent':a['url'],
                                            'depth':link['_navigation_depth']})
                except research.ResearchErro as exc:
                    if parar():
                        cancelado = True
                        break
                    if exc.codigo != "cancelada":
                        if not concluida:
                            _registrar_falha(a)
                        emitir(db, job["id"], job["owner"], "analyst", "source_opened", "falha",
                               f"Ignorada ({exc.codigo}): {a['url'][:60]}.", {})
                        read_trace(a,'fetch_failed',code=exc.codigo)
                    else:
                        substituir = False
                except Exception as exc:
                    if not concluida and isinstance(exc, OSError):
                        _registrar_falha(a)
                    emitir(db, job["id"], job["owner"], "analyst", "source_opened", "falha",
                           f"Ignorada ({type(exc).__name__}): {a['url'][:60]}.", {})
                    read_trace(a,'reader_failed',code=type(exc).__name__)
                if (substituir and not parar() and (not prazo or time.monotonic() < prazo)
                        and len(alvos) < min(limite_tentativas, len(novas_paginas))):
                    proxima = novas_paginas[len(alvos)]
                    alvos.append(proxima)
                    job['usados']['paginas'] += 1
                    retrieval_trace.record(job['id'], etapa.get('id', ''), proxima, 'SELECTED', charged=True)
                    novo_fut = pool.submit(copy_context().run, _ler_cronometrado, proxima)
                    futs[novo_fut] = proxima
                    pendentes.add(novo_fut)
                    emitir(db, job['id'], job['owner'], 'analyst', 'source_replacement_started', 'ok',
                           'Tentando a próxima fonte após leitura sem conteúdo útil, dentro do orçamento.',
                           {'previous_source_id': str(a.get('id') or '')[:120],
                            'source_id': str(proxima.get('id') or '')[:120]})
            if cancelado:
                break
            if expirado:
                break
    finally:
        for fut in futs:
            fut.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
    attempted_urls = {a['url'] for a in alvos}
    for candidate in novas_paginas:
        if candidate['url'] not in attempted_urls:
            reason = ('BUDGET_EXHAUSTED' if job['usados']['paginas'] >= job['orcamento']['paginas']
                      else 'SKIPPED_LOW_PRIORITY')
            retrieval_trace.record(job['id'], etapa.get('id',''), candidate, reason)
    if expirado:
        emitir(db, job["id"], job["owner"], "analyst", "source_reading_timeout", "alerta",
               "Prazo de leitura esgotado; apenas resultados concluídos no prazo serão usados.",
               {"completed": len(baixados), "attempted": len(alvos)})
    if not cancelado and not parar():
        for lead in discovery_only[:3]:
            baixados[lead['url']]={'titulo':lead.get('titulo',''),'texto':'','final':lead['url'],
                'texto_lido':False,'content_scope':'feed_metadata','access_state':'snippet_only'}
            alvos.append(lead)
    alvos.extend(cached_candidates)
    evidencias = list(reutilizadas)
    for a in alvos:
        if cancelado or parar():
            break
        rec = baixados.get(a["url"])
        if rec is None:
            continue
        midia = rec.get("midia") or []
        if midia:
            _agregar_midia(db, job, midia)
        texto = rec["texto"]
        if not texto and not a.get("trecho"):
            emitir(db, job["id"], job["owner"], "analyst", "source_opened",
                   "vazia", f"Sem texto: {a['url'][:60]}.", {})
            continue
        academic = a.get("metadata_source") == "academic_provider"
        candidate = _candidato(a, rec)
        if texto and not _corresponde(a, rec):
            read_trace(a,'relevance_rejected',rec,code=','.join(search_verticals.assess(request,candidate).get('reasons')
                or orch._context_mismatch(candidate,job['objetivo']) or ['TOPIC_MISMATCH']))
            emitir(db, job["id"], job["owner"], "analyst", "source_irrelevant", "alerta",
                   "Fonte aberta sem correspondência demonstrável com o pedido; não usada como evidência.", {})
            continue
        trecho_fonte = str(rec.get("trecho_usado") or "").strip()
        answer_coverage = _eg.requirement_coverage(job['objetivo'], [{**rec,'url':a['url']}])
        answer_passages = _eg.select_answer_passages(answer_coverage)
        if answer_coverage['applicable'] and not answer_passages:
            read_trace(a,'topic_only',rec,code='NO_ANSWER_PASSAGE')
            continue
        if answer_passages:
            for label,event in (('DIRECT_SUPPORT','EVIDENCE_SUPPORTED'),('PARTIAL_SUPPORT','EVIDENCE_PARTIAL')):
                matching=[p for p in answer_passages if p.get('support_label')==label]
                if matching:retrieval_trace.record(job['id'],etapa.get('id',''),a,event,rec=rec,coverage={**answer_coverage,'passages':matching})
            retrieval_trace.record(job['id'],etapa.get('id',''),a,'PASSAGE_SELECTED',rec=rec,coverage={**answer_coverage,'passages':answer_passages})
            trecho_fonte = answer_passages[0]['text']
        history_field = re.search(r'\b(funda[cç][aã]o|fundad[ao]|fundadores?|inaugura[cç][aã]o|inaugurad[ao]|founded)\b', texto, re.I)
        if not answer_passages and not academic and re.search(r'\bhist[oó]ria\b', job['objetivo'], re.I) and history_field:
            # Generic source-request words can otherwise pick a maintenance
            # notice instead of the requested founding/history information.
            start = max(0, history_field.start() - 80)
            while start and not texto[start - 1].isspace():
                start -= 1
            end = min(len(texto), start + 1500)
            while end < len(texto) and end > start and not texto[end].isspace():
                end -= 1
            trecho_fonte = texto[start:end].strip()
        if not trecho_fonte:
            trecho_fonte = texto[:1500] or str(a.get("trecho") or "")
        fonte = {"id": a.get("id", ""), "url": a["url"],
                 "titulo": rec.get("titulo") or a.get("titulo", ""),
                 "content_scope": rec.get("content_scope", "page_text"),
                 **({"full_text_fetched": False} if rec.get("content_scope") == "abstract_only" else {}),
                 "dominio": research._dominio(a["url"]),
                 "texto_lido": bool(rec.get("texto_lido")) and not academic,
                 "trecho_usado": trecho_fonte[:1500],
                 "access_state": rec.get("access_state") or (
                     "metadata_only" if academic else
                     ("read" if texto else "snippet_only")),
                 "acessado_em": rec.get('fetched_at') or (a.get("fetched_at") if academic else None)
                 or research.agora_iso()}
        import query_intelligence
        import search_verticals
        fonte['vertical']=search_verticals.assess(request,candidate)
        fonte['publicado_em']=candidate.get('publicado_em') or ''
        fonte['structured']=(candidate.get('structured') or [])[:2]
        fonte['publicador']=(rec.get('metadados') or {}).get('site') or a.get('publicador','')
        fonte['imagens'] = (rec.get('imagens') or [])[:2]
        for key in ('retrieval_provenance',):
            if key in a:fonte[key]=a[key]
        for key in ('content_hash','document_id','duplicate_of'):
            if key in rec:fonte[key]=rec[key]
        if answer_coverage['applicable']:
            fonte['answer_passages'] = answer_passages
            fonte['answerability'] = {'state':'DIRECT_ANSWER' if answer_coverage['complete'] else 'PARTIAL_ANSWER',
                                     'scope':answer_coverage['scope'],
                                     'aspects':[r['description'] for r in answer_coverage['requirements'] if r['state']=='SUPPORTED'],
                                     'partial_aspects':[r['description'] for r in answer_coverage['requirements'] if r['state']=='PARTIALLY_SUPPORTED']}
        if a.get('source_recovery'):
            fonte['source_recovery'] = {**a['source_recovery'],
                'state':'original_read' if fonte['texto_lido'] else 'original_unread',
                'final_url':rec.get('final') or a['url']}
        if academic:
            for key in ("doi", "authors", "year", "journal", "repository", "abstract",
                        "landing_url", "pdf_url", "license", "review_status", "publication_type", "publication_date_origin", "provider",
                        "provider_url", "source_url", "fetched_at", "abstract_untrusted",
                        "abstract_kind", "provider_metadata_untrusted", "content_scope",
                        "full_text_fetched",
                        "citation_count", "citation_count_kind"):
                if key in a:
                    fonte[key] = a[key]
            fonte['full_text_fetched']=bool(rec.get('full_text_fetched'))
            fonte['full_text_url']=rec.get('full_text_url','')
            fonte['full_text_format']=rec.get('full_text_format','')
            fonte['extraction_scope']=rec.get('extraction_scope','')
            fonte['full_document_read']=False
            fonte['scientific_sections']=rec.get('scientific_sections') or []
            fonte['sections']=[{'title': str(s.get('titulo') or '')[:160], 'text': str(s.get('texto') or '')[:800]}
                               for s in (rec.get('secoes') or [])[:8] if isinstance(s,dict)]
            fonte['content_scope']=rec.get('content_scope',a.get('content_scope','metadata_only'))
            fonte['texto_lido']=bool(rec.get('full_text_fetched'))
            fonte['access_state']='read' if rec.get('full_text_fetched') else 'metadata_only'
            fonte["publicado_em"] = str(a.get("publicado_em") or a.get("year") or "")
        if not academic and fonte['texto_lido'] and rec.get('secoes'):
            fonte['scientific_sections'] = academic_research.scientific_sections(rec)
        doi = str(a.get('doi') or '')
        if not academic and re.fullmatch(r'10\.\d{4,9}/\S+', doi) and doi.casefold() in texto.casefold():
            fonte['doi'] = doi[:200]
        ev = registrar_evidencia(db, job, fonte, trecho_fonte)
        for key in ('retrieval_provenance','content_hash','document_id','duplicate_of'):
            if key in fonte:ev[key]=fonte[key]
        if answer_coverage['applicable']:
            ev['answer_passages'] = answer_passages
            ev['answerability'] = fonte['answerability']
        if fonte.get('doi'):
            ev['doi'] = fonte['doi']
        if fonte.get('scientific_sections'):
            ev['scientific_sections'] = fonte['scientific_sections']
        read_trace(a,'evidence_stored' if fonte['texto_lido'] else 'discovery_stored',rec, coverage=answer_coverage)
        for key in ('vertical','structured','publicador'):
            ev[key]=fonte[key]
        if academic:
            ev.update({key: value for key, value in fonte.items()
                       if key not in ("url", "titulo", "dominio", "acessado_em")})
            ev["content_scope"] = fonte['content_scope']
            ev["abstract_untrusted"] = bool(a.get("abstract_untrusted", False))
        else:
            ev["texto_lido"] = fonte["texto_lido"]
            ev["content_scope"] = fonte["content_scope"]
            if "full_text_fetched" in fonte:
                ev["full_text_fetched"] = fonte["full_text_fetched"]
            ev["access_state"] = fonte["access_state"]
            ev["trecho_usado"] = fonte["trecho_usado"]
        ev["score"] = _relevancia(etapa["alvo"], ev["trecho"])
        evidencias.append(ev)
        descricao = (f"PDF aberto lido de {ev['dominio']}; identidade bibliográfica conferida."
                     if ev.get('full_text_fetched') else f"Metadados acadêmicos de {ev['dominio']}; "
                     f"{'resumo apenas' if academic and texto else 'sem texto completo'}."
                     if academic else f"Lida {ev['dominio']} (relevância {ev['score']})."
                     if ev.get('texto_lido') else f"Fonte encontrada em {ev['dominio']}; conteúdo não lido.")
        emitir(db, job["id"], job["owner"], "analyst", "extraction_completed", "ok",
               descricao, {})
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
            for passage in answer_passages[:8]:
                np = _eg.criar_no(db,job['owner'],job['id'],'evidence','passage:'+passage['id'],
                    {'passage_id':passage['id'],'evidence_id':ev['id'],'text_span':passage['text_span'],
                     'section':passage.get('section',''),'url':ev['url'],
                     **{k:passage[k] for k in ('section_id','source_span','element_type','context_heading') if k in passage}})
                _eg.ligar(db,job['owner'],job['id'],np,ndoc,'DERIVED_FROM','literal_extraction','Passagem do texto extraído, não do HTML bruto.')
                if passage.get('section_id') and passage.get('section'):
                    ns=_eg.criar_no(db,job['owner'],job['id'],'document','section:'+passage['section_id'],
                        {'type':'section','section_id':passage['section_id'],'title':passage['section'],
                         'source_sha256':(passage.get('source_span') or {}).get('sha256','')})
                    _eg.ligar(db,job['owner'],job['id'],ns,ndoc,'DERIVED_FROM','literal_extraction','Seção identificada no documento.')
                    _eg.ligar(db,job['owner'],job['id'],np,ns,'DERIVED_FROM','literal_extraction','Passagem da seção identificada.')
                for rid in passage.get('requirement_ids') or [passage['requirement_id']]:
                    req = next(r for r in answer_coverage['requirements'] if r['id']==rid)
                    nr = _eg.criar_no(db,job['owner'],job['id'],'claim','requirement:'+req['id'],
                        {'requirement_id':req['id'],'description':req['description'],'entity':req['entity']})
                    _eg.ligar(db,job['owner'],job['id'],np,nr,'REQUIRES_VERIFICATION','explicit_relation_pattern',
                              'Passagem candidata ao requisito; vínculo não comprova verdade factual.')
            emitir(db, job["id"], job["owner"], "analyst", "evidence_linked", "ok",
                   f"Evidência ligada ao documento ({ev['dominio']}).",
                   {"evidencia_id": ev["id"], "dominio": ev["dominio"],
                    "trecho": ev["trecho"][:300], "url": ev["url"][:200]})
        except Exception as exc:
            emitir(db,job['id'],job['owner'],'analyst','evidence_graph_failed','alerta',
                   'Evidência preservada; vínculo do grafo não concluído.',{'code':type(exc).__name__})
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


def _evidencia_lida(e: dict) -> bool:
    if e.get("access_state") in ("snippet_only", "found", "inaccessible") or e.get("status") in ("encontrada", "inacessivel"):
        return False
    if e.get("content_scope") == "abstract_only" and (e.get("abstract") or e.get("trecho")):
        return True  # The retrieved abstract supports only its own content.
    if "texto_lido" in e:
        return bool(e["texto_lido"])
    if e.get("access_state"):
        return e["access_state"] == "read"
    return bool(e.get("trecho"))  # Legacy manually registered evidence, not discovered URLs.


def agente_verificador(db, job: dict, evidencias: list) -> list:
    """Fact Checker 2.0: claims v2 × evidências (regras válidas; resto UNVERIFIED).

    Mantém chaves {afirmacao, estado, cobertura_lexica} + metodo/relacoes.
    """
    import evidence_graph as _eg
    elegiveis = [e for e in evidencias if _evidencia_lida(e)]
    base = job["objetivo"] + ". " + " ".join(e.get("trecho", "") for e in elegiveis)
    claims = _eg.extrair_afirmacoes_v2(base)
    if not claims and evidencias:
        claims = [{"texto": job["objetivo"], "condicoes": {"comparado_a": "", "metrica": "",
                                                           "quantidades": [], "datas": []}}]
    vereditos = []
    nos_lote = []
    arestas_lote = []
    for c in claims[:12]:
        emitir(db, job["id"], job["owner"], "checker", "claim_identified", "ok",
               f"Afirmação: {c['texto'][:90]}", {})
        contrad = [e["id"] for e in elegiveis if e.get("status") == "contradiz"
                   and _relevancia(c["texto"], e.get("afirmacao") or e.get("trecho", "")) > 0]
        if contrad:
            res = {"estado": "CONTRADICTED", "metodo": "evidencia-contradiz",
                   "evidencia": contrad[0], "cobertura_lexica": 0.0}
        else:
            res = _eg.verificar_claim(c, [{"id": e["id"], "trecho": e["trecho"]} for e in elegiveis])
        ncl = _eg.no_id("claim", job["id"], c["texto"][:200])
        nos_lote.append(("claim", c["texto"][:200],
                         {"texto": c["texto"][:500], "condicoes": c["condicoes"]}))
        fontes_detalhe = []
        for e in evidencias:
            nev = _eg.no_id("evidence", job["id"], e["id"])
            relacao = "REQUIRES_VERIFICATION"
            if res["estado"] == "SUPPORTED" and res.get("evidencia") == e["id"]:
                relacao = "SUPPORTS"
                arestas_lote.append((nev, ncl, relacao,
                                     res["metodo"], "quantidade exata no trecho"))
            elif res["estado"] == "CONTRADICTED" and e["id"] in contrad:
                relacao = "CONTRADICTS"
                arestas_lote.append((nev, ncl, relacao,
                                     "evidencia-contradiz", "fonte marcada como contraditória"))
            elif _evidencia_lida(e) and res["estado"] == "PARTIALLY_SUPPORTED" and \
                    _relevancia(c["texto"], e.get("trecho", "")) >= 0.25:
                relacao = "PARTIALLY_SUPPORTS"
                arestas_lote.append((nev, ncl, relacao,
                                     res["metodo"], "cobertura parcial"))
            elif _relevancia(c["texto"], e.get("trecho", "")) > 0:
                relacao = "MENTIONS"
                arestas_lote.append((nev, ncl, relacao,
                                     "lexico", "citação contextual"))
            else:
                arestas_lote.append((nev, ncl, relacao,
                                     "sem-cobertura", "sem relação lexical detectada"))
            lida = bool(e.get("texto_lido")) if "texto_lido" in e else (
                e.get("access_state") == "read" if e.get("access_state")
                else bool(e.get("trecho")))
            if relacao in ("SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS") or \
                    len(fontes_detalhe) < 8:
                fontes_detalhe.append({
                    "evidence_id": e["id"], "title": e.get("titulo", "")[:160],
                    "url": e.get("url", "")[:500], "domain": e.get("dominio", "")[:120],
                    "relation": relacao, "read": lida,
                    "access_state": e.get("access_state", "read" if lida else "snippet_only"),
                    "used_excerpt": e.get("trecho", "")[:500],
                    "published_at": e.get("publicado_em", ""),
                })
        supporting_ids = [item["evidence_id"] for item in fontes_detalhe
                          if item["relation"] in ("SUPPORTS", "PARTIALLY_SUPPORTS")]
        contradicting_ids = [item["evidence_id"] for item in fontes_detalhe
                             if item["relation"] == "CONTRADICTS"]
        evidence_ids = list(dict.fromkeys(
            supporting_ids + contradicting_ids
            + ([res["evidencia"]] if res.get("evidencia") else [])))
        if not evidence_ids and fontes_detalhe:
            evidence_ids = [item["evidence_id"] for item in fontes_detalhe[:3]]
        vereditos.append({"afirmacao": c["texto"], "estado": res["estado"],
                          "cobertura_lexica": res.get("cobertura_lexica", 0.0),
                          "metodo": res.get("metodo", ""),
                          "condicoes_ausentes": res.get("condicoes_ausentes", []),
                          "evidence_ids": evidence_ids,
                          "supporting_ids": supporting_ids,
                          "contradicting_ids": contradicting_ids,
                          "fontes": fontes_detalhe[:12],
                          "fontes_encontradas": len(evidencias),
                          "fontes_lidas": sum(1 for item in fontes_detalhe if item["read"]),
                          "fontes_usadas": sum(1 for item in fontes_detalhe
                                               if item["relation"] in (
                                                   "SUPPORTS", "PARTIALLY_SUPPORTS",
                                                   "CONTRADICTS"))})
        emitir(db, job["id"], job["owner"], "checker", "claim_verified", "ok",
               f"{res['estado']} ({res.get('metodo', '?')}): {c['texto'][:90]}",
               {"estado": res["estado"], "afirmacao": c["texto"][:200],
                "fontes_encontradas": len(evidencias),
                "fontes_lidas": sum(1 for item in fontes_detalhe if item["read"]),
                "fontes_usadas": sum(1 for item in fontes_detalhe
                                     if item["relation"] in (
                                         "SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS"))})
    try:
        _eg.criar_nos_lote(db, job["owner"], job["id"], nos_lote)
        _eg.ligar_lote(db, job["owner"], job["id"], arestas_lote)
    except Exception as exc:
        emitir(db, job["id"], job["owner"], "checker", "claim_verified", "alerta",
               f"Grafo parcial ({type(exc).__name__}); vereditos preservados.", {})
    emitir(db, job["id"], job["owner"], "checker", "claim_verification_completed", "ok",
           f"{len(vereditos)} afirmações avaliadas.", {})
    return vereditos


def analisar_independencia_job(db, job: dict, evidencias: list) -> list:
    """Source Independence: pares de documentos → laudo + arestas."""
    import evidence_graph as _eg
    docs = [{"url": e.get("url", ""), "texto": e.get("trecho", ""), "id": e.get("id", "")}
            for e in evidencias or [] if _evidencia_lida(e)]
    laudos = []
    arestas = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            laudo = _eg.analisar_independencia(docs[i], docs[j])
            laudo.update({"a": docs[i]["id"], "b": docs[j]["id"]})
            laudos.append(laudo)
            na = _eg.no_id("document", job["id"], _eg.hash_conteudo(docs[i]["texto"][:1500]))
            nb = _eg.no_id("document", job["id"], _eg.hash_conteudo(docs[j]["texto"][:1500]))
            arestas.append((na, nb, laudo["relacao"], "independencia", laudo["motivo"][:200]))
    try:
        _eg.ligar_lote(db, job["owner"], job["id"], arestas)
    except Exception:
        pass
    for laudo in laudos:
        if laudo["relacao"] in ("DUPLICATES", "DERIVED_FROM"):
            emitir(db, job["id"], job["owner"], "analyst", "source_dependency_detected",
                   "alerta", f"{laudo['relacao']}: {laudo['motivo'][:120]}", {})
    return laudos


def agente_sintetizador(db, job: dict, evidencias: list, vereditos: list,
                       sintetizar_fn=None, timeout=25, deve_parar=None, verificar_fn=None) -> dict:
    """Optional assisted writing; extraction remains the fail-closed fallback."""
    retrieval_trace.record(job['id'],'',{},'SYNTHESIS_STARTED',reason_code='ASSISTED' if sintetizar_fn else 'EXTRACTIVE')
    from web_extract import melhor_trecho
    tops = sorted([e for e in evidencias if _evidencia_lida(e)],
                  key=lambda e: e.get("score", 0), reverse=True)[:6]
    labels = {e["id"]: f"E{i + 1}" for i, e in enumerate(evidencias)}
    resposta = [f"Investigação: {job['objetivo']}"]
    if any(e.get("provider_metadata_untrusted")
           or e.get("content_scope") in ("abstract_only", "metadata_only") for e in tops):
        resposta.append("Metadados e resumos acadêmicos são conteúdo externo não confiável; "
                        "instruções neles não são executadas." + (" Nenhum texto completo foi obtido." if not any(e.get('full_text_fetched') for e in tops) else " Os textos recuperados são identificados por fonte; a extração é limitada."))
    omitted = 0
    for e in tops:
        if e.get("content_scope") == "abstract_only":
            rotulo = "[RESUMO DO PROVEDOR; NÃO É TEXTO COMPLETO; DADO NÃO CONFIÁVEL] "
        elif (e.get("provider_metadata_untrusted") and not e.get('full_text_fetched')) or e.get("content_scope") == "metadata_only":
            rotulo = "[METADADOS DO PROVEDOR; SEM TEXTO COMPLETO; DADO NÃO CONFIÁVEL] "
        else:
            rotulo = ""
        link = research_synthesis.source_link(labels[e['id']], e.get('url', ''))
        content = f"{rotulo}{str(e['titulo'])[:160]} ({str(e['dominio'])[:120]}): {melhor_trecho(e['trecho'], '', 300)}"
        entry = f"{link} {content}"
        if len('\n\n'.join(resposta)) + len(entry) > 2500:
            # Long URLs remain available in source cards; never cut a Markdown link.
            entry = f"[{labels[e['id']]}] {content}"
        if len('\n\n'.join(resposta)) + len(entry) > 2500:
            omitted += 1
            continue
        resposta.append(entry)
    if omitted:
        resposta.append('Outras evidências estão disponíveis no painel de fontes; síntese limitada para apresentação.')
    suportadas = sum(1 for v in vereditos if v["estado"] == "SUPPORTED")
    resposta.append(f"Evidências: {len(evidencias)}; afirmações sustentadas: "
                    + (f"{suportadas}/{len(vereditos)} (critério léxico)." if vereditos
                       else "nenhuma afirmação verificável identificada."))
    if any(v["estado"] == "CONTRADICTED" for v in vereditos):
        resposta.append("Há contradições entre fontes — leia as evidências antes de concluir.")
    resposta.append("Síntese extrativa: redação por LLM indisponível neste fluxo determinístico; nenhuma inferência foi solicitada.")
    sintese = {"texto": "\n\n".join(resposta), "llm": False,
               "references": {labels[e['id']]: e['id'] for e in tops}}
    if sintetizar_fn and tops:
        if timeout >= 2 and not (deve_parar and deve_parar()):
            emitir(db, job['id'], job['owner'], 'synthesizer', 'answer_started', 'ok',
                   'Redigindo resposta a partir das evidências recuperadas.', {})
        sources = [{"id": labels[e['id']], "evidence_id": e['id'],
                    "title": str(e.get('titulo', ''))[:160], "url": e.get('url', ''),
                    "excerpt": str(e.get('trecho', ''))[:1800],
                    "scope": e.get('content_scope', 'retrieved_excerpt'),
                    "accessed_at": str(e.get('acessado_em', ''))[:40]}
                   for e in tops if str(e.get('trecho', '')).strip()]
        # Distinct literal passages, never concatenate distant spans into a
        # fabricated quote. Citation IDs still resolve to the stored evidence.
        for source in sources:
            evidence = next(e for e in tops if e['id']==source['evidence_id'])
            passages = evidence.get('answer_passages') or []
            if passages:
                excerpt, ranges, seen = '', [], set()
                for passage in passages:
                    if passage['id'] in seen or len(excerpt)+len(passage['text'])+2>1800: continue
                    seen.add(passage['id'])
                    prefix = '\n\n' if excerpt else ''
                    start = len(excerpt)+len(prefix)
                    excerpt += prefix+passage['text']
                    ranges.append({'id':passage['id'],'start':start,'end':len(excerpt),
                                   **{k:passage[k] for k in ('element_type','section','context_heading',
                                     'table_header','table_header_span','source_span') if k in passage}})
                if excerpt:
                    source.update(excerpt=excerpt,passage_ranges=ranges)
        context_meta = {'source_count':len(sources),'context_chars':sum(len(s['excerpt']) for s in sources),
                        'timeout_seconds':min(25,timeout),'attempts':1}
        job.setdefault('usados',{})['synthesis_budget'] = context_meta
        try:
            candidate = research_synthesis.generate(job['objetivo'], sources, vereditos,
                                                    sintetizar_fn, timeout, deve_parar, verificar_fn)
            if candidate:
                import evidence_graph
                answer_coverage = evidence_graph.requirement_coverage(job['objetivo'], [
                    {'id':'answer','url':'','texto_lido':True,
                     'trecho':'\n\n'.join(f['text'] for f in candidate.get('findings',[])) or candidate['texto']}])
                candidate['answer_coverage'] = evidence_graph.compact_coverage(answer_coverage)
                notes = ["Redação assistida por IA; citações e trechos conferidos. "
                         "Suporte revisado automaticamente por parágrafo; essa revisão pode errar e não comprova a verdade."]
                removed = sum(r['state'] != 'SUPPORTED' for r in candidate['semantic_review'])
                if removed:
                    notes.append(f'{removed} parágrafo(s) omitido(s) por suporte parcial, contraditório ou inconclusivo.')
                if any(s['scope'] in ('abstract_only', 'metadata_only') for s in sources):
                    notes.append("Parte das fontes contém apenas resumos ou metadados; não é texto completo.")
                if any(v.get('estado') == 'CONTRADICTED' for v in vereditos):
                    notes.append("Há divergências nas evidências; não há conclusão única confirmada.")
                candidate['texto'] += '\n\n' + ' '.join(notes)
                sintese = candidate
            else:
                sintese['fallback_reason'] = 'unavailable_or_cancelled'
        except Exception as exc:
            # Provider errors can contain credentials/request bodies; never persist them.
            sintese['fallback_reason'] = 'provider_or_validation_failure'
            sintese['fallback_detail'] = research_synthesis.failure_detail(exc)
            if isinstance(exc, research_synthesis.ReviewUnavailableError):
                sintese['review_failure_cause'] = exc.cause
                if exc.provider_code:
                    sintese['fallback_provider_code'] = exc.provider_code
            elif sintese['fallback_detail'] == 'provider_failure':
                sintese['fallback_provider_code'] = research_synthesis.safe_provider_code(exc)
            if isinstance(exc, research_synthesis.SupportReviewError):
                sintese['semantic_review'] = exc.reviews
        if not sintese['llm']:
            sintese['texto'] = sintese['texto'].replace(
                'Síntese extrativa: redação por LLM indisponível neste fluxo determinístico; nenhuma inferência foi solicitada.',
                'Síntese extrativa: a redação assistida não foi concluída ou não passou nas validações; evidências preservadas.')
            if sintese.get('semantic_review'):
                sintese['texto'] += '\n\nConclusões geradas sem suporte suficiente foram omitidas; os trechos originais foram preservados.'
    emitir(db, job["id"], job["owner"], "synthesizer", "answer_started", "ok",
           f"Síntese {'assistida' if sintese['llm'] else 'extrativa'} com {len(tops)} evidências.",
           {"llm": sintese['llm'], "fallback_reason": sintese.get('fallback_reason', ''),
            "fallback_detail": sintese.get('fallback_detail', ''),
            "review_failure_cause": sintese.get('review_failure_cause', ''),
            "provider_code": sintese.get('fallback_provider_code', '')})
    retrieval_trace.record(job['id'],'',{},'SYNTHESIS_COMPLETED' if sintese.get('llm') or not sintetizar_fn else 'SYNTHESIS_FAILED',
                           reason_code='ASSISTED' if sintese.get('llm') else 'EXTRACTIVE')
    return sintese


def agente_auditor(db, job: dict, sintese: dict, evidencias: list) -> dict:
    """Evidence Auditor: citações existem? afirmações exageram?"""
    valid_evidence = {e['id'] for e in evidencias if _evidencia_lida(e)}
    ids = ([label for label, eid in sintese['references'].items() if eid in valid_evidence]
           if 'references' in sintese else [f"E{i + 1}" for i in range(len(evidencias))])
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
    if uso.get("buscas", 0) >= orc.get("buscas", 0):
        return "orçamento de buscas esgotado"
    if uso.get("paginas", 0) >= orc.get("paginas", 0):
        return "orçamento de páginas esgotado"
    return ""


def _orcamento_etapa(job: dict, tipo: str) -> str:
    orc, uso = job["orcamento"], job["usados"]
    if tipo == "busca" and uso.get("buscas", 0) >= orc.get("buscas", 0):
        return "orçamento de buscas esgotado"
    if tipo == "ler" and uso.get("paginas", 0) >= orc.get("paginas", 0):
        return "orçamento de páginas esgotado"
    return ""


def preparar_retomada(db, owner: str, job_id: str) -> dict:
    """Explicit user resume only; preserve reads and permit one new writing attempt."""
    job = carregar_job(db, owner, job_id)
    if job['status'] not in ('interrompida', 'cancelada', 'falhou'):
        raise AgentErro('pesquisa não pode ser retomada neste estado', 'estado')
    job['status'] = 'em_andamento'
    job.get('usados',{}).pop('partial_delivery_ready',None)
    if job.get('usados', {}).get('research_outcome', {}).get('state') == 'blocked':
        job['usados'].pop('synthesis_attempted', None)
    salvar_job(db, job, forcar_status=True)
    return job


def _completion_outcome(job, evidencias, lacunas, assisted=False):
    import evidence_graph
    coverage = evidence_graph.requirement_coverage(job.get('objetivo',''),evidencias)
    job.setdefault('usados',{})['answer_coverage'] = evidence_graph.compact_coverage(coverage)
    sintese = job.get('sintese') or {}
    provider_code = sintese.get('fallback_provider_code', '')
    blocked = bool(provider_code)
    read = [e for e in evidencias if _evidencia_lida(e)]
    read_ids={e['id'] for e in read}
    reviews=sintese.get('semantic_review') or []
    findings=sintese.get('findings') or []
    # Preliminary extraction also includes the user's question and unused
    # context. Keep those verdicts intact; assess the published answer using
    # its own validated citations, review and requirement coverage.
    reviewed_answer=bool(sintese.get('llm') and findings and reviews
        and len(reviews)==len(findings) and all(r.get('state')=='SUPPORTED' for r in reviews)
        and all(set(f.get('evidence_ids',[])) & read_ids for f in findings)
        and sintese.get('provenance') and sintese.get('answer_coverage',{}).get('complete'))
    provenance_unverified = bool(re.search(r'fontes? (?:oficiais|prim[aá]rias)|documenta[cç][aã]o oficial',
                                          job.get('objetivo',''),re.I))
    incomplete = (not read or bool(lacunas) or bool(job.get('pendencias'))
                  or not coverage['complete']
                  or provenance_unverified
                  or (sintese.get('llm') and sintese.get('answer_coverage',{}).get('applicable')
                      and not sintese['answer_coverage'].get('complete'))
                  or any(g.get('status') == 'OPEN' for g in job.get('usados', {}).get('research_gaps', []))
                  or (assisted and not sintese.get('llm'))
                  or job.get('auditoria', {}).get('ok') is False
                  or any(v.get('estado') == 'CONTRADICTED' for v in job.get('achados', []))
                  or (not reviewed_answer and any(v.get('estado') != 'SUPPORTED' for v in job.get('achados', []))))
    state = 'blocked' if blocked else ('partial' if incomplete else 'complete')
    return {'state': state, 'unresolved_fronts': lacunas[:8], 'source_authority_unverified':provenance_unverified,
            'provider_code': provider_code, 'read_sources': len(read),
            'reason': ('redação ou revisão bloqueada pelo provedor; evidências preservadas'
                       if blocked else 'evidências insuficientes ou limitações remanescentes'
                       if incomplete else 'etapas concluídas dentro do escopo recuperado')}


def executar(db, job_id: str, owner: str, provedores: list, recuperar_fn=None,
             deve_parar=None, t0: float = 0, sintetizar_fn=None) -> dict:
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
    state = _restore_context_checkpoint(db, job)
    local_context = _lookup_local_context(db, job)
    if local_context:
        state = {**state, **local_context}
    _save_context_checkpoint(db, job)
    t0 = t0 or time.monotonic()
    timeout = job["orcamento"].get("timeout_s", 120)
    prazo = t0 + timeout
    vistas = set(job["usados"].get("consultas_etapas", {}))
    todas_evid = []
    vereditos = []
    for step in job["plano"]:
        todas_evid.extend(step.get("_evidencias", []))
        if step.get("_vereditos"):
            vereditos = step["_vereditos"]
    todas_evid.extend(_evidencias_job(db, job))
    # Deduplicate restored in-memory and durable evidence records.
    todas_evid = list({item["id"]: item for item in todas_evid if item.get("id")}.values())
    try:
        for etapa in sorted(job["plano"], key=lambda step: step.get("prioridade", 50)):
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
            prerequisite_states = {s["id"]: s.get("status") for s in job["plano"]}
            if any(prerequisite_states.get(dep) not in ("feita", "falhou", "removida")
                   for dep in etapa.get("dependencias", [])):
                job["pendencias"].append(
                    f"{etapa['id']}: aguardando dependências explícitas concluírem"
                )
                continue
            if deve_parar is not None and deve_parar():
                job["status"] = "interrompida"
                salvar_job(db, job)
                if job["status"] in ("cancelada", "pausada"):
                    return _resumo(db, job)
                emitir(db, job["id"], owner, "orchestrator", "research_cancelled", "ok",
                       "Interrompida pelo usuário; retomável.", {})
                return _resumo(db, job)
            if time.monotonic() > prazo:
                job["pendencias"].append("tempo esgotado antes de " + etapa["id"])
                break
            msg = _orcamento_etapa(job, etapa["tipo"])
            if msg and etapa["tipo"] == "busca":
                job["pendencias"].append(f"{etapa['id']}: {msg}")
                continue
            emitir(db, job["id"], owner, "orchestrator", "step_started", "ok",
                   f"Etapa {etapa['id']} ({etapa['tipo']}): {etapa['alvo'][:80]}", {})
            etapa["tentativas"] = etapa.get("tentativas", 0) + 1
            step_started_at = time.monotonic()
            try:
                if etapa["tipo"] == "busca":
                    etapa["_achados"] = agente_busca(db, job, etapa, provedores, vistas,
                                                     deve_parar=deve_parar, prazo=prazo)
                elif etapa["tipo"] == "ler":
                    teto = max(1, job["orcamento"].get("paginas", 3) // max(1, len(
                        [s for s in job["plano"] if s["tipo"] == "ler"])))
                    fonte = _achados_etapa(job, etapa)
                    etapa["_evidencias"] = agente_analista(db, job, etapa, fonte,
                                                          recuperar_fn, teto,
                                                          deve_parar=deve_parar, prazo=prazo)
                    todas_evid.extend(etapa["_evidencias"])
                    todas_evid = list({e["id"]: e for e in todas_evid if e.get("id")}.values())
                elif etapa["tipo"] == "analisar":
                    etapa["_n"] = len(todas_evid)
                    _avaliar_rodada(db, job, etapa, todas_evid)
                elif etapa["tipo"] == "verificar":
                    base_ev = todas_evid or _evidencias_job(db, job)
                    analisar_independencia_job(db, job, base_ev)
                    vereditos = agente_verificador(db, job, base_ev)
                    job["achados"] = [{"afirmacao": v["afirmacao"], "estado": v["estado"],
                                       "metodo": v.get("metodo", ""),
                                       "cobertura_lexica": v.get("cobertura_lexica", 0.0),
                                       "evidence_ids": v.get("evidence_ids", []),
                                       "supporting_ids": v.get("supporting_ids", []),
                                       "contradicting_ids": v.get("contradicting_ids", []),
                                       "fontes": v.get("fontes", []),
                                       "fontes_encontradas": v.get("fontes_encontradas", 0),
                                       "fontes_lidas": v.get("fontes_lidas", 0),
                                       "fontes_usadas": v.get("fontes_usadas", 0)}
                                      for v in vereditos]
                    job["investigacoes"] = investigar_contradicoes_job(db, job, base_ev)
                    etapa["_vereditos"] = vereditos
                    _persist_hypotheses(db, job, vereditos)
                    emitir(db, job["id"], owner, "analyst", "hypotheses_updated", "ok",
                           f"{len(hypothesis_engine.HypothesisStore(db).list_for_job(owner, job_id))} "
                           "hipótese(s) aberta(s) para investigação.",
                           {"status": "open", "diagnosis": False})
                elif etapa["tipo"] == "sintetizar":
                    etapa["_sintese"] = agente_sintetizador(
                        db, job, todas_evid or _evidencias_job(db, job), vereditos)
                    job["sintese"] = etapa["_sintese"]
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
            timings = job['usados'].setdefault('stage_timings',[])
            timings.append({'step_id':etapa['id'],'type':etapa['tipo'],
                            'seconds':round(time.monotonic()-step_started_at,4)})
            job['usados']['stage_timings'] = timings[-40:]
            salvar_job(db, job)
            _save_context_checkpoint(db, job)
            if job["status"] == "cancelada":
                return _resumo(db, job)
        lacunas = _lacunas(job)
        if job.get("investigacoes"):
            lacunas += [q for inv in job["investigacoes"] for q in inv.get("follow_up", [])]
        lacunas = list(dict.fromkeys(lacunas))[:8]
        zero_gain = bool(job["usados"].get("replans", 0) and
                         (job["usados"].get("adaptive_rounds") or [{}])[-1].get("new_evidence") == 0)
        if lacunas and not zero_gain and not _orcamento_ok(job) and job["plano"] and \
                job["usados"].get("replans", 0) < job["orcamento"].get("replans", 1) and \
                all(s.get("status") != "pendente" for s in job["plano"]):
            v0 = job["plano_versao"]
            replanejar(db, job, lacunas)
            salvar_job(db, job)
            if job["plano_versao"] > v0:
                return executar(db, job_id, owner, provedores, recuperar_fn, deve_parar, t0,
                                sintetizar_fn=sintetizar_fn)
        # One writing/review pair after adaptive rounds, never one pair per round.
        if sintetizar_fn and not job['usados'].get('synthesis_attempted') and prazo-time.monotonic() >= 2:
            job['usados']['synthesis_attempted'] = True
            salvar_job(db, job)
            final_verdicts = next((s.get('_vereditos') for s in reversed(job['plano'])
                                   if s.get('_vereditos')), [])
            final = agente_sintetizador(db, job, todas_evid or _evidencias_job(db, job),
                                       final_verdicts, sintetizar_fn,
                                       prazo-time.monotonic(), deve_parar)
            job['sintese'] = final
            for step in job['plano']:
                if step['tipo'] == 'sintetizar':
                    step['_sintese'] = final
            job['auditoria'] = agente_auditor(db, job, final, todas_evid or _evidencias_job(db, job))
            if deve_parar and deve_parar():
                job['status'] = 'interrompida'
                salvar_job(db, job)
                _save_context_checkpoint(db, job)
                return _resumo(db, job)
        if not (job.get('sintese') or {}).get('texto'):
            # Budget/dependency exits can skip planned final steps. A completed
            # read still deserves an extractive, persisted result without an LLM.
            durable = todas_evid or _evidencias_job(db,job)
            job['sintese'] = agente_sintetizador(db,job,durable,vereditos)
            job['auditoria'] = agente_auditor(db,job,job['sintese'],durable)
        job["status"] = "concluida" if not job["pendencias"] or todas_evid else \
            ("concluida" if todas_evid else "interrompida")
        if job["status"] == "interrompida" and not job["pendencias"]:
            job["pendencias"].append("sem evidências suficientes")
        job["usados"]["research_outcome"] = _completion_outcome(
            job, todas_evid or _evidencias_job(db, job), lacunas, bool(sintetizar_fn))
        if job['usados']['research_outcome']['state'] == 'blocked':
            job['status'] = 'interrompida'
        if job['status']=='interrompida':
            # Natural completion without enough data must also leave an honest
            # terminal result. Early user cancellation/interruption returns above.
            job['usados']['partial_delivery_ready'] = True
        _save_context_checkpoint(db, job, "Pesquisa encerrada; revisar resultados, hipóteses e limitações.")
        # V5.7.3: o estado terminal é persistido ANTES do evento: quem consultar
        # no instante do research_completed já enxerga o status final (sem
        # janela em que o evento diz "acabou" e o job ainda está rodando).
        salvar_job(db, job)
        if job["status"] in ("cancelada", "pausada"):
            return _resumo(db, job)
        emitir(db, job["id"], owner, "orchestrator", "research_completed",
               "ok" if job['usados']['research_outcome']['state'] == 'complete' else 'alerta',
               f"Pesquisa {job['status']}: {len(todas_evid or _evidencias_job(db, job))} evidências.",
               {"outcome": job['usados']['research_outcome']})
        return _resumo(db, job)
    except Exception as exc:
        if isinstance(exc, json_store.JSONLimitError):
            # The rejected in-memory payload is still oversized. Record failure
            # against the last valid checkpoint instead of trying to save it again.
            job = carregar_job(db, owner, job_id)
            job["erros"] = job["erros"][-20:]
        job["status"] = "falhou"
        job["erros"].append(f"orquestrador: {type(exc).__name__}: {exc}"[:300])
        salvar_job(db, job)
        if job["status"] in ("cancelada", "pausada"):
            return _resumo(db, job)
        emitir(db, job["id"], owner, "orchestrator", "research_failed", "falha",
               f"Falha: {type(exc).__name__}. Estado preservado.", {})
        return _resumo(db, job)


def _achados_etapa(job: dict, etapa: dict) -> list:
    for s in reversed(job["plano"]):
        if s.get("tipo") == "busca" and s.get("alvo") == etapa["alvo"] and "_achados" in s:
            return s["_achados"]
    return []


def _evidencias_job(db, job: dict) -> list:
    return listar_evidencias(db, job["owner"], job["id"])


def _save_context_checkpoint(db, job: dict, next_action: str = "") -> int:
    """Persist execution context independently of the compact jobs row."""
    evs = _evidencias_job(db, job)
    results = {}
    plan = []
    for step in job.get("plano", []):
        plan.append({key: value for key, value in step.items() if not key.startswith("_")})
        step_results = {}
        for key in ("_achados", "_evidencias", "_sintese", "_auditoria", "_vereditos"):
            if key in step:
                step_results[key[1:]] = step[key]
        if step_results:
            results[step.get("id", "")] = step_results
    pending = [step["id"] for step in job.get("plano", [])
               if step.get("status") == "pendente"]
    if not next_action:
        next_step = min(
            (step for step in job.get("plano", []) if step.get("status") == "pendente"),
            key=lambda step: step.get("prioridade", 50),
            default=None,
        )
        next_action = (f"Executar {next_step['id']} ({next_step['tipo']})"
                       if next_step else "Nenhuma etapa pendente; revisar evidências e limitações")
    state = {
        "objective": job.get("objetivo", ""),
        "restrictions": job.get("ajustes", {}).get("restricoes", []),
        "plan": plan,
        "sources": [{"id": item["id"], "title": item.get("titulo", ""),
                     "url": item.get("url", "")} for item in evs],
        "document_chunks": [
            {"doc_id": item.get("doc_id"), "chunk_id": item.get("chunk_id"),
             "section": item.get("section"), "page": item.get("page"),
             "content_hash": item.get("content_hash"), "evidence_id": item["id"]}
            for item in evs if item.get("doc_id")
        ],
        "evidence": evs,
        "contradictions": job.get("investigacoes", []),
        "media": job.get("midia", []),
        "hypotheses": [vars(item) for item in hypothesis_engine.HypothesisStore(db)
                       .list_for_job(job["owner"], job["id"])],
        "decisions": job.get("ajustes", {}).get("memory_context", []),
        "results": {"steps": results, "claims": job.get("achados", []),
                    "synthesis": job.get("sintese", {}),
                    "structured_analysis": job.get("structured_analysis", [])},
        "pending_steps": pending,
        "next_action": next_action,
    }
    sequence = continuous_research.ResearchContextStore(db).save(
        job["owner"], job["id"], state)
    emitir(db, job["id"], job["owner"], "orchestrator", "context_checkpoint_saved", "ok",
           f"Contexto persistido (checkpoint {sequence}).",
           {"sequence": sequence, "context_version": continuous_research.CONTEXT_VERSION})
    return sequence


def _restore_context_checkpoint(db, job: dict) -> dict:
    restored = continuous_research.ResearchContextStore(db).restore_latest(
        job["owner"], job["id"])
    if not restored:
        return {}
    state = restored.get("state", {})
    if state.get("objective") != job.get("objetivo"):
        return {}
    results = (state.get("results") or {}).get("steps", {})
    by_id = {step.get("id"): step for step in job.get("plano", [])}
    for step_id, step_results in results.items():
        step = by_id.get(step_id)
        if step is None:
            continue
        for key, value in step_results.items():
            if key in ("achados", "evidencias", "sintese", "auditoria", "vereditos"):
                step["_" + key] = value
    job["achados"] = (state.get("results") or {}).get("claims", job.get("achados", []))
    job["sintese"] = (state.get("results") or {}).get("synthesis", job.get("sintese", {}))
    job["structured_analysis"] = (state.get("results") or {}).get(
        "structured_analysis", job.get("structured_analysis", []))
    job["investigacoes"] = state.get("contradictions", job.get("investigacoes", []))
    if state.get("media") and not job.get("midia"):
        job["midia"] = [item for item in state["media"] if isinstance(item, dict)][:40]
    return state


def _lookup_local_context(db, job: dict) -> dict:
    """Use owner-scoped saved memory and document chunks as context, not as diagnoses."""
    if job["usados"].get("local_context_checked"):
        return {}
    memory_context = []
    try:
        import pc_agent
        for item in pc_agent.memorias_relevantes(db, job["objetivo"], k=5,
                                                 owner=job["owner"]):
            value = str(item.get("value", ""))
            if item.get("assunto") != "sensivel" and not pc_agent.eh_sensivel(value):
                memory_context.append({"key": str(item.get("key", ""))[:120],
                                       "value": value[:300]})
    except Exception:
        memory_context = []
    job.setdefault("ajustes", {})["memory_context"] = memory_context

    document_chunks = []
    try:
        import docs_agent
        chunks = docs_agent.trechos_relevantes(db, job["objetivo"], k=4,
                                               owner=job["owner"])
    except Exception:
        chunks = []
    for chunk in chunks:
        try:
            doc_id = str(chunk.get("doc_id", ""))[:64]
            chunk_id = str(chunk.get("chunk_id", ""))[:100]
            if not doc_id or not chunk_id:
                continue
            source_key = f"doc:{doc_id}:{chunk_id}"
            exists = db.execute(
                "SELECT 1 FROM evidence WHERE owner_id=? AND job_id=? AND fonte_id=? LIMIT 1",
                (job["owner"], job["id"], source_key),
            ).fetchone()
            if exists:
                continue
            locator = f"chunk-{int(chunk.get('idx', 0))}"
            source = {
                "id": source_key,
                "url": f"document://{doc_id}#{locator}",
                "titulo": str(chunk.get("doc", doc_id))[:160],
                "dominio": "documento local",
                "acessado_em": agora_iso(),
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "section": str(chunk.get("section") or "")[:160],
                "page": chunk.get("page"),
                "content_hash": str(chunk.get("content_hash") or "")[:128],
                "version": chunk.get("version"),
                "source": str(chunk.get("source") or "")[:200],
                "table_hint": bool(chunk.get("table_hint")),
            }
            evidence = registrar_evidencia(
                db, job, source, str(chunk.get("trecho") or "")[:1500],
                afirmacao="Trecho recuperado lexicalmente; não confirma uma afirmação.",
                relacao="contexto_documento",
            )
            evidence["doc_id"] = doc_id
            evidence["chunk_id"] = chunk_id
            document_chunks.append({
                "doc_id": doc_id, "chunk_id": chunk_id,
                "section": source["section"], "page": source["page"],
                "content_hash": source["content_hash"], "evidence_id": evidence["id"],
            })
        except Exception:
            continue
    job["usados"]["local_context_checked"] = True
    salvar_job(db, job)
    if memory_context:
        emitir(db, job["id"], job["owner"], "orchestrator", "memory_context_retrieved", "ok",
               f"{len(memory_context)} memória(s) relevantes recuperadas para contexto local.",
               {"count": len(memory_context), "evidence": False})
    if document_chunks:
        emitir(db, job["id"], job["owner"], "analyst", "document_context_retrieved", "ok",
               f"{len(document_chunks)} trecho(s) documental(is) recuperados lexicalmente.",
               {"count": len(document_chunks), "evidence_ids": [
                   item["evidence_id"] for item in document_chunks]})
    return {"memory_context": memory_context, "document_chunks": document_chunks}


def _persist_hypotheses(db, job: dict, vereditos: list) -> list:
    store = hypothesis_engine.HypothesisStore(db)
    for verdict in vereditos:
        statement = f"Investigar se: {verdict['afirmacao'][:1000]}"
        identifier = hashlib.sha256(statement.encode("utf-8")).hexdigest()[:20]
        missing = [str(item)[:1200] for item in verdict.get("condicoes_ausentes", [])[:10]
                   if str(item).strip()]
        if not verdict.get("evidence_ids"):
            missing.append("Nenhuma evidência específica foi atribuída pelo verificador.")
        store.save(hypothesis_engine.Hypothesis(
            hypothesis_id=identifier,
            owner_id=job["owner"],
            job_id=job["id"],
            statement=statement,
            status="open",
            evidence_ids=tuple(verdict.get("evidence_ids", [])[:20]),
            missing_evidence=tuple(missing[:20]),
            next_steps=("Revisar as evidências armazenadas e buscar validação independente.",),
            result_summary=(
                f"Resultado do verificador determinístico: {verdict.get('estado', 'UNVERIFIED')} "
                f"({verdict.get('metodo') or 'método não informado'}). "
                "Não é diagnóstico nem conclusão causal."
            ),
        ))
    for index, investigation in enumerate(job.get("investigacoes") or []):
        statement = ("Investigar divergência registrada: "
                     + str(investigation.get("explicacao", investigation.get("tipo", "")))[:900])
        identifier = hashlib.sha256(f"{index}:{statement}".encode("utf-8")).hexdigest()[:20]
        store.save(hypothesis_engine.Hypothesis(
            hypothesis_id=identifier,
            owner_id=job["owner"],
            job_id=job["id"],
            statement=statement,
            status="open",
            evidence_ids=tuple(investigation.get("entre", [])[:20]),
            missing_evidence=("Metodologia, período e condições comparáveis",),
            next_steps=tuple(str(step)[:1200] for step in
                             (investigation.get("follow_up") or [])[:10]),
            result_summary="Divergência lexical/quantitativa detectada; causa não determinada.",
        ))
    return store.list_for_job(job["owner"], job["id"])


def gerar_relatorio(db, owner: str, job_id: str,
                    report_type: str = "executive_summary") -> dict:
    """Build a report only from persisted evidence and validated evidence references."""
    job = carregar_job(db, owner, job_id)
    evidencias = listar_evidencias(db, owner, job_id)
    _restore_context_checkpoint(db, job)
    synthesis = job.get('sintese') or {}
    sources = [
        research_reports.ReportSource(
            source_id=item["id"], title=item["titulo"] or item["id"],
            url=item["url"], source_type="documento" if item.get("doc_id") else "web",
            access_note=f"Acessado em {item['acessado_em']}" if item.get("acessado_em") else None,
        )
        for item in evidencias if item.get("url")
    ]
    valid_ids = {source.source_id for source in sources}
    tabular_findings = []
    for item in job.get("structured_analysis", [])[-5:]:
        if not isinstance(item, dict) or not item.get("document_id"):
            continue
        analysis_result = item.get("analysis")
        if not isinstance(analysis_result, dict):
            continue
        provenance = analysis_result.get("provenance")
        data = analysis_result.get("data")
        if not isinstance(provenance, dict) or not isinstance(data, dict):
            continue
        document_id = str(item["document_id"])
        content_hash = str(item.get("content_hash") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", document_id) or not re.fullmatch(
            r"[0-9a-f]{64}", content_hash
        ):
            continue
        source_id = f"structured:{document_id}:{item.get('method')}"
        if source_id not in valid_ids:
            valid_ids.add(source_id)
            sources.append(research_reports.ReportSource(
                source_id=source_id,
                title=str(item.get("document_name") or document_id)[:160],
                url=f"document://{document_id}#{content_hash}",
                source_type="documento tabular",
                access_note=(
                    f"content hash {content_hash}; versão {item.get('version')}; "
                    f"método {provenance.get('method') or item.get('method')}; "
                    f"período {provenance.get('period') or 'não informado'}; "
                    f"metodologia {provenance.get('methodology') or 'não informada'}"
                )[:240],
            ))
        citation = (source_id,)
        if item.get("method") == "chart_series":
            series_items = data.get("series")
            if isinstance(series_items, list):
                for series in series_items[:6]:
                    if not isinstance(series, dict) or series.get("status") != "ok":
                        continue
                    points = series.get("points")
                    if not isinstance(points, list):
                        continue
                    observed = [
                        f"{point.get('x')}={point.get('y')}"
                        for point in points[:24] if isinstance(point, dict)
                    ]
                    if observed:
                        unit = str(series.get("unit") or "")
                        tabular_findings.append(research_reports.ReportPoint(
                            text=(f"{item.get('document_name')}: série "
                                  f"{series.get('name') or '(única)'} — "
                                  + "; ".join(observed) + (f" {unit}" if unit else ""))[:1200],
                            source_ids=citation,
                        ))
        elif item.get("method") == "differences":
            groups = data.get("groups")
            if isinstance(groups, list):
                for group in groups[:13]:
                    if not isinstance(group, dict) or group.get("status") != "ok":
                        continue
                    unit = str(group.get("unit") or "")
                    label = group.get("group")
                    tabular_findings.append(research_reports.ReportPoint(
                        text=(f"{item.get('document_name')}: grupo {label}, média "
                              f"{group.get('value')}{(' ' + unit) if unit else ''}")[:1200],
                        source_ids=citation,
                    ))
    evidence_points = [
        research_reports.ReportPoint(
            text=(item.get("trecho") or "")[:1200],
            source_ids=(item["id"],) if item["id"] in valid_ids else (),
        )
        for item in evidencias if item.get("trecho")
    ]
    findings = [
        research_reports.ReportPoint(
            text=f"{claim.get('estado', 'UNVERIFIED')}: {claim.get('afirmacao', '')[:800]}",
            source_ids=tuple(eid for eid in claim.get("evidence_ids", []) if eid in valid_ids),
        )
        for claim in job.get("achados", [])
        if claim.get("evidence_ids") and any(eid in valid_ids for eid in claim["evidence_ids"])
    ]
    if synthesis.get('llm'):
        findings = [research_reports.ReportPoint(
            text=point['text'], source_ids=tuple(eid for eid in point['evidence_ids'] if eid in valid_ids))
            for point in synthesis.get('findings', [])
            if any(eid in valid_ids for eid in point.get('evidence_ids', []))] + findings
    divergences = []
    for item in job.get("investigacoes", []):
        refs = tuple(eid for eid in item.get("entre", []) if eid in valid_ids)
        if refs:
            divergences.append(research_reports.ReportPoint(
                text=str(item.get("explicacao") or item.get("tipo") or "Divergência registrada")[:800],
                source_ids=refs,
            ))
    limitations = [
        "Verificação lexical determinística; não estabelece causalidade ou diagnóstico.",
        ("Redação assistida por IA; referências e trechos conferidos, sem garantia de suporte semântico."
         if synthesis.get('llm') else "Não há redação generativa validada neste relatório."),
    ]
    review_counts = research_synthesis.support_summary(synthesis)
    if review_counts:
        limitations.append('Revisão automática de suporte por parágrafo (pode errar): '
                           + ', '.join(f'{state}={count}' for state, count in review_counts.items())
                           + '. Apenas parágrafos SUPPORTED integram a redação assistida.')
    if not evidencias:
        limitations.append("Nenhuma evidência foi armazenada para este job.")
    midia_resumo = media_evidence.resumo_midia(job.get("midia") or [])
    if midia_resumo["total"]:
        limitations.append(
            f"{midia_resumo['total']} item(ns) de mídia foram descobertos como metadados/links; "
            "imagens não são evidência e vídeos não foram assistidos, transcritos ou analisados."
        )
    if job.get("ajustes", {}).get("memory_context"):
        limitations.append(
            "Memória local do proprietário foi consultada apenas como contexto, não como evidência citável."
        )
    hypotheses = hypothesis_engine.HypothesisStore(db).list_for_job(owner, job_id)
    next_questions = [step for hypothesis in hypotheses
                      for step in hypothesis.missing_evidence + hypothesis.next_steps][:20]
    markdown = research_reports.build_research_report(
        report_type=report_type, objective=job["objetivo"],
        scope=f"Job {job_id}; status {job['status']}; modo {job['modo']}.",
        methodology=("Coleta e verificações determinísticas com redação assistida por IA sobre evidências armazenadas."
                     if synthesis.get('llm') else
                     "Pesquisa determinística; os achados e citações abaixo vêm dos registros armazenados."),
        findings=findings + tabular_findings, evidence=evidence_points, divergences=divergences,
        limitations=limitations, next_questions=next_questions, sources=sources,
    )
    return {"job_id": job_id, "report_type": report_type, "markdown": markdown,
            "source_count": len(sources), "evidence_count": len(evidencias)}


def analisar_documento_estruturado(
    db,
    owner: str,
    job_id: str,
    doc_id: str,
    *,
    method: str,
    columns: dict,
) -> dict:
    """Analyze owner-scoped saved CSV/JSON data with an explicit column mapping."""
    import docs_agent

    job = carregar_job(db, owner, job_id)
    document = db.execute(
        "SELECT name, ext, extracted_meta, content_hash, version, conversation_id "
        "FROM documents WHERE id=? AND owner_id=?",
        (doc_id, owner),
    ).fetchone()
    if document is None:
        raise AgentErro("documento não encontrado", "ausente")
    name, extension, raw_metadata, content_hash, version, document_conv = document
    if document_conv != job["conv"]:
        raise AgentErro("documento não pertence à conversa deste job", "ausente")
    if extension not in (".csv", ".tsv", ".json"):
        raise AgentErro("análise estruturada aceita somente CSV, TSV ou JSON", "formato")
    try:
        metadata = json.loads(raw_metadata or "{}")
        if metadata.get("truncated"):
            raise structured_analysis.AnalysisError(
                "extração documental truncada; não é seguro analisar apenas um subconjunto"
            )
        docs_root = docs_agent.docs_dir().resolve()
        raw_path = (docs_root / f"{doc_id}{extension}").resolve()
        if docs_root not in raw_path.parents or not raw_path.is_file():
            raise structured_analysis.AnalysisError(
                "arquivo tabular original não está disponível no armazenamento local"
            )
        raw_bytes = raw_path.read_bytes()
        stored_size = db.execute(
            "SELECT size FROM documents WHERE id=? AND owner_id=?", (doc_id, owner)
        ).fetchone()[0]
        if len(raw_bytes) != stored_size:
            raise structured_analysis.AnalysisError(
                "arquivo original diverge do tamanho registrado; reenvie o documento"
            )
        extracted_text = docs_agent.extrair_texto(extension, raw_bytes, name)
        if hashlib.sha256(extracted_text.encode("utf-8")).hexdigest() != content_hash:
            raise structured_analysis.AnalysisError(
                "arquivo original não corresponde à proveniência registrada; reenvie o documento"
            )
        if not isinstance(columns, dict):
            raise structured_analysis.AnalysisError("mapeamento de colunas deve ser um objeto")
        allowed_columns = {
            "title": 160, "period": 120, "methodology": 240, "x": 200, "y": 200,
            "series": 200, "unit": 200, "chart_title": 120, "chart_type": 20,
            "group": 200, "value": 200, "baseline": 120, "baseline_label": 120,
        }
        unsupported = set(columns) - set(allowed_columns)
        if unsupported:
            raise structured_analysis.AnalysisError(
                f"mapeamento contém parâmetro não suportado: "
                f"{sorted(str(key) for key in unsupported)[0]}"
            )
        columns = {
            key: str(value)[:limit]
            for key, limit in allowed_columns.items()
            if (value := columns.get(key)) is not None
        }
        title = str(columns.get("title") or name)[:160]
        locator = f"document {doc_id}, content hash {content_hash}, version {version}"
        dataset_source = f"document:{doc_id}:{content_hash or version}"
        dataset_metadata = {
            "period": str(columns.get("period") or "")[:120],
            "methodology": str(columns.get("methodology") or "deterministic tabular analysis"),
        }
        if extension in (".csv", ".tsv"):
            dataset = structured_analysis.load_csv(
                raw_bytes, source=dataset_source, metadata=dataset_metadata,
                delimiter="\t" if extension == ".tsv" else ",")
        else:
            dataset = structured_analysis.load_json(
                raw_bytes, source=dataset_source, metadata=dataset_metadata)

        selected_method = str(method or "").strip()
        unit = str(columns.get("unit") or "").strip()
        if not unit:
            raise structured_analysis.AnalysisError(
                "informe unit=<coluna> ou unit=none explicitamente"
            )
        unit_column = None if unit.lower() == "none" else unit
        if selected_method == "chart_series":
            x = str(columns.get("x") or "")
            y = str(columns.get("y") or "")
            series = str(columns.get("series") or "")
            if not x or not y:
                raise structured_analysis.AnalysisError(
                    "informe explicitamente as colunas x e y para o gráfico"
                )
            result = structured_analysis.chart_series(
                dataset, x, y, series_column=series or None, unit_column=unit_column,
            )
            visual = research_visualizations.chart_message(
                result, title=str(columns.get("chart_title") or name)[:120],
                source_title=title, source_url=f"document://{doc_id}",
                locator=locator, chart_type=str(columns.get("chart_type") or "bar"),
            )
        elif selected_method == "differences":
            group = str(columns.get("group") or "")
            value = str(columns.get("value") or "")
            baseline = columns.get("baseline")
            if not group or not value or baseline is None:
                raise structured_analysis.AnalysisError(
                    "informe explicitamente as colunas group/value e o baseline da comparação"
                )
            result = structured_analysis.differences(
                dataset, group, value, baseline, unit_column=unit_column,
            )
            visual = research_visualizations.compare_message(
                result, title=str(columns.get("chart_title") or name)[:120],
                baseline_label=str(columns.get("baseline_label") or baseline)[:120],
                source_title=title, source_url=f"document://{doc_id}", locator=locator,
            )
        else:
            raise structured_analysis.AnalysisError(
                "método deve ser chart_series ou differences"
            )
    except (structured_analysis.AnalysisError, ValueError, OSError) as exc:
        raise AgentErro(str(exc), "structured_analysis") from exc
    output = {
        "method": selected_method,
        "job_id": job_id,
        "document_id": doc_id,
        "document_name": name,
        "extension": extension,
        "content_hash": content_hash,
        "version": version,
        "columns": columns,
        "analysis": result,
        "visualization": visual,
        "locator": locator,
    }
    if len(json.dumps(output, ensure_ascii=False, allow_nan=False)) > 50_000:
        raise AgentErro(
            "resultado ultrapassa o limite seguro de persistência do job; reduza os dados",
            "limite",
        )
    _persist_structured_result(db, owner, output)
    return output


def _persist_structured_result(db, owner: str, result: dict) -> None:
    job_id = result.get("job_id")
    if not job_id:
        return
    job = carregar_job(db, owner, job_id)
    records = job.get("structured_analysis", [])
    records = [
        item for item in records
        if (item.get("document_id"), item.get("method"))
        != (result.get("document_id"), result.get("method"))
    ]
    records.append(result)
    records = records[-20:]
    while records and len(json.dumps(records, ensure_ascii=False)) > 50_000:
        records.pop(0)
    job["structured_analysis"] = records
    salvar_job(db, job)
    _save_context_checkpoint(db, job)
    emitir(db, job_id, owner, "analyst", "structured_analysis_completed", "ok",
           f"Análise determinística {result['method']} concluída para {result['document_name']}.",
           {"document_id": result["document_id"], "method": result["method"],
            "source_id": result["analysis"]["provenance"]["source"]})


def excluir_job(db, owner: str, job_id: str) -> dict:
    job = carregar_job(db, owner, job_id)
    if job["status"] in ("em_andamento", "pausada"):
        raise AgentErro("pesquisa em andamento; cancele antes de excluir", "ocupado")
    with db:
        db.execute("DELETE FROM eg_edges WHERE owner_id=? AND job_id=?", (owner, job_id))
        db.execute("DELETE FROM eg_nodes WHERE owner_id=? AND job_id=?", (owner, job_id))
        db.execute("DELETE FROM evidence WHERE owner_id=? AND job_id=?", (owner, job_id))
        db.execute("DELETE FROM research_events WHERE owner_id=? AND job_id=?", (owner, job_id))
        db.execute("DELETE FROM research_jobs WHERE owner_id=? AND id=?", (owner, job_id))
        db.execute("DELETE FROM research_cache WHERE owner_id=? AND provedor=?",(owner,'document:'+job_id))
    hypothesis_engine.HypothesisStore(db).delete_for_job(owner, job_id)
    continuous_research.ResearchContextStore(db).delete_for_job(owner, job_id)
    return {"job_id": job_id, "deleted": True}


def _consulta_lacuna(job: dict, dimension: str, alvo: str = "") -> str:
    # User constraints stay in the request; never replace the topic by generic words.
    base = alvo or job.get("objetivo", "")
    base = re.sub(r"\s+", " ", base).strip(" .?!")[:160]
    return base if base.casefold().endswith(dimension.casefold()) else base + " " + dimension


def _avaliar_rodada(db, job: dict, etapa: dict, evidencias: list) -> dict:
    import research_gaps
    import evidence_graph
    coverage = evidence_graph.requirement_coverage(job.get('objetivo',''),evidencias)
    job['usados']['answer_coverage'] = evidence_graph.compact_coverage(coverage)
    current = {e["id"] for e in evidencias if e.get("id") and _evidencia_lida(e)}
    gaps = research_gaps.identify(job, evidencias)
    job['usados']['research_gaps'] = gaps
    controller = research_gaps.decision(job, gaps)
    decisions = job['usados'].setdefault('controller_decisions', [])
    decisions.append({**controller, 'step_id': etapa['id'], 'executed': False})
    job['usados']['controller_decisions'] = decisions[-16:]
    previous = set(job["usados"].get("round_evidence_ids", []))
    new = current - previous
    decision = {"step_id": etapa["id"], "new_evidence": len(new),
                "total_evidence": len(current), "remaining_searches": max(0,
                job["orcamento"].get("buscas", 0) - job["usados"].get("buscas", 0)),
                "decision": "evidence_gained" if new else "no_new_evidence"}
    if coverage['applicable']:
        states = {r['id']:r['state'] for r in coverage['requirements']}
        before = job['usados'].get('requirement_states',{})
        decision['requirement_changes'] = [{'id':rid,'before':before.get(rid,'NOT_SEARCHED'),'after':state}
                                          for rid,state in states.items() if before.get(rid)!=state]
        job['usados']['requirement_states'] = states
    history = job["usados"].setdefault("adaptive_rounds", [])
    history.append(decision)
    job["usados"]["adaptive_rounds"] = history[-16:]
    job["usados"]["round_evidence_ids"] = sorted(current)
    emitir(db, job["id"], job["owner"], "orchestrator", "adaptive_round_evaluated", "ok",
           f"Rodada avaliada: {len(new)} nova(s) evidência(s); {decision['remaining_searches']} busca(s) restantes.", decision)
    return decision


def _lacunas(job: dict) -> list:
    subs_busca = {s.get("alvo") for s in job["plano"] if s.get("tipo") == "busca"}
    com_evid = set()
    needs_full = bool(re.search(r'texto completo|m[eé]todos|m[eé]tricas|compare estudos', job.get('objetivo',''), re.I))
    for s in job["plano"]:
        # Old callers supplied a compact plan with evidence IDs only. Preserve
        # that gap-list API; real jobs always carry an objective and read state.
        known = bool(s.get("_evidencias")) if "objetivo" not in job else any(
            _evidencia_lida(e) and (not needs_full or e.get('full_text_fetched') or e.get('content_scope')=='document_text')
            and (e.get('vertical') or {}).get('data_complete', True)
            for e in s.get("_evidencias", []))
        if s.get("tipo") == "ler" and known:
            com_evid.add(s.get("alvo"))
    covered = {base for base in subs_busca if any(
        done.casefold().startswith(base.casefold()) for done in com_evid)}
    lacunas = [(_consulta_lacuna(job, "fontes primárias texto completo", alvo) if "objetivo" in job else alvo)
               for alvo in sorted(subs_busca - covered)]
    # Lacunas de BUSCA reais (orquestrador): consultas complementares que o
    # pedido ainda não cobriu entram como novas buscas no replanejamento.
    for q in (job["usados"].get("recuperacao_busca") or []):
        if q and q not in subs_busca and q not in lacunas:
            lacunas.append(q)
    structured = job.get('usados', {}).get('research_gaps', [])
    queries = [g['query'] for g in structured if g.get('status') == 'OPEN' and g.get('query')]
    if queries or lacunas:
        missing=[r['id'] for r in (job.get('usados',{}).get('answer_coverage') or {}).get('requirements',[]) if r.get('state')!='SUPPORTED']
        retrieval_trace.record(job.get('id',''),'',{'retrieval_provenance':{'requirement_ids':missing}},'GAP_IDENTIFIED')
    if (job.get('usados',{}).get('answer_coverage') or {}).get('applicable'):
        return list(dict.fromkeys(queries))[:8]
    return list(dict.fromkeys(queries + lacunas))[:8]


def investigar_contradicoes_job(db, job: dict, evidencias: list) -> list:
    """Contradiction Agent: pares com negação assimétrica → investiga dimensão."""
    import evidence_graph as _eg
    evidencias=[e for e in evidencias or [] if _evidencia_lida(e)]
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
                inv = {"tipo": "valor_divergente", "status": "em_aberto", "state": "INCONCLUSIVE",
                       "explicacao": f"Mesma unidade, valores distintos ({a['valor']} × {b['valor']}). "
                                     "Verificar metodologia, data e condições.",
                       "follow_up": [_consulta_lacuna(job, "metodologia medição"),
                                     _consulta_lacuna(job, "data de publicação e condições")],
                       "entre": [evidencias[i]["id"], evidencias[j]["id"]]}
                inv['conditions_to_check']={
                    'publication_dates':[evidencias[k].get('publicado_em') or evidencias[k].get('year') for k in (i,j)],
                    'model_tokens':[sorted(set(re.findall(r'\b[a-z]+-?\d+[a-z0-9-]*\b',str(evidencias[k].get('titulo','')).lower()))) for k in (i,j)],
                    'methodology':'not_verified'}
                invs.append(inv)
                try:
                    na = _eg.no_id("evidence", job["id"], evidencias[i]["id"])
                    nb = _eg.no_id("evidence", job["id"], evidencias[j]["id"])
                    _eg.ligar(db, job["owner"], job["id"], na, nb, "REQUIRES_VERIFICATION",
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
            inv.update({"entre": [evidencias[i]["id"], evidencias[j]["id"]], "state": "INCONCLUSIVE"})
            inv["follow_up"] = [_consulta_lacuna(job, q) for q in inv.get("follow_up", [])[:2]]
            invs.append(inv)
            try:
                na = _eg.no_id("evidence", job["id"], evidencias[i]["id"])
                nb = _eg.no_id("evidence", job["id"], evidencias[j]["id"])
                _eg.ligar(db, job["owner"], job["id"], na, nb, "REQUIRES_VERIFICATION",
                          "contradicao", inv["tipo"])
            except Exception:
                pass
            emitir(db, job["id"], job["owner"], "contradiction", "contradiction_investigated",
                   "alerta" if inv["tipo"] == "valor_divergente" else "ok",
                   f"Divergência {inv['tipo']}: {inv['explicacao'][:140]}", {})
    return invs


def _hipotese_publica(item) -> dict:
    """Hypothesis with an explicit epistemic chain; never claims a test ran."""
    base = vars(item).copy()
    conclusao = {
        "supported": "SUPORTADA pelas evidências registradas (não é prova causal).",
        "weakened": "ENFRAQUECIDA pelas evidências registradas.",
        "inconclusive": "INCONCLUSIVA com as evidências disponíveis.",
        "open": "EM ABERTO; nenhuma conclusão foi estabelecida.",
    }.get(item.status, "INCONCLUSIVA; estado não reconhecido.")
    base["cadeia"] = [
        {"rotulo": "HIPÓTESE", "texto": item.statement},
        {"rotulo": "EVIDÊNCIAS", "texto": (
            f"{len(item.evidence_ids)} referência(s) ligada(s) a esta hipótese."
            if item.evidence_ids else "Nenhuma referência específica atribuída.")},
        {"rotulo": "LACUNAS", "texto": (
            "; ".join(item.missing_evidence)[:900]
            if item.missing_evidence else "Nenhuma lacuna explícita registrada.")},
        {"rotulo": "PRÓXIMOS PASSOS", "texto": (
            "; ".join(item.next_steps)[:900]
            if item.next_steps else "Nenhum teste foi executado ou agendado.")},
        {"rotulo": "CONCLUSÃO", "texto": conclusao},
    ]
    base["testes_executados"] = False
    return base


def _resumo(db, job: dict) -> dict:
    evs = _evidencias_job(db, job)
    invs = job.get("investigacoes") or []
    aud = job.get("auditoria") or {}
    hypotheses = hypothesis_engine.HypothesisStore(db).list_for_job(job["owner"], job["id"])
    synthesis = job.get("sintese")
    if synthesis is None and job.get("status") in ("concluida", "interrompida", "cancelada"):
        checkpoint = continuous_research.ResearchContextStore(db).restore_latest(job["owner"], job["id"])
        synthesis = ((checkpoint or {}).get("state", {}).get("results") or {}).get("synthesis", {})
    next_step = min((s for s in job["plano"] if s.get("status") == "pendente"),
                    key=lambda step: step.get("prioridade", 50), default=None)
    return {"id": job["id"], "status": job["status"], "modo": job["modo"],
            "objetivo": job["objetivo"], "plano_versao": job["plano_versao"],
            "etapas": [{"id": s["id"], "tipo": s["tipo"], "status": s.get("status", "pendente"),
                        "alvo": s.get("alvo", ""), "frente": s.get("frente", 0),
                        "objetivo_etapa": s.get("objetivo_etapa", ""),
                        "dependencias": s.get("dependencias", []),
                        "prioridade": s.get("prioridade", 50),
                        "priority_reason": s.get("priority_reason", ""),
                        "replan_reason": s.get("replan_reason", ""),
                        "regra_parada": s.get("regra_parada", ""),
                        "criterio_conclusao": s.get("criterio_conclusao", "")}
                       for s in job["plano"]],
            "evidencias": len(evs), "achados": job["achados"],
            "sintese": synthesis or {},
            "investigacoes": len(invs),
            "hipoteses": [_hipotese_publica(item) for item in hypotheses],
            "proxima_acao": (f"Executar {next_step['id']} ({next_step['tipo']})"
                             if next_step else "Revisar resultados e limitações"),
            "auditoria_ok": aud.get("ok") if aud else None,
            "pendencias": job["pendencias"], "erros": job["erros"],
            "usados": job["usados"], "orcamento": job["orcamento"],
            "midia": [item for item in (job.get("midia") or []) if isinstance(item, dict)],
            "midia_resumo": media_evidence.resumo_midia(job.get("midia") or []),
            "limites": {
                "buscas": job["orcamento"].get("buscas"),
                "paginas": job["orcamento"].get("paginas"),
                "timeout_s": job["orcamento"].get("timeout_s"),
                "subs": job["orcamento"].get("subs"),
                "replans": job["orcamento"].get("replans"),
                "midia": job["orcamento"].get("midia"),
                "concorrencia": job["orcamento"].get("concorrencia"),
                "max_bytes_pagina": job["orcamento"].get("max_bytes_pagina"),
            }}


def cancelar(db, owner: str, job_id: str) -> dict:
    job = carregar_job(db, owner, job_id)
    if job["status"] in ("concluida", "cancelada"):
        return _resumo(db, job)
    job["status"] = "cancelada"
    salvar_job(db, job)
    retrieval_trace.record(job['id'],'',{},'JOB_TERMINAL',reason_code='CANCELLED')
    emitir(db, job["id"], owner, "orchestrator", "research_cancelled", "ok",
           "Cancelada; resultados parciais preservados.", {})
    return _resumo(db, job)


def pausar(db, owner: str, job_id: str, pausar: bool = True) -> dict:
    job = carregar_job(db, owner, job_id)
    if job["status"] not in ("em_andamento", "pausada"):
        raise AgentErro("só pausa job em andamento", "estado")
    job["status"] = "pausada" if pausar else "em_andamento"
    salvar_job(db, job, forcar_status=True)
    emitir(db, job["id"], owner, "orchestrator",
           "research_cancelled" if pausar else "step_started",
           "ok", "Pausada pelo usuário." if pausar else "Retomada pelo usuário.", {})
    return _resumo(db, job)


OPS_INTERVENCAO = ("escopo_add", "escopo_remove", "priorizar_dominio",
                   "investigar_divergencia", "parar_topico", "adicionar_metrica")


def intervir(db, owner: str, job_id: str, op: str, params: dict = None) -> dict:
    """Alteração estruturada do plano (sem LLM): nova versão, feitas preservadas,
    incompatíveis invalidadas e listadas."""
    if not isinstance(params, dict):
        params = {}
    params = {
        str(chave)[:40]: (valor[:500] if isinstance(valor, str) else valor)
        for chave, valor in list(params.items())[:10]
        if isinstance(chave, str) and isinstance(valor, (str, int, float, bool))
    }
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
        search_id = f"p{len(job['plano']) + 1}"
        read_id = f"p{len(job['plano']) + 2}"
        for etapa_id, tipo, deps, prioridade in (
            (search_id, "busca", [], 10),
            (read_id, "ler", [search_id], 30),
            (f"p{len(job['plano']) + 3}", "analisar", [read_id], 50),
        ):
            job["plano"].append({
                "id": etapa_id, "tipo": tipo, "alvo": texto, "status": "pendente",
                "tentativas": 0, "prioridade": prioridade, "dependencias": deps,
                "replan_reason": f"intervenção manual: {op}",
                "regra_parada": "orçamento e timeout originais",
            })
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
        for step in job["plano"]:
            if step.get("tipo") == "busca" and step.get("status") == "pendente":
                step["prioridade"] = 1
                step["priority_reason"] = f"prioridade solicitada para {dom}"
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
            alvo = str(q)[:120]
            search_id = f"p{len(job['plano']) + 1}"
            read_id = f"p{len(job['plano']) + 2}"
            for etapa_id, tipo, deps, priority in (
                (search_id, "busca", [], 10),
                (read_id, "ler", [search_id], 30),
                (f"p{len(job['plano']) + 3}", "analisar", [read_id], 50),
            ):
                job["plano"].append({
                    "id": etapa_id, "tipo": tipo, "alvo": alvo, "status": "pendente",
                    "tentativas": 0, "prioridade": priority, "dependencias": deps,
                    "replan_reason": "intervenção manual: investigar divergência",
                    "regra_parada": "máximo de três follow-ups e orçamento/timeout originais",
                })
                adicionadas.append(tipo + ":" + alvo[:60])
    for ev in listar_evidencias(db, owner, job_id):
        if any(r in (ev.get("url", "") or "").lower() or r in (ev.get("titulo", "") or "").lower()
               for r in aj["restricoes"]):
            invalidadas.append(ev["id"])
    job["ajustes"] = aj
    job["plano_versao"] += 1
    if job["status"] in ("interrompida", "pausada"):
        job["status"] = "em_andamento"
    salvar_job(db, job, forcar_status=True)
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


def provedores_reais(orquestrado: bool = False):
    """Provedores reais dos agentes.

    Ordem legada preservada (ddg → searxng → wikipedia [→ academic]);
    `orquestrado=True` (liga em produção com `JULIA_WEB_SEARCH`) acrescenta
    a busca web multi-provedor V5.5 como ÚLTIMO provedor.
    """
    import os as _os
    if PROVS_FABRICA is not None:
        return PROVS_FABRICA()
    providers = [ProvedorDDG(), ProvedorSearXNG(_os.environ.get("JULIA_SEARXNG_URL", "")),
                 ProvedorWikipedia()]
    if _os.environ.get("JULIA_ACADEMIC_RESEARCH", "").strip().lower() in (
            "1", "true", "yes", "on"):
        providers.append(ProvedorAcademico(_os.environ.get("JULIA_RESEARCH_MAILTO", "")))
    if orquestrado:
        providers.append(ProvedorOrquestrado())
    return providers


def recuperar_real():
    if RECUPERAR_FABRICA is not None:
        return RECUPERAR_FABRICA()
    return None


class ProvedorAcademico(ProvedorBusca):
    """Optional keyless academic fallback; enabled by JULIA_ACADEMIC_RESEARCH=1."""
    nome = "academic"
    academic_search = True

    def __init__(self, mailto: str = ""):
        self.provider = academic_research.AcademicResearchProvider(mailto=mailto)

    def buscar(self, consulta: str, limite: int = 6) -> list:
        return self.provider.buscar(consulta, limite)
