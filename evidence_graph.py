"""JuliaEvidenceGraph (V4.6) — grafo de evidências em SQLite (sem banco externo).

Nós: sources, documents, claims, evidence (referencia `evidence`), runs.
Arestas tipadas: SUPPORTS, PARTIALLY_SUPPORTS, CONTRADICTS, MENTIONS,
DERIVED_FROM, DUPLICATES, REPLACES, REQUIRES_VERIFICATION.

Princípio (§2): rótulo factual NUNCA vem de similaridade pura. Similaridade
gera MENTIONS/DERIVED_FROM/DUPLICATES (provisório, estrutural). SUPPORTS só
por regra determinística válida (quantidade exata); o resto verificável fica
UNVERIFIED até inferência real (BLOQUEADA hoje).
"""
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone

TIPOS_RELACAO = ("SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS", "MENTIONS",
                 "DERIVED_FROM", "DUPLICATES", "REPLACES", "REQUIRES_VERIFICATION")
KINDS_NO = ("source", "document", "claim", "evidence", "run")


class GraphErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS eg_nodes (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        job_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
        dados TEXT NOT NULL DEFAULT '{}', criado_em TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS eg_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL DEFAULT 'local',
        job_id TEXT NOT NULL DEFAULT '', src TEXT NOT NULL DEFAULT '',
        dst TEXT NOT NULL DEFAULT '', tipo TEXT NOT NULL DEFAULT '',
        metodo TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL,
        UNIQUE (job_id, src, dst, tipo))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_nodes_job ON eg_nodes(owner_id, job_id, kind)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_edges_job ON eg_edges(owner_id, job_id, tipo)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_edges_dst ON eg_edges(owner_id, dst, tipo)")
    db.commit()


def _nid(*partes: str) -> str:
    return hashlib.sha256("\x00".join(partes).encode()).hexdigest()[:16]


def no_id(kind: str, job_id: str, chave: str) -> str:
    return f"{kind}:{_nid(job_id, chave)}"


def criar_no(db, owner: str, job_id: str, kind: str, chave: str, dados: dict) -> str:
    if kind not in KINDS_NO:
        raise GraphErro("kind inválido", "kind")
    nid = no_id(kind, job_id, chave)
    with db:
        db.execute("INSERT OR IGNORE INTO eg_nodes (id, owner_id, job_id, kind, dados, criado_em)"
                   " VALUES (?,?,?,?,?,?)",
                   (nid, owner, job_id, kind, json.dumps(dados, ensure_ascii=False)[:8000],
                    agora_iso()))
    return nid


def ligar(db, owner: str, job_id: str, src: str, dst: str, tipo: str,
          metodo: str = "", nota: str = "") -> None:
    if tipo not in TIPOS_RELACAO:
        raise GraphErro("relação inválida", "relacao")
    with db:
        db.execute("INSERT OR IGNORE INTO eg_edges (owner_id, job_id, src, dst, tipo, metodo,"
                   " nota, criado_em) VALUES (?,?,?,?,?,?,?,?)",
                   (owner, job_id, src, dst, tipo, metodo[:40], nota[:300], agora_iso()))


def nos_do_job(db, owner: str, job_id: str, kind: str = "") -> list:
    sql = "SELECT id, kind, dados FROM eg_nodes WHERE owner_id=? AND job_id=?"
    args = [owner, job_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    rows = db.execute(sql + " ORDER BY id", args).fetchall()
    out = []
    for nid, k, dados in rows:
        try:
            out.append({"id": nid, "kind": k, **json.loads(dados or "{}")})
        except (TypeError, ValueError):
            continue
    return out


def arestas_do_job(db, owner: str, job_id: str, tipo: str = "") -> list:
    sql = "SELECT src, dst, tipo, metodo, nota FROM eg_edges WHERE owner_id=? AND job_id=?"
    args = [owner, job_id]
    if tipo:
        sql += " AND tipo=?"
        args.append(tipo)
    return [{"src": r[0], "dst": r[1], "tipo": r[2], "metodo": r[3], "nota": r[4]}
            for r in db.execute(sql + " ORDER BY src, dst", args).fetchall()]


# ── Proveniência ────────────────────────────────────────────────────
def canonical_url(url: str) -> str:
    """URL canônica: host minúsculo, sem tracking, sem barra final boba."""
    try:
        p = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return (url or "")[:500]
    host = (p.hostname or "").lower()
    if not host:
        return (url or "")[:500]
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
          if not k.lower().startswith(("utm_", "fbclid", "gclid", "mc_", "igshid"))]
    path = p.path.rstrip("/") or "/"
    out = urllib.parse.urlunsplit((p.scheme.lower(), host, path,
                                   urllib.parse.urlencode(qs), ""))
    return out[:500]


