"""Bounded, owner-scoped research exports rendered as real bytes (V5.8).

The relay receives only owner-scoped records from the PC, validates them and
renders Markdown, CSV or JSON in memory.  Nothing is persisted on Render and
no media/file is rehosted.  Calls must pass the authenticated owner's payload;
this module deliberately has no database access.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

MAX_EXPORT_BYTES = 2_000_000
MAX_ITEMS = 200
FORMATS = ("md", "csv", "json")
MIME = {
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
}


class ExportError(ValueError):
    pass


def _text(value, limit=2000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _int(value, limit=10_000) -> int:
    try:
        return max(0, min(limit, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def _surface(items, limit=MAX_ITEMS) -> list:
    return [item for item in (items or []) if isinstance(item, dict)][:limit]


def _csv_cell(value) -> str:
    text = _text(value, 4000)
    # Spreadsheet formula injection is data, not an export instruction.
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        text = "'" + text
    return text


def _safe_filename(job_id: str, fmt: str) -> str:
    ident = re.sub(r"[^A-Za-z0-9_-]", "-", str(job_id or "pesquisa"))[:64] or "pesquisa"
    return f"vexx-pesquisa-{ident}.{fmt}"


def _context(job: dict, media: list, claims: list, evidence: list, hypotheses: list) -> dict:
    return {
        "schema": "vexx-research-export/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "id": _text(job.get("id"), 80),
            "objective": _text(job.get("objetivo"), 2000),
            "mode": _text(job.get("modo"), 40),
            "status": _text(job.get("status"), 40),
            "plan_version": _int(job.get("plano_versao"), 100_000),
            "usage": job.get("usados") if isinstance(job.get("usados"), dict) else {},
            "limits": job.get("limites") if isinstance(job.get("limites"), dict) else {},
        },
        "claims": claims,
        "evidence": evidence,
        "media": media,
        "hypotheses": hypotheses,
        "limitations": [
            "A verificação é lexical/determinística e não estabelece causalidade.",
            "Itens de mídia são descobertas de metadados/links; imagens não são evidência "
            "e vídeos não foram assistidos, transcritos ou analisados.",
            "Export gerado a partir dos registros persistidos; nenhum valor foi inventado.",
        ],
    }


def _markdown(ctx: dict) -> bytes:
    job = ctx["job"]
    out = [
        "# Relatório de pesquisa Vexx AI",
        "",
        f"**Objetivo:** {job['objective'] or '(não informado)'}",
        f"**Modo:** {job['mode'] or '-'}  ",
        f"**Status:** {job['status'] or '-'}  ",
        f"**Job:** `{job['id'] or '-'}`  ",
        f"**Gerado em:** {ctx['generated_at']}",
        "",
        "## Conclusões por afirmação",
        "",
    ]
    if not ctx["claims"]:
        out.append("_Nenhuma afirmação verificada foi registrada._")
    for index, claim in enumerate(ctx["claims"], 1):
        out.append(f"### {index}. {_text(claim.get('afirmacao'), 1200)}")
        out.append(f"- **Estado:** `{_text(claim.get('estado'), 40) or 'UNVERIFIED'}`")
        if claim.get("metodo"):
            out.append(f"- **Método:** {_text(claim.get('metodo'), 200)}")
        fontes = _surface(claim.get("fontes"), 12)
        if fontes:
            out.append("- **Fontes da afirmação:**")
            for source in fontes:
                relation = _text(source.get("relation"), 40) or "REQUIRES_VERIFICATION"
                read = "lida" if source.get("read") else "não lida"
                title = _text(source.get("title") or source.get("domain"), 200)
                url = _text(source.get("url"), 500)
                out.append(f"  - `{relation}` — {title} ({read}) {url}")
                if source.get("used_excerpt"):
                    out.append(f"    - Trecho: {_text(source.get('used_excerpt'), 500)}")
        else:
            out.append("- **Fontes da afirmação:** nenhuma referência específica atribuída.")
        out.append("")
    out.extend(["## Evidências registradas", ""])
    if not ctx["evidence"]:
        out.append("_Nenhuma evidência registrada._")
    for item in ctx["evidence"]:
        status = _text(item.get("status"), 40) or "recuperada"
        title = _text(item.get("titulo") or item.get("url"), 300)
        out.append(f"- `{status}` **{title}** — {_text(item.get('url'), 500)}")
        if item.get("trecho"):
            out.append(f"  - {_text(item.get('trecho'), 800)}")
    out.extend(["", "## Hipóteses", ""])
    if not ctx["hypotheses"]:
        out.append("_Nenhuma hipótese registrada._")
    for hypothesis in ctx["hypotheses"]:
        out.append(f"### {_text(hypothesis.get('statement'), 1000)}")
        for link in hypothesis.get("chain") or hypothesis.get("cadeia") or []:
            if isinstance(link, dict):
                out.append(f"- **{_text(link.get('label') or link.get('rotulo'), 40)}:** "
                           f"{_text(link.get('text') or link.get('texto'), 1200)}")
        out.append("- **Testes executados:** não; próximos passos são propostas.")
        out.append("")
    out.extend(["## Mídia e documentos descobertos", ""])
    if not ctx["media"]:
        out.append("_Nenhuma mídia descoberta._")
    for item in ctx["media"]:
        out.append(f"- `{_text(item.get('type'), 20)}` **{_text(item.get('title'), 300)}** — "
                   f"{_text(item.get('url'), 500)}")
        out.append(f"  - Acesso: {_text(item.get('access_state'), 40)}; validação: "
                   f"{_text(item.get('validation_state'), 40)}; análise: "
                   f"{_text(item.get('analysis_state'), 40)}; evidência: "
                   f"{'sim' if item.get('evidence') is True else 'não'}")
        if item.get("source_url"):
            out.append(f"  - Página de origem: {_text(item.get('source_url'), 500)}")
    out.extend(["", "## Limitações", ""])
    out.extend(f"- {item}" for item in ctx["limitations"])
    return ("\n".join(out).strip() + "\n").encode("utf-8")


def _csv(ctx: dict) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")

    def row(cells):
        writer.writerow([_csv_cell(cell) for cell in cells])

    row(["tipo", "id", "estado_relacao", "titulo", "url", "dominio",
         "data", "lido", "acesso", "trecho_usado", "detalhe"])
    job = ctx["job"]
    row(["job", job["id"], job["status"], job["objective"], "",
         "", ctx["generated_at"], "", "", "", f"modo={job['mode']}"])
    for claim in ctx["claims"]:
        row(["afirmacao", "", claim.get("estado"), claim.get("afirmacao"),
             "", "", "", "", "", "", claim.get("metodo")])
        for source in _surface(claim.get("fontes"), 12):
            row([
                "fonte_afirmacao", source.get("evidence_id"), source.get("relation"),
                source.get("title"), source.get("url"), source.get("domain"),
                source.get("published_at"), "sim" if source.get("read") else "não",
                source.get("access_state"), source.get("used_excerpt"), "",
            ])
    for item in ctx["evidence"]:
        row([
            "evidencia", item.get("id"), item.get("status"), item.get("titulo"),
            item.get("url"), item.get("dominio"), item.get("publicado_em"),
            "sim" if item.get("texto_lido") else "não", item.get("access_state"),
            item.get("trecho"), item.get("afirmacao"),
        ])
    for item in ctx["media"]:
        row([
            "midia_" + _text(item.get("type"), 20), item.get("id"), "",
            item.get("title"), item.get("url"), item.get("publisher"),
            item.get("date"), "não", item.get("access_state"), item.get("excerpt"),
            "validação=" + _text(item.get("validation_state"), 40) + "; análise="
            + _text(item.get("analysis_state"), 40) + "; evidência="
            + ("sim" if item.get("evidence") is True else "não"),
        ])
    for hypothesis in ctx["hypotheses"]:
        row(["hipotese", hypothesis.get("hypothesis_id"),
             hypothesis.get("status"), hypothesis.get("statement"),
             "", "", "", "", "", "", hypothesis.get("result_summary")])
    row(["limitacao", "", "", "Verificação lexical; mídia não analisada", "", "",
         "", "", "", "", ""])
    text = buffer.getvalue()
    # Excel-compatible BOM without changing CSV semantics.
    return text.encode("utf-8-sig")


def build_export(resumo: dict, evidencias: list, hypotheses: list,
                 formato: str = "md") -> tuple[bytes, str, str]:
    """Return (bytes, content-type, filename); reject oversized/invalid input."""
    fmt = str(formato or "md").lower()
    if fmt not in FORMATS:
        raise ExportError("Formato inválido; use md, csv ou json.")
    if not isinstance(resumo, dict):
        raise ExportError("Pesquisa inválida.")
    job_id = _text(resumo.get("id"), 80)
    if not job_id:
        raise ExportError("Pesquisa sem identificador.")
    media = _surface(resumo.get("midia"))
    claims = _surface(resumo.get("achados"))
    evidence = _surface(evidencias)
    hypotheses = _surface(hypotheses)
    ctx = _context(resumo, media, claims, evidence, hypotheses)
    if fmt == "md":
        payload = _markdown(ctx)
    elif fmt == "csv":
        payload = _csv(ctx)
    else:
        payload = json.dumps(ctx, ensure_ascii=False, indent=2).encode("utf-8")
    if len(payload) > MAX_EXPORT_BYTES:
        raise ExportError("Export excede o limite de 2 MB; reduza o escopo.")
    return payload, MIME[fmt], _safe_filename(job_id, fmt)
