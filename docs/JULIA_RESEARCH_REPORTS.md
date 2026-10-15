# Julia Research Reports

## Status

`research_reports.py` implements a deterministic Markdown report builder used
by the owner-scoped research-job report endpoint. It reads persisted evidence,
claims, divergences, and hypotheses; it does not generate findings or
conclusions. Claims are cited only when the verifier stored explicit evidence
IDs, and the builder validates every citation against the supplied source set.

## API and report contents

`build_research_report(...)` accepts an objective, optional scope and
methodology, findings/evidence/divergences/conclusions with source IDs,
limitations, next questions, and a report type. It emits only sections with
provided content; empty placeholder sections are omitted.

The supported report types are executive summary, comparative analysis,
technical report, academic research, feasibility study, literature review,
contradiction investigation, product comparison, and document analysis.
Every cited source ID must resolve to a supplied source record. Sources require
an ID, title, and safe URL/reference. HTTP(S) links are validated and encoded;
local `document://` references are restricted to safe IDs and rendered as text.
External titles and notes are escaped before Markdown output.

The builder emits Markdown only. PDF export is not implemented. It performs no
research or independent source-authenticity check; safe-reference and
citation-ID validation are implemented, while report content must come from
stored investigation records.

## Validation

Focused tests cover section omission, citation mapping, unknown/duplicate
sources, unsupported report types, unsafe URLs, and escaped source metadata.

## Structured visualizations

`research_visualizations.py` provides validated `chart_message` and
`compare_message` adapters for real `structured_analysis` results and preserves
their provenance. The same-owner/same-conversation chat command path accepts
saved CSV/TSV and tabular JSON, verifies the raw file against stored size and
extraction hash, runs deterministic analysis, and persists actual results in
the job/checkpoint. The chat emits a JDUI block only after adapter validation.
Reports include cited observations from those stored chart/comparison results
and a document source reference containing the content hash. Missing or
ambiguous inputs and incompatible data are reported as limitations; no values
or series are synthesized.
