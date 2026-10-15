# Julia Hypothesis Engine

## Status

The deterministic, owner-scoped persistence primitive is implemented in
`hypothesis_engine.py` and is connected to completed research-job verification.
The orchestrator stores claims as open investigation questions, attaches only
evidence IDs returned by the deterministic checker, and persists explicit
missing-evidence and next-step fields. It does not infer or diagnose causes.

## Stored state

Each hypothesis is tied to an owner and research job and records:

- A stable hypothesis ID and statement.
- One of `open`, `supported`, `weakened`, or `inconclusive`.
- IDs of supporting evidence and descriptions of missing evidence.
- Next tests or research steps.
- A result summary supplied by the caller.

`supported` means that the investigation marked the hypothesis as supported; it
does not mean a diagnosis or truth has been established. The module does not
decide status from evidence or text.

## Persistence and limits

`HypothesisStore` creates its SQLite table/index using the caller's connection.
Reads and deletion are scoped by both `owner_id` and `job_id`. Statements and
list entries are bounded, and invalid statuses or empty values raise
`ValueError`. The caller must derive the owner from authenticated server state,
not from untrusted client input.

## Validation

Focused tests cover persistence/update, owner/job isolation, scoped deletion,
invalid state, lifecycle persistence, and the open/non-diagnostic status.
Semantic hypothesis generation and evidence interpretation remain unavailable
without a real inference provider.
