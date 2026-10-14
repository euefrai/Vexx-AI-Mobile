# RELATÓRIO JDUI MOBILE 1.0 — fajulto Dynamic UI Engine

Data: 2026-10-13. Regras respeitadas: sem push, sem deploy, sem tocar em
Brave/Fajulto/VERY/Hermes, sem Supabase/Firebase, sem quebrar login/SQLite/
IndexedDB/sync. E2E real excluído da rotina (lento) e declarado abaixo.

## 1. Arquivos criados
- `jdui.py` — schema, validadores, normalização (backend).
- `public/jdui.js` — registry, renderers, ações, OPS (frontend).
- `tests/test_jdui.py` (9), `tests/test_interactive.py` (3, +2 steering),
  `tests/test_frontend_smoke.py` (+1 paridade JDUI).
- `docs/JDUI_AUDIT.md`, `docs/fajulto_DYNAMIC_UI_ENGINE.md`,
  `docs/fajulto_DYNAMIC_UI_EXAMPLES.md`, `docs/JDUI_PROGRESS.md`.

## 2. Arquivos modificados
- `pc_agent.py` — PresentationEngine, catálogo, normalizar (2 caminhos),
  fences fora do contexto, tabela `ui_state`, handlers WS, system prompt JDUI.
- `server.py` — `POST/GET /api/ui-state` (validação, tetos, auth+CSRF).
- `public/app.js` — extração de fences, slots, mount, `ui_state` (IDB v2),
  preload, sync com debounce, streaming com remontagem mínima.
- `public/index.html` — `<script jdui.js>`. `public/styles.css` — design JDUI.
- `public/sw.js` — v0.6.0 + `jdui.js` no shell offline.

## 3–4. Componentes e ações
| Item | Estado |
|---|---|
| quiz (seleção, feedback, progresso, nav, resultado, refazer, explicar erros) | FUNCIONAL |
| checklist (progresso, persistência) | FUNCIONAL |
| calculator basic/imc/porcentagem/juros (sem eval) | FUNCIONAL |
| cards + ação Detalhar (chat) | FUNCIONAL |
| diagram v/h expansível | FUNCIONAL |
| table com ordenação local | FUNCIONAL |
| form com calc registrado | FUNCIONAL |
| progress, tabs, accordion | FUNCIONAL |
| chart (gráficos) | AUSENTE (usar table/progress) |
| Ações locais sem IA | FUNCIONAL |
| Ações de chat autenticadas | FUNCIONAL |
| Ações externas arbitrárias | AUSENTE (só links https e retry existentes) |

## 5–9. Integrações e qualidades
- Hermes: steering por intenção + normalização com fallback; modelo free
  desobedece às vezes (limitação externa, não do motor). PARCIAL (por natureza).
- FastAPI: endpoints com validação/tetos/auth. FUNCIONAL.
- Streaming: placeholder em fence aberto, monta com novos slots, preserva texto,
  sem duplicar. FUNCIONAL.
- IndexedDB `ui_state` + restore por conversa. FUNCIONAL.
- Sync SQLite idempotente + merge newer-wins. FUNCIONAL.
- UX: dark-first herdado, touch ≥40px, scroll-x, reduced-motion. FUNCIONAL*.
- Segurança: sem eval/innerHTML bruto/JS do modelo; URLs e tamanhos limitados;
  CSRF/auth. FUNCIONAL (revisão por código + testes; sem pentest).
- Performance: sem frameworks, remontagem mínima, debounce 4s, tetos.
  FUNCIONAL (*sem medição em aparelho real).

## 13–15. Testes
- Executados: `pytest -k "not e2e"` → **48 passed**; `node --check` app+jdui OK.
- Novos: schema (7+2), steering/normalização, ui-state relay+agente, smoke Node
  (markdown, widgets, SVG, XSS, paridade JDUI).
- Reprovados: 0. Regressão: todos os 38 anteriores continuam passando.
- Testes A–F (navegador manual), G (reabrir app), H (PC offline): **NÃO
  executados aqui** — sem ambiente de navegador neste ciclo; *não declarar
  como feitos*. Guia manual: pedir quiz/calculadora/checklist/diagrama/
  comparação + "o que é variável" (texto puro), fechar/reabrir, desligar PC.

## 16. Bugs corrigidos no ciclo
- Profundidade máxima 4→8 (quiz legítimo era rejeitado); teto de blocos agora
  trunca em vez de rejeitar tudo; `widget` legado redirecionado ao JDUI.

## 17. Limitações
1. Modelo free pode ignorar o fence → cai em Markdown (by design).
2. Sem charts; sem OCR; sem embeddings; sem testes em aparelho físico.
3. `widget-html` antigo segue no histórico (sandbox); modelo não o usa mais.
4. Estado de abas internas aninhadas (`jdui` dentro de `tabs`) não suportado.

## 18. Próximos passos
1. Testes A–H manuais no celular (roteiro na §13–15 acima).
2. Telemetria de `erros_jdui` para ajustar o catálogo ao modelo free.
3. `chart` via SVG gerado no frontend a partir de dados (sem JS do modelo).
4. `since` incremental no `/api/ui-state` quando houver volume.
