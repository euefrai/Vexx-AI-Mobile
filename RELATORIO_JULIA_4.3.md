# RELATÓRIO JÚLIA 4.3 — Advanced JDUI (+ estabilização V4.2.1)

## 1. Auditoria e baseline

- HEAD `199ac8a` (V4.2 commitada), working tree limpo no início.
- Baseline V4.2 confirmado: 146 passed + 1 e2e flaky (não 146/1 cego — ver §2).

## 2. V4.2.1 — Estabilização

| Item | Status | Evidência |
|---|---|---|
| E2E Hermes | FUNCIONAL | Causa: sleep fixo + DEVNULL (boot flaky), não bug. Polling readiness, logs em falha, `e2e_real` + skip sem uvicorn. 10 s, determinístico |
| Hermes real | BLOQUEADA (provedor) | 15/10: `/v1/models` OK; inferência falha (vazia / slug rejeitado). Docstring `test_ai.py` atualizada. Quota: zero |
| Aula canônica | FUNCIONAL | `lessons`/`lesson_sections` + schema + CRUD + seção + síntese LLM validada + renderer + intents (completa e stream) |
| Fila offline | FUNCIONAL | Outbox IndexedDB, `queueLearn`, sync com descarte 404/409, finish online-only, idempotência servidor testada |

Regra explícita de prova offline (§4): sem cronômetro no produto; respostas
offline valem pelo estado da tentativa **no recebimento**; pontuação do
cliente nunca é confiável (servidor corrige; `corrigida_em` = hora do PC).

## 3. V4.3 — Componentes (todos FUNCIONAL, testes py + node)

| Componente | Validador | Renderer | Interatividade |
|---|---|---|---|
| `chart` line/bar/pie/area/scatter | limites 1–6 séries, 1–24 pts, finitude, pie=1 série, labels casados | SVG puro responsivo, `<title>`, legenda, fonte, vazio útil | — (leitura; dados via API ou props) |
| `dashboard` | 1–8 métricas + chart ≤3 séries | cards + `R.chart` delegada | — |
| `compare` | 2 colunas, 1–12 linhas, melhor a/b/= | tabela lado a lado + destaque + aria | — |
| `lesson` | id persistido | seções expansíveis + concluir + "explicar mais" | server-backed |
| `conversor` | kind novo | selects + `OPS.conversao` (tabela fixa) | persiste estado |
| tabela filtro | — | input search local | persiste `st.filtro` |
| diagrama + | icon/group passthrough | zoom ±, grupos, seleção persistida | `st.sel`/`st.zoom` |
| `update_of` | id + allowlist (exam/quiz/studyprogress vetados) | remonta bolha-alvo com ctx original (estado preservado) | — |

Gráficos factuais: `GET /api/learn/history` → `sintetizar_grafico_evolucao`
(determinístico; "evolução dos meus simulados" testado com nota real 100.0).
Modelo pode explicar, nunca numerar.

## 4. Arquivos

- Modificados: `learning.py` (aulas, histórico), `pc_agent.py` (síntese aula/
  gráfico, intents, PresentationEngine, catálogo), `server.py` (5 endpoints:
  lessons ×4, history), `jdui.py` (7 validadores + update), `public/jdui.js`
  (renders + OPS + update), `public/app.js` (outbox, `queueLearn`, update_of),
  `public/styles.css` (V4.3), `requirements.txt` (`tzdata`),
  `tests/test_ai.py` (e2e robusto), `tests/test_{learning,learn_api,jdui,
  frontend_smoke}.py` (cobertura nova).
- Criados: `tests/test_jdui_v43.py`, `docs/JULIA_LEARNING_{ENGINE,SCHEMA,
  PROGRESS,TESTS}.md` (V4.2), `RELATORIO_JULIA_4.2.md`, este relatório.

## 5. Testes: 157 passed, 0 failed, 0 ignorados (suite padrão)

Inclui e2e com processos reais. Reprovados: nenhum. Segurança §16/17:
NaN/Inf/1e13/pie-dupla/scatter ímpar/labels divergentes/teto 24/oversize/
profundidade/URLs `javascript:`/XSS em título/desconhecido/`calcExpr` sem
eval/`update_of` malicioso e em exam/quiz/studyprogress — todos rejeitados
ou neutralizados com fallback. Isolamento multiusuário e regressões
preservados (suíte V4.0–V4.2 intacta, nenhum teste eliminado).

## 6. Limitações, riscos e próximos passos

- Hermes inferência BLOQUEADA no provedor (texto/SSE reais indisponíveis hoje).
- Aparelho físico (320–430 px, teclado, foco, acessibilidade): PARCIAL (CSS
  responsivo + aria; sem lab).
- `update_of` em streaming aplica no render final; histórico de patches: só
  estado atual (sem undo entre mensagens).
- Filtros/seletores de dashboard: AUSENTE (métricas + gráfico entregues).
- Scattering avançado e área empilhada: AUSENTE (fora de necessidade real).
- Riscos: modelo pode gerar `chart` com números inventados quando o usuário
  fornece dados informais — mitigado pelo catálogo ("só com números dados"),
  mas sem verificação automática; `update_of` confia no id citado (só afeta
  a própria conversa renderizada).
- Desempenho: SVG inline < 24 pts/série; fences ≤ 24 KB; sem deps novas no app.
