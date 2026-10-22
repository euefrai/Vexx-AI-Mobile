# Combined HEAD after V5.8 - 2026-10-21

## Context

V5.8 was closed locally at commit `4b9aca6`. After that closure, concurrent
provider/model/UI work was committed on the same branch, and the local
`origin/main` ref moved to `52a4bc4`. The V5.8 commits are **not** reachable from
`origin/main`; `git merge-base --is-ancestor 4b9aca6 origin/main` returned false.
Nothing was pushed or deployed by this V5.8 work.

The combined HEAD was validated rather than assumed. The code/QA commit for this
document is `22c0ce3` (`fix(ui): keep login after a late session probe`). The
concurrent commits are not claimed as V5.8 work.

## Auth race found by Chrome E2E

The first combined-head Chrome run reached the real login form but failed. The
relay log showed a successful `POST /api/login` (HTTP 200) followed by the
initial `GET /api/session` returning 401. That late 401 reopened the login
overlay after the login had already succeeded.

The fix tracks authentication transitions (`authEpoch`) and an in-flight login
or registration (`authBusy`). `restoreSession()` now ignores a stale 401 or a
stale 200 when a newer login/registration has taken over, and a late 401 cannot
clear an already authenticated session. Client-side registration validation
does not set the busy flag.

Regression coverage is behavioral, not a source-string check:
`tests/test_frontend_smoke.py::test_login_nao_e_derrubado_por_sessao_atrasada`
covers:

- a 401 that arrives after login;
- a session probe that starts during login, before the cookie exists;
- a stale 200 that would otherwise overwrite the new owner;
- the control case where a 401 without a concurrent login still opens login.

## Final combined-head results

| Check | Result |
|---|---|
| Full local suite | **966 passed, 4 skipped, 2 warnings in 140.48 s** |
| Focused combined suite | **105 passed, 1 warning in 22.86 s** |
| Frozen quality/search benchmarks | **38 passed, 1 skipped in 11.97 s** |
| Frozen search benchmark | **34/34, global rate 1.0, no failures** |
| Security/ownership subset | **42 passed in 11.17 s** |
| Real Chrome E2E | **3/3 final-code runs passed** |
| JDUI view build | **4.742 ms**, 6 blocks, 0.11 MB peak Python allocation |
| Exports | Markdown 15.081 ms / CSV 21.58 ms / JSON 5.33 ms for 200 records |
| Process RSS after imports | **21.46 MB** |
| Heavy libraries imported | **none** |

The four skips are the same pre-existing skips; they are not counted as passes.
The combined-head security invocation explicitly includes all 13 V5.8 contract
tests in addition to ownership, auth and export tests, so its count is not
directly comparable to the closure subset.

## Chrome evidence

Three consecutive runs on the final combined-head code passed:

| Run | Timestamp | Result |
|---|---|---|
| 1 | `2026-10-21T21:14:37` | ok |
| 2 | `2026-10-21T21:14:52` | ok |
| 3 | `2026-10-21T21:15:05` | ok |

Canonical run: Chrome `155.0.8059.85`, desktop 1280x900, emulated mobile
390x844, 5 JDUI slots, 6 plan nodes, 3 media cards, 8 badges, 1,839 real export
bytes, no horizontal overflow, no uncaught JavaScript exceptions.

This is still an isolated local stack with a pre-persisted job. It is not an
external investigation, a physical phone, or production.

## Evidence files

- `qa-artifacts/v58/full-suite-combined-head.txt`
- `qa-artifacts/v58/combined-head-focused.txt`
- `qa-artifacts/v58/frozen-benchmarks-combined-head.txt`
- `qa-artifacts/v58/bench-pesquisa-frozen-combined-head.txt`
- `qa-artifacts/v58/security-combined-head.txt`
- `qa-artifacts/v58/chrome-e2e.json` / `chrome-e2e.txt`
- `qa-artifacts/v58/chrome-e2e-combined-head.txt`
- `qa-artifacts/v58/chrome-e2e-final-run1.txt`, `run2.txt`, `run3.txt`
- `qa-artifacts/v58/chrome-e2e-stability.txt`
- `qa-artifacts/v58/performance.json` / `performance-combined-head.txt`
- five screenshots in `qa-artifacts/v58/*.png`

All new text evidence was normalized to UTF-8/LF so it is readable by the same
tooling as the V5.8 closure artifacts.

## Unchanged limits and production state

The V5.8 classification remains **READY_WITH_LIMITATIONS**, local only. The
following are still not proven:

- external provider/Hermes behavior against live services;
- real LLM inference or semantic entailment;
- media download, transcription, thumbnail generation or visual analysis;
- PDF OCR/layout analysis;
- physical mobile devices;
- browser reload during a live model stream;
- production/Render deployment.

Production PID `24356` was not started, stopped or restarted by this work. At the
final check it was not running; that is an observed external state, not a deploy
or a claim that production is current.
