# Local commit map - V5.8

Branch: `main`. No V5.8 commit was pushed. During the V5.8 work the local
`origin/main` ref stayed at
`ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`. After closure it moved to
`52a4bc4` because of concurrent provider/model/UI work. V5.8 commit `4b9aca6`
is not an ancestor of `origin/main`.

## V5.8 commits

| Commit | Scope |
|---|---|
| `52e3195` | `audit: snapshot concurrent 2026-10-20 corrections and QA evidence` - preserved the pre-existing staged audit work before V5.8 commits |
| `de0597d` | `feat(v5.8): implement deep-search provenance, evidence view, bounded exports and JDUI schemas` - research agents/media/view/exports, JDUI backend, server routes, contracts |
| `e4cf84d` | `feat(v5.8): add research workspace, multimedia JDUI renderers and export actions` - frontend page, renderers, styles, frontend smoke test |
| `634511d` | `test(v5.8): add real Chrome E2E, performance benchmark and QA evidence` - tools + `qa-artifacts/v58` |
| `17014d1` | `docs(v5.8): add architecture, capability, QA, security and performance reports` - `docs/v5.8/`, final report, matrix update |
| `4806454` | `fix(v5.8): polish research status label and workspace error title` |
| `c65a1c1` | `test(v5.8): refresh Chrome evidence after UI polish` |
| `2562a77` | `docs(v5.8): record final commit map and refreshed Chrome hash` |
| `6d4f73b` | `test(v5.8): record final-head full suite and update QA report` |
| `ff84de4` | `docs(v5.8): finalize local commit map` |
| `4b9aca6` | `chore(qa): normalize V5.8 text evidence to UTF-8` |

Commit boundaries are local and can be reorganized before an authorized push.
The audit snapshot commit is intentionally separate so V5.8 does not claim
concurrent audit work as its own.

## Post-V5.8 combined HEAD

The branch then received concurrent work outside the V5.8 scope, integrated by
merge commits `438f048`, `81d0f82`, `fafe5e2` and `5f41220`:

| Commit | Scope |
|---|---|
| `54127e2` | copy/cache/interactive-state improvements |
| `4358356` | history and saved-items stabilization, assistant labels |
| `e5db2e2` | provider key workflows and model selection |
| `52a4bc4` | provider configuration feedback; this is the current `origin/main` ref |
| `22c0ce3` | `fix(ui): keep login after a late session probe` - auth race guard, behavioral regression test and combined-head QA evidence |

A documentation commit follows `22c0ce3` and adds this map plus the combined-head
report. It does not change runtime code.

## Verification

V5.8 closure (`4b9aca6`):

```text
954 passed, 4 skipped, 2 warnings in 211.39s
38 passed, 1 skipped (frozen quality)
34/34 frozen search benchmark
33 passed (security/ownership subset)
Chrome E2E ok: true (desktop + emulated mobile)
```

Combined HEAD (`22c0ce3`, after the auth guard):

```text
966 passed, 4 skipped, 2 warnings in 140.48s
105 passed (focused combined suite)
38 passed, 1 skipped (frozen quality/search)
34/34 frozen search benchmark, rate 1.0
42 passed (security/ownership subset)
Chrome E2E: 3/3 final-code runs ok; 1,839-byte export
```

The 966 count includes tests from the concurrent work and the new auth race
test. It is not a claim that all new tests are V5.8 behavior.
