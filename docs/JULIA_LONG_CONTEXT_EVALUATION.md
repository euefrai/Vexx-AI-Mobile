# Long-context and checkpoint evaluation

The frozen benchmark includes 10-, 25-, and 50-step persistence scenarios.
`run_checkpoint_benchmark` writes each successive state using the production
`ResearchContextStore`, closes SQLite, reopens it, restores the latest
checkpoint, and measures exact set coverage for the objective, restrictions,
decisions, evidence IDs, and pending steps.

Current sample run: 85 checkpoint writes across three scenarios; every listed
state item was restored in the local fixture. This tests serialization,
owner/job-scoped persistence and restart restoration only. It does not model
network disconnections, corrections, source replacement, re-planning
decisions, or real operations performed by the Orchestrator.

Duplicate execution is not measured: generated fixture step IDs are not a
production operation ledger. The lab marks that metric unavailable. Semantic
summaries/compaction and LLM continuity are separately blocked without real
inference; deterministic checkpoints remain the authoritative persisted state.
