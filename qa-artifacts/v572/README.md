# Evidências V5.7.2 — linhagem dos artefatos

Todos os artefatos são de execuções isoladas (portas livres, SQLite temporário);
nada foi executado contra produção. Artefatos de falha são mantidos como
histórico honesto — a linha “válido para aceitação” indica o que o relatório
usa como evidência final.

## Chrome E2E (`chrome/`)

| Artefato | Resultado | Observação |
|---|---|---|
| `chrome-e2e-20261019-150126.json` | falha no login | Harness usava hash scrypt; o login legacy exige **argon2**. Defeito do harness, não do app. |
| `chrome-e2e-20261019-150205.json` | chat 8,07 s; falha no `/api/sync` (403) | Faltava `X-CSRF-Token`; defeito do harness. |
| `chrome-e2e-20261019-150234.json` | **ok**, chat 10,59 s | Execução intermediária válida (card/mobile). |
| `chrome-e2e-20261019-150401.json` | **ok**, chat 4,04 s | **Evidência final** citada no relatório; screenshots `desktop-chat.png`, `desktop-card.png`, `mobile-card.png`. |

Os screenshots foram regravados na execução final (`150401`).

## Smoke integrado (`smoke-integrado-*.json`)

| Artefato | Resultado | Observação |
|---|---|---|
| `smoke-integrado-20261019-150728.json` | 6/7 | Harness não persistia a mensagem do usuário no histórico; o cenário de comparação recebeu só o system prompt. **Inválido para aceitação** (defeito do harness, corrigido). |
| `smoke-integrado-20261019-151919.json` | **7/7** | Primeira execução válida (comparação em 2 turnos com docs.python.org). |
| `smoke-integrado-20261019-152738.json` | 6/7 | Falha **apenas** no cenário de pesquisa por **429 externo** do Hermes (erro honesto registrado). |
| `smoke-integrado-20261019-152951.json` | **7/7** | **Evidência final** citada no relatório (1 oferta R$ 134,29; 3 fontes; doc oficial; continuação ordenada; falha honesta). |

## Hermes

- `grounded-fotossintese.json` — resposta fundamentada real (3 fontes,
  27,15 s, modelo free).

## Smoke externo

- `../v57/smoke-externo-v57f-2026-10-19.json` — 2/2 ofertas confirmadas com
  preço numérico (R$ 28,60 / R$ 68,32), 3/3 fontes, Wikipédia aberta, Magalu
  bloqueada honestamente.
