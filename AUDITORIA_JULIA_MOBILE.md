# AUDITORIA — Júlia Mobile v0.2 (offline-first, SQLite no PC)

Data: 2026-10-11. Método: leitura integral dos arquivos + execução real de testes
(pytest, E2E com uvicorn + `pc_agent.py` de verdade, checagens de segurança e SQLite).
Nenhum deploy no Render foi executado (sem credenciais/ambiente) — tudo que depende
de deploy real está marcado como não validado.

## Estrutura e pontos de entrada

| Componente | Arquivo | Função |
|---|---|---|
| Relay/backend | `server.py` | FastAPI: login, sessão, CSRF, relay WebSocket efêmero, estáticos |
| Agente do PC | `pc_agent.py` | Cliente WSS de saída + SQLite durável (WAL) |
| Frontend/PWA | `public/app.js`, `index.html`, `styles.css`, `sw.js`, `manifest.webmanifest` | Chat offline-first, IndexedDB, polling de sync |
| Deploy | `render.yaml`, `requirements.txt` | Web Service Python, `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers` |
| Testes | `tests/test_core.py`, `tests/test_extended.py` | 9 testes (5 originais + 4 novos) |

## Classificação por funcionalidade

- **FUNCIONAL** — login/logout com Argon2id + cookie HttpOnly/SameSite=Strict + CSRF
  (testes: login válido/inválido, logout sem CSRF → 403, origem errada → 403).
- **FUNCIONAL** — escrita local primeiro no IndexedDB, status `pending` → `synced`
  somente após ACK do SQLite (código confere `confirmed_ids`; E2E real confirmou).
- **FUNCIONAL** — idempotência por ID (`INSERT OR IGNORE`; retry e sync concorrente
  duplicado não duplicam; validado em teste real e E2E com processo verdadeiro).
- **FUNCIONAL** — PC offline → `503`, celular mantém mensagens (E2E real após matar o
  agente; teste de reload/persistência do IndexedDB é comportamental do navegador e
  foi validado por inspeção de código: `storeMessages` com transação + `renderMessages`
  na inicialização; **não** executado em navegador real — sem Playwright aqui).
- **FUNCIONAL** — SQLite Windows: criação automática, índice `(origin, created_at)`,
  WAL, `busy_timeout=5000`, transações, filtro por `origin='mobile'`, persistência
  após reopen (testes reais em arquivo temporário).
- **PARCIAL** — estados de mensagem: só `pending`/`synced`. Não há `sending`/`failed`
  distintos; falha = permanece `pending` e retenta no próximo poll (12 s). Suficiente
  e honesto, mas fora do ideal de 4 estados da especificação.
- **PARCIAL** — retentativas: polling fixo de 12 s + `visibilitychange`/`online`, sem
  backoff exponencial. Aceitável para v0.2; backoff fica como melhoria futura.
- **PARCIAL** — UX/responsividade: breakpoints 360 px/650 px, `prefers-reduced-motion`,
  `focus-visible`, alvos de toque adequados por inspeção; **não testado em dispositivos
  reais nem com teclado virtual aberto**.
- **SIMULADA (declarada)** — controle remoto: mock estático com aviso explícito na UI
  ("VISUALIZAÇÃO DE EXEMPLO", "A imagem é fictícia"). Nenhum WebRTC/mouse/teclado.
- **AUSENTE** — resposta da IA: mensagens são armazenadas/sincronizadas, sem geração de
  resposta. README declara isso abertamente.
- **AUSENTE** — integração com a extensão Júlia: nenhum endpoint/contrato existe;
  `fajulto_SQLITE_PATH` é banco próprio do Mobile, não o da extensão.
- **BLOQUEADA** — deploy real no Render (sem acesso): `render.yaml` e config
  (host/porta, HTTPS/WSS, sem persistência) validados só por inspeção + equivalência local.
- **BLOQUEADA** — PWA com navegador totalmente fechado: nenhuma sincronização em
  segundo plano é prometida (limitação real de PWA, documentada no README).

## Segurança (verificado por execução)

- Hash Argon2id, `compare_digest` em usuário e token do agente. OK.
- Sessão stateless assinada (12 h); **sem revogação server-side** (trocar
  `fajulto_SESSION_SECRET` invalida tudo) — limitação documentada.
- Rate limit de login: 5 tentativas/5 min por IP → 429 (testado). Em memória:
  reinício do Render zera contadores — documentado; reforço via WAF sugerido no código.
- XSS: frontend só usa `textContent`; payload `<script>` armazenado literalmente sem
  execução (teste real). SQLi neutralizada por query parametrizada (teste real).
- Cabeçalhos: `nosniff`, `DENY`, CSP restritiva, `no-store` em `/api/`. Testado.
- Arquivos privados (`server.py`, `pc_agent.py`, `.env`) retornam 404. Testado.
- Validação Pydantic + validação independente no agente (defesa em profundidade). 422
  testado para 6 classes de payload inválido.
- Agente exige HTTPS fora de localhost; WS do agente exige `Bearer` (teste de token
  errado fecha a conexão). Testado.
- Não autenticado **não** lê/envia/acessa nada (401 em `/api/status`, `/api/messages`,
  `/api/sync` com payload válido). Testado.

## Bugs encontrados e tratamento

1. `maxlength="600"` no input vs limite de 10 000 no backend/JS → **corrigido**
   (alinhado a `10000`, igual ao Pydantic e ao guarda do JS).
2. Falta de `.env.example` e scripts Windows → **criados** (`.env.example`,
   `iniciar-servidor.bat`, `iniciar-agente.bat`).
3. Cobertura de testes insuficiente (sem validação 422, sem concorrência, sem lockout)
   → **4 testes novos adicionados**, todos passando.
4. Não-bugs confirmados: validação 422 antes de 401 em payload inválido (comportamento
   padrão FastAPI, sem vazamento); `failed`/`sending` ausentes (decisão de simplicidade,
   documentada); rate limit em memória (documentado).

## Código morto / duplicações

Nada relevante: sem funções duplicadas; botões da UI sem backend real exibem toasts
explícitos ("ainda não implementado") em vez de simulação silenciosa. `sw.js` nunca
intercepta `/api/`. Aprovado.
