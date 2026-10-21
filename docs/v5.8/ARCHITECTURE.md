# V5.8 architecture — Deep Research & JDUI 4.0

## Design rule

V5.8 extends the existing Julia/Vexx research orchestration. It does **not**
create a second agent platform, a new graph runtime, or a separate browser
application. The existing jobs, plan, evidence tables, SSE stream, relay,
workspace store, JDUI engine and document agent remain the substrate.

```text
chat / intent / explicit /research
        │
        ▼
research_agents.criar_job ──► research_jobs (SQLite, owner_id)
        │                      research_events (SSE)
        ▼
montar_plano (deterministic, non-redundant subquestions)
        │
        ▼
executar (persisted after each step; resume-safe)
  ├─ busca     → providers / fallback / BLOCKED recorded
  ├─ ler       → page extraction + evidence + media discovery
  ├─ analisar  → claims, contradictions, hypotheses
  ├─ verificar → states + found/read/used source counts
  ├─ sintetizar→ extractive synthesis (LLM only if really available)
  └─ auditar   → citation audit and limitations
        │
        ├─ replanejar (bounded, gap-driven, one extra round)
        ▼
_resumo + evidence DB + hypothesis DB + media metadata
        │
        ├─ SSE events / replay / cursor
        ├─ research_view.build_view ──► jdui.validar_mensagem
        │        └─ researchplan / evidence / media / filecard / text
        ├─ research_exports (md/csv/json, real bytes, 2 MB cap)
        └─ /api/research/{status,view,export,evidence,jobs}
```

## Modules

| Module | Role in V5.8 | Reuse |
|---|---|---|
| `research.py` | intent detection, page acquisition, extraction | existing, unchanged boundary |
| `research_agents.py` | jobs, plans, budgets, agents, evidence persistence, media aggregation, hypotheses, reports | extended |
| `media_evidence.py` | conservative media discovery from already-read HTML | **new, pure** |
| `research_view.py` | converts real summary/evidence/hypotheses into validated JDUI blocks | **new, pure** |
| `research_exports.py` | bounded Markdown/CSV/JSON rendering from relay data | **new, pure** |
| `jdui.py` | backend schemas, allowlists, normalization, provenance | extended |
| `server.py` | authenticated owner-scoped view/export routes | extended |
| `public/jdui.js` | frontend validators/renderers for the four components | extended |
| `public/app.js` | live panel, progress, exports, structured view, research page | extended |
| `public/index.html` | `page-research`, view/export containers, navigation | extended |
| `public/interface.css` | workspace, progress, evidence, media, file-card styling | extended |
| `hypothesis_engine.py` | owner/job-scoped hypothesis persistence | reused |
| `continuous_research.py` | context checkpoints | reused |
| `research_reports.py` | deterministic report assembly | reused |
| `workspace_store.py` | owner-scoped workspace persistence | reused |

## Deep Search lifecycle

### Creation and triggering

`research.criar_job`/the intent layer can create a job for an explicit research
request or a suggested one. The job records the objective, mode, owner and
budget. Mode aliases (`deep`, `deep search`, `deep_research`, `investigativa`,
`profunda`, etc.) map to `rapida`, `pro`, `profunda` or `investigativa`.

### Structured plan

`montar_plano` creates bounded subquestions and steps with:

- a stable step id and type (`busca`, `ler`, `analisar`, `verificar`,
  `sintetizar`, `auditar`);
- an objective, priority and `priority_reason`;
- explicit dependencies;
- a stop rule (`regra_parada`) and completion criterion;
- duplicate-query detection normalized with `_chave_consulta`;
- plan-version increments persisted with the job.

The plan removes redundant subquestions before adding steps. Search queries are
also checked against persisted `consultas_etapas`, so a resumed job does not
repeat a query already executed.

### Execution and budgets

`executar` is idempotent per step: steps already `feita`/`removida` are skipped,
so resume after interruption is safe. It persists the job and a context
checkpoint after each step and emits only backend-recorded events.

Budgets are per job and fixed at creation (environment overrides are read
only then):

| Mode | searches | pages | time | subquestions | depth | media | replans |
|---|---:|---:|---:|---:|---:|---:|---:|
| rápida | 2 | 3 | 30 s | 1 | 1 | 8 | 1 |
| pro | 4 | 6 | 60 s | 3 | 2 | 12 | 1 |
| profunda | 8 | 12 | 120 s | 4 | 2 | 16 | 2 |
| investigativa | 12 | 20 | 300 s | 6 | 3 | 20 | 2 |

Environment names are `JULIA_RESEARCH_MAX_*` with `JULIA_DEEP_MAX_*` aliases:
`BUSCAS`, `PAGINAS`, `SEGUNDOS`, `SUBCONSULTAS`, `PROFUNDIDADE`, `MIDIA`,
`CONCORRENCIA`, `REPLANS`, `BYTES_PAGINA`. Page size is capped at 2 MB per page
by default. The concurrency field is a configured ceiling; V5.8 executes
research steps sequentially, so the effective parallelism is 1.

Stopping conditions are: explicit cancellation, interruption by the caller,
timeout, exhausted search/page budget, no pending steps, or a completed single
replan round. The job is persisted in a terminal state **before** the
`research_completed` event is emitted.

