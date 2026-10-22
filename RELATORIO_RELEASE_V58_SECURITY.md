# Relatório de Release — VEXX AI V5.8 (endurecimento de segurança)

**Data:** 21/10/2026 (horário local; 22/10/2026 UTC)
**Repositório:** `euefrai/Vexx-AI-Mobile`
**Produção:** https://vexx-ai.onrender.com
**Commit funcional verificado:** `10e7028` (HSTS + código de segurança)
**Commit de evidências:** `217bba7`
**Decisão final:** **GO_WITH_LIMITATIONS**

---

## 1. Resumo executivo

O V5.8 foi endurecido contra abuso, esgotamento de recursos e acesso indevido sem criar planos pagos, assinaturas, restrições comerciais ou funcionalidades novas. As mudanças foram validadas localmente, no Chrome real (desktop e mobile emulado), na CI e em produção com uma conta de QA descartável.

Resultado:

- Suíte completa: **993 passed, 4 skipped, 2 warnings** (139,75 s).
- Suítes focados de segurança, autenticação, isolamento, pesquisa, shopping, deep research, JDUI, SSE, contratos, documentos e IA: **339 passed, 2 skipped** somados.
- Chrome local (stack isolado): **desktop + mobile aprovados**, JDUI, export e screenshots.
- Produção: login, sessão, CSRF, IA, shopping, pesquisa profunda (`modo=pro`), SSE, PWA/HTTPS e Chrome desktop/mobile aprovados.
- CI final: **success** (run `39706107860`, 1m31s).
- Render: deploy automático confirmado; `/api/diag` reporta o commit novo e PC online.
- PC Agent reiniciado pelo Fajulto Studio, banco preservado e schema aditivo aplicado.

Não foi identificado vazamento de segredo, acesso cruzado entre usuários, job órfão bloqueando novas pesquisas ou falha interna mascarada. As limitações residuais estão na seção 7 e não bloqueiam a release.

---

## 2. Escopo implementado

### 2.1 Autenticação e sessão

- Throttle **persistente no SQLite do PC** para login, com reserva atômica **antes** da verificação de senha.
- Janelas por usuário e por IP, configuráveis por ambiente:
  - `JULIA_LOGIN_MAX_FALHAS` (padrão 5/300 s por usuário);
  - `JULIA_LOGIN_MAX_FALHAS_IP` (padrão 20/300 s por IP).
- Limpeza do histórico em login bem-sucedido; poda de 24 h e teto de 20 mil linhas.
- Mensagem genérica preservada; `AuthErro.retry_after` propagado ao relay como HTTP 429 + `Retry-After`.
- Sessões continuam isoladas por `uid`; revogação e epoch existentes foram mantidos e cobertos pela suíte.

### 2.2 Limites técnicos contra abuso

- Novo `rate_limit.py`: janela deslizante com no máximo **4096 chaves**, poda e `Retry-After`.
- Limites por ação e por sujeito (usuário ou IP) + teto global:
  - login, cadastro, IA, início/acompanhamento de pesquisa, documentos, admin, qualidade, tela e entrada remota.
- SSE de pesquisa: **4 conexões por dono** e **20 globais**, com 429 explícito.
- Extração de IP opcional via proxy confiável (`JULIA_TRUST_PROXY=1` no `render.yaml`), sem confiar em cabeçalhos por padrão.

### 2.3 Corpo de requisição e upload

- Limite central antes do parse/spool:
  - JSON de `/api/*`: **2 MiB**;
  - `/api/docs/upload`: **16 MiB** (15 MiB de arquivo + margem multipart);
  - `/api/export/xlsx`: **8 MiB**.
- Rejeição por `Content-Length` e por streaming, com 413.
- Limites de descompactação de OOXML já existentes foram preservados e revalidados (entradas, tamanho por membro, total, razão e caminhos).

### 2.4 CSRF e administração

