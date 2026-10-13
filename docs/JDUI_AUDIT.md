# JDUI — Auditoria real do Júlia Mobile (ETAPA 1)

Data: 2026-10-13. Método: leitura direta de todos os arquivos + suíte de testes.
Nada aqui é presumido: cada item foi verificado no código ou nos testes.

## 1. Estrutura real

```
julia-mobile-v0.2/
├── server.py              # Relay FastAPI (Render). Sem banco. Auth + WS efêmero.
├── pc_agent.py            # Agente do PC. SQLite durável + Hermes + streaming.
├── hermes_bridge.py       # Cliente OpenAI-compatible do Hermes Proxy local.
├── docs_agent.py          # Upload/leitura/resumo/tópicos de documentos.
├── remoto.py              # Tela ao vivo + mouse/teclado (JULIA_REMOTE=1).
├── public/
│   ├── index.html         # Chat fullscreen + drawer lateral.
│   ├── app.js             # ~970 linhas. IndexedDB, SSE, markdown, widgets.
│   ├── styles.css         # Dark-first, roxo neon.
│   └── sw.js              # PWA, shell cacheado (network-first + fallback).
├── tests/                 # test_core, test_ai, test_extended, test_remoto,
│                          # test_docs_memoria, test_interactive, test_frontend_smoke.
└── docs/                  # REMOTO_ANYDESK.md (+ este arquivo).
```

## 2. Frontend (real)

- Chat fullscreen + drawer (sessões, documentos, PC, atividades, ajustes). Sem framework.
- IndexedDB `julia-mobile-cache-v2`: stores `messages` e `sessions`. Migração da v1 OK.
- Streaming SSE com `requestAnimationFrame` (throttle) + barra de geração + POST fallback.
- Renderer markdown próprio, XSS-safe (escapa antes de inserir tags): code blocks com
  copiar, tabelas, listas, quotes, links segurados (`http/https` + `noopener`),
  imagens com fallback, referências em caixa própria.
- `widget-html` → iframe `sandbox="allow-scripts"` (origem opaca) + toggle de código.
- ```` ```svg ```` → SVG inline **sanitizado** (sem script/eventos/foreignObject).
- Bugs reais encontrados e corrigidos nesta semana: `dados='{}'` (stream nunca
  entregava), `sessionsCache` não declarado, autolink corrompendo `<img src>`.

## 3. Backend relay (real, testado)

- Auth: Argon2id + cookie HttpOnly + CSRF por sessão + checagem de Origin.
- WS `/api/agent/ws` com token Bearer; RPC efêmero (`pending`/`streams`).
- Endpoints: sync, messages, conversations, ai, ai/stream (SSE), ai/models,
  screen, input, docs (upload/list/resumo/topicos), memories (list/forget).
- CSP: `img-src 'self' data: https:` (permite imagens do chat).
- Limites: `max_size` 25MB no agente (uploads até 15MB); timeouts 12–180s.

## 4. Agente Python (real, testado)

- SQLite WAL em `JULIA_SQLITE_PATH`: `messages`, `ai_requests` (máquina de estados
  queued→processing→completed/failed/cancelled, idempotente por mensagem),
  `memories`, `memory_facts`, `documents`, `doc_chunks`. **Ausente: `ui_state`.**
- Hermes via `hermes_bridge` (loopback-only, anti-SSRF). Modelo padrão
  `poolside/laguna-s-2.1:free`. Inferência real validada; sem tool calling.
- Montagem de prompt: contexto local (12 msgs) + memórias por relevância +
  trechos de documentos + pesquisa web (DDG html→lite, cache 10min, data atual) +
  diretivas por intenção (pesquisa/imagem/widget).
- Aprendizado em 2º plano (thread, nunca bloqueia): extração de fatos via LLM +
  consolidação acima de 60 fatos. Comandos diretos de memória sem LLM.
- Documentos: PDF (pypdf→pypdfium2), DOCX, XLSX, CSV/TSV, HTML, TXT/MD. Resumo
  map-reduce amostrado (≤6 trechos). Q&A por sobreposição de palavras.

## 5. Mensagens e streaming (real)

- Celular grava em IndexedDB → `POST /api/sync` (só `role=user` pendentes) →
  `INSERT OR IGNORE` no SQLite → ACK → marca `synced`.
- IA: `GET /api/ai/stream?message_id&conversation_id&model&memory` → deltas
  `ai_delta` → `ai_done`/`ai_cancelled`/`ai_error`. Fechar cancela (parcial salva).
- Idempotência fim a fim verificada em teste E2E com processos reais.

## 6. Hermes / Laguna S 2.1 Free (real, com limites)

- Integração funcional via proxy local; **modelo free é pequeno e desobediente**:
  ignora instruções genéricas (caso calculadora→Python), inventa URLs, diz que
  "mostrou imagem" sem markdown. Por isso existem: diretivas impositivas por
  turno, `anexar_fontes`, fallback de imagem, retry de imagem.
- Sem saída estruturada nativa confiável → JDUI precisa de **normalização com
  fallback para Markdown** (nunca travar o chat).

## 7. Testes (executados)

- `pytest tests/ -k "not e2e"`: **38 passed** (2026-10-13).
- E2E com processos reais existe (`test_e2e_ai_completo_com_processos_reais`),
  porém lento; excluído da rotina local.
- `test_frontend_smoke.py` executa o `renderMarkdown` real no Node (cobre o que
  `node --check` não cobre).

## 8. Simulado / ausente (não declarar como pronto)

- PIN offline, criptografia do IndexedDB, fallback de IA em nuvem, WebRTC,
  OCR de PDF escaneado, embeddings semânticos, PPT/ODT/EPUB.
- `ui_state` (estado de interfaces) ainda não existe em nenhum lado.

## 9. Decisão arquitetural JDUI vs widget-html

- O `widget-html` (JS do modelo em iframe sandbox) **viola o §4 do spec JDUI**
  ("IA NÃO deve produzir JavaScript executável"). Decisão: o renderer continua
  existindo para não quebrar o histórico já armazenado, mas o modelo **não será
  mais instruído a usá-lo** — o caminho ensinado passa a ser o declarativo JDUI.
- SVG sanitizado continua (não é JS executável após sanitização).
- Componentes reutilizáveis existentes: codeblock+copiar, tabelas, refs,
  imagens com fallback, drawer, toast, barra de geração, retry.

## 10. Riscos mapeados para o JDUI

1. Modelo free gera JSON inválido → normalizador tolerante + fallback Markdown.
2. Blocos gigantes → limites de tamanho/profundidade/quantidade por mensagem.
3. Streaming parcial com fence aberto → renderizar só blocos fechados/validados.
4. Estado offline → IndexedDB `ui_state` por (message_id, índice); sync
   idempotente com SQLite quando online (sem reenviar histórico).
5. Ações externas → só as implementadas (chat-link, doc-retry); resto é local.
