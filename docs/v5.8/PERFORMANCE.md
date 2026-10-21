# Performance and resources — V5.8

## Local measurements

Command: `python tools/bench_v58.py`
Raw: `qa-artifacts/v58/performance.json`.

Environment: Windows, Python 3.14.4, process RSS 22.06 MB after imports.
These are pure-module measurements, not network or browser-render latency.

| Operation | Input | Mean | Peak Python allocations | Output |
|---|---|---:|---:|---:|
| Build validated JDUI view | 24 steps, 10 claims, 12 media, 8 hypotheses | **7.35 ms** | 0.11 MB | 6 blocks |
| Export Markdown | 200 evidence, 50 hypotheses | **21.70 ms** | 0.48 MB | 64,486 B |
| Export CSV | same | **33.81 ms** | 0.46 MB | 62,071 B |
| Export JSON | same | **9.01 ms** | 0.43 MB | 112,699 B |

Limits measured by the code: export max **2,000,000 bytes**, max **200 items**,
JDUI view **6 blocks** (validator ceiling is 8; the view intentionally stays at
6). Heavy libraries imported: **none**.

Interpretation: the new features are cheap relative to network acquisition and
do not add a heavy multimedia runtime to the Render Free path. This does not
prove production behavior under concurrency.

## Configurable bounds

| Bound | Where | Default / range |
|---|---|---|
| searches/pages/time | per job mode | 2/3/30 s up to 12/20/300 s |
| subquestions/depth | per job mode | 1–6, depth 1–3 |
| media discovered | per job mode | 8–20; env max 0–40 |
| replans | per job mode | 1–2; env 0–3 |
| page bytes | per page | 2 MB; env 65,536–10,000,000 |
| concurrency ceiling | env | 1–8; V5.8 executes sequentially |
| JDUI blocks | validator | max 8; view 6 |
| plan steps | JDUI | 1–24 |
| claims/sources | JDUI | 10 claims, 12 sources each |
| media items | JDUI | 1–12 |
| file cards | JDUI | 1–8 |
| export items/bytes | renderer | 200 / 2 MB |
| browser media | renderer | lazy `loading="lazy"`; no rehosting |

## Library evaluation (required)

Versions/licenses checked on **2026-10-20** against the npm registry, unpkg and
the Docling GitHub repository. Byte sizes are raw published files, not a
tree-shaken application bundle.

| Library | Version | License | Maintenance | Published bytes | CSP / runtime | V5.8 decision |
|---|---|---|---|---|---|---|
| PDF.js (`pdfjs-dist`) | 6.4.299 | Apache-2.0 | active | package unpacked **34.9 MB**; main **458,904 B**; worker **1,264,342 B** | requires `worker-src 'self' blob:`; configure `isEvalSupported=false`; test WASM paths | **not adopted**; existing textual PDF extraction retained |
| Apache ECharts | 6.1.0 | Apache-2.0 | active | package unpacked **60.3 MB**; full dist **1,121,883 B** | no worker; verify CSP build; large DOM/canvas memory | **not adopted**; existing deterministic JDUI charts retained |
| Video.js | 10.1.0 | Apache-2.0 | active | npm package **48,496 B** unpacked, but v10 is modular ESM and pulls `@videojs/*`; not a single-file bundle | media-src/CSP; player memory; format support; remote URLs only | **not adopted**; media is discovery/link-only |
| Docling | 2.141.0 | MIT | active (GitHub pushed 2026-10-20) | Python package with `docling-slim` extras and model/OCR dependencies; models can add hundreds of MB to >1 GB | server-side; CPU/RAM heavy; not for Render Free | **not adopted**; no OCR/layout pipeline claimed |

Sources:

- `https://registry.npmjs.org/pdfjs-dist/latest`
- `https://registry.npmjs.org/echarts/latest`
- `https://registry.npmjs.org/video.js/latest`
- `https://unpkg.com/pdfjs-dist@6.4.299/build/pdf.min.mjs`
- `https://unpkg.com/pdfjs-dist@6.4.299/build/pdf.worker.min.mjs`
- `https://unpkg.com/echarts@6.1.0/dist/echarts.min.js`
- `https://pypi.org/pypi/docling/json`
- `https://api.github.com/repos/docling-project/docling`

All four licenses are permissive; none is copyleft. Adoption is rejected for
V5.8 on **weight, CSP surface and lack of a real analyzed-media/PDF use case**,
not on licensing.

## If adopted later

- Lazy-load only on an explicit viewer/action; never on initial chat load.
- Keep heavy libraries out of the Render Free backend.
- Add SRI/integrity and a CSP allowlist for scripts/workers/media.
- Measure real PDF/chart/video memory on the actual device before promising a
  capability.
- Obtain rights before rehosting media; V5.8 does not rehost.
