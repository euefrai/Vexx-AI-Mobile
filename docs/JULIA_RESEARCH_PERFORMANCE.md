# Research performance lab

The runner records actual local document ingestion/extraction and retrieval
duration, total elapsed time, document/query counts, and runtime versions.
It operates on a temporary SQLite database and a local fixture corpus. The
report does not claim web/provider latency, CPU utilization, process-wide RAM,
or token usage.

One development-machine sample (Windows 11, Python 3.14.4, SQLite 3.50.4,
dataset v1.0.0, K=5) indexed 11 fictional records and issued nine queries:

- Total measured run: 503.952 ms.
- Mean ingestion/extraction call: 26.936 ms.
- Mean retrieval call: 0.926 ms; maximum: 3.314 ms.

These are one-run measurements, include local SQLite work, and are not
production guarantees. They are kept separate from E2E latency, which includes
service startup, agent connection, network search, and process teardown.
Checkpoint timings are reported separately per 10/25/50-step fixture.

The benchmark identified a real review target: mean Precision@5 was 0.244444
while Recall@5 was 0.944444 on this tiny, deliberately broad fixture. The lab
therefore recommends reviewing top-K specificity without sacrificing
coverage. This is a dataset-specific optimization hypothesis, not evidence
that every live query has the same quality.
