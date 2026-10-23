"""JDUI 1.0 — contrato declarativo `JULIA-ui-message/v1`.

A IA descreve interfaces em blocos ```jdui (JSON). NENHUM JavaScript do modelo
é executado: o frontend renderiza apenas componentes do registry, com funções
locais previamente registradas. Blocos inválidos/desconhecidos caem em
fallback seguro (nunca travam o chat).

Este módulo (stdlib only) faz extração + validação + normalização no PC.
O frontend possui o espelho de validação/render em `public/jdui.js`; ambos
são testados contra os mesmos payloads de `docs/JULIA_DYNAMIC_UI_EXAMPLES.md`.
"""
import json
import logging
import re
import model3d
from urllib.parse import urlsplit

log = logging.getLogger("JULIA-jdui")

VERSION = "JULIA-ui-message/v1"
FENCE_RE = re.compile(r"```jdui\s*\n([\s\S]*?)(?:```|$)", re.IGNORECASE)
MAX_BLOCOS_MSG = 6
MAX_JSON_BYTES = 24000
MAX_DEPTH = 8
MAX_STR = 2000

TIPOS_CAMPO = ("text", "number", "select")


def _str(v, limite=MAX_STR) -> str:
    return str(v or "")[:limite] if isinstance(v, (str, int, float)) else ""