def hash_conteudo(texto: str) -> str:
    norm = re.sub(r"\s+", " ", (texto or "").lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def contexto_trecho(texto: str, trecho: str, janela: int = 120) -> str:
    i = (texto or "").find(trecho or "")
    if i < 0 or not trecho:
        return ""
    return texto[max(0, i - janela):i + len(trecho) + janela].strip()[:600]


# ── Claims v2 (texto + condições) ───────────────────────────────────
_RX_QTD = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(%|por cento|milh[õo]es?|"
    r"bilh[õo]es?|mil\b|R\$|US\$|km\/h|km|kg|W|kW|anos?|dias?|°C|GB|MB)?", re.IGNORECASE)
_RX_COMP = re.compile(r"\b(mais|menos|maior|menor|melhor|pior|superior|inferior|rápido|lento|"
                      r"eficiente|caro|barato)\b\s+(\w+(?:\s+\w+){0,3}?)\s+(?:que|do que|em relação a|vs\.?|comparado a)\s+"
                      r"([\w\s]{2,40}?)(?:[.,;]|$)", re.IGNORECASE)
_RX_DATA = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}|janeiro|fevereiro|março|abril|maio|"
                      r"junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", re.IGNORECASE)


def _num_norm(bruto: str):
    b = bruto.replace(" ", "")
    if "." in b and "," in b:
        b = b.replace(".", "").replace(",", ".")
    elif "," in b:
        b = b.replace(",", ".")
    try:
        return float(b)
    except (TypeError, ValueError):
        return None


def extrair_quantidades(texto: str) -> list:
    out = []
    for m in _RX_QTD.finditer(texto or ""):
        v = _num_norm(m.group(1))
        if v is None or not (-1e12 < v < 1e12):
            continue
        out.append({"valor": v, "unidade": (m.group(2) or "").strip()[:12]})
    return out[:8]


def extrair_afirmacoes_v2(texto: str, teto: int = 12) -> list:
    """Divide em afirmações + condições (comparado, métrica, valor, data).

    Sem LLM: condições ausentes → marcadas como desconhecidas e o estado
    factual fica NÃO VERIFICADO (nunca presumido).
    """
    out = []
    for s in re.split(r"(?<=[.!?])\s+", texto or ""):
        s = s.strip()
        if len(s) < 40 or len(s) > 400:
            continue
        if not (re.search(r"\d", s) or re.search(r"\b[A-ZÀ-Ú][a-zà-ú]{3,}\b", s)):
            continue
        partes = re.split(r"\s+e\s+|\s+além disso,?\s+|;\s*", s)
        for parte in partes:
            parte = parte.strip()
            if len(parte) < 40:
                continue
            cond = {"comparado_a": "", "metrica": "", "quantidades": extrair_quantidades(parte),
                    "datas": _RX_DATA.findall(parte)[:3]}
            m = _RX_COMP.search(parte)
            if m:
                cond["metrica"] = (m.group(1) + " " + m.group(2)).strip()[:80]
                cond["comparado_a"] = m.group(3).strip()[:80]
            if parte not in [o["texto"] for o in out]:
                out.append({"texto": parte, "condicoes": cond})
            if len(out) >= teto:
                return out
    return out


