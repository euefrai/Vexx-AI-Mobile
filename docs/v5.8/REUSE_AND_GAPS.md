# Reuse map and gaps

## Reused, not duplicated

| Existing capability | Reuse in V5.8 |
|---|---|
| `research_agents` job/plan/execute loop | extended with media budgets, replan limits, plan metadata and provenance |
| SQLite `research_jobs`, `evidence`, `research_events` | same tables, same owner scoping, small JSON migration for media |
| SSE event store and relay | same cursor/replay/terminal semantics |
| `hypothesis_engine` | same owner/job-scoped records; only public presentation enriched |
| `continuous_research` checkpoints | same persisted resume mechanism |
| `research_reports` | same deterministic report assembly |
| `research.py` page acquisition/extraction | media discovery consumes already-read HTML; no second fetch path |
| `jdui.py` / `public/jdui.js` | new components added to the same registry and validator |
| `pc_agent` relay commands | `research_jobs_list`, status/evidence/hypotheses used by the view |
| `workspace_store` | existing owner-scoped persistence, not replaced |
| `docs_agent` | existing document extraction (including textual PDFs); no new PDF stack |
| existing tabular/data-analysis JDUI | no second chart engine |

## New modules

| Module | Reason | Isolation |
|---|---|---|
| `media_evidence.py` | media discovery and provenance without trusting HTML | pure, no network, no DB |
| `research_view.py` | one validated JDUI view from real records | pure, no DB, caller supplies owner-scoped data |
| `research_exports.py` | real bytes with bounds and CSV safety | pure, no DB, no filesystem |
| `tests/test_v58_deep_research.py` | contracts for the new behavior | test only |
| `tools/chrome_e2e_v58.py` | real Chrome desktop/mobile evidence | isolated temp stack, never production |
| `tools/bench_v58.py` | reproducible local performance evidence | pure modules only |

## Gaps found in the audit

1. No persisted media metadata or media JDUI component existed.
2. No plan-progress component existed; the UI could only show text/events.
3. Evidence cards lacked explicit found/read/used counts and source relation.
4. Hypotheses had records but no user-facing epistemic chain in the workspace.
5. No export route produced real server-side bytes for research.
6. No dedicated research workspace page; research was chat-only.
7. No bounded JDUI schemas for research plans, evidence, media or file cards.
8. Media could be mistaken for evidence; no enforced discovery-only state.
9. Chrome/mobile E2E did not cover the research workspace.
10. Heavy PDF/chart/video libraries were not evaluated against Render Free and
    CSP constraints.

## Gaps deliberately left open

- Real media download, thumbnails, transcript and visual analysis.
- Semantic claim verification without a real LLM.
- Full PDF layout/OCR/Docling pipeline.
- Interactive chart rendering from arbitrary datasets in the deep-research view.
- A full persistent “research notebook” with user annotations and report
  versions; the current workspace is a saved-job viewer with real exports.
- Parallel research execution; the configured concurrency is a ceiling only.
- Live production validation and external-provider stability.

## Untouched scope

V5.8 did not change credentials, paid services, Lucas identity, the 3D engine,
the Júlia extension, Fajulto Studio, social integrations or Apify. It did not
weaken SSRF/CSP/RBAC/owner isolation. It did not delete tests or alter fixtures
to inflate scores. Concurrent audit work in the working tree was preserved in a
separate local commit (`52e3195`) before the V5.8 commits.
