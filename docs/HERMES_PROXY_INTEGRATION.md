# Integração Hermes Proxy (Opção A — inferência)

Respostas reais do Hermes Subscription Proxy local no chat mobile, com
streaming progressivo, persistência idempotente e offline-first preservado.

## Arquitetura

```text
CELULAR → HTTPS/WSS → RENDER (sem banco) → WSS autenticado → PC_AGENT
→ HERMES_BRIDGE → http://127.0.0.1:8645/v1 → MODELO → SQLite → CELULAR
```

- `hermes_bridge.py`: cliente OpenAI-compatible (stdlib). `listar_modelos`,
  `chat_complete`, `chat_stream` (SSE com `AcumuladorSSE`), erros mapeados
  (auth, modelo-nao-encontrado, rate_limit, provedor, timeout, vazia).
  URL restrita a loopback (anti-SSRF); bearer arbitrário local — o proxy troca
  pela credencial real. Nenhum token do Render vai ao proxy.
- `pc_agent.py`: tabela `ai_requests` (PK = id da mensagem do usuário; estados
  queued/processing/completed/failed/cancelled) + respostas `assistant` na
  tabela `messages` (coluna `model`, migração idempotente). Tipos WS:
  `ai` (completa), `ai_stream` (worker thread + lock de envio),
  `ai_cancel`, `ai_models`. Contexto = últimas N mensagens da conversa
  (`FAJULTO_AI_CONTEXT`, padrão 20) + `FAJULTO_SYSTEM_PROMPT`.
- `server.py`: `POST /api/ai` (completa, idempotente), `GET /api/ai/stream`
  (SSE: delta/done/cancelled/error; fechar cancela), `GET /api/ai/models`
  (lista real para o seletor). Relay sem armazenamento.
- App: placeholder "gerando" + deltas ao vivo + interromper + retry (toque na
  resposta falha); `generating` preso vira `failed` ao reabrir; seletor de
  modelo (localStorage) alimentado pelo proxy.

## Configuração (só no PC)

```powershell
$env:HERMES_PROXY_URL="http://127.0.0.1:8645/v1"
$env:FAJULTO_AI_MODEL="poolside/laguna-s-2.1:free"
$env:FAJULTO_SYSTEM_PROMPT="Você é a Júlia, ..."   # opcional
$env:FAJULTO_AI_CONTEXT="20"                        # 1–50
$env:FAJULTO_AI_MAX_TOKENS="2000"                   # 1–8000
python pc_agent.py
```

Antes: `hermes proxy start`. Conferir: `GET /v1/models` (422 modelos em
2026-10-11, incluindo `poolside/laguna-s-2.1:free`).

## Offline e idempotência

- PC offline: IndexedDB guarda; nada se perde.
- Hermes offline: mensagem persistida, erro `indisponivel`, botão tentar de novo.
- Retry usa o mesmo id: `completed` devolve a resposta guardada sem rechamar o
  modelo; `failed`/`cancelled` permitem nova tentativa; `processing` responde
  `busy`. Resposta concluída antes da queda é recuperada do SQLite.
- Render reiniciado: agente reconecta; frontend reconstrói do IndexedDB.

## Diagnóstico

- `falha 401/403 do proxy`: `hermes proxy status` (bearer do Nous expirado?).
- `modelo-nao-encontrado (404)`: proxy rotacionou o catálogo — abra o seletor e
  troque (`GET /api/ai/models`).
- `429`: quota do provedor — aguarde; bridge já evita martelar.
- Stream trava: verifique `/api/health` do relay e o log do agente.

## Testes

`pytest -q tests` (18): unidade de SSE/SSRF/erros, idempotência sem rechamada,
auth/validação/roteamento no relay e E2E com processos reais (relay + agente +
Hermes falso). Proxy real validado manualmente (modelos + `OK_FAJULTO`/`FAJULTO_OK`
via `laguna-s-2.1:free`, SSE incluso) para não gastar quota na suíte.

## Limitações da Opção A

Só inferência: sem execução de terminal, arquivos, mouse, nem memória/skills do
Hermes Agent. Contexto é o histórico SQLite da conversa. Sem PWA fechada não há
processamento em segundo plano. Estrutura pronta para futuro
`HermesAgentAPIAdapter` (desativado; ferramentas exigiriam camada própria de
autorização).
