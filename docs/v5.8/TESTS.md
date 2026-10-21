# V5.8 tests and evidence

## Results

| Suite | Command | Result |
|---|---|---|
| Pre-V5.8 baseline | `python -m pytest -q` (2026-10-20) | **929 passed, 4 skipped, 2 warnings in 227.42 s** |
| Focused research/JDUI/server | `pytest tests/test_v58... tests/test_research... tests/test_jdui... -q` | **156 passed, 1 skipped** |
| Full local suite after V5.8 + audit snapshot | `python -m pytest -q` | **954 passed, 4 skipped, 2 warnings in 211.39 s** (final HEAD; an earlier run took 172.87 s with the same counts) |
| Frozen quality benchmarks | `pytest tests/test_research_quality_lab.py tests/test_bench_pesquisa_v57.py tests/test_evidence_benchmarks.py -q` | **38 passed, 1 skipped** |
| Frozen search benchmark | `python tools/bench_pesquisa_v57.py --sem-salvar` | **34/34, taxa 1.0** |
| Security/ownership subset | `test_isolamento`, `test_auth`, `test_exports`, SSRF, V5.8 route/URL tests | **33 passed** |
| New V5.8 contracts | `tests/test_v58_deep_research.py` | **13 passed** |
| Node syntax | `node --check public/jdui.js` / `public/app.js` | pass |
| Real Chrome E2E | `python tools/chrome_e2e_v58.py` | **ok: true** |
| Performance | `python tools/bench_v58.py` | see `performance.json` |

Raw outputs:

- `qa-artifacts/v58/full-suite-final.txt` (final HEAD)
- `qa-artifacts/v58/full-suite.txt`
- `qa-artifacts/v58/frozen-benchmarks.txt`
- `qa-artifacts/v58/bench-pesquisa-frozen.txt`
- `qa-artifacts/v58/security.txt`
- `qa-artifacts/v58/chrome-e2e.json` / `.txt` / console
- `qa-artifacts/v58/performance.json` / `.txt`
- `qa-artifacts/v573/baseline-v58.txt` (pre-V5.8 baseline)

The full-suite delta from 929 to 954 includes the new V5.8 tests **and** the
concurrent audit test file preserved in commit `52e3195`. It is not a claim that
all 25 new passes are V5.8 behavior.

## What the V5.8 tests cover

- media discovery: safe URL only, deduplication, no implicit logo, metadata
  provenance, forced non-evidence state;
- plan deduplication, normalized duplicate-query suppression, server-computed
  progress, spoofed percent rejection;
- evidence source counts, source relation/read/excerpt, supported-claim source
  requirement;
- hypothesis `cadeia` and explicit “tests not executed” statement;
- file-card URL allowlist and export-route validation;
- real Markdown/CSV/JSON bytes, CSV formula injection protection, 2 MB cap;
- analyst media persistence and verifier read-source provenance;
- relay view/export routes with authenticated owner and real bytes;
- frontend JDUI parity for the four new components (Node harness);
- Chrome desktop/mobile workspace, component count, evidence/media rendering,
  overflow, button height and export fetch.

## Evidence kinds (kept separate)

| Kind | V5.8 status |
|---|---|
| Deterministic/simulated | proven by unit/integration tests and frozen fixtures |
| External providers | not re-run as a V5.8 pass; existing 403/429/bot-wall paths remain BLOCKED |
| Inference/LLM | **not available**; no semantic synthesis claim |
| Chrome | real headless Chrome 155, local isolated stack; desktop and emulated mobile |
| Physical mobile | not performed |
| Production/Render | not tested, not updated |
| Real-byte export | proven locally through authenticated Chrome fetch and route tests |

## Chrome E2E details

`tools/chrome_e2e_v58.py` starts:

- `uvicorn server:app` on a free loopback port;
- `pc_agent.py` with a temporary SQLite database and fake/unused model endpoint;
- Chrome `--headless=new` with a temporary profile and CDP;
- a pre-persisted research job containing a real evidence record, plan,
  media metadata and hypothesis.

It logs in through the real form, opens **Pesquisas**, opens the job, waits for
at least four JDUI slots, asserts the plan/evidence/media labels, opens the
evidence details, fetches the Markdown export through the real authenticated
route, switches to 390×844 mobile emulation, and asserts no horizontal
overflow. Captures are in `qa-artifacts/v58/*.png`.

Observed: 5 JDUI slots, 6 plan nodes, 3 media cards, 8 badges, 1,839 export
bytes, mobile width 390, no overflow, no uncaught exceptions.

## Limits of this test evidence

- The E2E job is prepared locally; it is not an external web investigation.
- External search providers were not required for the Chrome run.
- The mobile viewport is Chrome emulation, not a physical device.
- No test was altered to inflate a result; the 4 skips are unchanged and are
  not counted as passes.
- Production PID `24356` was not touched.
