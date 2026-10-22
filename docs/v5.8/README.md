# Vexx AI V5.8 — Deep Research & JDUI 4.0

Documentation index for the V5.8 local increment. Status: **implemented,
tested locally, not deployed**. Production was not updated, and the V5.8
changes were not pushed.

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | End-to-end flow, modules, evidence/media/JDUI contracts |
| [REUSE_AND_GAPS.md](REUSE_AND_GAPS.md) | What was extended, what is new, and what remains untouched |
| [CAPABILITIES.md](CAPABILITIES.md) | Honest capability matrix with evidence and limits |
| [QUALITY_CASES.md](QUALITY_CASES.md) | The 20 required quality cases mapped to real evidence |
| [EXAMPLES.md](EXAMPLES.md) | Valid JDUI blocks, export URLs, commands |
| [TESTS.md](TESTS.md) | Unit/integration/contract/security/E2E/Chrome evidence |
| [BENCHMARKS.md](BENCHMARKS.md) | Frozen benchmark results and interpretation |
| [SCREENSHOTS.md](SCREENSHOTS.md) | Desktop and emulated-mobile captures |
| [PERFORMANCE.md](PERFORMANCE.md) | Local measurements and limits |
| [RESOURCES.md](RESOURCES.md) | PDF.js/ECharts/Video.js/Docling evaluation |
| [SECURITY.md](SECURITY.md) | Ownership, SSRF, CSP, JDUI and export boundaries |
| [LIMITATIONS.md](LIMITATIONS.md) | What V5.8 does not prove or provide |
| [PENDING.md](PENDING.md) | Prioritized pending work |
| [COMBINED_HEAD_2026-10-21.md](COMBINED_HEAD_2026-10-21.md) | Post-closure integration, auth race fix and combined-head QA |
| [COMMITS.md](COMMITS.md) | Local commit map |

Raw evidence is in `qa-artifacts/v58/`. Final report:
[`RELATORIO_VEXX_AI_V5.8_DEEP_RESEARCH.md`](../../RELATORIO_VEXX_AI_V5.8_DEEP_RESEARCH.md).

## Short result

- V5.8 closure (`4b9aca6`): **954 passed, 4 skipped, 2 warnings in 211.39 s**.
- Combined HEAD (`22c0ce3`, after concurrent provider/model/UI work and the
  auth race fix): **966 passed, 4 skipped, 2 warnings in 140.48 s**.
- Frozen research/search benchmarks: **34/34**, quality-lab suite **38 passed,
  1 skipped**.
- Focused security/ownership suite on the combined HEAD: **42 passed**.
- Real headless Chrome 155, desktop 1280x900 and emulated mobile 390x844:
  **passed**; three consecutive final-code runs, no horizontal overflow, real
  1,839-byte Markdown export through the authenticated route, no uncaught JS
  exceptions.
- Combined-head pure-module performance: JDUI view build **4.742 ms** (24
  steps, 10 claims, 12 media, 8 hypotheses); exports **5-22 ms** for 200
  records; RSS **21.46 MB**.
- Heavy libraries were evaluated but **not added**; none is imported by the
  measured runtime.
