# Twenty required quality cases

Each row is a real, reproducible test or artifact. “Partially” means the
deterministic/local part is proven but the external or multimodal part is not.

| # | Case | Evidence | Result / limit |
|---:|---|---|---|
| 1 | Factual | `tests/test_research_quality_lab.py::test_factual_verification_benchmark`; frozen cases | Pass; lexical verification only |
| 2 | Complex / multi-hop | `research_quality_v2` multi-hop cases; `test_format_benchmark_formatos_reais` | Pass on frozen fixtures; not open web |
| 3 | Contradictory sources | `tests/test_research_agents.py::test_verificador_estados`; contradiction metric test | Pass; reports CONTRADICTED/PARTIAL without forced consensus |
| 4 | Technical | `units-conversion` and `specs` frozen cases; 34/34 benchmark | Pass; deterministic units/specs |
| 5 | Scientific | `tests/test_academic_research.py`; `test_evidence_benchmarks.py` | Metadata/abstract only; full-text article reading not claimed |
| 6 | News | `pesquisa_v57` news/link fixtures; blocked-source tests | Partial; no live news E2E |
| 7 | Commercial | `pesquisa_v57` product/spec/link cases; shopping suite | Partial; external stores can block |
| 8 | Hypotheses | `test_hypotheses_persist_updates_and_remain_owner_scoped`; `cadeia` in view/export | Pass; `Testes executados: não` |
| 9 | PDFs | `test_docs_memoria.py::test_pdf_textual_e_vazio`; docs_agent contract | Pass for textual PDF; OCR absent |
| 10 | Charts | `test_owner_scoped_tabular_chat_creates_real_chart_and_comparison` | Pass for existing tabular JDUI; no ECharts |
| 11 | Images | `test_media_discovery_is_metadata_only_safe_and_deduplicated`; Chrome media card | Discovery only; no image understanding |
| 12 | Videos | V5.8 media discovery of video links; existing JDUI video allowlist tests | Discovery only; no transcript/analysis |
| 13 | Exports | `test_exports_are_real_bounded_bytes_and_csv_safe`; Chrome fetched 1,839 bytes | Pass; MD/CSV/JSON, 2 MB |
| 14 | Cancellation / resume | `test_worker_thread_completa_e_cancela`, `test_pausa_segura_worker`, `test_checkpoint_restores_completed_search_results_for_resume` | Pass; step-level persistence |
| 15 | Hermes 429 | `test_academic_research.py::test_429_retries_with_backoff_then_raises_explicit_error`; `test_bridge_mapeia_quota_e_pedido` | Pass; 429 stays blocked/quota, never success |
| 16 | Blocked sources | `test_providers_v57.py::test_http_403_e_429_bloqueado_sem_bypass`; recovery tests | Pass; BLOCKED remains BLOCKED |
| 17 | Insufficient evidence | `test_sem_fontes_continua_erro`; `test_v56_pesquisa_sem_fontes...`; view text fallback | Pass; explicit limitation |
| 18 | Invalid JDUI | `test_jdui.py::test_invalidos`; `test_research_view_omits_invalid_component_without_raw_json` | Pass; omitted with textual note |
| 19 | Reload during streaming | `test_sse_entrega_ordenada_com_replay_e_fechamento`; replay/idempotence tests | Partial: SSE replay proven; no V5.8 Chrome live-stream reload |
| 20 | Real-byte export | Chrome E2E + authenticated route tests | Pass in local isolated stack; production not tested |

## What is explicitly not claimed

- Cases 1–5, 7, 9, 10 and 19 are not a production or open-web quality score.
- Cases 11 and 12 do not prove image/video understanding.
- Case 20 proves bytes and headers, not download behavior in every browser.
- A skipped test never counts as a pass.