- CSRF aplicado **centralmente** em `admin_uid` para todo método não-GET/HEAD/OPTIONS.
- Todos os endpoints administrativos de escrita cobertos, inclusive qualidade, convites, registros e configuração.
- Teste parametrizado cobre 11 rotas administrativas.

### 2.5 Pesquisa, cancelamento e jobs órfãos

- Cancelamento e prazo propagados para o agente de busca e o analista de páginas.
- Cadeia de provedores interrompida antes do próximo provedor.
- `salvar_job` preserva atomicamente `cancelada`/`pausada` concorrentes via `CASE` no próprio `UPDATE` (sem janela TOCTOU).
- Retomada manual do usuário usa `forcar_status=True` e vence cancelamento/pausa anteriores.
- `recover_interrupted_research` no boot marca jobs `em_andamento`/`criada` como `interrompida`, preserva plano/evidências e emite evento terminal.
- Parâmetros de intervenção limitados (10 chaves, 40 caracteres por chave, 500 por string, 4 KB no total).

### 2.6 Cabeçalhos de segurança

- HSTS em produção: `Strict-Transport-Security: max-age=31536000`.
- Mantidos: CSP restritiva, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` em `/api/*`.

### 2.7 Arquivos alterados

- `server.py`
- `julia_auth.py`
- `pc_agent.py`
- `research_agents.py`
- `rate_limit.py` (novo)
- `render.yaml`
- `tests/conftest.py` (novo)
- `tests/test_security_hardening_v58.py` (novo, 27 testes)
- `tests/test_audit_fixes.py` (mock compatível com o novo parâmetro `deve_parar`)
- `tests/test_provider_catalog_regressions.py` (mock de sessão compatível com o limite por usuário)
- `qa-artifacts/v58/*` (evidências)

Nenhum plano pago, assinatura, limite comercial ou funcionalidade nova foi introduzido.

---

## 3. Validação local

### 3.1 Suíte completa

Comando:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Resultado final:

```text
993 passed, 4 skipped, 2 warnings in 139.75s
```

Antes das mudanças: `966 passed, 4 skipped in 141.82s`.
O delta de **+27 testes** corresponde ao novo arquivo de regressão de segurança.

Warnings (pré-existentes, não relacionados às mudanças):

- `mss.mss` deprecado em `remoto.py`;
- `timeout` do `TestClient` em `test_research_agents.py` (Starlette).

Evidência: `qa-artifacts/v58/pytest_full_v58_security.txt`.

### 3.2 Suítes focados

| Grupo | Resultado | Tempo | Evidência |
|---|---:|---:|---|
| Segurança, autenticação e isolamento | 66 passed | 14,35 s | `security-auth-isolation-v58.txt` |
| Pesquisa, shopping e deep research | 156 passed, 2 skipped | 51,61 s | `research-shopping-deep-v58.txt` |
| JDUI, frontend e SSE | 59 passed | 4,54 s | `jdui-frontend-sse-v58.txt` |
| Contratos, documentos e IA | 58 passed | 20,11 s | `contracts-docs-ai-v58.txt` |

### 3.3 Regressões de abuso e concorrência

O arquivo `tests/test_security_hardening_v58.py` cobre, entre outros:

- limiter limitado a 4096 chaves e `Retry-After` correto;
- IP de cliente sem confiança em cabeçalho forjável;
- rajada de login com 429 e `Retry-After`;
- corpo JSON acima de 2 MiB rejeitado antes da autenticação;
- CSRF central em 11 rotas administrativas;
- parâmetros de intervenção aninhados/grandes rejeitados;
- throttle persistente sobrevive a reinício do processo;
- login bem-sucedido limpa o histórico;
- 8 logins concorrentes respeitam exatamente o teto atômico;
- cancelamento antes do próximo provedor e da segunda consulta;
- analista não baixa página após o prazo;
- `salvar_job` preserva cancelamento/pausa concorrentes;
- retomada manual vence cancelamento e, se o worker não inicia, volta a `interrompida`;
- recuperação de jobs órfãos no boot;
- HSTS somente em produção.

### 3.4 Chrome local (stack isolado)

`tools/chrome_e2e_v58.py` aprovado:

- Chrome real headless, desktop e mobile emulado;
- login, lista de pesquisas, workspace JDUI, evidências, mídia e export;
- export Markdown de 1.839 bytes via Chrome;
- sem overflow horizontal em 1280×900 e 390×844;
- screenshots em `qa-artifacts/v58/research-workspace-*.png`.

Evidência: `qa-artifacts/v58/chrome-e2e-security.txt`.

---

## 4. CI e entrega

| Etapa | Resultado |
|---|---|
| Commit de endurecimento | `dd74df2` |
| Correção do import do `conftest.py` no CI | `dc71cc8` |
| HSTS + testes finais | `10e7028` |
| Evidências de smoke | `8dba16e` / `217bba7` |
| CI final | **success** — run `39706107860` (1m31s) |
| CI anterior | **success** — run `39705779472` (1m40s) |

Transparência: o primeiro run (`39704561030`) falhou **somente** porque o novo `tests/conftest.py` importava `server` sem inserir a raiz do repositório no `sys.path`. O problema foi corrigido em `dc71cc8`; nenhuma falha de produto foi mascarada. O run final passou.

O push foi fast-forward normal (`8613994 → dd74df2 → dc71cc8 → 10e7028 → 8dba16e → 217bba7`), sem force-push e sem reescrita de histórico.

Render:

- deploy automático concluído;
- `/api/diag` confirmou `pc_online: true` e o commit novo;
- HSTS confirmado em produção;
- PC Agent reconectado automaticamente após cada deploy.

---

## 5. Validação em produção

### 5.1 Smoke autenticado (conta QA descartável)

Conta criada pelo Fajulto Studio local, usada apenas no smoke e removida ao final. Nenhuma senha ou token foi impresso ou gravado.

| Verificação | Resultado |
|---|---|
| `/api/health` | 200, `status=ok`, `configured=true` |
| `/api/diag` | 200, PC online, commit correto |
| `/api/session` anônimo | 401 esperado |
| Criação da conta QA | ok |
| Login real | 200, cookie + CSRF, `uid` confere |
| `/api/session` autenticado | 200, `uid` confere |
| `/api/account` | 200 |
| POST `/api/ai` sem CSRF | 403 esperado |
| IA real | 200, resposta `OK`, sem chave vazada |
| Shopping via IA | 200, resposta honesta com links; preços/estoque não confirmados |
| Pesquisa `modo=pro` | 200, job `rj-...`, 6 etapas |
| SSE de pesquisa | 200, `text/event-stream`, eventos `research` com `data` |
| Resultado da pesquisa | `concluida`, 12 achados, 6 evidências, sem erros |
| Limpeza da conta QA | ok, 1 usuário removido |

Evidência: `qa-artifacts/v58/prod-smoke-v58-security.json`.

### 5.2 Chrome real em produção

- Desktop: 1264 px, sem overflow, app carregado, overlay de login oculto.
- Mobile emulado: 390×844, sem overflow, 71 botões, login persistido.
- Manifest: 200, `application/manifest+json`.
- `sw.js`: 200, `text/javascript`.
- Console: **0 erros** (o 401 de sondagem anônima inicial foi tratado como esperado).
- HTTPS/HSTS: `max-age=31536000`.
- CSP, `nosniff`, `DENY` e `Referrer-Policy` presentes.

Screenshots: `qa-artifacts/v58/prod-chrome-desktop-v58.png` e `prod-chrome-mobile-v58.png`.
Evidência: `qa-artifacts/v58/prod-chrome-v58-security.json`.

### 5.3 Preservação de dados e serviços

- Banco live: `C:\Users\efrai\.julia-mobile\memory.sqlite3`.
- Nenhum dado apagado ou recriado.
- Antes do reinício: nenhuma pesquisa ativa e nenhuma requisição de IA `queued`/`processing`.
- Reinício feito **somente** pelo endpoint local do Fajulto Studio:
  `POST http://127.0.0.1:8755/api/controle/julia/reiniciar`.
- Novo PID do PC Agent: `26684`.
- Schema aplicado no boot: tabela `login_attempts` + 2 índices; 0 tentativas residuais.
- Usuários reais preservados: 5 contas; 18 sessões ativas preservadas.
- Nenhuma conta QA remanescente.
- Hermes, Fajulto Studio e extensão Júlia não foram modificados.

---

## 6. Falhas e correções encontradas

1. **`salvar_job` poderia ressuscitar job cancelado** — corrigido com preservação atômica de `cancelada`/`pausada` via `CASE` no `UPDATE`.
2. **Retomada manual não vencia cancelamento** — corrigida com `forcar_status=True`.
3. **Cancelamento não interrompia a cadeia de provedores/segunda consulta** — corrigido com `deve_parar` e prazo propagados.
4. **Job órfão após reinício bloqueava novas pesquisas** — corrigido com `recover_interrupted_research`.
5. **Login concorrente podia executar scrypt acima do teto** — corrigido com reserva atômica antes da verificação.
6. **CSRF administrativo não era central** — corrigido em `admin_uid`.
7. **Corpo de API sem teto global** — corrigido com middleware por rota.
8. **CI quebrado pelo import do novo `conftest.py`** — corrigido; não era falha de produto.
9. **Shopping externo sem preços/estoque verificáveis** — não é defeito interno; a resposta foi honesta e explícita sobre a limitação.

---

## 7. Limitações residuais (não bloqueantes)

1. **Limiter do relay é volátil e por instância.** Ele é defesa em profundidade; o controle autoritativo de login é o SQLite persistente do PC. Em múltiplas instâncias Render, os buckets não são compartilhados.
2. **`JULIA_TRUST_PROXY=1` confia em `CF-Connecting-IP`/`X-Forwarded-For`.** Um acesso direto à origem Render poderia forjar o IP. Mitigações: tetos globais por ação e throttle persistente por usuário no PC. Recomendação: restringir a origem ao Cloudflare ou usar cabeçalho autenticado de proxy.
3. **429 de login em produção não foi provocado intencionalmente**, para não bloquear o IP real nem contas reais. O comportamento está coberto por testes locais de rajada e concorrência.
4. **Service worker não é registrado pelo app.** `manifest.webmanifest` e `sw.js` são servidos corretamente sobre HTTPS, mas `navigator.serviceWorker.getRegistrations()` retornou 0; o modo offline continua dependendo do IndexedDB. É uma limitação pré-existente de PWA, sem impacto de segurança nesta release.
5. **Render free** pode hibernar/sofrer cold start; indisponibilidade temporária não é falha de segurança.
6. **HSTS sem `includeSubDomains`/preload.** Suficiente para o domínio atual, sem risco para subdomínios.
7. **Shopping depende de sites externos.** Bloqueios 403/429 e páginas sem dados estruturados podem impedir preço/estoque; o produto responde com limitação honesta, sem inventar dados.

---

## 8. Rollback

Se necessário:

1. Reverter `10e7028` (código) com um commit normal de revert; não usar force-push.
2. O schema `login_attempts` é **aditivo** e compatível com versões anteriores; não há migração destrutiva.
3. O Render fará novo deploy automático.
4. Reiniciar o PC Agent pelo Fajulto Studio somente após confirmar que não há pesquisa/IA em andamento.
5. Nenhum dado precisa ser apagado para rollback.

---

## 9. Decisão

**GO_WITH_LIMITATIONS.**

Todos os controles de segurança previstos foram implementados, testados e verificados em produção. Não há falha crítica aberta, vazamento de segredo, acesso cruzado ou perda de dados. As limitações da seção 7 são arquiteturais/conhecidas, estão documentadas e possuem mitigações; nenhuma impede o uso seguro da V5.8.

**Assinatura técnica:** validação automatizada + Chrome real + produção autenticada + CI verde + Render/PC sincronizados.