# ── Independência ───────────────────────────────────────────────────
def _shingles(texto: str, n: int = 5) -> set:
    toks = re.findall(r"[a-zà-ú0-9]{2,}", (texto or "").lower())
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))} or set()


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def citacoes_raras_em_comum(a: str, b: str, minimo: int = 60) -> list:
    """Trechos literais longos compartilhados (sinal de republicação)."""
    out = []
    for m in re.finditer(r'"([^"]{40,})"', (a or "") + "\n" + (b or "")):
        frag = m.group(1)
        if frag in (a or "") and frag in (b or "") and len(frag) >= minimo:
            out.append(frag[:120])
    return out[:3]


def analisar_independencia(doc_a: dict, doc_b: dict) -> dict:
    """Domínio diferente NÃO prova independência; conclusão igual NÃO prova
    dependência. Retorna laudo com evidências estruturais."""
    url_a = canonical_url(doc_a.get("url", ""))
    url_b = canonical_url(doc_b.get("url", ""))
    mesmo_doc = url_a == url_b and bool(url_a)
    hash_a, hash_b = hash_conteudo(doc_a.get("texto", "")), hash_conteudo(doc_b.get("texto", ""))
    sim = jaccard(_shingles(doc_a.get("texto", "")), _shingles(doc_b.get("texto", "")))
    citadas = citacoes_raras_em_comum(doc_a.get("texto", ""), doc_b.get("texto", ""))
    dom_a = (urllib.parse.urlsplit(url_a).hostname or "") if url_a else ""
    dom_b = (urllib.parse.urlsplit(url_b).hostname or "") if url_b else ""
    if mesmo_doc or hash_a == hash_b:
        return {"relacao": "DUPLICATES", "confianca": "estrutural",
                "motivo": "mesmo documento/conteúdo idêntico"}
    if sim >= 0.6 or citadas:
        return {"relacao": "DERIVED_FROM", "confianca": "estrutural",
                "motivo": f"similaridade {sim}" + (" + citação literal" if citadas else "")}
    if dom_a and dom_a == dom_b:
        return {"relacao": "MENTIONS", "confianca": "estrutural",
                "motivo": "mesmo domínio, textos distintos: relação desconhecida"}
    return {"relacao": "MENTIONS", "confianca": "estrutural",
            "motivo": "domínios distintos sem cópia detectada: independência NÃO presumida"}


# ── Contradições: investigação por dimensão ─────────────────────────
UNIDADES_CONVERSIVEIS = {"W", "kW", "km", "m", "kg", "g", "C", "F", "%"}


def _mesma_medida(qa: dict, qb: dict) -> bool:
    ua, ub = (qa.get("unidade") or ""), (qb.get("unidade") or "")
    if ua == ub:
        return True
    pares = ({"W", "kW"}, {"km", "m"}, {"kg", "g"}, {"C", "F"})
    return any({ua, ub} == p for p in pares)


def investigar_divergencia(claim_a: dict, claim_b: dict, fonte_a: str, fonte_b: str) -> dict:
    """Classifica a dimensão da divergência; nunca inventa reconciliação."""
    qa = (claim_a.get("condicoes", {}) or {}).get("quantidades", [])
    qb = (claim_b.get("condicoes", {}) or {}).get("quantidades", [])
    da = (claim_a.get("condicoes", {}) or {}).get("datas", [])
    db = (claim_b.get("condicoes", {}) or {}).get("datas", [])
    if qa and qb and not _mesma_medida(qa[0], qb[0]):
        return {"tipo": "unidade_ou_metrica", "status": "em_aberto",
                "explicacao": f"Medidas distintas ({qa[0].get('unidade')} × {qb[0].get('unidade')}): "
                              "podem não falar da mesma coisa.",
                "follow_up": [f"{qa[0].get('unidade')} vs {qb[0].get('unidade')} metodologia medição"]}
    if qa and qb and qa[0].get("unidade") == qb[0].get("unidade") and qa[0]["valor"] != qb[0]["valor"]:
        return {"tipo": "valor_divergente", "status": "em_aberto",
                "explicacao": f"Mesma unidade, valores distintos ({qa[0]['valor']} × {qb[0]['valor']}). "
                              "Verificar metodologia, data e condições.",
                "follow_up": ["metodologia medição", "data atualização dado"]}
    if da != db and (da or db):
        return {"tipo": "data_divergente", "status": "em_aberto",
                "explicacao": "Datas distintas: a mais recente pode atualizar a anterior.",
                "follow_up": ["dado atualizado"]}
    ca, cb = (claim_a.get("condicoes", {}) or {}).get("comparado_a", ""), \
        (claim_b.get("condicoes", {}) or {}).get("comparado_a", "")
    if ca and cb and ca.lower() != cb.lower():
        return {"tipo": "contexto_divergente", "status": "em_aberto",
                "explicacao": f"Comparados distintos ('{ca}' × '{cb}'): conclusões podem coexistir.",
                "follow_up": []}
    return {"tipo": "inconclusivo", "status": "em_aberto",
            "explicacao": "Divergência sem dimensão identificável; requer leitura humana.",
            "follow_up": []}


