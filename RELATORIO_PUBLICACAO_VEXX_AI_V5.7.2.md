# RELATÓRIO DE PUBLICAÇÃO — VEXX AI V5.7.2

- **Data:** 2026-10-19 (America/Sao_Paulo)
- **Repositório:** `C:\Users\efrai\Documents\julia-mobile-v0.2-offline-sqlite\julia-mobile-v0.2`
- **Commit publicado:** `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`
- **Commit anterior em produção:** `020c85f` (referência para rollback)
- **Render:** `https://vexx-ai.onrender.com` — instância `a67901fc`, commit `ed0d44fd8b40`
- **CI:** workflow `39309139991` — **success**
- **Decisão:** **GO_WITH_LIMITATIONS**
- **Natureza:** publicação controlada com smoke real em produção; sem alteração de código após o deploy.

> Este relatório não contém senha, cookie, CSRF, token ou segredo. A identidade da conta de teste foi omitida dos artefatos públicos. O único agente ativo é o processo supervisionado pelo Fajulto Studio; não foi iniciado agente concorrente.

---

## Resumo executivo

A V5.7.2 foi publicada por fast-forward (`020c85f..ed0d44f`), o CI passou e o Render está saudável no commit correto. O PC Agent foi consolidado em **um único processo** (`PID 24356`, filho do Studio `25812`), com o código novo, e permaneceu online durante o smoke.

O transporte e a interface funcionam: login real, sessão, CSRF, streaming SSE, chat, pesquisa com fontes, análise de URL, comparação, falha externa honesta, Chrome desktop e mobile emulado. Segurança (401/403), integridade do SQLite, estáticos remotos e links de pesquisa também passaram.

A publicação **não é um GO de qualidade plena**. O smoke revelou limitações de conteúdo e roteamento:

1. **B — identidade:** a resposta atribuiu a criação da Vexx AI a uma empresa “Vexxia”, não documentada no repositório. Classificação: **PREEXISTING** (comportamento do modelo; o diff não alterou identidade).
2. **D — produtos:** nenhuma oferta com preço verificado/JDUI foi produzida; os provedores externos não expuseram dados estruturados. A resposta foi honesta ao não inventar preço, mas vazou um `<tool_call>` cru. Classificação: **EXTERNAL_LIMITATION + PREEXISTING** (limitação de tool call já declarada no aceite local).
3. **G — continuação:** após um 429 do Hermes, o fallback pesquisou a frase literal e devolveu fontes de clima/investimentos, sem relação com produtos. Classificação: **EXTERNAL_LIMITATION (429) + UNKNOWN/PREEXISTING (rota de fallback sem baseline com 0 produtos)**.
4. **F — comparação:** a tabela principal está correta, mas incluiu uma afirmação de desempenho não sustentada pela página citada. Classificação: **PREEXISTING** (conteúdo do modelo).
5. **Bug determinístico de evento:** a frase “teste visual concluido” acionou o fluxo de concluir evento. O mesmo bloco existe em `020c85f`; classificação: **PREEXISTING**. Evidência preservada em screenshots próprios.
6. **JDUI ao vivo:** não houve card de produto em produção porque não houve oferta validada; a paridade e o card local com dado real da KaBuM estão preservados como evidência separada. Classificação: **EXTERNAL_LIMITATION** para a ausência de oferta.

**Não foi comprovada regressão crítica.** Não houve queda, perda de dados, falha de segurança, migração ou corrupção. Por isso **não foi executado rollback**. Se for necessário reverter, a referência correta é `020c85f`; o checklist antigo cita `772ec3a`, que não era a revisão ativa em produção.

---

## Os 22 itens exigidos

Os itens 1–18 correspondem ao aceite local da V5.7.2. Os itens 19–22 registram a publicação, a saúde pós-deploy, o rollback/dados e a decisão final.

