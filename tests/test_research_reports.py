import pytest

from research_reports import ReportPoint, ReportSource, build_research_report


def test_report_includes_only_populated_sections_and_source_references():
    report = build_research_report(
        report_type="document_analysis",
        objective="Compare the provided documents.",
        methodology="Retrieve matching sections from each document.",
        findings=[ReportPoint("Both documents describe the same requirement.", ("doc-a",))],
        sources=[
            ReportSource(
                source_id="doc-a",
                title="Requirements",
                url="document://doc-a#section-2",
                source_type="uploaded document",
            )
        ],
    )

    assert "## Objetivo" in report
    assert "## Metodologia" in report
    assert "## Principais descobertas" in report
    assert "[S1]" in report
    assert "## Escopo" not in report
    assert "## Evidências" not in report
    assert "## Limitações" not in report
    assert "## Conclusões" not in report
    assert "`document://doc-a#section-2`" in report


def test_report_rejects_citation_to_unregistered_source():
    with pytest.raises(ValueError, match="Unknown source id"):
        build_research_report(
            report_type="technical_report",
            objective="Check a claim.",
            findings=[ReportPoint("A claim.", ("missing",))],
        )


def test_report_rejects_duplicate_sources_and_empty_objectives():
    source = ReportSource("source", "Title", "https://example.test")
    with pytest.raises(ValueError, match="Duplicate source id"):
        build_research_report(
            report_type="academic_research",
            objective="Research.",
            sources=[source, source],
        )
    with pytest.raises(ValueError, match="objective"):
        build_research_report(report_type="academic_research", objective=" ")


def test_report_rejects_unsupported_report_types():
    with pytest.raises(ValueError, match="Unsupported report type"):
        build_research_report(report_type="made_up", objective="Question.")


def test_report_rejects_non_http_sources_and_escapes_external_source_text():
    with pytest.raises(ValueError, match="HTTP"):
        build_research_report(
            report_type="academic_research",
            objective="Research.",
            sources=[ReportSource("bad", "Unsafe", "javascript:alert(1)")],
        )
    report = build_research_report(
        report_type="academic_research",
        objective="Research.",
        sources=[ReportSource("s1", "[Click](https://evil.test)", "https://example.test/a b")],
    )
    assert r"\[Click\]\(https://evil\.test\)" in report
    assert "<https://example.test/a%20b>" in report
