# Local commit map — V5.8

Branch: `main`. No commit was pushed. Origin remained at
`ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe` during the work.

| Commit | Scope |
|---|---|
| `52e3195` | `audit: snapshot concurrent 2026-10-20 corrections and QA evidence` — preserved the pre-existing staged audit work before V5.8 commits |
| `de0597d` | `feat(v5.8): implement deep-search provenance, evidence view, bounded exports and JDUI schemas` — research agents/media/view/exports, JDUI backend, server routes, contracts |
| `e4cf84d` | `feat(v5.8): add research workspace, multimedia JDUI renderers and export actions` — frontend page, renderers, styles, frontend smoke test |
| `634511d` | `test(v5.8): add real Chrome E2E, performance benchmark and QA evidence` — tools + `qa-artifacts/v58` |
| `17014d1` | `docs(v5.8): add architecture, capability, QA, security and performance reports` — `docs/v5.8/`, final report, matrix update |
| `4806454` | `fix(v5.8): polish research status label and workspace error title` |
| `c65a1c1` | `test(v5.8): refresh Chrome evidence after UI polish` |
| final docs update | records the commit map and refreshed screenshot hash |

Commit boundaries are local and can be reorganized before an authorized push.
The audit snapshot commit is intentionally separate so V5.8 does not claim
concurrent audit work as its own.

## Verification after commits

The code commits preserve the working behavior verified by:

```text
954 passed, 4 skipped, 2 warnings in 211.39s (final HEAD)
38 passed, 1 skipped (frozen quality)
34/34 frozen search benchmark
33 passed (security/ownership subset)
Chrome E2E ok: true (desktop + emulated mobile)
```

The final documentation commit changes only Markdown (and the updated
capability matrix), not runtime code.
