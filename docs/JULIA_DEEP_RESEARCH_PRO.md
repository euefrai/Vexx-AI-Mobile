# Julia Mobile V4.8 — Deep Research Pro

## Goal

Deep Research Pro extends the existing research orchestrator with grounded
document investigation, academic metadata lookup, deterministic data analysis,
traceable reports, and resumable state. Research remains inside the
conversation; this is not an IDE/workspace and does not add more research-agent
roles.

## Architecture

- **Documents:** the existing document agent extracts supported files, stores
  owner-scoped originals/chunks, and exposes retrieval/comparison with source
  locations. See [Document Intelligence](./JULIA_DOCUMENT_INTELLIGENCE.md) and
  [Document Retrieval](./JULIA_DOCUMENT_RETRIEVAL.md).
- **Academic lookup:** optional OpenAlex/Crossref Works metadata capability in
  the existing orchestrator. See [Academic Research](./JULIA_ACADEMIC_RESEARCH.md).
- **Structured calculations:** bounded CSV/JSON/tabular operations use
  deterministic Python arithmetic and existing unit conversion. See
  [Data Analysis](./JULIA_DATA_ANALYSIS.md).
- **Presentation:** existing JDUI chart/compare components accept source ID,
  title, link, locator, period, and methodology. The adapter rejects missing,
  incompatible, or unaligned data rather than filling gaps.
- **Investigation state:** `HypothesisStore` and `ResearchContextStore` provide
  owner/job-scoped SQLite persistence primitives. See
  [Hypothesis Engine](./JULIA_HYPOTHESIS_ENGINE.md) and
  [Continuous Research](./JULIA_CONTINUOUS_RESEARCH.md).
- **Reports:** deterministic Markdown assembly validates source references and
  omits empty sections. See [Research Reports](./JULIA_RESEARCH_REPORTS.md).

## Trust and inference boundaries

Titles, abstracts, web pages, PDFs, and extracted text are untrusted data, not
instructions. File content is parsed, never executed. PDFs without extractable
text are not described as read; OCR is not implemented. FTS5/lexical matches
are not semantic proof, and a missing match is not proof of absence.

Academic search returns metadata or abstracts; it does not download or read
full articles. Citation counts are metadata, not truth scores. Numerical
operations are deterministic, but cannot establish that sources or methods are
comparable without sufficient metadata.

Hermes inference remains blocked by provider availability. Semantic synthesis,
diagnosis, semantic hypothesis evaluation, and context-summary compaction
remain unavailable without real inference. Deterministic checks and persisted
state must remain independently useful and must not be presented as semantic
reasoning.

## Ownership and resource controls

Document and research state must be derived from authenticated server-side
ownership. Indexes and retrieval, deletion, academic requests, and checkpoint
lookups must remain bounded and scoped to the requesting owner. No external
database or paid API is required; academic lookup is opt-in.

## Delivery status

The initial audit recorded the actual V4.7 baseline as 241 passed, 2 skipped,
and 3 warnings, rather than the older count in previous roadmap text. V4.8
implementation is complete for the deterministic/documentary scope. The
focused V4.8 tests pass. Full-suite runs exposed intermittent Windows E2E
teardown failures while deleting temporary relay/agent log files; both E2E
tests pass when run individually. This test-runner limitation and the exact
counts are recorded in [RELATORIO_JULIA_4.8.md](../RELATORIO_JULIA_4.8.md).
Hermes-dependent semantic synthesis/evaluation, OCR, and PDF export remain
unavailable and are not simulated.
