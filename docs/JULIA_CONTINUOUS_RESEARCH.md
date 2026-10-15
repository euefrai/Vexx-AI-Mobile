# Julia Continuous Research Context

## Status

`continuous_research.py` provides a deterministic SQLite checkpoint store
integrated with the existing research-job orchestrator. Snapshots are saved
after plan creation and each completed step; restart restoration rehydrates
completed step results alongside the original evidence and provenance.

## Checkpoint contract

`ResearchContextStore` stores versioned JSON scoped to an owner and research
job. The allowed state fields are objective, restrictions, plan, sources,
document chunks, evidence, contradictions, hypotheses, decisions, results,
pending steps, and next action. IDs and original records should remain in the
state so a resumed task can recover provenance instead of relying on a
lossy summary.

The serialized checkpoint is limited to 1 MiB. Missing objectives, invalid
owner/job IDs, serialization errors, and oversize state fail explicitly.
Restoration returns the latest sequence for the authenticated owner/job only.
The store does not delete earlier checkpoints unless the owner-scoped deletion
method is explicitly called.

## Inference boundary

This implementation does not summarize or compact context semantically. The
restored metadata explicitly reports `unavailable_without_llm`. Structured
checkpoints work without inference; semantic compaction, if enabled later,
must preserve references to the original evidence and be tested for fidelity.

## Validation

Focused tests cover ordered checkpoints, retained evidence references,
owner/job isolation, deletion, missing objectives, and checkpoint size limits.
Lifecycle tests cover restoring a completed search after reopening the SQLite
connection and preserving retrieved document provenance.