| # | Item | Status |
|---|---|---|
| 1 | Escopo, base e método | **PASS** |
| 2 | Preço numérico (BRL, milhar/decimal, moeda) | **PASS local; não reexercitado ao vivo em D** |
| 3 | Filtros de orçamento | **PASS local; sem oferta precificada em D** |
| 4 | Sem preço, moeda diferente, variante, promocional | **PASS local; D manteve “preço não confirmado”** |
| 5 | Extração de conteúdo principal | **PASS (docs.python.org em produção)** |
| 6 | Latência do shopping | **PASS (instrumentado; tempos observados)** |
| 7 | Hermes — descoberta de modelos | **PASS (427 modelos; free)** |
| 8 | Hermes — inferência real | **PASS de transporte; conteúdo com ressalvas** |
| 9 | Hermes — streaming | **PASS (SSE real; G com 429)** |
| 10 | Hermes — resposta fundamentada | **PARTIAL** |
| 11 | Entrega no frontend (FRONTEND_DELIVERY) | **PASS** |
| 12 | Paridade JDUI Python × JS | **PASS local/estático; card ao vivo não exercitado** |
| 13 | Chrome desktop real | **PASS (layout); bug de evento separado** |
| 14 | Chrome mobile emulado | **PASS (emulado; não é Android/iOS físico)** |
| 15 | Smoke integrado A–H | **PARTIAL** |
| 16 | Regressão completa | **PASS** |
| 17 | Segurança preservada | **PASS** |
| 18 | Release readiness | **PASS, com ressalvas de conteúdo e tag** |
| 19 | Publicação controlada (push, CI, Render, PC Agent) | **PASS** |
| 20 | Saúde pós-deploy e estabilidade | **PASS** |
| 21 | Rollback, dados e continuidade | **DOCUMENTADO; sem rollback** |
| 22 | Decisão final, limitações e riscos | **GO_WITH_LIMITATIONS** |

\* Itens 2, 3, 4, 6 e 12 têm evidência local/estática forte; a oferta ao vivo não foi produzida em D, portanto não foram revalidados ponta a ponta no Render.

---

## 1. Escopo, base e método

- Base publicada: `ed0d44f`, quatro commits à frente de `020c85f`, fast-forward sem `--force`.
- Nenhum código foi alterado depois do push; a árvore local contém somente artefatos de QA e este relatório (não rastreados).
- Evidência separada por rótulo: **LOCAL REAL**, **PRODUÇÃO REAL**, **EXTERNO REAL**, **BLOQUEADO**.
- Fora de escopo, preservado: identidade Lucas, extensão Júlia, Fajulto Studio, Hermes, recursos 3D, Research Engine, credenciais e modelos pagos.
- Nenhuma migração, dependência nova, serviço pago ou refatoração foi adicionada.

## 2. Preço numérico (BRL, milhar/decimal, moeda)

- Aceite local: `Decimal` e normalização de preço cobrem `R$ 2.974,15`, milhar/decimal, `USD` e inválidos/ambíguos; testes de preço **12/12**.
- Smoke externo local: **2/2** ofertas com preço numérico (R$ 28,60 e R$ 68,32); smoke integrado local com R$ 134,29.
- **Produção:** D não produziu oferta com preço numérico; as referências ficaram como “Preço não confirmado”. Portanto, o caminho de preço não foi reexercitado ao vivo no Render nesta rodada. Não foi inventado nenhum valor.

## 3. Filtros de orçamento

- Aceite local: `≤ R$ 500`, `R$ 1.000–2.000`, `> R$ 3.000` e teto explícito passaram; itens acima do teto ficam como alternativas explícitas, fora do conjunto principal.
- **Produção:** sem oferta precificada em D, não houve promoção indevida nem violação de orçamento. O comportamento honesto foi preservar as referências sem preço.

## 4. Sem preço, moeda diferente, variante e promocional

- Aceite local: sem preço interpretável → `preco_nao_confirmado`; moeda ≠ BRL não é comparada com teto em BRL; variante incompatível não entra no conjunto principal; “a partir de”/promocional não vira preço único.
- **Produção:** D devolveu três referências com “Preço não confirmado” e uma referência não verificada, sem card e sem preço presumido. O comportamento está alinhado com a regra de não inventar.

## 5. Extração de conteúdo principal

- **Produção:** a análise de `https://docs.python.org/3/tutorial/datastructures.html` retornou **3.892 caracteres**, com títulos, métodos de listas e exemplos; o link respondeu **HTTP 206**.
- A resposta usou uma assinatura pseudoformal `list.pop(index=-1)`; é uma imprecisão de apresentação, não uma falha de extração.
- Aceite local: `test_web_extract_v572.py` **5/5**; Wikipédia e docs.python.org sem menu/sidebar; Magalu bloqueada com aviso honesto.
- Trafilatura não foi adicionada; a extração determinística cobriu o cenário.

## 6. Latência do shopping

- Instrumentação local preservada: notebook ≤ R$ 3.000 em 7,99–8,73 s; fone ≤ R$ 300 em 10,07 s; smoke externo final 11,7 s.
- **Produção:** D 15,3 s; G 10,8 s (com 429); E 30,8 s. São observações reais, não um SLO novo.
- Nenhuma otimização especulativa foi aplicada; verificações e limites foram mantidos.

