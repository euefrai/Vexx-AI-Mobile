# V5.8 screenshots

All captures are from the real headless Chrome E2E (`tools/chrome_e2e_v58.py`),
using an isolated local stack, temporary SQLite and a temporary Chrome profile.
Production was not opened or modified.

Chrome: `155.0.8059.85`; desktop 1280×900; mobile emulated 390×844.

| File | What it proves | SHA-256 prefix |
|---|---|---|
| `research-workspace-desktop.png` | “Pesquisas” page, saved job list, real objective | `4D75191F62C2126D` |
| `research-workspace-desktop-detail.png` | plan component, progress, status/mode, budget, epistemic limit, exports | `2ED4A409F664C0BA` |
| `research-workspace-desktop-evidence.png` | claim state `SUSTENTADA`, source counts, opened source details, used excerpt | `3E8A35B9CEED1974` |
| `research-workspace-desktop-evidence-media.png` | media gallery with “não é evidência”, metadata fallback, export file cards | `F5A4649256BB023E` |
| `research-workspace-mobile.png` | 390×844 emulated layout, no horizontal overflow, tappable buttons | `95204F46B483BD8C` |

Files are in `qa-artifacts/v58/`. JSON/text evidence:
`qa-artifacts/v58/chrome-e2e.json` and `chrome-e2e.txt`.

## Honest interpretation

- The image fallback “Imagem indisponível” is expected: `example.com` does not
  serve the discovered image. This demonstrates the fallback, not a broken
  production media pipeline.
- The “Conectado” toast is a transient connection indicator; it is not part of
  the research evidence.
- Mobile is Chrome device emulation. No physical phone was tested.
- The job and evidence were persisted locally to exercise rendering; this is a
  UI/contract E2E, not an open-web research quality run.
