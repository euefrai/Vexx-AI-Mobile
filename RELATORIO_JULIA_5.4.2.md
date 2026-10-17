# Relatório Júlia V5.4.2 — Provedores externos REAIS e troca de modelo a qualquer momento

Data: 2026-10-16 · Commits locais (sem push/deploy)

## Pedido

"Faça com que dê para usar provedores externos e que seja real, não só
fictício — e que dê para trocar o modelo que vai responder a qualquer
momento."

## Diagnóstico central (honesto)

O encanamento já existia desde o commit dos provedores (3488648): o app
envia `model` por mensagem; o PC roteia `provedor/modelo` para chamadas
HTTP reais; o relay só transporta. **O que estava "fictício" era a chave:
a `OPENAI_API_KEY` deste PC é RECUSADA pela OpenAI — HTTP 401
`invalid_api_key`** (chave com formato normal: `sk-`, 164 caracteres, sem
espaços/aspas; provavelmente revogada ou de projeto removido). Ou seja: o
seletor mostrava modelos da OpenAI que nunca funcionariam, e o erro exibido
era confuso (falava de "hermes proxy status").

Evidências (sem expor nenhum valor): `tools/ia_smoke.py` (chamada real a
`api.openai.com`) → `codigo=auth`; `/v1/models` → HTTP 401
`code=invalid_api_key`. O Hermes local (425 modelos) segue funcionando.

## Entregas

1. **Erros honestos por provedor** (`providers.py`)
   - 401/403 → "OpenAI recusou a chave (HTTP 401/403). Atualize
     OPENAI_API_KEY no PC e reinicie o agente." (nome do provedor + variável;
     nunca fala de proxy local nem de chave inexistente).
   - Qualquer fragmento de chave que o provedor ecoe é removido (`sk-…` → `***`).
   - Vale para completo, stream e Anthropic.
2. **Seletor não anuncia o que não roda**
   - Chave recusada → grupo "· chave recusada no PC", opções desabilitadas;
     falha de rede na listagem continua caindo na curadoria (não pune).
   - Relay repassa só metadados (`auth_error`, mapa id→provedor) — nada de chaves.
   - Corrigido também grupo/rodapé errado para ids Hermes com barra
     (`poolside/laguna-s-2.1:free` não vira "sem chave").
3. **Fallback que atravessa provedores**
   - Fila `[escolhido, *JULIA_AI_FALLBACKS]`: erro de chave só interrompe se
     o candidato seguinte for do MESMO provedor; se for de outro, tenta.
   - Stream: mesma regra, e nunca troca no meio do texto (deltas já emitidos).
4. **Trocar o modelo a qualquer momento**
   - Botão **Atualizar** no seletor (recarrega catálogo/provedores sem reiniciar o app).
   - Toque em Status → linha **Modelo** abre o seletor direto (menu/intocável no chat).
   - A próxima mensagem usa o modelo novo na MESMA conversa; Regenerar e
     Continuar usam a escolha do momento do toque (já valia; verificado).
   - Rodapé mostra `IA pronta · modelo` com aviso real quando o provedor
     escolhido está sem chave/recusado.
5. **`.env` local agora é lido de verdade** (`env_local.py`)
   - Agente e relay carregam `.env` da raiz na inicialização (setdefault:
     variável de sistema sempre manda; `%USERPROFILE%` expandido; nada logado).
6. **Proxy Hermes configurado propaga** para o caminho multi-provedor.
7. **`tools/ia_smoke.py`** — teste real: `python tools/ia_smoke.py
   openai/gpt-4o-mini` faz 1 chamada + 1 stream e mostra latências/códigos.

## Prova executada

- **Suíte completa: 515 passed, 10 deselected** (era 504; +11 novos em
  `tests/test_providers_switch.py`, e `test_ai.py` do relay atualizado para
  validar o `items`/`auth_error`, sem deixar campo extra vazar).
- **E2E Chrome real** (`tools/3d/qa-ia-providers.cjs` no preview descartável):
  - Seletor: 7 grupos; "OpenAI · chave recusada no PC" com opções desabilitadas.
  - Atualizar: toast "Lista de modelos atualizada" (catálogo recarregado no PC).
  - Status → Modelo: abre o seletor sem sair do chat.
  - Mensagem real com `openai/gpt-4o-mini`: pedido SAIU para a API da OpenAI
    (401 real) e a bolha diz exatamente o motivo — com "Tentar novamente".
  - Mesma conversa, troca para `gemini/gemini-2.0-flash`: a resposta seguinte
    acusa o NOVO provedor. Zero erros de console; capturas em
    `qa-artifacts/ia-providers/` (`picker-honesto.png`, `atalho-modelo.png`,
    `erro-honesto.png`, `troca-na-mesma-conversa.png`, `metrics.json`).

## BLOQUEADO (sem bypass, sem invenção)

- **OpenAI ao vivo até o fim**: impossível enquanto a chave deste PC estiver
  recusada. Para destravar: `setx OPENAI_API_KEY "chave-nova"` (ou `.env`),
  reabrir o agente e rodar `python tools\ia_smoke.py` — o smoke dirá a
  verdade. Depois, no app: escolher `openai/…` e conversar.
- **Gemini/Anthropic/DeepSeek/Groq/Mistral/OpenRouter ao vivo**: sem chaves
  neste PC — mesma receita acima quando houver.
- **SearXNG**: segue sem instância autorizada (como no relatório anterior).

## Como validar no seu PC

1. Atualize a chave: `setx OPENAI_API_KEY "sk-…"` e **feche/reabra o agente**
   (ou crie `.env` na raiz com a chave — agora é lido na inicialização).
2. `python tools\ia_smoke.py` → deve dizer "ok" para `openai/…`.
3. No app: menu → Conexão e memória → **Atualizar** → escolher o modelo →
   conversar. Trocar de modelo no meio da conversa vale para a próxima resposta.

## Arquivos tocados

`providers.py`, `pc_agent.py`, `server.py`, `env_local.py` (novo),
`public/app.js`, `public/index.html`, `public/styles.css`,
`tests/test_providers_switch.py` (novo), `tests/test_ai.py`,
`tools/ia_smoke.py` (novo), `tools/3d/qa-ia-providers.cjs` (novo),
`docs/JULIA_PROVIDERS.md`, `.env.example`, `qa-artifacts/ia-providers/`.
