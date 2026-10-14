# RELATÓRIO — Hermes Proxy Integration 1.0 (Opção A)

Data: 2026-10-11. Baseline reexecutado antes: **9/9**. Final: **18/18** + JS válido.

## Arquivos criados / modificados

- Criado `hermes_bridge.py` (bridge OpenAI-compatible, SSE, anti-SSRF loopback).
- Modificado `pc_agent.py` (migração `model`, tabela `ai_requests`, tipos
  `ai`/`ai_stream`/`ai_cancel`/`ai_models`, contexto, worker thread).
- Modificado `server.py` (`POST /api/ai`, `GET /api/ai/stream` SSE,
  `GET /api/ai/models`, roteamento de deltas, `fail_pending` em streams).
- Modificados `public/app.js`/`index.html`/`styles.css` (streaming, seletor de
  modelo, status IA/Hermes, retry, layout com scroll interno do chat).
- Criado `tests/test_ai.py` (9 testes). Atualizados `.env.example`, `README.md`,
  `docs/HERMES_PROXY_INTEGRATION.md`. Studio: bloco Hermes no status + linha na UI.

## Endpoints e modelos

Proxy real: `http://127.0.0.1:8645/v1` — `GET /v1/models` (422 ids),
`POST /v1/chat/completions` (completo + SSE). Modelo padrão e validado:
`poolside/laguna-s-2.1:free`.

## Resultados reais (não simulados)

- Inferência real: `OK_fajulto` e `fajulto_OK` via laguna-s-2.1:free; SSE real
  (chunks `choices[].delta.content`, `[DONE]`).
- Cadeia completa real (relay + agente + Hermes): sync → models(422) →
  resposta `fajulto_OK` → SQLite (`assistant` + `model`) → `ai_requests=completed`.
- E2E em suíte com processos reais e Hermes falso: non-stream idempotente (sem
  2ª chamada), stream com 2 deltas + done, SQLite íntegro.
- Bugs corrigidos: duplo `/v1` no bridge; roteamento que engolia `ai_done` sem
  stream (hang); 3 asserts de teste (decode UTF-8, HTTPError, uptime simulado).

## Testes: 18 aprovados, 0 reprovados, 0 ignorados

Itens da especificação cobertos: modelos real/inválido, proxy on/off,
inferência com/sem streaming, SSE fragmentado, resposta vazia, 401/403/429/500
(via falso; 404 real contra o proxy na investigação), cancelamento, duplicada,
reconexão (herdada e revalidada), persistência, recuperação, offline, sync,
XSS (texto literal), auth do agente, segredos (varredura: nenhum em log/resposta),
testes anteriores preservados (9/9 intactos).

## Classificação

- FUNCIONAL: bridge, modelos, resposta completa, streaming SSE, cancelamento,
  idempotência, contexto, offline-first, seletor de modelo, layout do chat,
  visibilidade Hermes no Studio.
- PARCIAL: cancelamento (cooperativo; proxy sem endpoint de cancel — parcial
  preservada, sem reenvio); System Prompt via env (sem UI).
- AUSENTE (fora da Opção A, por regra): execução terminal/arquivos/mouse,
  memória/skills do Agent, `HermesAgentAPIAdapter` (estrutura pronta, desativado).
- BLOQUEADA: AnyDesk (tela ao vivo + controle) — próxima fase; processamento com
  PWA fechada (limite de plataforma); deploy Render (sem autorização).

## Riscos e pendências

Bearer do Nous expira (visto `hermes proxy status`): 401/403 exige `hermes`
relogar — erro é acionável na UI. Quota do provedor: 429 com retry honesto.
Próximo: fase AnyDesk, PIN/criptografia local, deploy Render (sem push feito).
