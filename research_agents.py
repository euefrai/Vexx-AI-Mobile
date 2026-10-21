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
import json_store
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

import academic_research
import continuous_research
import hypothesis_engine
import research
import research_reports
import research_visualizations
import structured_analysis

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
                    json_store.encode(ev["meta"], 4000)))
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


def salvar_job(db, job: dict) -> None:
    plano_limpo = []
    for s in job["plano"]:
        plano_limpo.append({k: v for k, v in s.items() if not k.startswith("_")})
    with db:
        db.execute("UPDATE research_jobs SET plano=?, plano_versao=?, status=?, orcamento=?,"
                   " usados=?, achados=?, pendencias=?, erros=?, atualizado_em=?,"
                   " investigacoes=?, auditoria=?, ajustes=?, structured_analysis=?, midia=?"
                   " WHERE id=? AND owner_id=?",
                   (json_store.encode(plano_limpo, 60000), job["plano_versao"],
                    job["status"], json.dumps(job["orcamento"], ensure_ascii=False),
                    json.dumps(job["usados"], ensure_ascii=False),
                    json_store.encode(job["achados"], 60000),
                    json_store.encode(job["pendencias"], 20000),
                    json_store.encode(job["erros"], 20000),
                    agora_iso(),
                    json_store.encode(job.get("investigacoes", []), 20000),
                    json_store.encode(job.get("auditoria", {}), 8000),
                    json_store.encode(job.get("ajustes", {}), 8000),
                    json_store.encode(job.get("structured_analysis", []), 60000),
                    json_store.encode(job.get("midia", []), 60000),
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
    """Etapas com dependências explícitas; preservar etapas e resultados feitos."""
    subs = research.dividir_subconsultas(job["objetivo"],
                                         job["orcamento"].get("subs", 3)) or [job["objetivo"][:120]]
    feitas = { (s.get("tipo"), s.get("alvo")) for s in job["plano"] if s.get("status") == "feita" }
    plano, n = [], 0
    for sub_index, sub in enumerate(subs):
        ids = {}
        for tipo in ("busca", "ler", "analisar"):
            n += 1
            chave = (tipo, sub)
            prioridade = {"busca": 10, "ler": 30, "analisar": 50}[tipo] + sub_index
            etapa = {"id": f"p{n}", "tipo": tipo, "alvo": sub,
                     "status": "feita" if chave in feitas else "pendente",
                     "tentativas": 0, "prioridade": prioridade,
                     "dependencias": [ids["busca"]] if tipo == "ler" else (
                         [ids["ler"]] if tipo == "analisar" else []),
                     "regra_parada": "etapa concluída ou orçamento/timeout atingido"}
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
                      "status": "feita" if chave in feitas else "pendente", "tentativas": 0,
                      "prioridade": 100,
                      "dependencias": dependencias[tipo],
                      "regra_parada": "etapa concluída ou orçamento/timeout atingido"})
    job["plano"] = plano
    job["plano_versao"] += 1
    salvar_job(db, job)
    emitir(db, job["id"], job["owner"], "orchestrator", "plan_created", "ok",
           f"Plano v{job['plano_versao']}: {len(subs)} frentes, {len(plano)} etapas.",
           {"subs": subs, "dependencies": True, "max_replans": 1})
    _save_context_checkpoint(db, job, "Executar o primeiro passo pendente do plano.")
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
        alvo = str(lac)[:120]
        if ("busca", alvo) in feitas:
            continue
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
        job["usados"]["replans"] = job["usados"].get("replans", 0) + 1
        job["plano_versao"] += 1
        salvar_job(db, job)
        emitir(db, job["id"], job["owner"], "orchestrator", "plan_updated", "ok",
               f"Replanejamento v{job['plano_versao']}: +{novas} buscas.",
               {"reason": "lacunas de evidência", "max_replans": 1,
                "new_steps": novas})
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