### Gap-driven follow-up and replanning

After the main plan, `_lacunas` collects real gaps (missing evidence, failed
reads, unverified claims and follow-up queries recorded by investigations).
`replanejar` is bounded by `replans` and:

- never repeats an executed front or normalized query;
- creates at most a short set of search/read/analyze steps;
- can re-open a read step when new search results arrived;
- increments the plan version and emits `plan_updated`;
- preserves the original budget and timeout, avoiding an unbounded loop.

If the budget is exhausted or the replan ceiling is reached, the job finishes
with explicit limitations instead of pretending completeness.

### Cancellation and resume

`cancelar`/`pausar` update the persisted job; the worker checks the stop
callback and persisted status between steps. Interruption stores the state and
returns a resumable summary. Evidence already read is rehydrated from SQLite and
from step checkpoints on resume. Duplicate evidence ids are collapsed.

### Model unavailability

The orchestrator remains useful without an LLM. Planning, lexical verification,
source counts, contradiction checks, report assembly and exports are
deterministic. Synthesis is **extractive** and marked `llm=false` when Hermes
is unavailable; no semantic reasoning or test execution is invented.

## Evidence contract

The five V5.8 claim states are:

`SUPPORTED`, `CONTRADICTED`, `PARTIALLY_SUPPORTED`, `UNVERIFIED`,
`INCONCLUSIVE`.

Each claim carries:

- `statement`/`afirmacao`, `state`/`estado`, verification method and lexical
  coverage where applicable;
- `evidence_ids`, `supporting_ids`, `contradicting_ids`;
- `found_count`, `read_count`, `used_count` (source counts are computed from the
  actual source records, not accepted from the model);
- per-source `relation` (`SUPPORTS`/`CONTRADICTS`/`REQUIRES_VERIFICATION`),
  `read`, `access_state`, `used_excerpt`, title, domain/date.

The UI and JDUI view distinguish **found**, **read** and
**claim-supporting** sources. A source with no excerpt is not presented as
proof. `UNVERIFIED` is not converted into a positive claim.

## Media contract

`media_evidence.extrair_midia` reads HTML that was already fetched by the
existing safe acquisition path. It discovers `<img>`, `<video>`, poster and
Open Graph media metadata, normalizes only `http(s)` URLs, rejects credentials
and unsafe schemes, deduplicates by canonical URL, and preserves source page,
publisher, date, rights, access state, validation state and excerpt.

Every discovered item is forced to:

```json
{
  "evidence": false,
  "analysis_state": "not_analyzed",
  "access_state": "metadata_only"
}
```

unless a future real analyzer actually reads/validates the bytes. V5.8 has no
media download, thumbnail rehosting, transcript or visual analysis. JDUI media
is **discovery only**; the validators refuse `evidence=true` and refuse
`analysis_state=validated`.

## JDUI 4.0

`research_view.build_view` constructs a validated message from real records:

1. text summary with objective/status/budget/limits;
2. `researchplan` — steps, dependencies, server-recomputed progress,
   completion criteria and stopping rules;
3. `evidence` — claims, states, source counts and source details; invalid
   claims or unsupported claims without sources are omitted;
4. `accordion` — real hypothesis chains (HIPÓTESE, EVIDÊNCIAS, LACUNAS,
   PRÓXIMOS PASSOS, CONCLUSÃO) with `Testes executados: não`;
5. `media` — discovery metadata with a visible “não é evidência” label;
6. `filecard` — real export links or remote `http(s)` links, never arbitrary
   local paths.

`jdui.validar_mensagem` enforces version, block/size limits, component and
property allowlists. Unknown or invalid blocks are omitted and the view adds a
textual note; raw invalid JSON is never returned. The frontend registry mirrors
the backend rules and renders native components only. No model-supplied HTML or
JavaScript is executed.

## Exports and workspace

`GET /api/research/export?job_id=…&formato=md|csv|json` is authenticated,
owner-scoped through the relay, and renders bytes in memory with a 2 MB cap.
CSV cells are protected against formula injection. `Content-Disposition` is
attachment, content type is explicit and `nosniff`/`no-store` headers prevent
sniffing and caching. Nothing is persisted on Render.

`GET /api/research/view` returns the validated JDUI message. The dedicated
“Pesquisas” page lists saved jobs, opens a job, shows the structured view,
exposes the three download links and keeps the chat path (“Acompanhar no chat”).
Empty and error states are textual; no fake rows or fake progress are shown.

## SSE and continuity

The existing event stream is preserved: monotonic cursor, replay, ordered
delivery, deduplication, terminal flush and persisted events. The research panel
polls/refreshes the live summary only from relay data and backend events. It
does not invent “thinking” steps or expose private chain-of-thought.

## What is deliberately not here

- No new agent platform, graph database, social integration, Apify, or paid
  service.
- No production deploy, credentials changes, Lucas identity changes, 3D engine
  changes, Júlia extension changes or Fajulto Studio work.
- No media download/rehost, OCR, transcript or visual claim verification.
- No PDF.js, ECharts, Video.js or Docling runtime adoption in this increment.
