# RELATÓRIO JÚLIA 4.5 — Deep Research Agents & Live Research

## 1. Auditoria

HEAD `d0205df` (V4.4), tree limpo; baseline **174 passed, 0 failed**.
V4.0–V4.4 preservadas; sem push/deploy; sem bancos/serviços pagos.

## 2. O que foi entregue (por fase)

- FASE 2/13: `research_agents.py` — jobs, checkpoints, orçamentos por modo
  (rapida/pro/profunda/investigativa), concorrência (1/dono, teto 2),
  cancelamento, retomada idempotente.
- FASE 3: provedores DDG (preservado) + SearXNG configurável
  (`JULIA_SEARXNG_URL`; sem URL = indisponível declarado) + fallback com
  erros rastreados. SearXNG sem instância aqui: PARCIAL (interface + testes,
  sem validação ao vivo).
- FASE 4/5: analista (relevância), evidências com 6 status, verificador
  determinístico (5 estados), contradições.
- FASE 6: ciclo + replan (1 rodada, sem loop — guardado por versão e teto).
- FASE 7: sintetizador extrativo honesto + auditor de citações. Redação e
  verificação por LLM: **BLOQUEADAS** (provedor Hermes segue sem inferência).
- FASE 8/12: transporte real — jobs em background no PC, endpoints
  start/status/cancel/jobs/evidence (owner do servidor, PC definitivo).
- FASE 9/11: painel live Minimal Premium (barra + detalhes + cancelar +
  fontes com links reais, polling com dedupe) + comandos de memória
  (`resultado`, `fontes`, `continue`, `pesquisa profunda: X` — funcionam
  **sem LLM**) + fence de evidências (cards).
- FASE 10: checkpoints = registros (retenção testada).
- FASE 14: Quality Lab com métricas + 15 casos (LLM-real = skip BLOQUEADO).

## 3. Arquivos

- Criados: `research_agents.py`, `tests/test_research_agents.py` (16),
  `tests/test_research_quality.py` (8+1 skip), 6 docs, este relatório.
- Modificados: `pc_agent.py` (jobs bg, intents, transforms, SearXNG env),
  `server.py` (5 rotas), `public/{index.html,app.js,styles.css}` (painel),
  `research.py` (minor), testes de fiação.

## 4. Testes

Suíte final: **198 passed, 0 failed, 1 skipped** (skip = inferência LLM
real, BLOQUEADA no provedor). Reais vs simulados separados; destaques:
circuit breaker, replan sem loop, retomada sem duplicar, isolamento,
injection como dado, ocupação 409, cancelamento. Nenhum teste eliminado;
nenhuma falha mascarada.

## 5. Riscos e pendências honestas

- Sem LLM: síntese é extrativa e verificação é léxica (declarado ao usuário
  no próprio texto). Fluxo agêntico completo com LLM: BLOQUEADO.
- `agent_started/agent_completed/answer_delta` de pesquisa: não emitidos
  (sem agentes LLM) — documentado, não fingido.
- Polling 2 s (não push); status "pesquisando…" narrativo ausente no stream.
- TOCTOU DNS residual; SearXNG sem validação ao vivo; lab sem aparelho físico.