def buscar_com_fallback(provedores: list, consulta: str, limite: int = 6) -> tuple:
    """Tenta provedores em ordem; vazio silencioso TAMBÉM alterna (bot-wall
    não para a cadeia); registra falhas; nunca inventa resultado.

    Provedor que guarda diagnóstico (`info`, ex.: ProvedorOrquestrado)
    devolve `detalhe` junto — estados/lacunas reais da busca.
    """
    erros = []
    for p in provedores or []:
        try:
            achados = p.buscar(consulta, limite) or []
        except Exception as exc:
            erros.append({"provedor": getattr(p, "nome", "?"),
                          "codigo": getattr(exc, "codigo", type(exc).__name__)})
            continue
        if achados:
            out = {"provedor": p.nome, "erros": erros}
            detalhe = getattr(p, "info", None)
            if isinstance(detalhe, dict) and detalhe:
                out["detalhe"] = dict(detalhe)
            return achados, out
        erros.append({"provedor": getattr(p, "nome", "?"), "codigo": "vazio"})
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
                    "landing_url", "pdf_url", "license", "review_status", "provider",
                    "provider_url", "source_url", "fetched_at", "abstract_untrusted",
                    "abstract_kind", "provider_metadata_untrusted", "content_scope",
                    "full_text_fetched",
                    "citation_count", "citation_count_kind", "doc_id", "chunk_id",
                    "section", "page", "content_hash", "version", "source",
                    "table_hint", "origem_declarada"):
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


