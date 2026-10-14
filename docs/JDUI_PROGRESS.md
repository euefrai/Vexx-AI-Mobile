# JDUI_PROGRESS — retomada entre sessões

## ETAPA 1 — Auditoria ✅ (2026-10-13)
- `docs/JDUI_AUDIT.md` criado. Baseline: 38 passed (e2e excluído).
- Decisão: `widget-html` mantido só para histórico; modelo usa JDUI.

## ETAPA 2 — Schema + validação ✅
- `jdui.py`: envelope, 10 validadores, limites, `normalizar`.
- `tests/test_jdui.py`: 9 testes (schema, limites, segurança, ui-state).

## ETAPAS 3–5 — Registry + renderers ✅
- `public/jdui.js`: validação espelho, 10 renderers nativos, OPS/calcExpr sem eval,
  dispatcher local/chat, fallback silencioso.
- CSS JDUI em `styles.css`. Smoke Node com paridade (`test_frontend_smoke.py`).

## ETAPA 6 — PresentationEngine ✅
- `pc_agent.JULIAPresentationEngine` + `JDUI_CATALOGO` compacto por intenção.
- `jdui.normalizar` nos caminhos completo e stream; fences fora do contexto.
- System prompt ensina JDUI e proíbe JS do modelo.

## ETAPA 7 — Streaming + persistência ✅
- Fence aberto = placeholder; monta só com novos slots; inválido some.
- IndexedDB `ui_state` (DB v2) + `POST/GET /api/ui-state` + tabela no PC + merge.

## ETAPAS 8–10 — UX/segurança/regressão ✅
- Touch ≥40px, tabelas/diagramas com scroll, reduced-motion herdado.
- Sem eval/innerHTML bruto; auth+CSRF; 48+ testes passando (ver relatório).

## Para retomar
- Ponta solta: `chart` (gráficos) não implementado — usar table/progress.
- Testes G/H (dispositivo real) não executados — só navegador/desktop.
- Se o modelo gerar fence inválido recorrente, ver logs `JDUI descartado`.