## 7. Hermes — descoberta de modelos

- Log do agente novo: `Hermes proxy OK: 427 modelos (padrão poolside/laguna-s-2.1:free)`.
- `/v1/models` já havia retornado 200 no aceite local (428 modelos, com o free presente).
- Nenhum modelo pago foi ativado ou usado; o modelo das respostas de produção foi `poolside/laguna-s-2.1:free`.

## 8. Hermes — inferência real

- B, C, D, E, F e H retornaram **HTTP 200** via `/api/ai/stream`.
- Modelo registrado em todas as respostas avaliadas: `poolside/laguna-s-2.1:free`.
- Tempo total observado: B 4,8 s; C 16,3 s; D 15,3 s; G 10,8 s; E 30,8 s; F 11,0 s; H 5,1 s.
- O transporte e a inferência funcionaram; os problemas de conteúdo estão descritos nos itens 10 e 15.

## 9. Hermes — streaming

- SSE real observado com eventos `delta` e `done`; o Chrome recebeu a resposta em streaming e exibiu o texto.
- Primeiro delta: B 2,8 s; C 7,1 s; D 1,0 s; E 5,3 s; F 2,1 s; H 1,8 s. G teve um único delta tardio (10,8 s) após `AI_AGENT_ERROR code=rate_limit`.
- O `done` foi recebido em B/C/D/E/F/H; G não concluiu pelo caminho normal do modelo, mas o fallback entregou uma resposta de fontes sem síntese.
- Nenhum corpo vazio; nenhum erro de protocolo no cliente.

## 10. Hermes — resposta fundamentada

- **C — pesquisa:** 1.703 caracteres; 3 fontes lidas no log (`sources=3`); os três links citados responderam **200/206** (Brasil Escola, Biologianet, Toda Matéria). **PASS**.
- **E — URL:** 3.892 caracteres; a página oficial foi lida e o link respondeu **206**. **PASS**.
- **H — falha externa:** domínio inválido; resposta honesta e específica, sem conteúdo inventado. **PASS**.
- **B — identidade:** resposta coerente em forma, mas atribuiu a criação a “Vexxia”, empresa não documentada. **FALHA DE CONTEÚDO**; classificação **PREEXISTING**.
- **F — comparação:** mutabilidade/métodos/indexação corretos; a linha “Desempenho: tuplas mais rápido devido à imutabilidade” não está sustentada pela página citada. **RESSALVA**; classificação **PREEXISTING**.
- **G — continuação:** o fallback devolveu fontes de clima de Marabá, horário e Ágora Investimentos para o pedido “Agora mostre apenas os resultados mais baratos”. **FALHA**; 429 + rota de fallback.
- O log registra `síntese JDUI falhou (BridgeErro); mantendo só texto` em F; o texto foi entregue, mas não houve card.

## 11. Entrega no frontend (FRONTEND_DELIVERY)

- Chrome real **155.0.8059.82** via CDP, login pela interface, sessão persistida e chat com streaming.
- Pergunta neutra de controle: “Qual é a capital do Brasil?” → “A capital do Brasil é Brasília.”
- Desktop 1280×900: **sem overflow** (1280/1280). Mobile emulado 390×844, DPR 2, touch: **sem overflow** (390/390).
- Console: 1 erro esperado **401 antes do login**; 2 `ERR_ABORTED` de reload; **0 exceções JS**.
- Screenshots sem conta/credencial: `desktop-chat-capital.png` e `mobile-chat-capital.png`.
- O bug de evento foi capturado separadamente, sem esconder a resposta: `desktop-evento-bug.png` / `mobile-evento-bug.png`.

## 12. Paridade JDUI Python × JS

- Aceite local: `test_jdui_visual_v572.py` **2/2** e `test_jdui_paridade_produto_v57f.py` verdes; imagem, selos parciais/não verificados e “original declarado” preservados.
- Card local real da KaBuM: **R$ 110,12**, imagem **verificada**, link **parcial**, fonte “original declarado: Manual do fabricante”; screenshots `qa-artifacts/v572/chrome/desktop-card.png` e `mobile-card.png`.
- **Produção:** `public/jdui.js` remoto é byte-equivalente ao commit após normalização CRLF→LF; porém D não gerou oferta, então **não houve card de produto ao vivo** para validar. Não se declara oferta verificada.

