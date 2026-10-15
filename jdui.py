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
    return u if re.match(r"^https?://", u) else ""


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
            "x_label": _str(p.get("x_label"), 60), "y_label": _str(p.get("y_label"), 60)}


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
            "source": _str(p.get("source"), 160)}


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
            "columns": [_str(cols[0], 40), _str(cols[1], 40)], "rows": norm}


CALCULATOR_KINDS = ("basic", "imc", "porcentagem", "juros", "conversor")


def _v_calculator(p: dict) -> dict:
    kind = str(p.get("kind", "basic")).lower()
    if kind not in CALCULATOR_KINDS:
        raise JduiErro("calculator.kind inválido")
    return {"kind": kind, "title": _str(p.get("title"), 120)}


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


VALIDADORES = {
    "quiz": _v_quiz, "checklist": _v_checklist, "calculator": _v_calculator,
    "cards": _v_cards, "diagram": _v_diagram, "table": _v_table,
    "form": _v_form, "progress": _v_progress, "tabs": _v_tabs,
    "accordion": _v_accordion, "exam": _v_exam, "studyplan": _v_studyplan,
    "flashcards": _v_flashcards, "studyprogress": _v_progresso,
    "lesson": _v_lesson, "chart": _v_chart, "dashboard": _v_dashboard,
    "compare": _v_compare,
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
