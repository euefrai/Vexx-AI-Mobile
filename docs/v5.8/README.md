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
| [COMMITS.md](COMMITS.md) | Local commit map |

Raw evidence is in `qa-artifacts/v58/`. Final report:
[`RELATORIO_VEXX_AI_V5.8_DEEP_RESEARCH.md`](../../RELATORIO_VEXX_AI_V5.8_DEEP_RESEARCH.md).

## Short result

- Full local suite: **954 passed, 4 skipped, 2 warnings in 211.39 s** (final HEAD).
- Frozen research/search benchmarks: **34/34**, quality-lab suite **38 passed,
  1 skipped**.
- Focused security suite: **33 passed**.
- Real headless Chrome 155, desktop 1280×900 and emulated mobile 390×844:
  **passed**, no horizontal overflow, real 1,839-byte Markdown export fetched
  through the authenticated route, no uncaught JS exceptions.
- New pure-module performance: JDUI view build **7.35 ms** (24 steps, 10
  claims, 12 media, 8 hypotheses); exports **9–34 ms** for 200 records.
- Heavy libraries were evaluated but **not added**; none is imported by the
  measured runtime.
