# V5.8 capability matrix

States: **FUNCTIONAL** = verified with reproducible evidence; **PARTIAL** =
works with a known limitation; **BLOCKED** = external/provider refusal recorded
honestly; **NOT_IMPLEMENTED** / **NOT_TESTED**. A passing unit test alone is not
enough for FUNCTIONAL.

| # | Capability | State | Evidence | Limit |
|---|---|---|---|---|
| 1 | Explicit/suggested deep-search trigger | FUNCTIONAL | intent/research tests; `research_agents` modes | Suggestion quality depends on intent layer |
| 2 | Structured plan with non-redundant subquestions | FUNCTIONAL | `test_plan_rejects_redundant_subquestions_and_duplicate_queries`; plan v3 metadata | Deterministic planner, not semantic planning |
| 3 | Gap-driven follow-up and bounded replanning | FUNCTIONAL | `test_replan_sem_loop`, `test_replanejar_*`, `test_executar_replaneja_por_lacuna_do_orquestrador` | Max 0–3 rounds; no infinite investigation |
| 4 | Duplicate query/evidence suppression | FUNCTIONAL | persisted `consultas_etapas`, normalized keys, evidence-id collapse | Normalization is lexical |
| 5 | Stopping criteria, budgets, timeouts | FUNCTIONAL | `test_cancelar_e_orcamento`; per-mode budgets; timeout test | Concurrency ceiling is not used to parallelize |
| 6 | Cancellation, pause and resume | FUNCTIONAL | `test_worker_thread_completa_e_cancela`, `test_pausa_segura_worker`, `test_executar_fim_a_fim_e_retomada`, checkpoint restore tests | Resume is per persisted step; not mid-page streaming |
| 7 | Honest model-unavailable behavior | FUNCTIONAL | extractive synthesis tests; `llm=false`; Hermes blocked recorded | No semantic synthesis when model is unavailable |
| 8 | Five evidence states + source counts | PARTIAL | `test_verificador_estados`; V5.8 claims include found/read/used and supporting/contradicting IDs | Semantic implication remains BLOCKED without LLM |
| 9 | Found vs read vs claim-supporting sources | FUNCTIONAL | `test_analyst_persists_media_and_verifier_records_read_sources`; JDUI evidence card | “Read” means extracted text was stored, not deep comprehension |
| 10 | Hypothesis chain, never fake tests | FUNCTIONAL | hypothesis tests; `cadeia`; `Testes executados: não`; exports | Tests are proposals, not executed by V5.8 |
| 11 | Media discovery metadata | FUNCTIONAL | `test_media_discovery_is_metadata_only_safe_and_deduplicated`; Chrome media card | Only HTML metadata; no media bytes/transcript/visual analysis |
| 12 | Media cannot become evidence | FUNCTIONAL | backend + frontend validators force `evidence=false`, `not_analyzed` | This is a guard, not a capability to analyze |
| 13 | JDUI 4.0 validated schemas | FUNCTIONAL | `researchplan`/`evidence`/`media`/`filecard` backend + JS parity tests | Unknown blocks removed with textual note |
| 14 | Real Chrome desktop + emulated mobile | FUNCTIONAL (local) | `qa-artifacts/v58/chrome-e2e.json`, 5 captures | Emulated mobile only; no physical device |
| 15 | Structured research workspace | FUNCTIONAL | dedicated page; saved jobs, open, view, exports, chat link | No annotations/report versioning |
| 16 | Real-byte exports | FUNCTIONAL | route tests; Chrome fetched 1,839 bytes; CSV formula test | MD/CSV/JSON only, 2 MB, no persistent storage |
| 17 | Owner isolation | FUNCTIONAL | `test_relay_view_and_export_routes...`, `test_isolamento.py`, owner-scoped queries | Production multi-user validation not run |
| 18 | SSE/replay/terminal continuity | FUNCTIONAL (tests) | `test_sse_entrega_ordenada_com_replay_e_fechamento`; existing streaming tests | Browser reload during a live model stream not re-tested in V5.8 Chrome |
| 19 | PDF/document extraction | FUNCTIONAL (existing) | `test_docs_memoria::test_pdf_textual_e_vazio`; docs_agent | OCR absent; Docling not adopted |
| 20 | Charts/data analysis | FUNCTIONAL (existing JDUI) | `test_owner_scoped_tabular_chat_creates_real_chart_and_comparison` | No ECharts; deep-research view does not add new chart E2E |
| 21 | Commercial research | PARTIAL | frozen `pesquisa_v57` product/spec/link cases 34/34; shopping tests | External stores vary and can block |
| 22 | News research | PARTIAL | `pesquisa_v57` news/link fixtures; blocked-source tests | No live news-provider E2E in V5.8 |
| 23 | External providers | BLOCKED (variable) | 403/429/bot-wall recorded as BLOCKED; tests | Never converted to PASS |
| 24 | Performance/resources | FUNCTIONAL (local) | `performance.json`: 7.35 ms view, 9–34 ms exports, no heavy imports | Not a production load test |
| 25 | Production/Render validation | NOT_TESTED | — | No push/deploy authorization; PID 24356 untouched |

## Reading the matrix

- `PARTIAL` and `BLOCKED` are accepted honest states, not failures hidden by
  wording.
- V5.8 proves a complete **local deterministic deep investigation** with real
  exports and a real browser UI. It does not prove semantic reasoning,
  multimodal understanding, production behavior or external-provider
  availability.
- The 20-case evidence mapping is in [QUALITY_CASES.md](QUALITY_CASES.md).
