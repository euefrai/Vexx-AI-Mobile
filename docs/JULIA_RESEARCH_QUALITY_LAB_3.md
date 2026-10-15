# Júlia Research Quality Lab 3.0

## Current delivery status: partial

The first reproducible slice is implemented in `research_quality_lab.py` and
`run_research_quality_lab.py`. It evaluates the real local document extractor
and `docs_agent.trechos_relevantes` retriever against a versioned, synthetic
fixture corpus. A separate harness reopens the real SQLite checkpoint store
after repeated writes.

The lab is offline and does not require Hermes. It does not measure LLM
generation, factual truth about the real world, web-provider quality, CPU,
process-wide RAM, or tokens. Those capabilities are not inferred from
retrieval metrics. Citation-stage, claim-label, contradiction-label, and
checkpoint-state metric functions accept explicit reference labels; none of
them automatically assigns semantic truth.

Run:

```powershell
python run_research_quality_lab.py --output .\research-quality-report.json
```

The runner creates a temporary SQLite database and temporary originals folder.
It does not index the corpus into a user's document store. Reports identify
the dataset version/hash, environment, measured timings, computed metrics, and
unmeasured capabilities. The report is a local diagnostic artifact, not a
production dashboard.

## What is measured

- Retrieval: Precision@K, Recall@K, MRR@K, graded NDCG@K and duplicate-result
  rate, by query and case category.
- Limited source-selection checks: whether the annotated primary source,
  latest temporal record, and both annotated sides of a fixture conflict were
  retrieved.
- Performance: document save/extraction average, actual retrieval latency per
  query, total measured benchmark duration, and the SQLite/Python/platform
  versions.
- Checkpoint persistence: 10-, 25-, and 50-step fixtures repeatedly save to
  SQLite, close the connection, reopen it, restore the latest state, and
  compare objective, restrictions, decisions, evidence IDs, and pending steps.

The checkpoint fixture does not run the research worker or prove that the
Orchestrator will avoid repeating a real search. Its duplicate-operation
metric is explicitly not measured. Semantic compaction remains unavailable
without a real LLM.

## Recommendation policy

Recommendations are deterministic review prompts based on observed retrieval
metrics only. They never patch production code or tune the Orchestrator
automatically. Every recommendation includes the measured signal that
triggered it. A recommendation is a hypothesis to investigate, not proof of a
root cause.

## Planned but not delivered

There is no administrator dashboard, web-search benchmark runner, semantic
citation-support judge, audited source-independence model, real contradiction
benchmark execution, real mode comparison, historical V4.7/V4.8 comparison,
or competitor integration. Those remain partial/blocked until a trustworthy
dataset and executable measurement path exist. Online tests must remain
separate from the frozen local corpus.
