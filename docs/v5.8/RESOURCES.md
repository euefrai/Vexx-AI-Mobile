# Resource and library assessment — V5.8

This file records the required evaluation of PDF.js, Apache ECharts, Video.js
and Docling. **None was adopted in V5.8.** Measured numbers and runtime budgets
are in [PERFORMANCE.md](PERFORMANCE.md).

## Decision summary

| Library | License | Current version | Maintenance signal | Adopted? | Why |
|---|---|---|---|---|---|
| PDF.js (`pdfjs-dist`) | Apache-2.0 | 6.4.299 | active npm releases | No | 459 KB main + 1.26 MB worker, worker/CSP surface, no new PDF viewer use case |
| Apache ECharts | Apache-2.0 | 6.1.0 | active npm releases | No | 1.12 MB full dist, canvas/DOM memory, existing deterministic JDUI charts suffice |
| Video.js | Apache-2.0 | 10.1.0 | active, modular ESM v10 | No | player/CSP/media surface, media is discovery/link-only in V5.8 |
| Docling | MIT | 2.141.0 | active GitHub project (pushed 2026-10-20) | No | Python/model/OCR weight, CPU/RAM unsuitable for Render Free |

All licenses are permissive; none is copyleft. The decision is about weight,
CSP and real product need, not licensing.

## PDF.js

- Package: `pdfjs-dist@6.4.299`, Apache-2.0.
- Registry unpacked size: **34,913,648 B** (554 files).
- Published main file: **458,904 B**; worker: **1,264,342 B**.
- Browser requirements: a worker (typically `worker-src 'self' blob:`),
  careful `isEvalSupported` configuration, and testing of WASM/image paths.
- RAM: a worker per PDF; large PDFs can add tens of MB. This is a risk on the
  Render Free browser path and must be measured on the target device.
- V5.8 uses the existing textual PDF extraction and shows an honest limitation
  when text is absent. No PDF viewer or OCR is claimed.

## Apache ECharts

- Package: `echarts@6.1.0`, Apache-2.0.
- Registry unpacked size: **60,297,703 B** (1,347 files).
- Full published dist: **1,121,883 B** (a custom/tree-shaken build is smaller).
- No worker required, but canvas/DOM memory and animation cost vary by chart.
  CSP must be checked for the chosen build.
- V5.8 keeps the existing validated JDUI chart/data path; the deep-research
  view does not embed a new charting engine.

## Video.js

- Package: `video.js@10.1.0`, Apache-2.0.
- Registry package unpacked size: **48,496 B**, but v10 is a modular ESM entry
  that pulls `@videojs/*` packages; it is not a single 48 KB production bundle.
- Adds a player, media loading, format/source policy and CSP `media-src`
  requirements, plus player memory.
- V5.8 only discovers video links/metadata. It does not play, transcribe or
  analyze video, so the player is not justified.

## Docling

- PyPI: `docling==2.141.0`; GitHub license **MIT**; repository active.
- The PyPI package pulls `docling-slim` and optional OCR/model extras. Model
  downloads and OCR/CPU work can consume hundreds of MB to more than 1 GB.
- Server-side only; not a browser library. It would require a separate worker,
  bounded queue and chunk storage, not a request-path import on Render Free.
- V5.8 does not provide OCR or layout understanding and does not claim Docling
  behavior.

## Lazy-loading policy if adopted later

1. Load only after an explicit user action (open PDF/chart/video).
2. Keep the library and model work off the Render Free request path.
3. Add SRI/integrity and a narrow CSP allowlist (`script-src`, `worker-src`,
   `media-src`).
4. Enforce byte, duration, format and concurrency limits.
5. Measure real memory and interaction latency on desktop and physical mobile.
6. Rehost media only with documented rights; otherwise link out.

## Sources consulted (2026-10-20)

- `https://registry.npmjs.org/pdfjs-dist/latest`
- `https://registry.npmjs.org/echarts/latest`
- `https://registry.npmjs.org/video.js/latest`
- `https://unpkg.com/pdfjs-dist@6.4.299/build/pdf.min.mjs`
- `https://unpkg.com/pdfjs-dist@6.4.299/build/pdf.worker.min.mjs`
- `https://unpkg.com/echarts@6.1.0/dist/echarts.min.js`
- `https://pypi.org/pypi/docling/json`
- `https://api.github.com/repos/docling-project/docling`

These are published package metadata/file sizes, not a full security audit or
a guarantee of future maintenance.
