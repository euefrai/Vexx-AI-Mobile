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

## Checkpoint 2

- Intent cleaning had removed Compare/source preference before retrieval; original request now reaches discovery and relevance checks. Official docs discovered first; never evidence until opened.
- 113 focused contract tests pass; frozen search 34/34 and experience 16/16 unchanged. First broad shopping query intentionally stays price-free (legacy contract), with mandatory budget validation and explicit priced second query; earlier proposed all-query enrichment reverted.
- Existing DDG reused as general fallback; block/cooldown stops repeat calls; Stack Exchange shares one deadline across sites; empty MLB no longer terminates fallback. Recovery retains attempts, failure history and one total deadline.
- Real arXiv HTML selected arXivLabs boilerplate instead of its labelled abstract. Semantic abstract selection fixed; scope is abstract_only, not full text. Explicit user URL reads bypass topic gate, while read/usable states are separate.
- Shopping now labels exact/partial/alternative/irrelevant and retains actual source for late confirmed offers; missing RAM is visible as partial in existing cards. No component rewrite.
- Next: finish extraction checks, capture final real/source comparison, run frozen/security/contract suites; full suite once at end; coherent local commits and final report.

## Checkpoint 3 — engine complete

- Security/auth/academic contracts: 57 passed. Focused research/contracts: 232 passed, 2 skipped. Extraction regressions: 37 passed. Frozen benchmarks: search34/34, shopping59/59, experience16/16; original benchmark fixtures untouched.
- Real arXiv extraction reproduced from captured HTML: old selected 518 chars arXivLabs; fixed selects 1,146-char actual abstract, relevant=True, full_text_fetched=False. Ordinary HTML does not claim full scholarly text.
- Final live run: Transformer=1 useful abstract; frameworks=2 useful official docs; asyncio=1 useful official doc; batteries=0 useful (external DDG blocked, generic Bing results rejected). Three shopping cases still 0 confirmed offers; limitations must be explicit.
- Read status is now actual retrieval; relevance is separate. Explicit user-selected URL remains readable without invented topic constraints. One initial price-query proposal was reverted to preserve intentional legacy coverage contract.
- Next: final full suite exactly once, diagnose any regression without changing expected fixtures, write before/after report and final local commits. No push/deploy/restart.

## Final regression repair

- First complete suite: 1,015 passed, 2 failed, 4 skipped; original log retained. Both failures were compatibility issues: public HTTP429 code must remain bloqueado, and relevance must recognize 3.000 as 3000. Fixed code (not old expected fixtures); diagnostic category still identifies rate limits. Focused regressions: 92 passed.
- Full suite rerun is required due to those failures, not routine repetition. Next: final report/QA commit after result.

## Complete

- Final full suite after compatibility repairs: 1,018 passed, 4 skipped, 2 deprecation warnings, 243.81s. Code commits: 99560c9, 35cdb28, 8f268be. No original frozen fixtures modified.
- Final report: RELATORIO_VEXX_AI_V5.9.0_SEARCH_COVERAGE.md. Comparison artifacts include live failure/offer limits; no commercial confirmation gain is claimed. Local document Quality Lab v2 temporal source 0/1 is explicitly residual.
- No push, deploy, production restart, credential/data changes, identity/3D/extension/Fajulto changes. Final QA/report commit closes this task.