## 13. Chrome desktop real

- Login, chat e resposta em streaming no Chrome real; viewport 1280×900; sem overflow horizontal.
- Screenshot de controle: `qa-artifacts/v572/prod-chrome/desktop-chat-capital.png`.
- O layout passou; o bug de roteamento de “teste visual concluido” é um achado separado, **PREEXISTING**, visível nas evidências `*-evento-bug.png`.
- Nenhuma exceção JavaScript; o 401 de console ocorre antes do login e é esperado.

## 14. Chrome mobile emulado

- `Emulation.setDeviceMetricsOverride` 390×844, DPR 2, touch; sem overflow (390/390).
- Screenshot: `qa-artifacts/v572/prod-chrome/mobile-chat-capital.png`.
- **Não é teste em Android/iOS físico.** A declaração de limitação é explícita; nenhum teste físico foi alegado.

## 15. Smoke integrado A–H (produção real)

| Cenário | Resultado observado | Status |
|---|---|---|
| **A — login** | HTTP 200; `authenticated`, sessão e CSRF; login inválido 401 | **PASS** |
| **B — chat/Hermes** | HTTP 200; 317 chars; streaming; mas “Vexxia” inventada | **PARTIAL (conteúdo)** |
| **C — pesquisa** | HTTP 200; 1.703 chars; 3 fontes; links 200/206 | **PASS** |
| **D — produtos** | HTTP 200; 0 cards; 3 referências sem preço; `<tool_call>` cru; nenhum preço inventado | **PARTIAL/FAIL de produto** |
| **E — URL** | HTTP 200; docs.python.org; 3.892 chars; link 206 | **PASS** |
| **F — comparação** | HTTP 200; tabela correta; afirmação de desempenho não sustentada; JDUI BridgeErro | **PARTIAL** |
| **G — continuação** | HTTP 200; 429; fontes de clima/horário/investimentos; 0 cards | **FAIL** |
| **H — falha externa** | HTTP 200; domínio inválido explicado; sem invenção | **PASS** |

Resumo: **A, C, E, H passam; B e F passam no transporte com falha/ressalva de conteúdo; D é limitação externa + vazamento de tool call; G falha no fallback.**

## 16. Regressão completa

- Suíte local preservada: **891 passed, 4 skipped** (102,51 s).
- Benchmarks: pesquisa **34/34**; shopping **59/59**; experiência **16/16**.
- Testes novos V5.7.2: **23/23**; nenhum teste removido/alterado para “passar”.
- CI do commit publicado: **success** (workflow `39309139991`, job `tests` 1m38s; apenas avisos de depreciação do Node 20).
- Produção: sem crash, sem exceção JS, sem perda de conexão durante o smoke.

## 17. Segurança preservada

Teste real em produção, sem imprimir credenciais:

| Verificação | Resultado |
|---|---|
| GET `/api/conversations` sem sessão | **401** |
| Login válido | **200**, autenticado, CSRF presente |
| GET `/api/conversations` com sessão | **200** |
| POST `/api/sync` com sessão e **sem CSRF** (payload válido) | **403** |
| POST `/api/sync` com sessão e CSRF inválido | **403** |
| POST `/api/sync` sem sessão | **401** |

- Nenhuma senha, cookie, CSRF ou token foi encontrado nos artefatos `qa-artifacts/v572/` (varredura do valor da senha: **0 ocorrências**).
- Credenciais, identidade e modelos pagos não foram alterados; nenhum serviço pago novo.

## 18. Release readiness

- Contratos relay × PC Agent, endpoints, payloads e WS preservados; sem migração (`CREATE/ALTER` ausentes).
- `requirements.txt` inalterado; nenhuma dependência nova em runtime.
- Estáticos remotos conferem com o commit após normalização CRLF→LF: `app.js`, `jdui.js`, `styles.css`, `interface.css`, `sw.js`, `manifest.webmanifest` — **6/6 match**.
- `sw.js` permanece `VEXX-shell-live-data-1`; network-first e bypass de `/api/*`.
- Uma leitura inicial de `/sw.js` retornou 502 transitório; o retry retornou 200 e o hash normalizado coincide. Não houve falha persistente.
- **Tag:** nenhuma tag foi criada/publicada nesta rodada; o deploy não depende dela. Se o processo exigir tag de release, criá-la depois com autorização.

## 19. Publicação controlada (push, CI, Render, PC Agent)

