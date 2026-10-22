# Benchmarks — V5.8

## Frozen research/search benchmark

Command:

```powershell
python tools/bench_pesquisa_v57.py --sem-salvar
```

Result at V5.8 closure (2026-10-20): **34/34**, global rate **1.0**, no failures.
Rerun on the combined HEAD (2026-10-21): **34/34**, rate **1.0**, no failures.

Groups include reformulation, correspondence, junk-flow, republication, product,
specs, links, outdated content and gain. These are **frozen fixtures**, not a
live internet score. They are useful for regression detection and are explicitly
separate from external probes.

Raw: `qa-artifacts/v58/bench-pesquisa-frozen.txt` (closure) and
`qa-artifacts/v58/bench-pesquisa-frozen-combined-head.txt` (combined HEAD).

## Research quality lab

Command:

```powershell
python -m pytest tests/test_research_quality_lab.py tests/test_bench_pesquisa_v57.py tests/test_evidence_benchmarks.py -q
```

Result at closure: **38 passed, 1 skipped in 17.53 s**.
Rerun on the combined HEAD: **38 passed, 1 skipped in 11.97 s**.

The skipped case is the pre-existing semantic/LLM benchmark, which remains
BLOCKED without a real provider. It is not counted as a pass.

Covered: dataset versioning, retrieval metrics, citation stages, contradiction
metrics, checkpoint restore, memory/graph retrieval, factual verification,
format benchmarks, unit conversion and document peak-memory measurement.

Raw: `qa-artifacts/v58/frozen-benchmarks.txt` (closure) and
`qa-artifacts/v58/frozen-benchmarks-combined-head.txt` (combined HEAD).

## What is not measured

- Open-web answer quality over time; providers vary and may block.
- Semantic entailment; no LLM is available.
- Human evaluation of report usefulness.
- Production latency or Render Free memory under concurrent users.
- A quality uplift caused by the new UI; only contract/regression behavior is
  measured.

## Interpretation rule

A frozen fixture pass proves the deterministic pipeline still behaves as
specified. It does **not** prove that live web research is correct, complete or
available. Blocked external providers stay BLOCKED.