def _num(v, padrao=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def _url(u) -> str:
    u = _str(u, 500)
    if not re.match(r"^https?://", u, re.IGNORECASE) or any(ord(char) < 32 for char in u):
        return ""
    try:
        parsed = urlsplit(u)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        parsed.port
    except ValueError:
        return ""
    return u


def _url_recurso(u) -> str:
    """A real remote URL or a narrow same-origin download route.

    This is intentionally stricter than a generic relative URL: generated UI
    may point to a research export it knows about, not to arbitrary internal
    endpoints (which could become a confused-deputy action).
    """
    remote = _url(u)
    if remote:
        return remote
    path = _str(u, 500)
    if not path.startswith("/api/research/export?"):
        return ""
    try:
        parsed = urlsplit(path)
        allowed = {"job_id", "formato"}
        query = parsed.query
        if parsed.scheme or parsed.netloc or parsed.fragment:
            return ""
        if parsed.path != "/api/research/export" or not query or len(query) > 200:
            return ""
        from urllib.parse import parse_qsl
        pares = parse_qsl(query, keep_blank_values=False)
        if not pares or any(k not in allowed for k, _ in pares):
            return ""
        dados = dict(pares)
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", dados.get("job_id", "")):
            return ""
        if dados.get("formato", "md") not in ("md", "csv", "json"):
            return ""
    except (ValueError, TypeError):
        return ""
    return path


def _provenance(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise JduiErro("sources deve ser uma lista com até 20 referências")
    sources, ids = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise JduiErro("source inválida")
        source_id = _str(item.get("id"), 100)
        title = _str(item.get("title"), 160)
        if not source_id or not title or source_id in ids:
            raise JduiErro("source exige id e título únicos")
        ids.add(source_id)
        sources.append({
            "id": source_id,
            "title": title,
            "url": _url(item.get("url")),
            "locator": _str(item.get("locator"), 120),
            "period": _str(item.get("period"), 100),
            "methodology": _str(item.get("methodology"), 200),
            "analysis_method": _str(item.get("analysis_method"), 80),
        })
    return sources


def _profundidade(obj, nivel=0):
    if nivel > MAX_DEPTH:
        return nivel
    if isinstance(obj, dict):
        return max([nivel] + [_profundidade(v, nivel + 1) for v in obj.values()], default=nivel)
    if isinstance(obj, list):
        return max([nivel] + [_profundidade(v, nivel + 1) for v in obj], default=nivel)
    return nivel


# ── Validadores por componente (retornam props normalizadas ou levantam JduiErro)
class JduiErro(ValueError):
    pass


def _v_quiz(p: dict) -> dict:
    titulo = _str(p.get("title"), 160)
    qs = p.get("questions")
    if not isinstance(qs, list) or not (1 <= len(qs) <= 12):
        raise JduiErro("quiz.questions: 1..12 obrigatórias")
    out = []
    for q in qs:
        if not isinstance(q, dict):
            raise JduiErro("quiz.question inválida")
        opts = q.get("options")
        if not isinstance(opts, list) or not (2 <= len(opts) <= 6):
            raise JduiErro("quiz.options: 2..6 obrigatórias")
        ans = q.get("answer", 0)
        if not isinstance(ans, int) or not (0 <= ans < len(opts)):
            raise JduiErro("quiz.answer fora do intervalo")
        out.append({"q": _str(q.get("q"), 400),
                    "options": [_str(o, 200) for o in opts],
                    "answer": ans, "explain": _str(q.get("explain"), 500)})
    return {"title": titulo, "questions": out}


def _v_checklist(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (1 <= len(itens) <= 30):
        raise JduiErro("checklist.items: 1..30 obrigatórios")
    return {"title": _str(p.get("title"), 160),
            "items": [{"label": _str(i.get("label") if isinstance(i, dict) else i, 200),
                       "checked": bool(i.get("checked")) if isinstance(i, dict) else False}
                      for i in itens]}


def _v_cards(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (1 <= len(itens) <= 8):
        raise JduiErro("cards.items: 1..8 obrigatórios")
    out = []
    for c in itens:
        if not isinstance(c, dict) or not _str(c.get("title")):
            raise JduiErro("cards.item sem title")
        acao = c.get("action") or {}
        out.append({"title": _str(c.get("title"), 160), "desc": _str(c.get("desc"), 400),
                    "value": _str(c.get("value"), 80), "badge": _str(c.get("badge"), 40),
                    "url": _url(c.get("url")),
                    "action": {"chat": _str(acao.get("chat"), 300)} if isinstance(acao, dict) and acao.get("chat") else {}})
    return {"title": _str(p.get("title"), 160), "items": out}


def _v_diagram(p: dict) -> dict:
    nos = p.get("nodes")
    if not isinstance(nos, list) or not (1 <= len(nos) <= 12):
        raise JduiErro("diagram.nodes: 1..12 obrigatórios")
    ids = set()
    norm_nos = []
    for n in nos:
        if not isinstance(n, dict) or not _str(n.get("id"), 40):
            raise JduiErro("diagram.node sem id")
        nid = _str(n.get("id"), 40)
        ids.add(nid)
        norm_nos.append({"id": nid, "label": _str(n.get("label"), 120),
                         "desc": _str(n.get("desc"), 300),
                         "status": _str(n.get("status"), 20),
                         "icon": _str(n.get("icon"), 12),
                         "group": _str(n.get("group"), 60)})
    arestas = []
    for e in p.get("edges") or []:
        if not isinstance(e, dict):
            continue
        f, t = _str(e.get("from"), 40), _str(e.get("to"), 40)
        if f in ids and t in ids and len(arestas) < 16:
            arestas.append({"from": f, "to": t, "label": _str(e.get("label"), 80)})
    direcao = _str(p.get("direction"), 10).lower()
    return {"title": _str(p.get("title"), 160), "nodes": norm_nos, "edges": arestas,
            "direction": direcao if direcao in ("v", "h") else "v"}


def _v_table(p: dict) -> dict:
    cols = p.get("columns")
    linhas = p.get("rows")
    if not isinstance(cols, list) or not (1 <= len(cols) <= 8):
        raise JduiErro("table.columns: 1..8 obrigatórias")
    if not isinstance(linhas, list) or len(linhas) > 30:
        raise JduiErro("table.rows: máx 30")
    cols = [_str(c, 80) for c in cols]
    norm = []
    for r in linhas:
        if not isinstance(r, list):
            raise JduiErro("table.row deve ser lista")
        norm.append([_str(c, 200) for c in r[:len(cols)]])
    return {"title": _str(p.get("title"), 160), "columns": cols, "rows": norm}


def _v_form(p: dict) -> dict:
    campos = p.get("fields")
    if not isinstance(campos, list) or not (1 <= len(campos) <= 10):
        raise JduiErro("form.fields: 1..10 obrigatórios")
    norm = []
    for f in campos:
        if not isinstance(f, dict) or not _str(f.get("name"), 40):
            raise JduiErro("form.field sem name")
        tipo = _str(f.get("type"), 10).lower() or "text"
        if tipo not in TIPOS_CAMPO:
            raise JduiErro("form.field.type inválido")
        norm.append({"name": _str(f.get("name"), 40), "label": _str(f.get("label"), 80),
                     "type": tipo,
                     "options": [_str(o, 80) for o in f.get("options", [])][:8] if tipo == "select" else [],
                     "required": bool(f.get("required"))})
    calc = _str(p.get("calc"), 40).lower()
    if calc and calc not in ("imc", "juros", "porcentagem", "soma"):
        raise JduiErro("form.calc desconhecido")
    return {"title": _str(p.get("title"), 160), "fields": norm,
            "calc": calc, "submit": _str(p.get("submit"), 40) or "Calcular"}


def _v_progress(p: dict) -> dict:
    total = _num(p.get("max", 100)) or 100
    return {"label": _str(p.get("label"), 120),
            "value": min(max(_num(p.get("value")), 0), total), "max": total}


def _v_tabs(p: dict) -> dict:
    abas = p.get("tabs")
    if not isinstance(abas, list) or not (2 <= len(abas) <= 6):
        raise JduiErro("tabs: 2..6 obrigatórias")
    return {"tabs": [{"title": _str(a.get("title"), 80), "markdown": _str(a.get("markdown"), 3000)}
                     for a in abas if isinstance(a, dict) and _str(a.get("title"))]}


def _v_accordion(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (1 <= len(itens) <= 10):
        raise JduiErro("accordion.items: 1..10 obrigatórios")
    return {"items": [{"title": _str(a.get("title"), 120), "markdown": _str(a.get("markdown"), 3000)}
                      for a in itens if isinstance(a, dict) and _str(a.get("title"))]}


def _v_exam(p: dict) -> dict:
    aid = _str(p.get("assessment_id"), 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", aid):
        raise JduiErro("exam.assessment_id inválido")
    return {"assessment_id": aid, "title": _str(p.get("title"), 160)}


def _v_studyplan(p: dict) -> dict:
    pid = _str(p.get("plan_id"), 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", pid):
        raise JduiErro("studyplan.plan_id inválido")
    return {"plan_id": pid}


def _v_flashcards(p: dict) -> dict:
    return {"assunto": _str(p.get("assunto"), 120)}


def _v_progresso(p: dict) -> dict:
    return {}


def _v_lesson(p: dict) -> dict:
    lid = _str(p.get("lesson_id"), 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", lid):
        raise JduiErro("lesson.lesson_id inválido")
    return {"lesson_id": lid, "title": _str(p.get("title"), 160)}


TIPOS_CHART = ("line", "bar", "pie", "area", "scatter")


def _num_finito(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise JduiErro("chart: valor numérico inválido")
    if f != f or f in (float("inf"), float("-inf")) or abs(f) > 1e12:
        raise JduiErro("chart: valor fora da escala")
    return f


def _v_chart(p: dict) -> dict:
    """Gráfico factual: séries numéricas validadas (a IA nunca inventa números aqui)."""
    tipo = str(p.get("type", "bar")).lower()
    if tipo not in TIPOS_CHART:
        raise JduiErro("chart.type: line|bar|pie|area|scatter")
    series = p.get("series")
    if not isinstance(series, list) or not (1 <= len(series) <= 6):
        raise JduiErro("chart.series: 1..6 obrigatórias")
    if tipo == "pie" and len(series) != 1:
        raise JduiErro("chart pie: exatamente 1 série")
    norm = []
    for s in series:
        if not isinstance(s, dict):
            raise JduiErro("chart.serie inválida")
        vals = s.get("values")
        if not isinstance(vals, list) or not (1 <= len(vals) <= 24):
            raise JduiErro("chart.values: 1..24 obrigatórios")
        if tipo == "scatter":
            pts = []
            for v in vals:
                if not isinstance(v, list) or len(v) != 2:
                    raise JduiErro("chart scatter: pares [x, y]")
                pts.append([_num_finito(v[0]), _num_finito(v[1])])
            norm.append({"label": _str(s.get("label"), 60), "values": pts})
        else:
            norm.append({"label": _str(s.get("label"), 60),
                         "values": [_num_finito(v) for v in vals]})
    labels = p.get("labels", [])
    if labels is not None and not isinstance(labels, list):
        raise JduiErro("chart.labels deve ser lista")
    labels = [_str(l, 40) for l in (labels or [])][:24]
    if labels and tipo != "scatter":
        ref = len(norm[0]["values"])
        if len(labels) != ref:
            raise JduiErro("chart.labels deve acompanhar os valores")
    return {"type": tipo, "title": _str(p.get("title"), 160), "labels": labels,
            "series": norm, "source": _str(p.get("source"), 160),
            "x_label": _str(p.get("x_label"), 60), "y_label": _str(p.get("y_label"), 60),
            "sources": _provenance(p.get("sources"))}


def _v_dashboard(p: dict) -> dict:
    mets = p.get("metrics")
    if not isinstance(mets, list) or not (1 <= len(mets) <= 8):
        raise JduiErro("dashboard.metrics: 1..8 obrigatórias")
    norm_m = []
    for m in mets:
        if not isinstance(m, dict) or not _str(m.get("label"), 60):
            raise JduiErro("dashboard.metric inválida")
        norm_m.append({"label": _str(m.get("label"), 60), "value": _str(m.get("value"), 40),
                       "hint": _str(m.get("hint"), 120)})
    chart = None
    if p.get("chart") is not None:
        if not isinstance(p.get("chart"), dict):
            raise JduiErro("dashboard.chart inválido")
        chart = _v_chart(p["chart"])
        if len(chart["series"]) > 3:
            raise JduiErro("dashboard.chart: máx 3 séries")
    return {"title": _str(p.get("title"), 160), "metrics": norm_m, "chart": chart,
            "source": _str(p.get("source"), 160), "sources": _provenance(p.get("sources"))}


def _v_compare(p: dict) -> dict:
    cols = p.get("columns")
    if not isinstance(cols, list) or len(cols) != 2 or not all(_str(c, 40) for c in cols):
        raise JduiErro("compare.columns: exatamente 2 rótulos")
    rows = p.get("rows")
    if not isinstance(rows, list) or not (1 <= len(rows) <= 12):
        raise JduiErro("compare.rows: 1..12 obrigatórias")
    norm = []
    for r in rows:
        if not isinstance(r, dict) or not _str(r.get("label"), 80):
            raise JduiErro("compare.row inválida")
        melhor = str(r.get("melhor", "")).lower()
        if melhor not in ("", "a", "b", "="):
            raise JduiErro("compare.melhor: a|b|=")
        norm.append({"label": _str(r.get("label"), 80), "a": _str(r.get("a"), 120),
                     "b": _str(r.get("b"), 120), "melhor": melhor})
    return {"title": _str(p.get("title"), 160),
            "columns": [_str(cols[0], 40), _str(cols[1], 40)], "rows": norm,
            "sources": _provenance(p.get("sources"))}


def _v_evidencegraph(p: dict) -> dict:
    """Grafo de evidências: nós (claim|source|evidence) + arestas tipadas."""
    nos = p.get("nodes")
    if not isinstance(nos, list) or not (1 <= len(nos) <= 30):
        raise JduiErro("evidencegraph.nodes: 1..30 obrigatórios")
    kinds = ("claim", "source", "evidence")
    norm_n, ids = [], set()
    for n in nos:
        if not isinstance(n, dict) or not _str(n.get("id"), 40):
            raise JduiErro("evidencegraph.node sem id")
        nid = _str(n.get("id"), 40)
        kind = str(n.get("kind", "evidence")).lower()
        if kind not in kinds:
            raise JduiErro("evidencegraph.kind: claim|source|evidence")
        ids.add(nid)
        norm_n.append({"id": nid, "label": _str(n.get("label"), 80), "kind": kind,
                       "estado": _str(n.get("estado"), 40), "detalhe": _str(n.get("detalhe"), 200)})
    norm_e = []
    for e in p.get("edges") or []:
        if not isinstance(e, dict):
            continue
        f, t = _str(e.get("from"), 40), _str(e.get("to"), 40)
        tipo = str(e.get("label", "")).upper()
        if f in ids and t in ids and len(norm_e) < 60 and tipo in (
                "SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS", "MENTIONS",
                "DERIVED_FROM", "DUPLICATES", "REQUIRES_VERIFICATION"):
            norm_e.append({"from": f, "to": t, "label": tipo})
    return {"title": _str(p.get("title"), 160), "nodes": norm_n, "edges": norm_e}


CALCULATOR_KINDS = ("basic", "imc", "porcentagem", "juros", "conversor")


def _v_calculator(p: dict) -> dict:
    kind = str(p.get("kind", "basic")).lower()
    if kind not in CALCULATOR_KINDS:
        raise JduiErro("calculator.kind inválido")
    return {"kind": kind, "title": _str(p.get("title"), 120)}


# ── Produtos (V4.9.1 Shopping Intelligence; dados reais de ferramenta) ──
DISPONIBILIDADE = ("em_estoque", "sem_estoque", "estoque_limitado",
                   "pre_venda", "desconhecida")
VEREDITOS_LINK = ("verificado", "parcial", "reprovado", "nao_verificado")


def _veredito_link(v) -> str:
    """V5.5: estado verificado do link/imagem (fora do enum → vazio, sem inventar)."""
    v = str(v or "").lower()
    return v if v in VEREDITOS_LINK else ""


def _v_oferta(o) -> dict:
    if not isinstance(o, dict):
        raise JduiErro("oferta inválida")
    pv = o.get("preco_valor", o.get("preco"))
    try:
        pv = float(pv) if pv is not None else None
    except (TypeError, ValueError):
        pv = None
    if pv is not None and not (0 < pv < 1e9):
        pv = None
    av = o.get("avaliacao")
    try:
        av = float(av) if av is not None else None
    except (TypeError, ValueError):
        av = None
    if av is not None and not (0 <= av <= 5):
        av = None
    try:
        nv = o.get("n_avaliacoes")
        nv = int(nv) if nv is not None else None
    except (TypeError, ValueError):
        nv = None
    if nv is not None and not (0 <= nv < 10_000_000):
        nv = None
    disp = str(o.get("disponibilidade", "desconhecida")).lower()
    if disp not in DISPONIBILIDADE:
        disp = "desconhecida"
    specs = o.get("specs") or {}
    if not isinstance(specs, dict):
        raise JduiErro("produto.specs deve ser objeto")
    norm_specs = {}
    for k, v in list(specs.items())[:12]:
        if _str(k, 40) and isinstance(v, (str, int, float)):
            norm_specs[_str(k, 40)] = _str(v, 120)
    ofertas = []
    for item in (o.get("ofertas") or [])[:6]:
        if not isinstance(item, dict):
            continue
        ofertas.append({"loja": _str(item.get("loja"), 80),
                        "preco": _str(item.get("preco"), 40),
                        "url": _url(item.get("url"))})
    return {
        "nome": _str(o.get("nome") or o.get("name"), 160),
        "marca": _str(o.get("marca") or o.get("brand"), 80),
        "modelo": _str(o.get("modelo") or o.get("model"), 80),
        "variante": _str(o.get("variante"), 80),
        "imagem": _url(o.get("imagem") or o.get("image")),
        "preco": _str(o.get("preco"), 40),
        "preco_valor": pv,
        "moeda": _str(o.get("moeda"), 3).upper() or "BRL",
        "loja": _str(o.get("loja") or o.get("store"), 80),
        "url": _url(o.get("url")),
        "specs": norm_specs,
        "avaliacao": av,
        "n_avaliacoes": nv,
        "disponibilidade": disp,
        "verificado_em": _str(o.get("verificado_em"), 48),
        "ofertas": ofertas,
        "link_veredito": _veredito_link(o.get("link_veredito")),
        "link_motivo": _str(o.get("link_motivo"), 120),
        "item_de_listagem": bool(o.get("item_de_listagem")),
        "imagem_veredito": _veredito_link(o.get("imagem_veredito")),
        "imagem_motivo": _str(o.get("imagem_motivo"), 120),
    }


def _v_produto_obrigatorio(p: dict) -> dict:
    prod = _v_oferta(p.get("produto") if isinstance(p.get("produto"), dict) else p)
    if not prod["nome"]:
        raise JduiErro("produto.nome obrigatório")
    return prod


def _v_productcard(p: dict) -> dict:
    prod = p.get("produto") if isinstance(p.get("produto"), dict) else p
    if not isinstance(prod, dict):
        raise JduiErro("productcard.produto obrigatório")
    return {"produto": _v_produto_obrigatorio(prod),
            "sources": _provenance(p.get("sources"))}


def _v_productgrid(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (1 <= len(itens) <= 6):
        raise JduiErro("productgrid.items: 1..6 obrigatórios")
    out = []
    for item in itens:
        if not isinstance(item, dict):
            raise JduiErro("productgrid.item inválido")
        out.append(_v_produto_obrigatorio(item))
    return {"title": _str(p.get("title"), 160), "items": out,
            "sources": _provenance(p.get("sources"))}


def _v_productcompare(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (2 <= len(itens) <= 4):
        raise JduiErro("productcompare.items: 2..4 obrigatórios")
    out = []
    for item in itens:
        if not isinstance(item, dict):
            raise JduiErro("productcompare.item inválido")
        out.append(_v_produto_obrigatorio(item))
    return {"title": _str(p.get("title"), 160), "items": out,
            "sources": _provenance(p.get("sources"))}


def _v_productdetails(p: dict) -> dict:
    prod = p.get("produto") if isinstance(p.get("produto"), dict) else None
    if not isinstance(prod, dict):
        raise JduiErro("productdetails.produto obrigatório")
    return {"produto": _v_produto_obrigatorio(prod),
            "sources": _provenance(p.get("sources"))}


def _v_productgallery(p: dict) -> dict:
    imgs = p.get("imagens") or p.get("images")
    if not isinstance(imgs, list) or not (1 <= len(imgs) <= 8):
        raise JduiErro("productgallery.imagens: 1..8 obrigatórias")
    out = []
    for img in imgs:
        if isinstance(img, str):
            u, legenda = img, ""
        elif isinstance(img, dict):
            u, legenda = img.get("url") or img.get("src"), img.get("legenda") or img.get("caption")
        else:
            continue
        u = _url(u)
        if u:
            out.append({"url": u, "legenda": _str(legenda, 120)})
    if not out:
        raise JduiErro("productgallery sem imagem válida")
    return {"title": _str(p.get("title"), 160), "imagens": out,
            "sources": _provenance(p.get("sources"))}


RESEARCH_STATES = ("SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED",
                   "UNVERIFIED", "INCONCLUSIVE")
RESEARCH_RELATIONS = ("SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS",
                      "MENTIONS", "REQUIRES_VERIFICATION")
PLAN_STATES = ("planned", "running", "paused", "completed", "failed", "cancelled")
PLAN_STEP_STATES = {"pending": "todo", "todo": "todo", "active": "doing",
                    "doing": "doing", "em_andamento": "doing", "pausada": "todo",
                    "done": "done", "feita": "done", "removida": "skipped",
                    "skipped": "skipped", "error": "error", "erro": "error"}
MEDIA_TYPES = ("image", "video", "document")
MEDIA_ACCESS = ("metadata_only", "link_only", "not_fetched", "read", "snippet_only")
MEDIA_VALIDATION = ("unverified", "blocked", "invalid")
MEDIA_ANALYSIS = ("not_analyzed",)


def _v_researchplan(p: dict) -> dict:
    """Plan/progress from real steps; percent is computed, never trusted."""
    steps = p.get("steps")
    if not isinstance(steps, list) or not (1 <= len(steps) <= 24):
        raise JduiErro("researchplan.steps: 1..24 obrigatórios")
    out, ids = [], set()
    for step in steps:
        if not isinstance(step, dict) or not _str(step.get("id"), 40):
            raise JduiErro("researchplan.step sem id")
        sid = _str(step.get("id"), 40)
        if sid in ids:
            raise JduiErro("researchplan.step id duplicado")
        if not _str(step.get("title")):
            raise JduiErro("researchplan.step sem title")
        ids.add(sid)
        status = PLAN_STEP_STATES.get(str(step.get("status", "pending")).lower(), "todo")
        deps = step.get("dependencies") if isinstance(step.get("dependencies"), list) else []
        out.append({
            "id": sid, "title": _str(step.get("title"), 160),
            "kind": _str(step.get("kind"), 24) or "research",
            "status": status,
            "detail": _str(step.get("detail") or step.get("objetivo_etapa"), 500),
            "stop_condition": _str(step.get("stop_condition") or step.get("regra_parada"), 300),
            "dependencies": [_str(d, 40) for d in deps[:8] if _str(d, 40)],
        })
    for step in out:
        step["dependencies"] = [d for d in step["dependencies"]
                                if d in ids and d != step["id"]]
    done = sum(1 for step in out if step["status"] == "done")
    skipped = sum(1 for step in out if step["status"] == "skipped")
    errors = sum(1 for step in out if step["status"] == "error")
    total = len(out)
    pct = round(done / total * 100, 1) if total else 0.0
    status = str(p.get("status", "planned")).lower()
    if status not in PLAN_STATES:
        status = "planned"
    orcamento = p.get("budgets") if isinstance(p.get("budgets"), dict) else {}
    usado = p.get("used") if isinstance(p.get("used"), dict) else {}
    def _nmap(obj, keys):
        return {key: max(0, min(1_000_000, _num(obj.get(key)))) for key in keys
                if obj.get(key) is not None}
    return {
        "title": _str(p.get("title"), 160) or "Plano de pesquisa",
        "objective": _str(p.get("objective") or p.get("objetivo"), 500),
        "mode": _str(p.get("mode") or p.get("modo"), 40),
        "status": status,
        "steps": out,
        "progress": {"done": done, "total": total, "skipped": skipped,
                     "errors": errors, "percent": pct},
        "budgets": _nmap(orcamento, ("buscas", "paginas", "timeout_s", "subs", "replans",
                                     "midia", "concorrencia", "max_bytes_pagina")),
        "used": _nmap(usado, ("buscas", "paginas", "replans")),
        "sources": _provenance(p.get("sources")),
    }


def _v_researchevidence(p: dict) -> dict:
    """Claim table where counts come from the sources actually attached."""
    claims = p.get("claims")
    if not isinstance(claims, list) or not (1 <= len(claims) <= 10):
        raise JduiErro("evidence.claims: 1..10 obrigatórias")
    out = []
    for claim in claims:
        if not isinstance(claim, dict) or not _str(claim.get("statement") or claim.get("afirmacao")):
            raise JduiErro("evidence.claim sem statement")
        estado = str(claim.get("state") or claim.get("estado") or "UNVERIFIED").upper()
        if estado not in RESEARCH_STATES:
            raise JduiErro("evidence.state inválido")
        fontes = claim.get("sources") or claim.get("fontes") or []
        if not isinstance(fontes, list) or len(fontes) > 12:
            raise JduiErro("evidence.sources: máx 12")
        norm_fontes = []
        for fonte in fontes:
            if not isinstance(fonte, dict):
                raise JduiErro("evidence.source inválida")
            relation = str(fonte.get("relation") or "REQUIRES_VERIFICATION").upper()
            if relation not in RESEARCH_RELATIONS:
                raise JduiErro("evidence.relation inválida")
            title = _str(fonte.get("title") or fonte.get("titulo"), 160)
            if not title:
                raise JduiErro("evidence.source sem título")
            norm_fontes.append({
                "id": _str(fonte.get("id") or fonte.get("evidence_id"), 80),
                "title": title,
                "url": _url(fonte.get("url")),
                "domain": _str(fonte.get("domain") or fonte.get("dominio"), 120),
                "relation": relation,
                "read": bool(fonte.get("read")),
                "access_state": _str(fonte.get("access_state"), 40),
                "excerpt": _str(fonte.get("excerpt") or fonte.get("used_excerpt"), 500),
                "published_at": _str(fonte.get("published_at") or fonte.get("data"), 48),
            })
        if estado in ("SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED") and not norm_fontes:
            raise JduiErro("evidence: estado apoiado exige fonte")
        if estado == "SUPPORTED" and not any(
                fonte["relation"] in ("SUPPORTS", "PARTIALLY_SUPPORTS") for fonte in norm_fontes):
            raise JduiErro("evidence: SUPPORTED exige relação de apoio")
        if estado == "CONTRADICTED" and not any(
                fonte["relation"] == "CONTRADICTS" for fonte in norm_fontes):
            raise JduiErro("evidence: CONTRADICTED exige fonte contraditória")
        out.append({
            "statement": _str(claim.get("statement") or claim.get("afirmacao"), 1200),
            "state": estado,
            "method": _str(claim.get("method") or claim.get("metodo"), 200),
            "coverage": max(0.0, min(1.0, _num(claim.get("coverage") or
                                              claim.get("cobertura_lexica")))),
            "sources": norm_fontes,
            "found_count": len(norm_fontes),
            "read_count": sum(1 for fonte in norm_fontes if fonte["read"]),
            "supporting_count": sum(1 for fonte in norm_fontes
                                    if fonte["relation"] in ("SUPPORTS", "PARTIALLY_SUPPORTS")),
            "contradicting_count": sum(1 for fonte in norm_fontes
                                       if fonte["relation"] == "CONTRADICTS"),
        })
    return {"title": _str(p.get("title"), 160) or "Evidências por afirmação",
            "claims": out, "sources": _provenance(p.get("sources"))}


def _v_researchmedia(p: dict) -> dict:
    """Discovery gallery: media can never be promoted to evidence here."""
    items = p.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 12):
        raise JduiErro("media.items: 1..12 obrigatórios")
    def dimension(value):
        number = _num(value)
        return int(number) if 0 < number <= 100000 else 0
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise JduiErro("media.item inválida")
        kind = str(item.get("type") or "").lower()
        if kind not in MEDIA_TYPES:
            raise JduiErro("media.type: image|video|document")
        url = _url(item.get("url"))
        if not url:
            raise JduiErro("media.url real obrigatória")
        access = str(item.get("access_state") or "link_only").lower()
        if access not in MEDIA_ACCESS:
            access = "link_only"
        validation = str(item.get("validation_state") or "unverified").lower()
        if validation not in MEDIA_VALIDATION:
            validation = "unverified"
        # No media analysis pipeline is exposed in V5.8: never trust a label
        # that claims a video was watched/transcribed or an image analysed.
        analysis = "not_analyzed"
        out.append({
            "type": kind,
            "title": _str(item.get("title"), 160) or f"{kind} descoberto",
            "url": url,
            "thumb": _url(item.get("thumb") or item.get("thumbnail")),
            "source_title": _str(item.get("source_title"), 160),
            "source_url": _url(item.get("source_url")),
            "publisher": _str(item.get("publisher"), 120),
            "date": _str(item.get("date"), 40),
            "rights": _str(item.get("rights"), 160) or "não informado",
            "attribution": _str(item.get('attribution'),240),
            "license_url": _url(item.get('license_url')),
            "mime": _str(item.get('mime'),80),
            "width": dimension(item.get('width')),
            "height": dimension(item.get('height')),
            "duration": _str(item.get('duration'),40),
            "metadata_state": 'METADATA_READ' if item.get('metadata_state')=='METADATA_READ' else 'VIDEO_FOUND' if kind=='video' else 'FOUND',
            "access_state": access,
            "validation_state": validation,
            "analysis_state": analysis,
            "excerpt": _str(item.get("excerpt"), 500),
            "alt": _str(item.get("alt") or item.get("title"), 200),
            "evidence": False,
        })
    return {"title": _str(p.get("title"), 160) or "Mídia descoberta",
            "items": out, "sources": _provenance(p.get("sources"))}


FILE_KINDS = ("pdf", "docx", "xlsx", "csv", "md", "txt", "json", "zip")


def _v_filecard(p: dict) -> dict:
    files = p.get("files")
    if not isinstance(files, list) or not (1 <= len(files) <= 8):
        raise JduiErro("filecard.files: 1..8 obrigatórios")
    out = []
    for item in files:
        if not isinstance(item, dict) or not _str(item.get("name")):
            raise JduiErro("filecard.file sem name")
        url = _url_recurso(item.get("url"))
        if not url:
            raise JduiErro("filecard.url real obrigatória")
        kind = str(item.get("kind") or "").lower()
        if kind not in FILE_KINDS:
            raise JduiErro("filecard.kind inválido")
        status = str(item.get("status") or "available").lower()
        if status not in ("available", "generated", "unverified"):
            status = "unverified"
        out.append({"name": _str(item.get("name"), 160), "url": url,
                    "kind": kind, "size": _str(item.get("size"), 40),
                    "source": _str(item.get("source"), 200),
                    "status": status})
    return {"title": _str(p.get("title"), 160) or "Arquivos",
            "files": out, "sources": _provenance(p.get("sources"))}


STATUS_FONTE = ("encontrada", "aberta", "utilizada")


def _v_sources(p: dict) -> dict:
    itens = p.get("items")
    if not isinstance(itens, list) or not (1 <= len(itens) <= 10):
        raise JduiErro("sources.items: 1..10 obrigatórios")
    out = []
    for f in itens:
        if not isinstance(f, dict) or not _str(f.get("titulo") or f.get("title")):
            raise JduiErro("sources.item sem titulo")
        url = _url(f.get("url"))
        status = str(f.get("status", "encontrada")).lower()
        if status not in STATUS_FONTE:
            status = "encontrada"
        out.append({"titulo": _str(f.get("titulo") or f.get("title"), 160),
                    "url": url,
                    "dominio": _str(f.get("dominio"), 120),
                    "data": _str(f.get("data"), 48),
                    "trecho": _str(f.get("trecho"), 300),
                    "origem_declarada": _str(f.get("origem_declarada"), 120),
                    "tipo": _str(f.get("tipo"), 40),
                    "escopo": _str(f.get("escopo"), 80),
                    "relacao": _str(f.get("relacao"), 80),
                    "data_evento": _str(f.get("data_evento"), 48),
                    "publicador": _str(f.get('publicador'),120), "autores":_str(f.get('autores'),300),
                    "doi":_str(f.get('doi'),160), "imagem":_url(f.get('imagem')),
                    "favicon":_url(f.get('favicon')), "texto_url":_url(f.get('texto_url')),
                    "leitura":f.get('leitura') if f.get('leitura') in ('FOUND','READ','PARTIAL','UNAVAILABLE') else 'READ' if status in ('aberta','utilizada') else 'FOUND',
                    "detalhes":[_str(v,240) for v in (f.get('detalhes') or [])[:6] if isinstance(v,str)] if isinstance(f.get('detalhes',[]),list) else [],
                    "status": status})
    return {"title": _str(p.get("title"), 160), "items": out,
            "sources": _provenance(p.get("sources"))}


DOMINIOS_VIDEO = ("youtube.com", "www.youtube.com", "m.youtube.com",
                  "youtu.be", "vimeo.com", "player.vimeo.com")


def _v_video(p: dict) -> dict:
    url = _url(p.get("url"))
    if not url:
        raise JduiErro("video.url obrigatória")
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        raise JduiErro("video.url inválida")
    if host not in DOMINIOS_VIDEO:
        raise JduiErro("video: somente YouTube/Vimeo")
    return {"titulo": _str(p.get("titulo") or p.get("title"), 160),
            "url": url,
            "thumb": _url(p.get("thumb") or p.get("thumbnail")),
            "duracao": _str(p.get("duracao"), 20),
            "fonte": _str(p.get("fonte"), 80),
            "sources": _provenance(p.get("sources"))}


STATUS_ETAPA = ("todo", "doing", "done")


def _v_roadmap(p: dict) -> dict:
    etapas = p.get("stages") or p.get("etapas")
    if not isinstance(etapas, list) or not (1 <= len(etapas) <= 12):
        raise JduiErro("roadmap.stages: 1..12 obrigatórias")
    out = []
    for e in etapas:
        if not isinstance(e, dict) or not _str(e.get("id")) or not _str(e.get("title")):
            raise JduiErro("roadmap.etapa exige id e title")
        status = str(e.get("status", "todo")).lower()
        if status not in STATUS_ETAPA:
            status = "todo"
        out.append({"id": _str(e.get("id"), 40), "title": _str(e.get("title"), 120),
                    "desc": _str(e.get("desc"), 500), "status": status,
                    "data": _str(e.get("data"), 48),
                    "marco": bool(e.get("marco"))})
    return {"title": _str(p.get("title"), 160), "stages": out,
            "sources": _provenance(p.get("sources"))}


# Componentes com resultado imutável: nunca aceitam patch in-place.
PATCH_PROIBIDO = frozenset(("exam", "quiz", "studyprogress"))
PATCH_ID_RE = r"[A-Za-z0-9_-]{2,100}"


def validar_update_of(obj: dict, componentes: list) -> str:
    """Envelope update_of: id da mensagem-alvo + componentes permitidos."""
    alvo = obj.get("update_of", "")
    if not alvo:
        return ""
    if not isinstance(alvo, str) or not re.fullmatch(PATCH_ID_RE, alvo):
        raise JduiErro("update_of inválido")
    for c in componentes:
        if c in PATCH_PROIBIDO:
            raise JduiErro(f"{c} não aceita atualização (resultado imutável)")
    return alvo


def _v_model3d(p):
    try:
        return model3d.validate(p)
    except ValueError as exc:
        raise JduiErro(str(exc)) from exc


VALIDADORES = {
    "model3d": _v_model3d,
    "quiz": _v_quiz, "checklist": _v_checklist, "calculator": _v_calculator,
    "cards": _v_cards, "diagram": _v_diagram, "table": _v_table,
    "form": _v_form, "progress": _v_progress, "tabs": _v_tabs,
    "accordion": _v_accordion, "exam": _v_exam, "studyplan": _v_studyplan,
    "flashcards": _v_flashcards, "studyprogress": _v_progresso,
    "lesson": _v_lesson, "chart": _v_chart, "dashboard": _v_dashboard,
    "compare": _v_compare, "evidencegraph": _v_evidencegraph,
    "productcard": _v_productcard, "productgrid": _v_productgrid,
    "productcompare": _v_productcompare, "productdetails": _v_productdetails,
    "productgallery": _v_productgallery,
    "sources": _v_sources, "video": _v_video, "roadmap": _v_roadmap,
    "researchplan": _v_researchplan, "evidence": _v_researchevidence,
    "media": _v_researchmedia, "filecard": _v_filecard,
}


def validar_mensagem(obj) -> tuple:
    """Valida envelope JULIA-ui-message/v1. Retorna (ok, normalizado|None, erros[])."""
    erros = []
    if not isinstance(obj, dict):
        return False, None, ["envelope deve ser objeto"]
    if obj.get("version") != VERSION:
        return False, None, [f"version deve ser {VERSION}"]
    blocos = obj.get("blocks")
    if not isinstance(blocos, list) or not blocos:
        return False, None, ["blocks: lista não vazia obrigatória"]
    if len(blocos) > MAX_BLOCOS_MSG + 2:
        erros.append(f"blocos além do teto ({MAX_BLOCOS_MSG + 2}) ignorados")
        blocos = blocos[:MAX_BLOCOS_MSG + 2]
    norm = []
    comps = []
    for b in blocos:
        if not isinstance(b, dict):
            erros.append("bloco deve ser objeto")
            continue
        if b.get("type") == "text":
            txt = _str(b.get("content"), 4000)
            if txt:
                norm.append({"type": "text", "content": txt})
            continue
        if b.get("type") == "ui":
            comp = _str(b.get("component"), 40)
            val = VALIDADORES.get(comp)
            if val is None:
                erros.append(f"componente desconhecido: {comp or '?'} (fallback: texto)")
                continue
            props = b.get("props")
            if not isinstance(props, dict):
                erros.append(f"props de {comp} devem ser objeto")
                continue
            try:
                norm.append({"type": "ui", "component": comp, "props": val(props)})
                comps.append(comp)
            except JduiErro as exc:
                erros.append(f"{comp}: {exc}")
            continue
        erros.append("bloco sem type text|ui")
    if not norm:
        return False, None, erros or ["nenhum bloco válido"]
    saida = {"version": VERSION, "blocks": norm[:MAX_BLOCOS_MSG + 2]}
    try:
        alvo = validar_update_of(obj, comps)
        if alvo:
            saida["update_of"] = alvo
    except JduiErro as exc:
        erros.append(str(exc))
    return True, saida, erros


def extrair_fences(texto: str) -> list:
    """Retorna conteúdos de fences ```jdui FECHADOS (incompletos são ignorados no stream)."""
    out = []
    for m in FENCE_RE.finditer(texto or ""):
        corpo = (m.group(1) or "").strip()
        if corpo and len(corpo.encode("utf-8", "ignore")) <= MAX_JSON_BYTES and m.group(0).rstrip().endswith("```"):
            out.append(corpo)
    return out


def normalizar(texto: str) -> tuple:
    """Extrai+valida fences; remove SÓ os inválidos; retorna (texto, blocos, erros).

    Offline-first: fences VÁLIDOS permanecem no texto guardado (fonte canônica;
    o frontend extrai+valida+renderiza, inclusive offline). Fences fechados mas
    inválidos são removidos e logados para nunca exibir JSON bruto. Fences
    ABERTOS (stream parcial) são mantidos.
    """
    erros = []
    blocos = []

    def _trocar(m):
        corpo = (m.group(1) or "").strip()
        fechado = m.group(0).rstrip().endswith("```")
        if not fechado:
            return m.group(0)  # stream parcial: mantém
        if len(corpo.encode("utf-8", "ignore")) > MAX_JSON_BYTES:
            erros.append("bloco excede 24KB")
            return ""
        try:
            obj = json.loads(corpo)
        except ValueError:
            erros.append("JSON inválido")
            return ""
        if _profundidade(obj) > MAX_DEPTH:
            erros.append("profundidade excessiva")
            return ""
        ok, norm, errs = validar_mensagem(obj)
        erros.extend(errs)
        if ok:
            if len(blocos) < MAX_BLOCOS_MSG:
                blocos.append(norm)
            return m.group(0)  # válido: fica no texto (frontend renderiza)
        return ""  # inválido: some (fallback é o texto ao redor)

    limpo = FENCE_RE.sub(_trocar, texto or "")
    limpo = re.sub(r"\n{3,}", "\n\n", limpo).strip()
    if erros:
        log.warning("JDUI normalizar: %s", "; ".join(erros[:4]))
    return limpo, blocos, erros