# ── Verificação 2.0 ─────────────────────────────────────────────────
def verificar_claim(claim: dict, evidencias: list) -> dict:
    """Regras determinísticas válidas; o resto fica UNVERIFIED (nunca similaridade)."""
    cond = claim.get("condicoes", {}) or {}
    cqs = cond.get("quantidades", [])
    for e in evidencias or []:
        eqs = extrair_quantidades(e.get("trecho", ""))
        for q in cqs:
            for x in eqs:
                if x["valor"] == q["valor"] and (x["unidade"] or "") == (q["unidade"] or ""):
                    return {"estado": "SUPPORTED", "metodo": "quantidade-exata",
                            "evidencia": e.get("id", ""), "cobertura_lexica": 1.0}
    neg = any("não " in (e.get("trecho", "") or "").lower() or "nunca " in
              (e.get("trecho", "") or "").lower() for e in evidencias or [])
    if evidencias and not neg:
        from research_agents import cobertura as _cob
        cov = _cob(claim["texto"], [e.get("trecho", "") for e in evidencias])
        if cov >= 0.25:
            return {"estado": "PARTIALLY_SUPPORTED", "metodo": "lexico-provisorio",
                    "evidencia": "", "cobertura_lexica": cov}
    if not evidencias:
        return {"estado": "INSUFFICIENT_EVIDENCE", "metodo": "sem-evidencia",
                "evidencia": "", "cobertura_lexica": 0.0}
    faltas = []
    if not cond.get("comparado_a") and re.search(r"(?i)\b(mais|menos|melhor|pior)\b", claim["texto"]):
        faltas.append("comparado ausente")
    if cqs and not cond.get("datas"):
        faltas.append("data ausente p/ quantidade")
    return {"estado": "UNVERIFIED", "metodo": "lexico-provisorio",
            "evidencia": "", "cobertura_lexica": 0.0,
            "condicoes_ausentes": faltas}


# ── Auditor 2.0 ─────────────────────────────────────────────────────
SUPERLATIVOS = ("sempre", "nunca", "todos", "todas", "garante", "garantido",
                "com certeza", "impossível", "ninguém", "jamais")


def auditar_resposta(texto: str, claims: list, vereditos: dict, fontes: list) -> dict:
    """Relatório de auditoria: afirmações × evidências × generalizações × lacunas."""
    ids = {f.get("id") for f in fontes or []}
    citadas = {m.group(0) for m in re.finditer(r"\[(?:E|S)\d+\]", texto or "")}
    fantasmas = sorted(c for c in citadas if c.strip("[]") not in ids)
    generalizacoes = []
    for c in claims or []:
        t = (c.get("texto") or "").lower()
        if any(s in t for s in SUPERLATIVOS):
            v = vereditos.get(c.get("texto", ""), {})
            if v.get("estado") != "SUPPORTED":
                generalizacoes.append(c["texto"][:140])
    sem_evidencia = [c["texto"][:140] for c in claims or []
                     if vereditos.get(c.get("texto", ""), {}).get("estado")
                     in ("UNVERIFIED", "INSUFFICIENT_EVIDENCE")]
    return {"afirmacoes": len(claims or []),
            "citacoes_fantasma": fantasmas,
            "generalizacoes_excessivas": generalizacoes,
            "sem_evidencia_suficiente": sem_evidencia,
            "etapa_semantica": "BLOQUEADA",
            "ok": not fantasmas and not sem_evidencia}
