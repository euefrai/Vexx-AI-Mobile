# V5.9 progress

- Base verified: `661d508`; tracked checkout initially clean. No push/deploy/restart authorized.
- Scope: search intent/query/provider/fetch/extraction/relevance/evidence/shopping; no identity/3D/JDUI rewrite, no parallel agents.
- Ledger: `search_orchestrator.py:160` usefulness accepts any single term; `:793` provider loop checks no elapsed budget inside fallback; `:924` recovery resets budget and provider attempts. `research.py:949` fetch omits query argument; `:793` opened state ignores unreadable flag. `shopping.py:2232` cache key only category/brand; `:2276` truncates candidate queue before second wave; `:2318` stops on any extracted product before checking constraints. These are candidates pending regression evidence.
- Baseline: seven real probes and frozen benchmarks run before engine edits. Reports under `qa-artifacts/v59/`. External blocking is a limitation, never a success.
- Next: finish baseline, prove defects with focused regressions, apply bounded fixes, compare identical probes/benchmarks, focused security/contracts, one final full suite, local commits/report.

## Checkpoint 1

- Baseline live complete: 7 queries; 0 confirmed shopping offers; research incorrectly called all four research queries ok (Transformer→architecture, batteries→study portals, asyncio→Maps/Prime Cursos). Frozen search 34/34; experience 16/16.
- Nine new offline regressions fail on original `661d508` modules (including corrected dict-shaped shopping download fixture), all pass after fixes. Focused set: 52 passed.
- Fixes: exact-token topic checks, generic instruction filtering, bounded fallback deadline, source readability/relevance gates, table/section/author propagation, criteria-aware shopping cache, budget preserved in every query, second wave until a matching confirmed offer.
- Next: primary-document retrieval, existing deep-research quality gates and bounded recovery, diagnostics, additional regressions; final live comparison and frozen benchmarks; full suite once at end.
