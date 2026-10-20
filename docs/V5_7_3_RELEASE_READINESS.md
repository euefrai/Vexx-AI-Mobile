# VEXX AI V5.7.3 — Release Readiness

- **Data:** 2026-10-19
- **Base inicial:** `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`
- **Commit de código/testes:** `63e12c00370c6b13b328e6836d5b3af9b7b45ff6`
- **HEAD final da entrega:** commit documental seguinte; hash em
  `qa-artifacts/v573/final-head.txt`
- **Branch:** `main` local
- **Push:** não realizado
- **Deploy:** não realizado
- **Reinício de produção:** não realizado (PID `24356` preservado)
- **Decisão:** **`READY_WITH_LIMITATIONS`**

## 1. Estado do repositório

| Item | Valor |
|---|---|
| Base | `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe` |
| Commit de código/testes | `63e12c00370c6b13b328e6836d5b3af9b7b45ff6` |
| Arquivos de código alterados | 12 rastreados + `tool_protocol.py` novo |
| Testes novos | `tests/test_trust_v573.py` (38) |
| Testes existentes ajustados | `tests/test_research.py` (fixture de título), `tests/test_research_agents.py` (push SSE mais forte) |
| Documentos novos | este arquivo, `V5_7_3_PROGRESS.md`, `V5_7_3_INCIDENT_REGRESSION.md`, relatório raiz |
| Artefatos | `qa-artifacts/v573/` |
| Produção | commit antigo, PID `24356` intocado |

Arquivos de código:

- `tool_protocol.py` (novo) — sanitização de chamadas internas.
- `hermes_bridge.py` — integração do sanitizador e erros tipados.
- `providers.py` — mesma barreira no adaptador alternativo.
- `assistant_identity.py` — fatos canônicos e limitador.
- `evidence_graph.py` — comparação e fonte não lida.
- `pc_agent.py` — identidade, digest, shopping, comparação e guard de stream.
- `research.py` — relevância de fonte e digest honesto.
- `research_agents.py` — status terminal antes do evento.
- `server.py` — `ResearchSSECursor` e ordenação SSE.
- `shopping.py` — follow-up sem contexto e ofertas verificadas.
- `search_orchestrator.py` — vocabulário de follow-up genérico.
- `tests/test_trust_v573.py` (novo) — 38 regressões.

## 2. Contratos e compatibilidade

- Endpoints HTTP existentes preservados: `/api/login`, `/api/session`,
  `/api/health`, `/api/diag`, `/api/sync`, `/api/messages`, `/api/ai`,
  `/api/ai/stream`, `/research`.
- Tipos WebSocket existentes preservados (`sync`, `list`, `ai`, `ack`,
  `ai_delta`, `ai_done`, erros); o relay ganhou **cursor interno** de SSE, não
  um novo protocolo público.
- Payloads de pesquisa preservados; `seq` continua sendo a ordem autoritativa.
- Variáveis de ambiente e credenciais inalteradas.
- Modelo free `poolside/laguna-s-2.1:free`; nenhum modelo pago ativado.
- Relay e agente podem ser publicados em qualquer ordem; as mudanças são
  internas ao processamento e não exigem migração coordinada.
- Sem dependências novas em `requirements.txt`; sem novo framework/provider.

## 3. Migrações, dados e estáticos

| Item | Status |
|---|---|
| `CREATE TABLE` / `ALTER TABLE` / `PRAGMA user_version` | nenhum |
| Tabelas/campos | reutilizados |
| Dados/fixtures apagados | nenhum |
| `public/app.js`, `public/jdui.js`, `public/*.css`, `public/sw.js` | inalterados |
| Bump de service worker | não necessário (sem mudança de shell) |
| Backup do SQLite | recomendado antes de atualizar o PC Agent (procedimento padrão) |

## 4. Segurança

| Controle | Status |
|---|---|
| Sessão/CSRF | intactos; testes de auth/remoto verdes |
| RBAC/isolamento por owner | intacto |
| SSRF/DNS/redirect/limites de download | intactos |
| Rate limiting | intacto |
| CSP/headers | intactos |
| Chamada de ferramenta emitida pelo modelo | **não executada**; removida e registrada |
| Segredos | apenas backend/env |
| Dependências pagas | nenhuma |
| Testes de segurança removidos | nenhum |

A suíte completa (929 passed, 4 skipped) inclui auth, segurança, pesquisa,
shopping, Evidence Graph, JDUI Python/Node e smoke de frontend.

## 5. Evidência de qualidade

