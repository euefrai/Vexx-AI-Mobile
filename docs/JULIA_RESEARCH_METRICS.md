# Research quality metrics

The implementation is in `research_quality_lab.py`. Metrics are computed from
explicit relevance or review labels; they do not determine whether a
real-world claim is true.

## Retrieval at K

- **Precision@K** = unique relevant documents in the first K result positions
  divided by K. If fewer than K results are returned, missing positions count
  as non-relevant.
- **Recall@K** = unique relevant documents retrieved in the first K divided by
  all annotated relevant documents for that query.
- **MRR@K** = reciprocal rank of the first relevant document, or zero if none
  is retrieved.
- **NDCG@K** uses graded relevance with gain `2^grade - 1` and logarithmic
  discount `log2(rank + 1)`, divided by ideal DCG. A repeated document only
  contributes gain at its first rank.
- **Duplicate rate@K** = repeated document positions divided by the number of
  returned positions.

Category and overall summaries are macro averages over queries, not weighted
by document count. This dataset is intentionally tiny; one fixture case can
materially change a category score.

## Labelled verifiers

Claim-classification metrics report a confusion matrix, accuracy and
per-class precision/recall for supplied labels:
`SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`, and
`INSUFFICIENT_EVIDENCE`. The metric function scores a prediction supplied by a
caller; it does not derive that prediction.

Contradiction metrics report TP, TN, FP, FN, precision and recall against
human/reference boolean labels. Detection is not resolution.

## Performance

Extraction/save and retrieval durations use `time.perf_counter()` around the
actual local document ingestion and retrieval calls. The total duration also
includes benchmark setup. A single run is an observation, not a stable
service-level guarantee. CPU, system RAM, token usage, provider calls, and
cache size are not currently measured.