- Push fast-forward: `020c85f..ed0d44f`; sem `--force`; `origin/main` = `ed0d44f` = HEAD.
- CI: [run 39309139991](https://github.com/euefrai/Vexx-AI-Mobile/actions/runs/39309139991) — **success**; sem falhas de teste.
- Render: deploy de `ed0d44fd8b40`, instância `a67901fc`; `/api/health` = `{"status":"ok","configured":true}`; `/api/diag` confirma o commit e `pc_online:true`.
- PC Agent: agentes antigos encerrados; **exatamente um** agente ativo, `PID 24356`, filho do Studio `PID 25812`, iniciado em 16:20:44 com o código novo.
- Nenhum job ativo antes do restart; após o smoke, `research_jobs=0` e `research_runs=0`.
- Nenhum SQLite/conversa foi apagado; nenhuma migração foi executada.

## 20. Saúde pós-deploy e estabilidade

- `/api/diag` final: `commit=ed0d44fd8b40`, `instance=a67901fc`, `pc_online=true`, `agente_ha=1135` (segundos desde a conexão, não quantidade de agentes).
- O agente teve duas reconexões iniciais (16:21:31 e 16:22:21) e reconectou às 16:22:25; depois disso, **nenhuma desconexão** durante o smoke.
- Processo único confirmado: `pythonw.exe ... pc_agent.py`, PID 24356, parent 25812.
- SQLite somente leitura: `PRAGMA quick_check = ok`; **180 mensagens**, **11 conversas distintas**, **8 consultas de shopping**, **0 research jobs/runs**.
- Avisos não bloqueantes no log: 429 do Hermes em G/aprendizado, listagem opcional OpenAI sem auth e uma falha de síntese JDUI em F. Nenhum modelo pago foi usado.
- O smoke persistiu mensagens normais na conta autorizada; o log registra aprendizado de `vexx_ai`. Nada foi apagado ou restaurado manualmente.

## 21. Rollback, dados e continuidade

- **Rollback não executado**, porque não foi comprovada regressão crítica; o serviço está saudável e o banco íntegro.
- Se necessário reverter:
  1. confirmar a revisão realmente ativa em `/api/diag`;
  2. redeploy de **`020c85f`** no Render (não `772ec3a`; o checklist antigo está desatualizado para a produção);
  3. voltar o PC Agent ao mesmo commit e reiniciar pelo procedimento do Studio;
  4. verificar `/api/diag`, login e uma resposta de IA;
  5. preservar estes artefatos.
- Não há migração a desfazer; o schema SQLite permanece compatível. Não foi criado backup adicional nesta rodada; `quick_check` está `ok` e nenhuma operação destrutiva foi feita.
- O banco ativo não foi apagado nem editado manualmente; conversas e mensagens foram preservadas.

## 22. Decisão final, limitações e riscos

### Decisão: `GO_WITH_LIMITATIONS`

O deploy é tecnicamente saudável e não há regressão crítica comprovada. Entretanto, a qualidade pública ainda tem limitações materiais de conteúdo, roteamento e disponibilidade de ofertas. Não é correto declarar “GO pleno” nem “ofertas de produto verificadas em produção”.

### Classificação dos achados

| Achado | Classificação | Evidência |
|---|---|---|
| B: “Vexxia” inventada | **PREEXISTING** (modelo; diff não alterou identidade) | `prod_smoke_v572.json`; `ASSISTANT_IDENTITY.md` |
| D: nenhuma oferta/preço verificado | **EXTERNAL_LIMITATION** (páginas sem dados estruturados) | D; links 200/206; `prod_link_checks.json` |
| D: `<tool_call>` cru no texto | **PREEXISTING** (limitação #4 do aceite local) | D; aceite local, item 20 |
| F: afirmação de desempenho não sustentada | **PREEXISTING** (conteúdo do modelo) | F; página docs.python.org |
| G: 429 do Hermes | **EXTERNAL_LIMITATION** | log `AI_AGENT_ERROR ... code=rate_limit` |
| G: fontes irrelevantes no fallback | **UNKNOWN/PREEXISTING** (sem baseline com 0 produtos) | G; fontes Climatempo/DataHora/Ágora |
| Evento: “concluido” aciona concluir evento | **PREEXISTING** (mesmo bloco em `020c85f`) | screenshots `*-evento-bug.png` |
| Card JDUI ao vivo ausente | **EXTERNAL_LIMITATION** (sem oferta) | D; card local KaBuM separado |
| **Regressão crítica** | **NÃO COMPROVADA** | nenhum crash/perda/segurança |

### Riscos residuais

- Provedores externos (MLB/Magalu/DDG/lojas) podem bloquear, variar preço/estoque ou não expor JSON-LD.
- Hermes free pode retornar 429; o fallback precisa ser mais honesto e contextual.
- O vazamento de `<tool_call>` é visível ao usuário e deve ser sanitizado.
- O fluxo de evento tem falso positivo determinístico para frases com “concluido”.
- A identidade factual da marca não está suficientemente ancorada no prompt/modelo.
- O mobile foi emulado; não há teste físico Android/iOS nesta rodada.

### Próximos passos recomendados (não executados nesta publicação)

1. Sanitizador determinístico de `<tool_call>` no texto final, com teste próprio.
2. Corrigir o falso positivo do fluxo de evento (`conclu` + `m_ev`), com testes para “concluí/concluído”.
3. Continuação sem produtos: responder “não há resultados anteriores” e **não** iniciar pesquisa literal.
4. Ancorar identidade/produto (“Vexx AI”, “Lucas”) e proibir empresa não documentada; teste de identidade.
5. Validar afirmações de desempenho somente contra a página lida; se não houver suporte, remover.
6. Quando houver oferta, abrir a página do produto e validar preço/moeda/imagem/link/JDUI antes de dizer “verificada”.
7. Se o processo exigir, criar tag de release após a decisão.

**Condição para um próximo GO pleno:** corrigir os itens 1–4 acima, obter uma oferta real com card JDUI em produção e reexecutar A–H. O rollback para `020c85f` não é recomendado agora; não corrigiria os achados preexistentes e interromperia a versão atual sem ganho comprovado.

---

## Evidências e artefatos

### Produção

| Artefato | Conteúdo |
|---|---|
| `qa-artifacts/v572/prod_smoke_v572.json` | Smoke A–H, respostas, tempos, modelos, avaliações e produtos (login anonimizado) |
| `qa-artifacts/v572/prod-chrome/prod-chrome-e2e-capital.json` | Chrome desktop/mobile, login, chat “Brasília”, overflow, console/rede |
| `qa-artifacts/v572/prod-chrome/desktop-chat-capital.png` | Screenshot desktop limpo |
| `qa-artifacts/v572/prod-chrome/mobile-chat-capital.png` | Screenshot mobile emulado limpo |
| `qa-artifacts/v572/prod-chrome/prod-chrome-evento-bug.json` | Evidência do falso positivo de evento |
| `qa-artifacts/v572/prod-chrome/desktop-evento-bug.png` | Screenshot desktop do bug de evento |
| `qa-artifacts/v572/prod-chrome/mobile-evento-bug.png` | Screenshot mobile emulado do bug de evento |
| `qa-artifacts/v572/prod_security_v572.json` | 401/403/200 de sessão e CSRF |
| `qa-artifacts/v572/prod_db_health.json` | `quick_check`, contagens, 0 jobs/runs |
| `qa-artifacts/v572/prod_static_parity.json` | Hashes normalizados dos 6 estáticos |
| `qa-artifacts/v572/prod_link_checks.json` | Links de C/E/D: 200/206 |

### Aceite local preservado

- `RELATORIO_VEXX_AI_5.7.2_FINAL_ACCEPTANCE.md`
- `docs/V5_7_2_E2E_RESULTS.md`
- `docs/V5_7_2_RELEASE_CHECKLIST.md`
- `qa-artifacts/v572/chrome/desktop-card.png` e `mobile-card.png` (card local KaBuM, R$ 110,12)
- `qa-artifacts/v572/smoke-integrado-20261019-152951.json` (7/7 local)
- `qa-artifacts/v572/grounded-fotossintese.json`
- `tests/test_precos_filtros_v572.py`, `tests/test_web_extract_v572.py`, `tests/test_jdui_visual_v572.py`

### Infra

- CI: https://github.com/euefrai/Vexx-AI-Mobile/actions/runs/39309139991
- Saúde: https://vexx-ai.onrender.com/api/health
- Diagnóstico: https://vexx-ai.onrender.com/api/diag
- Log do agente supervisionado: `C:\Users\efrai\AppData\Local\Temp\fajulto-julia-mobile.log`

---

**Conclusão:** publicação controlada concluída; serviço saudável, dados íntegros, segurança preservada e um único agente. Decisão **GO_WITH_LIMITATIONS** — sem rollback, com correções de conteúdo/roteamento recomendadas antes de elevar a qualidade a GO pleno.
