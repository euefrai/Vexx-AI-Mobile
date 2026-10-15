"""Deterministic Markdown reports built only from supplied research records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence
from urllib.parse import quote, urlsplit


REPORT_TYPES = frozenset(
    {
        "executive_summary",
        "comparative_analysis",
        "technical_report",
        "academic_research",
        "feasibility_study",
        "literature_review",
        "contradiction_investigation",
        "product_comparison",
        "document_analysis",
    }
)


@dataclass(frozen=True)
class ReportSource:
    source_id: str
    title: str
    url: str
    source_type: str | None = None
    access_note: str | None = None


@dataclass(frozen=True)
class ReportPoint:
    text: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


def build_research_report(
    *,
    report_type: str,
    objective: str,
    scope: str | None = None,
    methodology: str | None = None,
    findings: Sequence[ReportPoint] = (),
    evidence: Sequence[ReportPoint] = (),
    divergences: Sequence[ReportPoint] = (),
    limitations: Sequence[str] = (),
    conclusions: Sequence[ReportPoint] = (),
    next_questions: Sequence[str] = (),
    sources: Sequence[ReportSource] = (),
) -> str:
    """Build a cited report without generating facts or empty placeholder sections."""
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unsupported report type: {report_type}")
    if not objective.strip():
        raise ValueError("A report objective is required")

    source_numbers: dict[str, int] = {}
    for index, source in enumerate(sources, start=1):
        if not source.source_id.strip() or not source.title.strip() or not source.url.strip():
            raise ValueError("Each source requires an id, title, and URL")
        _safe_http_url(source.url)
        if source.source_id in source_numbers:
            raise ValueError(f"Duplicate source id: {source.source_id}")
        source_numbers[source.source_id] = index

    sections: list[tuple[str, list[str]]] = [
        ("Objetivo", [_safe_text(objective)]),
    ]
    if scope and scope.strip():
        sections.append(("Escopo", [_safe_text(scope)]))
    if methodology and methodology.strip():
        sections.append(("Metodologia", [_safe_text(methodology)]))

    def render_points(points: Iterable[ReportPoint]) -> list[str]:
        rendered: list[str] = []
        for point in points:
            if not point.text.strip():
                continue
            unknown = [source_id for source_id in point.source_ids if source_id not in source_numbers]
            if unknown:
                raise ValueError(f"Unknown source id(s): {', '.join(unknown)}")
            citations = " ".join(f"[S{source_numbers[sid]}]" for sid in point.source_ids)
            rendered.append(f"- {_safe_text(point.text)}" + (f" {citations}" if citations else ""))
        return rendered

    for title, points in (
        ("Principais descobertas", findings),
        ("Evidências", evidence),
        ("Divergências", divergences),
        ("Conclusões", conclusions),
    ):
        rendered = render_points(points)
        if rendered:
            sections.append((title, rendered))

    for title, values in (("Limitações", limitations), ("Próximas perguntas", next_questions)):
        rendered = [f"- {_safe_text(value)}" for value in values if value.strip()]
        if rendered:
            sections.append((title, rendered))

    if sources:
        source_lines = []
        for index, source in enumerate(sources, start=1):
            url = _safe_http_url(source.url)
            url_text = f"<{url}>" if url.startswith(("http://", "https://")) else f"`{url}`"
            details = [f"[S{index}] {_escape_markdown(source.title.strip())} — {url_text}"]
            if source.source_type and source.source_type.strip():
                details.append(f"tipo: {_escape_markdown(source.source_type.strip())}")
            if source.access_note and source.access_note.strip():
                details.append(_escape_markdown(source.access_note.strip()))
            source_lines.append("- " + " | ".join(details))
        sections.append(("Fontes", source_lines))

    title = report_type.replace("_", " ").strip().title()
    return "\n\n".join(
        [f"# {title}"]
        + [f"## {section_title}\n\n" + "\n".join(lines) for section_title, lines in sections]
    )


def _safe_http_url(value: str) -> str:
    raw = value.strip()
    if raw.startswith("document://"):
        if not re.fullmatch(r"document://[A-Za-z0-9_-]+(?:#[A-Za-z0-9._-]+)?", raw):
            raise ValueError("Document source reference is invalid")
        return raw
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise ValueError("Source URL must be a valid HTTP(S) URL without credentials") from exc
    return quote(raw, safe=":/?#[]@!$&'()*+,;=%-._~")


def _escape_markdown(value: str) -> str:
    return "".join("\\" + char if char in "\\`*_{}[]<>()#+-.!|>" else char for char in value)


def _safe_text(value: str) -> str:
    return _escape_markdown(" ".join(value.split()))