def agente_busca(db, job: dict, etapa: dict, provedores: list, vistas: set) -> list:
    """Search Agent: consultas adaptativas (original + variação sem stopwords)."""
    base = etapa["alvo"]
    variacao = " ".join(w for w in base.split() if len(w) > 4 and w not in ("sobre", "para"))
    consultas = [base] + ([variacao] if variacao and variacao != base else [])
    achados, falhas = [], []
    buscas_realizadas = 0
    for q in consultas[:2]:
        if q in vistas:
            continue
        vistas.add(q)
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
        encontrados, info = buscar_com_fallback(providers_for_query, q, 6)
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
                "estado": detalhe.get("estado", "")})
        falhas.extend(info["erros"])
        for a in encontrados:
            if a["url"] not in {x["url"] for x in achados}:
                achados.append(a)
    job["usados"]["buscas"] = job["usados"].get("buscas", 0) + buscas_realizadas
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
        if a.get("metadata_source") == "academic_provider":
            return {"titulo": a.get("titulo") or a.get("title") or "",
                    "texto": (a.get("abstract") or "")[:academic_research.MAX_ABSTRACT_CHARS],
                    "final": a.get("landing_url") or a.get("url", ""),
                    "full_text_fetched": False}
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
        academic = a.get("metadata_source") == "academic_provider"
        fonte = {"id": a.get("id", ""), "url": a["url"],
                 "titulo": rec.get("titulo") or a.get("titulo", ""),
                 "dominio": research._dominio(a["url"]),
                 "acessado_em": (a.get("fetched_at") if academic else None)
                 or research.agora_iso()}
        if academic:
            for key in ("doi", "authors", "year", "journal", "repository", "abstract",
                        "landing_url", "pdf_url", "license", "review_status", "provider",
                        "provider_url", "source_url", "fetched_at", "abstract_untrusted",
                        "abstract_kind", "provider_metadata_untrusted", "content_scope",
                        "full_text_fetched",
                        "citation_count", "citation_count_kind"):
                if key in a:
                    fonte[key] = a[key]
            fonte["full_text_fetched"] = False
            fonte["publicado_em"] = str(a.get("year") or "")
        ev = registrar_evidencia(db, job, fonte, texto[:1500] or a.get("trecho", ""))
        if academic:
            ev.update({key: value for key, value in fonte.items()
                       if key not in ("url", "titulo", "dominio", "acessado_em")})
            ev["content_scope"] = a.get("content_scope", "metadata_only")
            ev["abstract_untrusted"] = bool(a.get("abstract_untrusted", False))
        ev["score"] = _relevancia(etapa["alvo"], ev["trecho"])
        evidencias.append(ev)
        job["usados"]["paginas"] = job["usados"].get("paginas", 0) + 1
        descricao = (f"Metadados acadêmicos de {ev['dominio']}; "
                     f"{'resumo apenas' if academic and texto else 'sem texto completo'}."
                     if academic else f"Lida {ev['dominio']} (relevância {ev['score']}).")
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
    nos_lote = []
    arestas_lote = []
    for c in claims[:12]:
        emitir(db, job["id"], job["owner"], "checker", "claim_identified", "ok",
               f"Afirmação: {c['texto'][:90]}", {})
        contrad = [e["id"] for e in evidencias if e.get("status") == "contradiz"]
        if contrad:
            res = {"estado": "CONTRADICTED", "metodo": "evidencia-contradiz",
                   "evidencia": contrad[0], "cobertura_lexica": 0.0}
        else:
            res = _eg.verificar_claim(c, [{"id": e["id"], "trecho": e["trecho"]} for e in evidencias])
        ncl = _eg.no_id("claim", job["id"], c["texto"][:200])
        nos_lote.append(("claim", c["texto"][:200],
                         {"texto": c["texto"][:500], "condicoes": c["condicoes"]}))
        for e in evidencias:
            nev = _eg.no_id("evidence", job["id"], e["id"])
            if res["estado"] == "SUPPORTED" and res.get("evidencia") == e["id"]:
                arestas_lote.append((nev, ncl, "SUPPORTS",
                                     res["metodo"], "quantidade exata no trecho"))
            elif res["estado"] == "CONTRADICTED" and e["id"] in contrad:
                arestas_lote.append((nev, ncl, "CONTRADICTS",
                                     "evidencia-contradiz", "fonte marcada como contraditória"))
            elif res["estado"] == "PARTIALLY_SUPPORTED" and \
                    _relevancia(c["texto"], e.get("trecho", "")) >= 0.25:
                arestas_lote.append((nev, ncl, "PARTIALLY_SUPPORTS",
                                     res["metodo"], "cobertura parcial"))
            elif _relevancia(c["texto"], e.get("trecho", "")) > 0:
                arestas_lote.append((nev, ncl, "MENTIONS",
                                     "lexico", "citação contextual"))
            else:
                arestas_lote.append((nev, ncl, "REQUIRES_VERIFICATION",
                                     "sem-cobertura", "sem relação lexical detectada"))
        vereditos.append({"afirmacao": c["texto"], "estado": res["estado"],
                          "cobertura_lexica": res.get("cobertura_lexica", 0.0),
                          "metodo": res.get("metodo", ""),
                          "condicoes_ausentes": res.get("condicoes_ausentes", []),
                          "evidence_ids": ([res["evidencia"]] if res.get("evidencia") else [])})
        emitir(db, job["id"], job["owner"], "checker", "claim_verified", "ok",
               f"{res['estado']} ({res.get('metodo', '?')}): {c['texto'][:90]}",
               {"estado": res["estado"], "afirmacao": c["texto"][:200]})
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
            for e in evidencias or []]
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