| Verificação | Resultado | Rótulo |
|---|---|---|
| Suíte completa | **929 passed, 4 skipped** | `DETERMINISTIC_FIXTURE` |
| Trust V5.7.3 | **38/38** | `DETERMINISTIC_FIXTURE` |
| Pesquisa | **34/34** | `DETERMINISTIC_FIXTURE` |
| Shopping | **59/59** | `DETERMINISTIC_FIXTURE` |
| Experiência | **16/16** | `DETERMINISTIC_FIXTURE` + Node |
| Smoke integrado | **7/7** | `LOCAL_E2E` + `EXTERNAL_E2E` |
| Chrome desktop | sem overflow; card real | `CHROME_E2E` |
| Chrome mobile emulado | sem overflow | `CHROME_E2E` |

### Smoke integrado (destaques)

- Produtos: 3 ofertas confirmadas (R$ 28,60 / R$ 68,32 / R$ 134,29), todas
  dentro do orçamento, cards JDUI válidos.
- Pesquisa geral: 3 fontes lidas, resposta real, sem tool call.
- URL direta: Wikipédia aberta, 1.200 chars, sem menu/resíduo.
- Comparação: documentação oficial do Python, 2 turnos, sem tool call.
- Continuação: ordenação local correta; falha externa sem preço/fence.

### Chrome (destaques)

- Chrome 155.0.8059.85, login pela interface, chat real 5,03 s.
- Card real KaBuM R$ 110,12, imagem verificada, link parcial.
- Desktop 1280×900 e mobile 390×844 sem overflow.
- 1 console 401 esperado antes do login; 0 exceções JS.
- Primeira execução falhou por crash do network service do Chrome; reexecução
  limpa passou. Artefatos de ambas preservados.

## 6. Limitações declaradas

| Limitação | Impacto | Tratamento |
|---|---|---|
| Produção não atualizada | correções não validadas no serviço publicado | publicação autorizada + smoke pós-deploy |
| PC Agent de produção não reiniciado | PID `24356` permanece no código antigo | procedimento padrão de atualização |
| Provedores externos variáveis | 403/bot-wall/429 possível | mensagens honestas; nunca `PASS` artificial |
| Mobile emulado | não cobre Android/iOS físico | declarado; teste físico futuro |
| Crash do network service do Chrome | harness pode falhar antes do login | reexecução; artefato de falha preservado |
| Modelo free único | não cobre todos os modelos/providers | suíte e smoke usam o caminho configurado |

## 7. Sequência de publicação (somente quando autorizada)

1. Revisar o diff e os quatro relatórios; confirmar o commit local.
2. Push para o branch de deploy (Render) — **não feito**.
3. Render: build e deploy do relay; aguardar `/api/health` e `/api/diag`.
4. Atualizar o PC Agent para o mesmo commit pelo procedimento padrão;
   reiniciar o agente **somente** com autorização.
5. Confirmar `/api/diag` com `pc_online: true` e o commit novo.
6. Smoke autenticado no serviço publicado: login, chat/streaming, produtos,
   pesquisa, URL direta, continuação e falha externa.
7. Monitorar 429/403/bot-wall; confirmar fallback honesto e ausência de
   `<tool_call>`/identidade inventada.
8. Registrar artefatos da publicação sem sobrescrever `qa-artifacts/v573/`.

## 8. Rollback

1. Render: redeploy do commit anterior `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`.
2. PC Agent: voltar ao mesmo commit e reiniciar pelo procedimento padrão.
3. Não há migração a reverter; o SQLite permanece compatível.
4. Se necessário, restaurar o backup do SQLite feito antes da atualização.
5. Verificar `/api/health`, `/api/diag`, login e uma resposta de IA.
6. Preservar os artefatos desta rodada para auditoria.

## 9. Go / No-Go

| Critério | Status |
|---|---|
| Suíte completa verde | ✅ 929 passed, 4 skipped |
| Trust V5.7.3 | ✅ 38/38 |
| Benchmarks 34/34, 59/59, 16/16 | ✅ |
| Smoke integrado | ✅ 7/7 |
| Chrome desktop + mobile emulado | ✅ sem overflow |
| Identidade canônica | ✅ local; produção não validada |
| Tool calls contidas | ✅ local; produção não validada |
| Fontes relevantes | ✅ local |
| Ofertas verificadas preservadas | ✅ local/externo |
| Comparações sem evidência neutralizadas | ✅ local |
| SSE ordenado/deduplicado/terminal | ✅ local/integração |
| Segurança | ✅ sem regressão |
| Contratos/migrações/deps/estáticos | ✅ sem mudança incompatível |
| Serviço publicado com código novo | ❌ não executado (deploy proibido) |
| Mobile físico | ❌ não executado (apenas emulação) |
| Provedores externos 100% estáveis | ❌ variáveis |

## 10. Conclusão

**GO condicionado à autorização de publicação e ao smoke no ambiente
publicado.** O código local está pronto para a publicação, mas a classificação
é **`READY_WITH_LIMITATIONS`**, não `READY`: o serviço publicado permanece no
commit antigo, o PID `24356` não foi reiniciado e os provedores externos não
oferecem estabilidade garantida. Não há bloqueador de código conhecido.
