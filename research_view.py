"""Build a validated JDUI 4.0 view from real research records (V5.8).

The model never supplies HTML/JS.  This module maps persisted job data to the
allowlisted components and validates every block with :mod:`jdui`; a component
with invalid data is omitted and the textual summary explains the omission.
"""
from __future__ import annotations

import re

import jdui

MAX_TEXT = 4000
_STEP = {"feita": "done", "pendente": "todo", "falhou": "error",
         "removida": "skipped", "em_andamento": "doing", "pausada": "todo"}
_JOB = {"criada": "planned", "em_andamento": "running", "pausada": "paused",
        "concluida": "completed", "interrompida": "paused",
        "cancelada": "cancelled", "falhou": "failed"}
_STATE = {"SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED",
          "UNVERIFIED", "INCONCLUSIVE"}


def _text(value, limit=2000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _block_ok(component: str, props: dict) -> bool:
    ok, _, _ = jdui.validar_mensagem({
        "version": jdui.VERSION,
        "blocks": [{"type": "ui", "component": component, "props": props}],
    })
    return ok


def _plan(resumo: dict) -> dict:
    steps = []
    for step in (resumo.get("etapas") or [])[:24]:
        if not isinstance(step, dict) or not step.get("id"):
            continue
        tipo = _text(step.get("tipo"), 30) or "pesquisa"
        alvo = _text(step.get("alvo"), 160)
        rotulo = {"busca": "Buscar", "ler": "Ler", "analisar": "Analisar",
                  "verificar": "Verificar", "sintetizar": "Sintetizar",
                  "auditar": "Auditar"}.get(tipo, tipo.title())
        title = f"{rotulo}: {alvo}" if alvo else rotulo
        steps.append({
            "id": _text(step.get("id"), 40),
            "title": title[:160],
            "kind": tipo,
            "status": _STEP.get(step.get("status") or "pendente", "todo"),
            "detail": _text(step.get("objetivo_etapa")
                            or step.get("priority_reason"), 500),
            "stop_condition": _text(step.get("regra_parada")
                                    or step.get("criterio_conclusao"), 300),
            "dependencies": step.get("dependencias") or [],
        })
    return {
        "title": "Plano de pesquisa",
        "objective": _text(resumo.get("objetivo"), 500),
        "mode": _text(resumo.get("modo"), 40),
        "status": _JOB.get(resumo.get("status") or "criada", "planned"),
        "steps": steps,
        "budgets": resumo.get("orcamento") or {},
        "used": {key: (resumo.get("usados") or {}).get(key)
                 for key in ("buscas", "paginas", "replans")},
    }


def _claims(resumo: dict) -> dict:
    claims = []
    for item in (resumo.get("achados") or [])[:10]:
        if not isinstance(item, dict):
            continue
        state = _text(item.get("estado"), 40).upper()
        if state == "INSUFFICIENT_EVIDENCE":
            state = "INCONCLUSIVE"
        if state not in _STATE:
            state = "UNVERIFIED"
        sources = []
        for fonte in (item.get("fontes") or [])[:12]:
            if not isinstance(fonte, dict):
                continue
            sources.append({
                "id": _text(fonte.get("evidence_id"), 80),
                "title": _text(fonte.get("title") or fonte.get("domain"), 160),
                "url": _text(fonte.get("url"), 500),
                "domain": _text(fonte.get("domain"), 120),
                "relation": _text(fonte.get("relation"), 40).upper()
                            or "REQUIRES_VERIFICATION",
                "read": bool(fonte.get("read")),
                "access_state": _text(fonte.get("access_state"), 40),
                "excerpt": _text(fonte.get("used_excerpt"), 500),
                "published_at": _text(fonte.get("published_at"), 48),
            })
        has_support = any(s["relation"] in ("SUPPORTS", "PARTIALLY_SUPPORTS")
                          for s in sources)
        if state == "SUPPORTED" and not has_support:
            state = "INCONCLUSIVE" if sources else "UNVERIFIED"
        if state == "CONTRADICTED" and not any(
                s["relation"] == "CONTRADICTS" for s in sources):
            state = "INCONCLUSIVE" if sources else "UNVERIFIED"
        claims.append({
            "statement": _text(item.get("afirmacao"), 1200),
            "state": state,
            "method": _text(item.get("metodo"), 200),
            "coverage": item.get("cobertura_lexica", 0),
            "sources": sources,
        })
    return {"title": "Evidências por afirmação", "claims": claims}


def _hypotheses(resumo: dict) -> dict:
    items = []
    for hypothesis in (resumo.get("hipoteses") or [])[:8]:
        if not isinstance(hypothesis, dict) or not hypothesis.get("statement"):
            continue
        linhas = []
        for link in hypothesis.get("cadeia") or []:
            if isinstance(link, dict):
                linhas.append(f"**{_text(link.get('rotulo'), 40)}:** "
                              f"{_text(link.get('texto'), 700)}")
        linhas.append("**Testes executados:** não; hipótese e próximos passos "
                      "são propostas, não resultados.")
        items.append({"title": _text(hypothesis.get("statement"), 120),
                      "markdown": "\n\n".join(linhas)[:2800]})
    return {"items": items}


def _media(resumo: dict) -> dict:
    items = []
    for item in (resumo.get("midia") or [])[:12]:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        items.append({
            "type": item.get("type"),
            "title": item.get("title"), "url": item.get("url"),
            "thumb": item.get("thumb") or "",
            "source_title": item.get("source_title") or "",
            "source_url": item.get("source_url") or "",
            "publisher": item.get("publisher") or "",
            "date": item.get("date") or "",
            "rights": item.get("rights") or "não informado",
            "access_state": item.get("access_state") or "link_only",
            "validation_state": item.get("validation_state") or "unverified",
            "analysis_state": item.get("analysis_state") or "not_analyzed",
            "excerpt": item.get("excerpt") or "",
            "alt": item.get("title") or "",
        })
    return {"title": "Mídia descoberta (não é evidência)", "items": items}


def _files(resumo: dict) -> dict:
    ident = _text(resumo.get("id"), 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", ident):
        return {"files": []}
    base = f"/api/research/export?job_id={ident}&formato="
    return {"title": "Exportar pesquisa", "files": [
        {"name": "Relatório completo (Markdown)", "url": base + "md",
         "kind": "md", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
        {"name": "Dados estruturados (CSV)", "url": base + "csv",
         "kind": "csv", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
        {"name": "Registros completos (JSON)", "url": base + "json",
         "kind": "json", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
    ]}


def build_view(resumo: dict, evidencias: list = None, hypotheses: list = None) -> dict:
    """Return ``JULIA-ui-message/v1`` with only validated, real data."""
    resumo = resumo if isinstance(resumo, dict) else {}
    blocks, omitted = [], []
    candidatos = [
        ("researchplan", _plan(resumo)),
        ("evidence", _claims(resumo)),
        ("accordion", _hypotheses(resumo)),
        ("media", _media(resumo)),
        ("filecard", _files(resumo)),
    ]
    used = {eid for claim in resumo.get("achados", []) for eid in
            claim.get("supporting_ids", []) + claim.get("contradicting_ids", [])}
    source_items = []
    for item in (evidencias or [])[:10]:
        read = bool(item.get("texto_lido")) or item.get("access_state") == "read"
        abstract = item.get("content_scope") == "abstract_only"
        source_items.append({"titulo": item.get("titulo"), "url": item.get("url"),
            "dominio": item.get("dominio"), "data": item.get("publicado_em"),
            "trecho": item.get("trecho"), "tipo": item.get("publication_type") or item.get("tipo", "Fonte"),
            "escopo": "Somente resumo; texto completo não lido" if abstract else
                      "Texto recuperado" if read else "Página não lida; sem suporte factual",
            "relacao": "Trecho ligado a uma afirmação" if item.get("id") in used else "Fonte de contexto",
            "status": "utilizada" if item.get("id") in used and (read or abstract) else "aberta" if read or abstract else "encontrada"})
    if source_items:
        candidatos.append(("sources", {"title": "Fontes e estado da leitura", "items": source_items}))
    for component, props in candidatos:
        if component == "evidence" and not props.get("claims"):
            continue
        if component == "accordion" and not props.get("items"):
            continue
        if component in ("media", "filecard") and not props.get("items") and not props.get("files"):
            continue
        if _block_ok(component, props):
            blocks.append({"type": "ui", "component": component, "props": props})
        else:
            omitted.append(component)
    resumo_midia = resumo.get("midia_resumo") or {}
    status_rot = {"criada": "criada", "em_andamento": "em andamento",
                  "pausada": "pausada", "concluida": "concluída",
                  "interrompida": "interrompida", "cancelada": "cancelada",
                  "falhou": "falhou"}
    linhas = [
        f"**Objetivo:** {_text(resumo.get('objetivo'), 500) or '(não informado)'}",
        f"**Status:** {status_rot.get(resumo.get('status'), _text(resumo.get('status'), 40) or '-')} · "
        f"**Modo:** {_text(resumo.get('modo'), 40) or '-'} · "
        f"**Evidências:** {int(resumo.get('evidencias') or 0)}",
        f"**Mídia descoberta:** {int(resumo_midia.get('total') or 0)} item(ns); "
        "imagens não são evidência e vídeos não foram assistidos ou analisados.",
        "**Limite epistêmico:** a verificação é lexical/determinística; "
        "estados não estabelecem causalidade e lacunas permanecem explícitas.",
    ]
    if omitted:
        linhas.append("**Componentes omitidos por dados inválidos:** "
                      + ", ".join(sorted(set(omitted))) + ".")
    texto = "\n".join(linhas)[:MAX_TEXT]
    answer = str((resumo.get("sintese") or {}).get("texto") or "").strip()[:3500]
    text_blocks = [{"type": "text", "content": answer}] if answer else []
    mensagem = {"version": jdui.VERSION,
                "blocks": text_blocks + [{"type": "text", "content": texto}] + blocks}
    ok, normalizado, erros = jdui.validar_mensagem(mensagem)
    if not ok:
        # Last-resort honest fallback: text only, never raw invalid JSON.
        minimo = {"version": jdui.VERSION, "blocks": [{
            "type": "text",
            "content": (texto + "\n\nInterface estruturada indisponível: "
                        + "; ".join(erros[:3]))[:MAX_TEXT]}]}
        _, normalizado, _ = jdui.validar_mensagem(minimo)
    return normalizado