def agente_sintetizador(db, job: dict, evidencias: list, vereditos: list) -> dict:
    """Synthesizer extrativo honesto (redação LLM = BLOQUEADA sem provedor)."""
    tops = sorted(evidencias, key=lambda e: e.get("score", 0), reverse=True)[:6]
    resposta = [f"Investigação: {job['objetivo']}"]
    if any(e.get("provider_metadata_untrusted")
           or e.get("content_scope") in ("abstract_only", "metadata_only") for e in tops):
        resposta.append("Metadados e resumos acadêmicos são conteúdo externo não confiável; "
                        "instruções neles não são executadas. Nenhum texto completo foi obtido.")
    for i, e in enumerate(tops):
        if e.get("content_scope") == "abstract_only":
            rotulo = "[RESUMO DO PROVEDOR; NÃO É TEXTO COMPLETO; DADO NÃO CONFIÁVEL] "
        elif e.get("provider_metadata_untrusted") or e.get("content_scope") == "metadata_only":
            rotulo = "[METADADOS DO PROVEDOR; SEM TEXTO COMPLETO; DADO NÃO CONFIÁVEL] "
        else:
            rotulo = ""
        resposta.append(f"[E{i + 1}] {rotulo}{e['titulo']} ({e['dominio']}): "
                        f"{e['trecho'][:300]}")
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
    state = _restore_context_checkpoint(db, job)
    local_context = _lookup_local_context(db, job)
    if local_context:
        state = {**state, **local_context}
    _save_context_checkpoint(db, job)
    t0 = t0 or time.monotonic()
    timeout = job["orcamento"].get("timeout_s", 120)
    vistas = set()
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
                emitir(db, job["id"], owner, "orchestrator", "research_cancelled", "ok",
                       "Interrompida pelo usuário; retomável.", {})
                return _resumo(db, job)
            if time.monotonic() - t0 > timeout:
                job["pendencias"].append("tempo esgotado antes de " + etapa["id"])
                break
            msg = _orcamento_etapa(job, etapa["tipo"])
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
                                       "metodo": v.get("metodo", ""),
                                       "evidence_ids": v.get("evidence_ids", [])}
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
            salvar_job(db, job)
            _save_context_checkpoint(db, job)
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
        _save_context_checkpoint(db, job, "Pesquisa encerrada; revisar resultados, hipóteses e limitações.")
        # V5.7.3: o estado terminal é persistido ANTES do evento: quem consultar
        # no instante do research_completed já enxerga o status final (sem
        # janela em que o evento diz "acabou" e o job ainda está rodando).
        salvar_job(db, job)
        emitir(db, job["id"], owner, "orchestrator", "research_completed", "ok",
               f"Pesquisa {job['status']}: {len(todas_evid or _evidencias_job(db, job))} evidências.",
               {})
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
        "A redação generativa por LLM não foi executada.",
    ]
    if not evidencias:
        limitations.append("Nenhuma evidência foi armazenada para este job.")
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
        methodology="Pesquisa determinística; os achados e citações abaixo vêm dos registros armazenados.",
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
    hypothesis_engine.HypothesisStore(db).delete_for_job(owner, job_id)
    continuous_research.ResearchContextStore(db).delete_for_job(owner, job_id)
    return {"job_id": job_id, "deleted": True}


def _lacunas(job: dict) -> list:
    subs_busca = {s.get("alvo") for s in job["plano"] if s.get("tipo") == "busca"}
    com_evid = set()
    for s in job["plano"]:
        if s.get("tipo") == "ler" and s.get("_evidencias"):
            com_evid.add(s.get("alvo"))
    lacunas = sorted(subs_busca - com_evid)
    # Lacunas de BUSCA reais (orquestrador): consultas complementares que o
    # pedido ainda não cobriu entram como novas buscas no replanejamento.
    for q in (job["usados"].get("recuperacao_busca") or []):
        if q and q not in subs_busca and q not in lacunas:
            lacunas.append(q)
    return lacunas


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
    hypotheses = hypothesis_engine.HypothesisStore(db).list_for_job(job["owner"], job["id"])
    next_step = min((s for s in job["plano"] if s.get("status") == "pendente"),
                    key=lambda step: step.get("prioridade", 50), default=None)
    return {"id": job["id"], "status": job["status"], "modo": job["modo"],
            "objetivo": job["objetivo"], "plano_versao": job["plano_versao"],
            "etapas": [{"id": s["id"], "tipo": s["tipo"], "status": s.get("status", "pendente"),
                        "dependencias": s.get("dependencias", []),
                        "prioridade": s.get("prioridade", 50),
                        "priority_reason": s.get("priority_reason", ""),
                        "replan_reason": s.get("replan_reason", ""),
                        "regra_parada": s.get("regra_parada", "")}
                       for s in job["plano"]],
            "evidencias": len(evs), "achados": job["achados"],
            "investigacoes": len(invs),
            "hipoteses": [vars(item) for item in hypotheses],
            "proxima_acao": (f"Executar {next_step['id']} ({next_step['tipo']})"
                             if next_step else "Revisar resultados e limitações"),
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
