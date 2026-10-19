# VEXX AI V5.7.2 — Release Checklist (2026-10-19)

**Decisão:** `READY_WITH_LIMITATIONS` — pronto para publicação **quando
autorizada**, sem bloqueador de código conhecido. Nada foi pushado ou
deployado nesta rodada.

## 1. Estado do repositório

| Item | Valor |
|---|---|
| Base | `772ec3a` — V5.7 FINAL (árvore limpa no início) |
| Commit local desta versão | ver `git log -1` (criado no fim da rodada) |
| Push | **não realizado** (proibido nesta rodada) |
| Deploy | **não realizado** (proibido nesta rodada) |
| Branch | local, sem remoto alterado |

Arquivos de código alterados (4):

- `shopping.py` — preço Decimal + filtros/alternativas.
- `web_extract.py` — extração de conteúdo principal/título/inline.
- `research.py` — consulta de pesquisa (pedido fora, tema fica).
- `tools/smoke_externo_v57f.py` — métrica `com_preco_numerico` corrigida.

Novos testes (4 arquivos, 23 testes): `test_precos_filtros_v572.py`,
`test_web_extract_v572.py`, `test_consulta_pesquisa_v572.py`,
`test_jdui_visual_v572.py`.

Novas ferramentas de evidência: `tools/chrome_e2e_v572.py`,
`tools/smoke_integrado_v572.py`.

Sem mudanças em: `server.py`, `pc_agent.py`, `public/*` (app.js, jdui.js, sw.js,
styles), motor 3D, extensão da Júlia, Fajulto Studio, `requirements.txt`,
`render.yaml`.

## 2. Contratos relay × PC Agent

- Endpoints e payloads **inalterados**: `/api/login`, `/api/session`,
  `/api/diag`, `/api/sync`, `/api/messages`, `/api/ai`, `/api/ai/stream`,
  `/research`.
- Tipos de mensagem WS inalterados (`sync`, `list`, `ai`, `ack`, `ai_delta`,
  `ai_done`, erros `op_error`).
- Variáveis de ambiente inalteradas:
  - `JULIA_USERNAME`, `JULIA_PASSWORD_HASH` (argon2), `JULIA_SESSION_SECRET`,
    `JULIA_AGENT_TOKEN`, `JULIA_SQLITE_PATH`, `JULIA_RELAY_URL`;
  - `HERMES_PROXY_URL` (local no PC), `JULIA_AI_MODEL`
    (`poolside/laguna-s-2.1:free`), `JULIA_AI_FALLBACKS` **não definido**.
- Nenhum modelo pago, nenhum provedor novo, nenhuma credencial alterada.
- Compatibilidade: relay e agente podem ser publicados em qualquer ordem;
  as mudanças são internas ao processamento (preço/extração/consulta).

## 3. Migrações e dados

- **Nenhuma migração**: o diff não contém `CREATE TABLE`, `ALTER TABLE` ou
  `PRAGMA user_version`.
- Tabelas/campos existentes reutilizados (`shopping_consultas`, `messages`,
  `research_*`, etc.).
- Nenhum dado apagado; nenhum fixture alterado.
- Recomendação operacional: backup do SQLite do PC antes de atualizar o agente
  (procedimento padrão), embora não haja schema a migrar.

## 4. Dependências

- `requirements.txt` **inalterado**; nenhuma dependência nova de runtime.
- `websockets` (já presente) e `argon2` (já presente) foram usados apenas nos
  harnesses de evidência.
- `playwright`, `trafilatura`, `httpx` e `requests` continuam ausentes;
  nenhum serviço pago novo.
- Build Render continua: `pip install -r requirements.txt`; start
  `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers`.

## 5. Estáticos, cache e service worker

- `public/app.js`, `public/jdui.js`, `public/styles.css`, `public/interface.css`
  e `public/sw.js` **não mudaram** nesta versão.
- `sw.js` permanece `VEXX-shell-live-data-1`; a estratégia é network-first
  para o shell e **bypass total** de `/api/*`; não é necessário bump de cache
  para este diff.
- Se uma publicação futura alterar `public/*`, incrementar `VERSION` no
  `sw.js` antes do deploy.
- JSON válido ≠ render correto: validado no Chrome real (seção 6).

## 6. Segurança (preservada)

| Controle | Status |
|---|---|
| Auth de sessão + CSRF | intacto; suíte de auth/remoto verde |
| RBAC / isolamento por usuário | intacto; `owner_id` em todas as consultas |
| SSRF / DNS / redirects / limites de download | intactos; mesma função `baixar` |
| Rate limiting / limites de uso | intactos |
| CSP / headers | intactos |
| Anti prompt-injection / páginas externas | nenhum script de página executado |
| Segredos | somente no backend/env; nada exposto no frontend |
| Controles do PC Agent | intactos; nenhuma porta nova aberta em produção |
| Dependências pagas | nenhuma |

A suíte completa (891 passed, 4 skipped) cobre segurança, shopping, research,
evidence graph, JDUI Python+Node e frontend smoke.

## 7. Sequência de publicação (somente quando autorizada)

1. Revisar o diff final e o commit local; criar tag de release.
2. Push para o branch de deploy (Render) — **não feito nesta rodada**.
3. Render: build + deploy do relay; aguardar health `/api/diag`.
4. PC Agent: atualizar para o mesmo commit e reiniciar pelo procedimento
   padrão; confirmar `pc_online: true` no `/api/diag`.
5. Smoke no serviço publicado: login, chat com streaming, produtos,
   pesquisa geral, URL do usuário, continuação e falha externa.
6. Monitorar 429/403/bot-wall; confirmar mensagens honestas de fallback.
7. Registrar evidências da publicação em `qa-artifacts/` (sem sobrescrever as
   desta rodada).

## 8. Rollback

1. Render: redeploy do commit anterior **`772ec3a`** (V5.7 FINAL).
2. PC Agent: voltar ao commit `772ec3a` e reiniciar pelo procedimento padrão.
3. Não há migração a reverter; o SQLite permanece compatível.
4. Se necessário, restaurar o backup do SQLite feito antes da atualização.
5. Verificar `/api/diag`, login e uma resposta de IA; preservar os artefatos
   desta rodada para auditoria.

## 9. Go / No-Go

| Critério | Status |
|---|---|
| Suíte completa verde | ✅ 891 passed, 4 skipped |
| Benchmarks 34/34 e 59/59 | ✅ |
| Bateria 16/16 | ✅ |
| Preços/filtros (12 testes + smoke real) | ✅ 2/2 com preço numérico |
| Extração (5 testes + ao vivo) | ✅ Wikipédia/docs.python.org limpos |
| Hermes discovery/inference/streaming/grounded | ✅ (free, custo 0) |
| Chrome desktop + mobile emulado | ✅ sem overflow; screenshots |
| Smoke integrado 6 cenários | ✅ 7/7 |
| Segurança | ✅ sem regressão |
| Contratos/migrações/deps/estáticos | ✅ sem mudanças |
| Serviço publicado testado | ❌ não executado (deploy proibido) |
| Mobile físico Android/iOS | ❌ não executado (apenas emulação) |
| Provedores externos 100% estáveis | ❌ variáveis (403/bot-wall/429) |

**Conclusão:** GO condicionado à autorização de publicação e ao smoke no
ambiente publicado. Limitações acima são de cobertura/ambiente, não defeitos
de código.
