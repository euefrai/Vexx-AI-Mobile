# Relatório Júlia 4.9 — Research Quality Lab 3.0

## Status: PARCIAL

The lab foundation now runs real local document extraction/retrieval and
persisted checkpoint restoration against a frozen synthetic fixture. It does
not yet measure semantic answer quality, real-world factual accuracy, live
web-search relevance, or LLM performance. Hermes inference remains blocked.

## Delivered in this increment

- Windows E2E process helper captures subprocess output outside inherited log
  handles, waits for process exit, kills on timeout, joins output readers, and
  keeps per-test logs under pytest `tmp_path`.
- Relay ports are allocated per test. The research E2E waits for both terminal
  status and the final persisted completion event. Test fake-server threads
  are joined.
- Versioned dataset: `benchmarks/research_quality_v1.json`, SHA-256
  `e29379d7b805d25a3a5bea69ab3f9ea11f101cec13cc86c30fa44c221a4d489b`.
  It contains 11 fictional documents, eight cases and nine queries, plus
  SQLite checkpoint scenarios of 10, 25 and 50 steps.
- Metrics implemented: Precision@K, Recall@K, MRR@K, graded NDCG@K,
  duplicate rate, labelled confusion matrices, four separate citation stages,
  contradiction TP/TN/FP/FN, checkpoint state coverage, and
  metric-triggered review recommendations.
- CLI: `python run_research_quality_lab.py --output <report.json>`.

## Measured sample

One local run on Windows 11 / Python 3.14.4 / SQLite 3.50.4 indexed 11
fictional records and ran nine queries:

| Metric | Result |
|---|---:|
| Precision@5 (macro) | 0.244444 |
| Recall@5 (macro) | 0.944444 |
| MRR@5 (macro) | 1.000000 |
| NDCG@5 (macro) | 0.990813 |
| Duplicate rate@5 | 0.000000 |
| Total local benchmark time | 503.952 ms |
| Mean ingestion/extraction call | 26.936 ms |
| Mean retrieval call | 0.926 ms |
| Maximum retrieval call | 3.314 ms |

The source-attribution, latest-source and both-sides-of-conflict fixture checks
each retrieved their annotated records in this run (one case per check).
These small denominators do not support broad quality claims. The benchmark
triggered a review recommendation for ranking specificity; the production
retriever was not automatically changed.

The checkpoint runner performed 85 save operations, closed and reopened
SQLite, and restored all listed fixture state for the 10/25/50-step cases.
This validates the checkpoint store on synthetic state, not real-work
deduplication or semantic continuity.

## Validation

Focused verification: **14 passed** in 23.89s, including both real-process
E2Es, process/log cleanup, and the quality-lab tests. Pylance diagnostics were
empty for `research_quality_lab.py` and `tests/e2e_processes.py`, and the CLI
passed a Python syntax check.

The repository suite was then run three consecutive times with
`-k "not test_jdui_v43_no_node"`:

| Run | Result | Duration |
|---|---|---:|
| 1 | 312 passed, 2 skipped, 1 deselected, 3 warnings | 174.10s |
| 2 | 312 passed, 2 skipped, 1 deselected, 3 warnings | 145.49s |
| 3 | 312 passed, 2 skipped, 1 deselected, 3 warnings | 109.70s |

The deselected test currently fails at `eg-render` against an uncommitted
working-tree edit in `public/jdui.js`; running its harness against the
committed `HEAD:public/jdui.js` passed. That unrelated local edit was preserved
and is not included in this increment. The three recurring warnings are an
existing test-thread `EndOfStream`, the `mss.mss` deprecation, and Starlette's
`TestClient` timeout deprecation. Therefore, these are three consecutive
passes of the suite excluding that known local UI regression, not three
unqualified full-suite passes.

## Not implemented / blocked

- No admin dashboard or persisted longitudinal metric store.
- No real-world independently reviewed factual QA gold dataset.
- No semantic claim/citation-support verifier or semantic contradiction
  resolution.
- No reviewed source-independence graph; domains/URLs are not treated as
  independence.
- No live web-search benchmark or quality-by-mode comparison.
- No verified V4.7/V4.8 historical reruns, competitor integrations, or
  comparative claims.
- No CPU/RAM/token measurements.
- LLM evaluation, semantic compaction, and PDF OCR remain unavailable.

Accordingly, this increment is a reproducible measurement foundation, not
completion of every V4.9 objective.
