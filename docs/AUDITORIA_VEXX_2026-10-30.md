# Auditoria técnica e de produto — Vexx AI

**Data:** 30/10/2026 (produção revalidada em 01/11/2026, 00:00 -03)  
**Alvo:** `julia-mobile-v0.2` (PC agent + relay Render + PWA), banco vivo `~/.julia-mobile/memory.sqlite3` e deploy `https://vexx-ai.onrender.com`  
**Método:** leitura de código, testes automatizados, consultas read-only ao SQLite de produção, chamadas HTTP ao relay, inspeção de artefatos de QA e documentação interna.  
**Natureza:** auditoria com remediação operacional posterior. O diagnóstico abaixo é a linha de base de 30/10; a Seção 1.5 registra o que foi corrigido em 01/11.

> **Veredito curto:** o Vexx já tem uma base de engenharia acima da média para um assistente local-first — proveniência, isolamento por dono, SSRF, CSRF, orçamentos de pesquisa e arquivos versionados. Ele **ainda não é Perplexity-class** porque a resposta comum não é retrieval-first, a pesquisa profunda superfiltra e falha “concluída” com zero evidências, as citações não são inline/verificadas de ponta a ponta e a operação não tem backup agendado, retenção nem observabilidade de produção.

---

## 1. Sumário executivo

### 1.1 O que o Vexx é hoje

O Vexx é um **assistente pessoal local-first**: o PC do dono é a fonte da verdade (SQLite + arquivos + chaves), o Render é um relay WebSocket/SSE, e o celular é a interface PWA. Isso é um diferencial real de privacidade e custo, não um defeito. O problema não é a arquitetura; é a **qualidade do caminho de resposta** e a **maturidade operacional**.

### 1.2 Os seis achados que mais importam

| ID | Severidade | Achado | Impacto |
|---|---|---|---|
| P0-1 | Crítico | Cadastro público aberto, sem aprovação, e **5/5 contas são admin**; 4 têm controle remoto liberado | Abuso de cota/LLM, escalada de privilégio e risco de controle do PC |
| P0-2 | Crítico | **3 de 5 jobs de pesquisa ao vivo terminaram “concluída” com 0 evidências**; o job “profunda” abriu 0 páginas | Resultado sem base apresentado como concluído; quebra de confiança |
| P0-3 | Crítico | O chat comum **não é retrieval-first**: só pesquisa se palavras-gatilho aparecerem; tool calls do modelo são descartadas, não executadas | Respostas factuais sem fonte, com aparência de autoridade |
| P0-4 | Crítico | **Drift de deploy:** relay em `a2caf6e` (30/10 00:17), agente do PC rodando `dd04190` (29/10 22:14) | UI nova sobre backend velho; funcionalidades podem falhar de forma intermitente |
| P0-5 | Crítico | **Agente do PC offline em 31/10 22:34:** `/api/diag` → `pc_online:false`, `agente_ha:-1`; `/api/health` continua `ok` | Backend do PC indisponível; contas do PC não logam; o health não serve como readiness |
| P1-1 | Alto | Modelo padrão `poolside/laguna-s-2.1:free`, sem `JULIA_AI_FALLBACKS`; **18/171 requisições falharam** (429, 500, vazio, timeout) | 10,5% de falhas visíveis ao usuário; sem redundância |

### 1.3 O que já está bom

- **Segurança de base:** cookie assinado HttpOnly/SameSite=Strict, CSRF HMAC + checagem de Origin, scrypt para senhas, throttle de login, revogação de sessão, limites de corpo, CSP/HSTS, token de agente, downloader SSRF-safe e grant explícito para tela/controle remoto.
- **Arquivos e documentos:** upload de 15 MB, PDF/DOCX/XLSX/CSV/HTML/JSON, chunking, FTS5/BM25, busca com fallback de conteúdo integral, arquivos gerados versionados com SHA-256, isolamento por dono e download via relay.
- **Pesquisa:** orçamentos por modo, plano/checkpoint/retomada, cache com TTL, síntese extrativa com quotes literais, revisão de suporte separada, exports reais md/csv/json e workspace de pesquisas.
- **UX:** PWA offline, streaming SSE, citações em cards, JDUI com 19 componentes, projetos, exports, compartilhamento nativo e tela remota.

### 1.4 O que falta para ser Perplexity-class

1. **Retrieval-first de verdade** em toda pergunta factual, não só quando o usuário escreve “pesquise”.
2. **Citações inline confiáveis** e verificação de suporte também no chat rápido, não só no job profundo.
3. **Pesquisa profunda que não “conclui” sem evidência** e que produza relatório longo, não 5 parágrafos.
4. **Operação de produção:** backup agendado, retenção, logs, métricas, alertas, canário e rollback.
5. **Paridade de UX:** seletor Auto/Quick/Pro/Deep, perguntas relacionadas, voz e link público — depois dos P0.

### 1.5 Remediação aplicada em 01/11/2026

**Agente de produção restaurado**

- Processo único: PID `16540`, `pythonw.exe`, wrapper `agent_runtime.py --script pc_agent.py`, checkout `vexx-pc-agent-publish-dd6f5c4`.
- Início: `2026-11-01T21:34:28-03`; recibo `C:\Users\efrai\.julia-mobile\ops-general-publish-dd6f5c4\standalone-receipt.json` (`revision dd6f5c4`, `old_pid 16224`, `new_pid 16540`, backup `before-1793579666.sqlite3`).
- Relay de produção `https://vexx-ai.onrender.com`; token DPAPI de 64 caracteres de `%APPDATA%\FajultoStudio\julia_mobile_token.dat` (o token de 8 caracteres do `.env` foi rejeitado com 403).
- `/api/diag` → `pc_online:true`, `commit:dd6f5c48e377`, `instance:78fd5ef0`; `/api/auth/config` → `convite/true/agent_online:true`; 328 mensagens preservadas antes/depois.
- Log: `C:\Users\efrai\.julia-mobile\ops-general-publish-dd6f5c4\agent-start.log`.
- Controle remoto continua desligado no agente (`JULIA_REMOTE` ausente).

**P0-1 aplicado no banco vivo**

- Backup verificado: `C:\Users\efrai\.julia-mobile\ops-production\pre-p0-1-20261101T015755Z.sqlite3` (4,12 MB, `quick_check=ok`).
- `modo_cadastro=convite`, `exigir_aprovacao=1`.
- Único admin ativo/aprovado: `efrain` (`u-a8295878023b`, 45 sessões e 216 mensagens).
- `owner`, `local`/`efrai`, `efraisir` e `iasdcentralubata` rebaixados para `user`; dados preservados.
- `remote_ok=1` apenas em `efrain`; 47 sessões revogadas; 3 convites revogados.
- Evento `p0_1_auth_hardened` no `audit_log`; recibo em `p0-1-auth-hardened.json`.

**P0-1 endurecido no código (testado localmente; deploy pendente)**

- `julia_auth.login_legado_permitido()`: login do `.env` só com `JULIA_ALLOW_LEGACY_LOGIN=1`.
- `server.py` recusa POST `/api/login` legado e cookies `uid=local` quando o opt-in está desligado.
- `julia_auth.registrar()` em modo convite passa a exigir aprovação por padrão.
- `julia_auth.pode_remoto('local')` deixa de ser passe livre: obedece `status`/`remote_ok` da linha e, sem linha, exige o opt-in.
- Regressões cobertas em `tests/test_auth.py` e `tests/conftest.py`; 78 testes focados de auth e 86 testes de relay/rotas passaram.
- **Ainda não deployado:** relay e PC estão operacionalmente em `dd6f5c4`, mas esse commit não contém o código P0-1; até o deploy, a proteção efetiva é a mudança no SQLite e o agente sem `JULIA_REMOTE`.

**P0-2 endurecido no código (testado localmente; deploy pendente)**

- `research_agents.executar()` só marca `concluida` quando existe pelo menos uma evidência realmente lida; sem isso, o job vira `interrompida` e recebe a pendência `sem evidências lidas suficientes`. O resultado parcial e a síntese extrativa são preservados.
- `agente_auditor()` agora falha com `NO_EVIDENCE` quando não há evidência (ou não há evidência lida), em vez de devolver `ok=True` com zero problemas.
- `listar_jobs()` passou a expor `evidencias` e `research_outcome`, permitindo que a lista de pesquisas mostre “sem evidências lidas” e o estado real da cobertura.
- Cada candidato descartado grava, de forma limitada a 60 entradas, `usados.rejection_reasons` com domínio, motivo (`ENTITY_MISMATCH`, `COVERAGE`, `FETCH_BLOCKED`, `SKIPPED_DUPLICATE` etc.) e etapa; a URL é armazenada sem query string.
- `research_view` marca jobs terminais sem leitura como “sem evidências lidas” e mostra um acordeão “Fontes descartadas” com os motivos persistidos.
- `public/app.js` exibe o mesmo aviso na lista de pesquisas, não só no workspace.
- Os 3 jobs históricos com 0 evidências continuam `concluida` no SQLite (não foram reescritos); a nova view os rotula como “sem evidências lidas”. A reexecução real dos 3 jobs fica pendente do deploy.
- Testes focados: `tests/test_research_agents.py` 30 passed; constelação de pesquisa/qualidade 134 passed, 2 skipped. Suíte completa desta etapa: **2337 passed, 4 failed, 4 skipped**; a quarta falha foi interferência de execuções paralelas e passou isolada, restando as 3 falhas conhecidas (bench externo e dois testes de frontend). A execução final após P0-3/P0-4/P0-5 está na Seção 9.1.
- **Ainda não deployado:** relay e agente em produção seguem no código `dd6f5c4`, que não contém o P0-2; portanto o P0-2 só protege produção depois do deploy.

**P0-3 implementado no código local (testado; deploy pendente)**

- `pc_agent.classificar_intencao_factual()` é determinístico e conservador: cobre `quem/qual/quando/onde/como`, entidades, datas, números, comparação, recomendação, resumo e “fale sobre”; exclui memória/pessoal, identidade, criação, instrução local, código, cálculo, documento anexado e follow-up curto.
- `ai_montar_mensagens()` dispara `research.pesquisa_rapida()` para pergunta factual mesmo sem palavra-gatilho, desde que `pesquisa_web` esteja ligada, não seja shopping, não haja `doc_id` nem URL do usuário; registra `extras["factual_first"]`.
- `anexar_fontes()` passou a exigir citação inline `[S#]` quando há fonte `status=aberta`; resposta sem citação válida é substituída pelo digest determinístico citado. Para fonte efetivamente lida, a checagem usa `inference_status.grounded_reply` (citação ausente, citação desconhecida ou quote não literal); o fallback P0-3 cobre fonte aberta sem `texto_lido`. `research.resumo_deterministico(..., citar=True)` numera `[S1]..` e `bloco_grounding()` exige citação no corpo.
- Golden set: **30/30** perguntas factuais com busca simulada e `[S1]`; **21/21** controles (pessoal, memória, código local, cálculo, criação, documento, identidade) sem busca.
- `tests/test_factual_first_v510.py`: 63 passed; `tests/test_inference_availability.py`: 23 passed. Constelações: 344 passed (chat/pesquisa/intenção/memória/ferramentas) e 168 passed (research agents/completion/quote catalog/auth/admin).

**P0-4 implementado no código local (testado; deploy pendente)**

- O agente envia `agent_hello` autenticado ao conectar, com commit do checkout, PID, uptime, início, `db_ok` (`PRAGMA quick_check`) e versão do Python. Nenhum dado de usuário entra no hello.
- O relay normaliza e limita esses campos, expõe `agent_commit`, `agent_pid`, `agent_uptime_s`, `agent_db_ok`, `drift`, `drift_status` e `stale` em `/api/diag`.
- Divergência de commit gera `log.error("DRIFT DE DEPLOY...")` no relay no momento da conexão; commit não verificável gera alerta e reprova readiness.
- Produção atual já está alinhada em `dd6f5c4` nos dois lados (relay e checkout do PC), mas o código que reporta o commit do agente ainda não foi deployado; `/api/diag` em produção ainda não mostra `agent_commit`.
- `tests/test_deploy_readiness_v511.py`: 13 passed (hello, drift, commit igual, SQLite inválido, alerta offline, cache `stale` do auth config).

**P0-5 implementado no código local (testado; deploy e instalação do watchdog pendentes)**

- `/api/health` continua liveness do relay. Novo `/api/ready` retorna **503** quando o agente está offline, o hello não chegou, o SQLite não foi verificado ou o commit diverge; retorna 200 apenas com `status:"ok"` e `stale:false`.
- Monitor de disponibilidade no relay alerta no log após `JULIA_OFFLINE_ALERT_S` (padrão 180 s) e `/api/diag` expõe `offline_s` e `alert`.
- `/api/auth/config` preserva a última configuração conhecida e devolve `agent_online:false` + `stale:true` em vez de mascarar como `modo:"fechado"`. A UI mostra “PC offline”, “versão diferente” em drift e mantém os dados locais.
- Agente: reconexão com backoff exponencial + jitter, tratamento de exceção inesperada sem derrubar o loop, log rotativo em `~/.julia-mobile/logs/agent.log`.
- `agent_watchdog.py` opcional: usa o lock do `agent_runtime`, só reinicia com `VEXX_AGENT_SCRIPT` explícito e registra em `watchdog.log`. **Não foi instalado** como tarefa do Windows nem alterou autostart.
- Testes: 13 de readiness + 8 do watchdog. A validação de reboot e a instalação do watchdog ficam pendentes de autorização.

**Estado do deploy**

- Produção roda `dd6f5c4` nos dois lados; o working tree contém P0-1/P0-2/P0-3/P0-4/P0-5 sem commit. Nenhum commit/push foi feito nesta rodada.
- Até o deploy, a proteção efetiva em produção continua sendo o banco endurecido (P0-1), o agente sem `JULIA_REMOTE` e o código `dd6f5c4`; P0-2/P0-3/P0-4/P0-5 de código ainda não valem no Render nem no PC.

---

## 2. Método, escopo e limites

### 2.1 O que foi verificado

| Fonte | Uso |
|---|---|
| Código do repo | 59 módulos Python (~30.664 LOC), 107 rotas, 10 arquivos JS (~8.222 LOC), 158 arquivos de teste, 253 docs |
| Suíte de testes | Execução completa no worktree principal; resultado na seção 9 |
| SQLite de produção | Mensagens, jobs, evidências, eventos, documentos, usuários, sessões, AI requests |
| Deploy Render | `/api/health`, `/api/diag`, `/api/auth/config`, `/sw.js` |
| Processo local | PID, hora de início, commit do checkout de publicação |
| Docs internos | `docs/RESEARCH_CAPABILITY_MATRIX.md`, `docs/v5.9.12/PROGRESS.md`, relatórios de QA |

### 2.2 Limites desta auditoria

- **Não houve validação autenticada de UI em navegador real**; as checagens públicas do deploy foram sem sessão. Não afirme E2E completo.
- A amostra viva é pequena: 5 jobs, 171 requisições de IA, 328 mensagens. Percentuais são indicativos, não estatisticamente robustos.
- Provedores externos variam por dia/hora; uma falha de rede pode não se reproduzir.
- Não foi feito teste de carga, teste de penetração nem restauração real de backup.
- O `README.md` está desatualizado (fala de “9 testes”); a fonte de verdade é o código + suíte.

---

## 3. Arquitetura observada

### 3.1 Visão geral

```
┌────────────────────┐        HTTPS / SSE         ┌─────────────────────┐
│  PWA no celular    │ ◄────────────────────────► │  Relay Render       │
│  app.js / jdui.js  │   cookie assinado + CSRF   │  FastAPI + WS       │
└────────────────────┘                            └──────────┬──────────┘
                                                             │ WebSocket
                                                             │ bearer token
                                                  ┌──────────▼──────────┐
                                                  │  PC Agent (Python)  │
                                                  │  pc_agent.py        │
                                                  │  pesquisa, LLM,     │
                                                  │  docs, arquivos     │
                                                  └──────────┬──────────┘
                                                             │
                                      ┌──────────────────────┼──────────────────────┐
                                      │                      │                      │
                              ┌───────▼───────┐      ┌───────▼───────┐      ┌───────▼───────┐
                              │ SQLite local  │      │ Provedores    │      │ LLM/Hermes    │
                              │ fonte da      │      │ de busca      │      │ + chaves      │
                              │ verdade       │      │ e páginas     │      │ no PC         │
                              └───────────────┘      └───────────────┘      └───────────────┘
```

### 3.2 Componentes e responsabilidades

| Camada | Arquivo principal | Papel | Observação |
|---|---|---|---|
| Relay | `server.py` | Sessão, CSRF, SSE, proxy para o PC, rotas de docs/files/research | 107 rotas; não guarda conteúdo privado |
| Agente | `pc_agent.py` | Orquestra intenção, prompt, pesquisa, anexos, LLM, arquivos | ~5.847 LOC; ponto único de falha |
| Pesquisa síncrona | `research.py` | Busca orquestrada, leitura, cache, grounding | Usada no chat quando há gatilho |
| Deep research | `research_agents.py` | Plano, etapas, orçamento, checkpoint, síntese, auditoria | ~3.314 LOC; jobs persistentes |
| Síntese | `research_synthesis.py` | Redação bounded + revisão de suporte | 1–5 parágrafos; ≤3.000 chars |
| Busca | `search_orchestrator.py` / `search_providers.py` | Provedores, ranking, gates de relevância | ~20 provedores, alguns opcionais |
| Documentos | `docs_agent.py` | Extração, chunking, FTS5/BM25, contexto | Lexical; sem embeddings/OCR |
| Arquivos | `files_agent.py` | Versionamento, SHA-256, path guard | Owner + conversation + nome |
| Auth | `julia_auth.py` | Usuários, papéis, sessões, quotas, convites | 5 admins no banco vivo |
| Admin | `admin_http.py` | Reauth recente + papel admin | Cookie de 10 min |

### 3.3 Fluxos principais

**Chat comum**
1. PWA envia mensagem + CSRF.
2. Relay encaminha ao PC via WebSocket.
3. `pc_agent` monta prompt, memória, documentos e histórico.
4. `intencao_pesquisa()` decide se busca na web — **só com palavras-gatilho**.
5. LLM streama; `anexar_fontes()` adiciona cards de fonte se houve pesquisa.
6. Resposta é persistida no SQLite e sincronizada.

**Pesquisa profunda**
1. Comando “pesquise a fundo…” cria job.
2. Worker monta plano, busca, lê, registra evidências, replaneja.
3. Síntese extrativa + revisão de suporte + auditoria.
4. `research_outcome` é gravado; status do job é definido em `research_agents.py:2296`.
5. UI mostra workspace, progresso e exports.

**Anexos**
1. Upload vai ao PC; extração e chunking.
2. `doc_mencionado()` acha o documento pelo marcador “📎 Documento anexado”.
3. `contexto_documento()` injeta trechos ou conteúdo integral.
4. Modelo responde; **não há verificação pós-geração** de que ele usou o conteúdo.

---

## 4. Matriz de capacidades

Estados: **FUNCTIONAL** (funciona e tem evidência), **PARTIAL** (funciona com limitação), **MISSING** (não existe), **BROKEN** (defeito aberto em produção). Nota de 0 a 5 na coluna “Score”.

| Dimensão | Estado | Score | O que funciona | Lacuna principal |
|---|---|---:|---|---|
| Qualidade da resposta | PARTIAL | 2,5 | Prompt de confiança, grounding, memória, documentos, JDUI | Não é retrieval-first; modelo padrão fraco; anexo pode ser ignorado |
| Citações | PARTIAL | 2,5 | Cards de fonte, IDs `S1`, evidências com quotes, exports | Citações inline não são garantidas/verificadas no chat; numeração depende do modelo |
| Pesquisa profunda | PARTIAL/BROKEN em produção | 1,5 | Plano, checkpoint, orçamento, retomada, auditoria | 3/5 jobs com 0 evidências “concluídos”; relatório limitado a 5 parágrafos |
| Follow-ups | PARTIAL | 2,0 | Histórico, projetos, memória, continuação de conversa | Sem sugestões de perguntas relacionadas; sem decomposição no chat |
| Arquivos/workspaces | FUNCTIONAL | 4,0 | 15 MB, PDF/DOCX/XLSX/CSV/HTML/JSON, FTS5, versionamento, owner-scope | Sem OCR, PPTX/ODT, embeddings ou reranker; HTML vira texto visível |
| UX | FUNCTIONAL | 3,5 | PWA, SSE, citações em cards, JDUI, projetos, exports, offline | Sem voz, seletor de modo, perguntas relacionadas ou link público; label `conclu?da` |
| Confiança | PARTIAL | 2,0 | Avisos de limitação, evidence graph, revisão separada | Status “concluída” com 0 evidências; auditor “0 problemas”; anexo ignorado sem aviso |
| Performance | PARTIAL | 2,5 | Streaming, cache 6h/24h, orçamentos, leitura paralela | p95 31,3 s; sem APM/TTFT; requisição órfã de 47 h |
| Segurança | FUNCTIONAL | 3,0 | CSRF, cookie, scrypt, throttle, SSRF, CSP, grants, owner-scope | Sem MFA; 5 admins; 4 com `remote_ok`; cadastro aberto |
| Operações | PARTIAL/MISSING | 1,0 | Snapshots manuais, CI básico, `/api/health` e `/api/diag` | Produção offline em 31/10; sem backup agendado, retenção, logs rotativos, métricas, alertas ou rollback |

**Leitura correta:** o Vexx é um produto local-first **bom** (3,5/5) e um Perplexity-class **incompleto** (≈2,5/5). As notas não medem “potencial”; medem o que o usuário recebe hoje.

---

## 5. Achados priorizados

## P0 — bloquear antes de divulgar/expandir

### P0-1. Cadastro público aberto + privilégio administrativo excessivo

**Status em 01/11/2026:** banco vivo corrigido (1 admin, convite + aprovação, `remote_ok` só no owner, sessões/convites revogados). Código endurecido e testado, com deploy pendente. Detalhes na Seção 1.5.

**Evidência viva (30/10, com agente online)**

- `GET /api/auth/config` → `{"modo":"aberto","exigir_aprovacao":false,"agent_online":true}`.
- Banco: 5 usuários, **todos `role=admin`, todos ativos/aprovados**:
  - `owner`, `local` (efrai), `u-a8295878023b` (efrain), `u-be1df68ffafc` (efraisir), `u-253834814eb7` (IASD Central de Ubatã).
- 4 dos 5 têm `remote_ok=1` (controle remoto/tela autorizado).
- 3 convites existem, mas todos expirados; o cadastro aberto **não precisa de convite**.
- Config: `modo_cadastro=aberto`, `exigir_aprovacao=0`.
- Em 31/10 22:34, com o agente offline, `/api/auth/config` retorna `{"modo":"fechado","exigir_aprovacao":true,"agent_online":false}` por **fallback** (`server.py:539-544`); o banco continua `aberto/0`. Não confundir o fallback com correção.
- `julia_auth.registrar()` em modo aberto cria conta **já ativa** (`aprovado=True`) quando `exigir_aprovacao=0`.
- Quota padrão por usuário: 120 requisições de IA/hora, 3 simultâneas.

**Causa**
Configuração de produção permissiva + migração `v5981` que promoveu contas humanas a admin (`admin_migration_promoted` no `audit_log`) sem reduzir depois. O código novo até cria `role=user`, mas o passado ficou todo admin.

**Impacto**
- Qualquer pessoa que descubra a URL pode criar conta e consumir LLM/cota.
- Um admin comprometido pode listar/alterar usuários, revogar sessões e **liberar controle remoto do PC**.
- Não há MFA nem separação “owner” vs “admin operacional”.

**Correção P0**
1. Mudar para `modo_cadastro=convite` e `exigir_aprovacao=1`.
2. Reduzir a **1 conta owner/admin**; demais viram `user` ou são desativadas.
3. `remote_ok=1` somente para o owner; conceder por tempo limitado e com auditoria.
4. Exigir MFA para admin (P1) e revisar sessões ativas.
5. Aceite: `/api/auth/config` mostra convite + aprovação; `SELECT role,count(*) FROM users` = 1 admin; `remote_ok` só no owner.

---

### P0-2. Pesquisa profunda “concluída” com zero evidências

**Status em 01/11/2026:** corrigido no código e testado, com deploy pendente. Job sem evidência lida termina `interrompida`, o auditor falha com `NO_EVIDENCE`, a lista expõe contagem/outcome e os motivos de rejeição ficam persistidos. Detalhes na Seção 1.5.

**Evidência viva (5 jobs, todos `status=concluida`)**

| Job | Modo | Buscas | Páginas | Evidências | Outcome | Duração |
|---|---|---:|---:|---:|---|---:|
| `rj-9a764b4ecfc6` | pro | 2/4 | 6/6 | 6 | ausente | 7,1 s |
| `rj-d9eb104b5c1c` | pro | 2/4 | 6/6 | 6 | ausente | 11,9 s |
| `rj-dd1e6bb3e790` | rápida | 1/2 | 3/3 | **0** | `partial` | 3,0 s |
| `rj-80157b50e470` | rápida | 1/2 | 3/3 | **0** | `partial` | 4,6 s |
| `rj-eb925b36e847` | profunda | 3/8 | **0/12** | **0** | `partial` | 9,5 s |

**O caso “profunda” (`rj-eb925b36e847`)**
- Objetivo: comparar `asyncio.TaskGroup` e `asyncio.gather` com documentação oficial.
- 3 buscas, 0 páginas lidas, 3 falhas de provedor.
- 52 candidatos rejeitados pelo gate: 18 + 17 + 17 (`context_mismatch`).
- Provedores: `web` falhou 3×, `ddg` vazio, `searxng` indisponível, `wikipedia` vazio.
- Evento final: `Síntese extrativa com 0 evidências`; auditoria: `0 problemas`.

**Causa raiz no código**
- `research_agents.py:2296`:
  ```python
  job["status"] = "concluida" if not job["pendencias"] or todas_evid else \
      ("concluida" if todas_evid else "interrompida")
  ```
  Se `pendencias` está vazio, o job vira `concluida` mesmo com `todas_evid == []`.
- `research_outcome` é calculado depois e fica `partial`; a UI de lista mostra apenas `job.status`, então o usuário vê “concluída”.
- O auditor não falha quando não há evidências: `auditoria: 0 problemas`.
- O gate de relevância exige 60% de cobertura lexical (`search_orchestrator.py:272`) e aplica checagens duras de entidade; para perguntas comparativas/naturais, isso rejeita documentação oficial legítima.
- O motivo exato de cada rejeição não é persistido (só o código `context_mismatch`), dificultando reparo.

**Impacto**
O pior tipo de falha: **resposta vazia/parcial com selo de concluída**. Destrói confiança e contamina exports, histórico e decisões.

**Correção P0**
1. `concluida` só se `read_sources > 0` **e** síntese revisada; caso contrário `interrompida`/`parcial`.
2. Auditor falha explicitamente com 0 evidências (`audit.ok=false`, problema `NO_EVIDENCE`).
3. UI: badge “sem evidências” na lista, não só no workspace.
4. Persistir motivo de rejeição por candidato (`ENTITY_MISMATCH`, `COVERAGE`, `AD`, etc.).
5. Afrouxar o gate para cobertura por **aspecto/entidade**, não 60% de todos os termos; permitir 1 página por lado em comparações.
6. Adicionar fallback de provedor e retry para `context_mismatch` (ex.: buscar URL oficial diretamente).
7. Aceite: reexecutar os 3 jobs; nenhum `concluida` com 0 evidências; “asyncio” lê ≥2 páginas e registra ≥1 evidência.

---

### P0-3. O chat comum não é retrieval-first; tool calls são descartadas

**Status em 01/11/2026:** corrigido parcialmente no código local e testado, com deploy pendente. O classificador factual determinístico dispara busca automática e respostas com fonte recuperada passam a exigir citação inline; a execução allowlisted de `webresearch` **não** foi implementada e tool calls continuam sanitizadas. Detalhes na Seção 1.5.

**Evidência no código**
- `pc_agent.py:1470` `intencao_pesquisa()` retorna `False` se não houver palavra de `TERMOS_PESQUISA` (`pesquise`, `notícia`, `preço`, `clima`, `hoje`, `fontes`, etc.) nem “encontre/procure”.
- `pc_agent.py:2148` só chama `research.pesquisa_rapida()` se `intencao_pesquisa()` for verdadeiro.
- `tool_protocol.py` **remove** `<tool_call>tools.webresearch{...}</tool_call>` do texto; não executa a ferramenta. O prompt diz “Sem resultado de ferramenta, diga que respondeu pelo conhecimento geral”.
- Resultado: perguntas factuais sem gatilho recebem resposta de conhecimento do modelo, sem busca e sem fonte.

**Evidência de produto**
- A própria UI descreve: “Pesquisa web — IA busca fontes **quando você pedir**”.
- Mensagem antiga no banco contém `<tool_call>tools.webresearch{...}` cru, prova de que o modelo tenta chamar busca e o protocolo não executa.
- `anexar_fontes()` só substitui a resposta por resumo determinístico em casos de promessa/negação/tool call; não verifica suporte claim-by-claim no chat rápido.

**Impacto**
- Respostas factuais com aparência de autoridade e sem citação.
- O usuário precisa saber “pedir” pesquisa; o comportamento padrão não é Perplexity.
- Tool calls descartadas podem virar texto estranho ou respostas inventadas.

**Correção P0**
1. Classificador de intenção factual (não só palavras): entidades, datas, números, “quem/qual/quando/onde/como”, comparações e pedidos de recomendação → busca automática.
2. Ou executar tool calls de busca de forma controlada (allowlist `webresearch`) em vez de descartar.
3. Toda resposta com fonte recuperada deve citar; se o modelo ignorar, cair para resumo determinístico.
4. Aceite: 30 perguntas factuais do golden set → ≥90% com ≥1 fonte e citação inline; nenhuma tool call não executada no texto final.

---

### P0-4. Drift de deploy entre relay e agente do PC

**Status em 01/11/2026:** mitigado operacionalmente (relay e PC agora em `dd6f5c4`) e corrigido no código local com hello autenticado, `drift` em `/api/diag` e alerta no relay; deploy pendente. Detalhes na Seção 1.5.

**Evidência (30/10, quando o agente ainda estava online)**
- Relay Render: `/api/diag` → `commit: "a2caf6eb8b77"`, `pc_online: true`, `agente_ha: 462`.
- Checkout de publicação no PC: `dd04190` (“fix: preserve exact text and full content for file edits”, 29/10 22:14).
- Processo do agente: PID 41664, iniciado **29/10 22:18:58**.
- Commit do relay: `a2caf6e` em **30/10 00:17:44**, ~2 h mais novo.
- Diff `dd04190..a2caf6e`: 35 arquivos, +6.273/−3.539, incluindo `public/app.js`, `research.py`, `research_agents.py`, `server.py`, `remoto.py`, `shopping.py`.
- O agente em execução **não tem** as mudanças de pesquisa/UI do relay.

**Impacto**
- UI nova chama comportamentos que o backend velho não tem (citações, comparison matrix, screen-to-research).
- Falhas intermitentes difíceis de reproduzir; “funciona no meu teste” vs produção.
- Rollback e suporte ficam ambíguos.

**Correção P0**
1. Publicar o **mesmo commit** no Render e no checkout do PC; reiniciar o agente.
2. `/api/diag` deve comparar `commit` do relay com `commit` reportado pelo agente e expor `drift: true`.
3. Startup do agente falha (ou alerta) se o commit não bater com o esperado.
4. Aceite: `relay.commit == agent.commit`; `/api/diag` mostra `drift:false`; smoke de chat/pesquisa/anexo passa.

---

### P0-5. Agente do PC offline e `/api/health` sem readiness

**Status em 01/11/2026:** agente restaurado e online (PID `16540`, `dd6f5c4`). Readiness real, cache `stale` do auth config, backoff com jitter e log rotativo foram implementados no código local; watchdog opcional criado, mas **não instalado**. Deploy e teste de reboot pendentes de autorização. Detalhes na Seção 1.5.

**Evidência (31/10/2026, 22:34 -03)**
- `GET /api/diag` → `{"pc_online":false,"agente_ha":-1,"commit":"a2caf6eb8b77","instance":"065044bf"}`.
- Nenhum processo `pythonw.exe`/`pc_agent.py` em execução; o PID 41664 não existe mais.
- `GET /api/health` → `{"status":"ok","configured":true}` mesmo com o PC offline.
- `GET /api/auth/config` → `{"modo":"fechado","exigir_aprovacao":true,"agent_online":false}` por fallback, não por mudança no banco (que segue `aberto/0`).
- `server.py:508-509`: login de contas do PC falha com 503 quando `relay.ws is None`.
- O supervisor tem `autostart: true`, mas não há evidência de watchdog, backoff ou alerta de queda; também não há log persistente para saber se houve crash ou parada manual.
- Última requisição de IA registrada: 29/10 18:06 UTC; último job: 29/10 02:35 UTC.

**Impacto**
- O aplicativo está **indisponível para contas do PC** e para chat/pesquisa/anexos.
- Monitoramento externo vê `status:ok` e não detecta a queda.
- A UI pode interpretar o fallback como “cadastro fechado”, mascarando o estado real.

**Correção P0**
1. Religar o agente e confirmar reconexão ao relay; investigar por que o autostart não o manteve vivo.
2. Adicionar watchdog com backoff e restauração automática; registrar início/crash/exit em log persistente.
3. Separar `/api/health` (liveness do relay) de `/api/ready` (agente conectado + SQLite íntegro + commit esperado); readiness deve retornar 503 quando o PC estiver offline.
4. Propagar `agent_online:false` para a UI com mensagem explícita, preservando a última configuração conhecida com `stale:true` em vez de “fechado”.
5. Alertar quando `pc_online=false` por mais de 2–5 min e expor PID, commit e uptime do agente no `/api/diag`.
6. Aceite: após reinício do PC, agente reconecta em <60 s; `/api/ready` falha enquanto offline; alerta dispara; UI mostra “PC offline”, não “cadastro fechado”.

---

## P1 — corrigir nas próximas 2–6 semanas

### P1-1. Modelo padrão gratuito sem fallback e 10,5% de falhas

**Evidência**
- `hermes_bridge.DEFAULT_MODEL = "poolside/laguna-s-2.1:free"`.
- `JULIA_AI_FALLBACKS` vazio no `.env` de publicação.
- 171 requisições: 151 `completed`, **18 `failed`**, 2 `cancelled`.
- Falhas: 8× laguna, 3× Gemini 2.5, 1× cada Gemini 3.x, DeepSeek 402, Mistral 429, timeout, resposta vazia, relay caiu, agente reiniciado.
- Latência fim-a-fim: p50 **8,5 s**, p90 **27,1 s**, p95 **31,3 s**. Há uma linha órfã de **47 h** (“Agente reiniciado durante a geração”).
- Modelo gratuito é o padrão em 143/171 requisições; o usuário vê 429/500/vazio sem redundância.

**Correção**
1. Configurar `JULIA_AI_FALLBACKS` com 2–3 modelos pagos/estáveis (DeepSeek/Gemini/Groq/Mistral já têm chaves no PC).
2. Retry com backoff em 429/5xx/timeout; circuit breaker por provedor.
3. Watchdog para requisições sem delta > N segundos; marcar `failed` e liberar UI.
4. Roteamento por tarefa: modelo barato para resumo, modelo forte para síntese/revisão.
5. Aceite: 429 forçado cai para fallback e responde; falha visível <2%; p95 <15 s.

---

### P1-2. Chat rápido sem verificação de suporte e citações inline frágeis

**Evidência**
- `pesquisa_rapida()` devolve fontes e grounding, mas **não** passa por `research_synthesis`/revisão de suporte.
- `anexar_fontes()` anexa um fence JDUI de fontes; não valida se o texto do modelo é sustentado.
- O parser de citações do `app.js` (`inlineFmt`) mapeia `[S1]` a URLs apenas a partir de um bloco final “Fontes:”/“Referências:”. O fence JDUI de sources **não alimenta** esse mapa.
- Formato do bloco gerado: `- [S1 Título](url)`; o regex de ID espera `[S1]`, então a numeração pode não resolver.
- Deep research tem `evidence_ids` internos, mas a resposta renderizada não anota cada frase com pílulas `[S#]`.
- O commit `a2caf6e` trocou o markup para `class="citation-pill"` sem atualizar o contrato do frontend: `test_render_markdown_no_node` falha em `real-citation`.
- O mesmo commit adicionou `onerror="this.style.display='none'"` inline no favicon do popover (`public/app.js:3420`); o CSP `script-src 'self'` bloqueia o handler, e `test_chat_imagens_csp_e_scroll_ancorado` falha — ou seja, o favicon quebrado não é escondido.
- O favicon é carregado de `https://www.google.com/s2/favicons?domain=...`; cada abertura de popover envia o domínio citado ao Google, o que contradiz o posicionamento local-first.
- O popover diz “Fonte citada como evidência para esta resposta na pesquisa profunda” mesmo em respostas rápidas, sem checar se a fonte sustenta o claim.

**Impacto**
- Citações viram decoração no fim, não prova inline.
- Usuário não consegue clicar na fonte exata de uma afirmação.
- Resposta rápida pode contradizer a fonte e ainda exibir “Fontes”.

**Correção**
1. Mapear IDs do fence JDUI para o citation map do chat.
2. Numerar fontes de forma estável (`S1..Sn`) e usar o mesmo ID no texto e no card.
3. Verificação leve de suporte no chat rápido (quote/claim ou entailment barato); se falhar, resumo determinístico.
4. “Copiar com citações” e hover com título/trecho/domínio.
5. Remover handlers inline do popover e atualizar `real-citation` para o novo markup; suíte frontend verde no HEAD.
6. Substituir o favicon do Google por avatar local (letra/ícone) ou proxy sem terceiro; não vazar domínio citado.
7. Aceite: 20 respostas com busca → 100% das pílulas resolvem para URL; 0 claims numéricos sem fonte; 0 falha de teste frontend; 0 requisição a domínio de terceiro ao abrir citação.

---

### P1-3. Anexo pode ser ignorado pelo modelo, sem aviso

**Evidência viva**
- Pergunta: “sobre o que é esse index.html?” + `📎 Documento anexado: "index.html"`.
- `doc_mencionado()` retorna `doc-dd7cb84578dd`; `contexto_documento()` retorna 141 chars, `modo=completo`.
- O pipeline **forneceu** o conteúdo; a resposta do modelo (`reflection/beam...:free`) disse: “não consigo visualizar o conteúdo do arquivo”.
- Não há pós-checagem “se doc_id e o modelo nega acesso, substituir por resumo determinístico”.

**Impacto**
- O recurso de anexos parece quebrado mesmo quando a extração funciona.
- Usuário perde confiança e reenvia/cola conteúdo.

**Correção**
1. Guard pós-geração: se `doc_id` e a resposta contém “não consigo ver/abrir/ler” ou não menciona o documento, usar resumo extrativo/título + trechos.
2. Para `.html`, preservar uma versão de código (não só texto visível) quando a pergunta for “o que é este código/arquivo”.
3. Incluir no prompt um lembrete curto e testável (“o conteúdo está abaixo; responda com base nele”).
4. Aceite: teste de anexo HTML/PDF/DOCX → resposta cita o conteúdo ou assume limitação explicitamente; 0 “não consigo ver” com conteúdo disponível.

---

### P1-4. Documentos: busca lexical, sem OCR/PPTX/ODT e sem semântica

**Evidência**
- `docs_agent.py` usa FTS5/BM25 (`unicode61 remove_diacritics 2`) e fallback de conteúdo integral; não há embeddings, vetores, reranker ou cross-encoder.
- Formatos: PDF, DOCX, XLSX, CSV/TSV, TXT/MD, HTML, JSON; **sem** `.pptx/.ppt/.odt/.ods/.epub` e **sem OCR** para PDF escaneado (matriz interna já admite `NOT_IMPLEMENTED`).
- HTML é extraído como texto visível; markup/código não é preservado.
- 3 documentos no banco, 8 chunks; pasta `docs/` tem **8.849 arquivos / 104,4 MB** (órfãos de execuções antigas).

**Impacto**
- Perguntas parafraseadas ou conceituais perdem trechos relevantes.
- PDF escaneado, apresentação e ODT não funcionam.
- Custo de disco e risco de privacidade por arquivos órfãos.

**Correção**
1. Busca híbrida: FTS5 + embeddings locais (ex.: modelo pequeno) + reranker; avaliar recall@5.
2. OCR opcional (Tesseract/PaddleOCR) com aviso de custo.
3. Suporte a PPTX/ODT/ODS/EPUB ou recusa explícita com conversão.
4. GC de arquivos sem documento; retenção e criptografia em repouso.
5. Aceite: 50 perguntas paráfrase → recall@5 ≥85%; PDF escaneado responde; 0 arquivo órfão após GC.

---

### P1-5. Operação: sem backup agendado, retenção, logs ou métricas

**Evidência**
- `~/.julia-mobile/backups/` tem **1** snapshot manual (`v597-preupdate-20261023-163438.sqlite3`, 3,0 MB); há snapshots manuais espalhados em `ops-*`, o mais novo de 29/10 12:50.
- Não há scheduler, retenção, verificação de integridade, cópia off-device nem teste de restauração.
- `docs/` 8.849 arquivos / 104,4 MB; `runtime/` 720 arquivos; sem limpeza.
- `pc_agent.py` usa `logging.basicConfig` para stderr; o processo vivo é `pythonw.exe` (sem console). Não há `RotatingFileHandler` nem log persistente garantido.
- `metricas_provedores()` existe, mas a matriz interna diz “sem chamador em produção”.
- `/api/health` e `/api/diag` são básicos; não há SLO, alerta, dashboard ou canário.
- Em 31/10, `/api/health` retornou `ok` com o agente offline — é liveness, não readiness; não existe endpoint que teste PC + SQLite + commit.
- CI: GitHub Actions roda `pytest -q tests` + `node --check public/app.js`; sem cobertura, lint, typecheck, security scan ou E2E.

**Impacto**
- Perda do SQLite = perda de conversas, memórias, evidências e arquivos.
- Falhas silenciosas; tempo de diagnóstico alto.
- Deploy sem rollback testado.

**Correção**
1. Backup diário online (`sqlite3 .backup`), 7 diários + 4 semanais + 12 mensais, cópia externa criptografada, `PRAGMA integrity_check` e restore drill mensal.
2. Retenção de docs/runtime e GC de órfãos.
3. Log rotativo (`RotatingFileHandler`, 10 MB × 10) e correlação por `request_id`/`job_id`.
4. Métricas: uptime do agente, falha por provedor, jobs com/sem evidência, p50/p95, 429, fila.
5. Alertas: agente offline >5 min, pesquisa 0 evidência, backup >24 h, erro 5xx >2%.
6. CI: `ruff`, `mypy` (módulos críticos), `pip-audit`, cobertura mínima, smoke Playwright e deploy staging.
7. Aceite: restore real documentado; backup <24 h; alerta de agente offline testado; dashboard com 7 dias.

---

### P1-6. “Pesquisa profunda” entrega resumo, não relatório

**Evidência**
- `research_synthesis.SYSTEM`: “Use 1 a 5 parágrafos, até 500 caracteres cada”; `generate()` rejeita `len(rendered) > 3000`.
- Orçamentos: rápida 2 buscas/3 páginas/30 s; pro 4/6/60; profunda 8/12/120; investigativa 12/20/300.
- Jobs “pro” bem-sucedidos: 2 buscas, 6 páginas, 6 evidências, 7–12 s.
- Não há sumário executivo, seções, tabela de evidências, limitações por seção, apêndice ou bibliografia numerada no corpo.

**Impacto**
- Para “deep research” de verdade (due diligence, comparação de mercado, revisão técnica), 5 parágrafos são insuficientes.
- Perplexity-class espera relatório multi-seção, 1,5–3 mil palavras, com citações por parágrafo.

**Correção**
1. Pipeline de relatório: outline → seções → verificação por seção → sumário → limitações → bibliografia.
2. Aumentar limite para 1.500–3.000 palavras, mantendo quotes e revisão.
3. Tabela de evidências e “confidence” por claim.
4. Export DOCX/PDF e link público (P2).
5. Aceite: 3 relatórios de 1.500+ palavras, 15+ fontes, 0 claims numéricos sem evidência.

---

### P1-7. Paridade de UX: falta o que o usuário espera de um Perplexity

**Evidência**
- Sem voz: `Permissions-Policy` bloqueia `microphone=()`, não há `SpeechRecognition`/`getUserMedia`/`MediaRecorder`.
- Sem seletor Auto/Quick/Pro/Deep na UI; `/api/research/start` aceita `modo`, mas a UI não expõe.
- Sem perguntas relacionadas/follow-ups sugeridos; `follow_up` existe só no motor de pesquisa (replanejamento), não na UI.
- Sem link público de resposta; “Compartilhar” usa Web Share/clipboard.
- Label visível `conclu?da` em `public/app.js:1238` (mojibake).
- Sem anotações/versionamento de relatório no workspace.

**Impacto**
- O produto parece “chat com pesquisa” e não “motor de resposta”.
- Usuário não descobre modos nem continua a investigação.

**Correção**
1. Seletor de modo no composer (Auto/Quick/Pro/Deep) com orçamento e custo.
2. 3–5 perguntas relacionadas após cada resposta (a partir de lacunas/evidências).
3. Voz: relaxar `Permissions-Policy` só para o próprio origin e usar Web Speech API com fallback.
4. Link público assinado, expiração e revogação (P2, após auth).
5. Corrigir `conclu?da` e revisar strings UTF-8.

---

### P1-8. Admin/segurança: MFA, menor privilégio e sessões

**Evidência**
- Sem TOTP/MFA/2FA em código.
- Senha mínima 8; scrypt; throttle 5 falhas/5 min por usuário, 20/5 min por IP.
- Sessão 12 h; cookie HttpOnly/Secure/SameSite=Strict; CSRF HMAC; Origin check.
- Admin reauth 10 min, mas depende de papel admin e PC online.
- 5 admins, 4 `remote_ok`; sem lista de dispositivos/sessões no UI.
- 47 sessões no banco, 45 não revogadas e **todas já expiradas**; não há rotina de limpeza, então o histórico de sessões cresce sem GC.
- CSP forte, mas `script-src 'self'` sem nonce/hash; `img-src https:` amplo.

**Correção**
1. MFA obrigatório para admin/owner.
2. Tela de sessões/dispositivos com revogação individual e “sair de todos”.
3. Notificação de novo login/admin action.
4. Revisar CSP para nonce/hash; limitar `img-src` a domínios conhecidos se possível.
5. Aceite: login admin sem MFA bloqueado; sessão revogada em <1 min; auditoria de ação admin.

---

## P2 — evoluir depois dos P0/P1

| ID | Tema | Ação | Por que |
|---|---|---|---|
| P2-1 | Qualidade de fonte | Data de publicação, autoridade, contradição, dedupe por URL canônica | Evita “fonte encontrada” ≠ “fonte confiável” |
| P2-2 | Follow-ups | Sugestões de perguntas, clarificação de escopo, “investigar mais” | Aumenta retenção e profundidade |
| P2-3 | Monitoramento | “Vigiar tema”, alertas de mudança, research contínuo | Caso de uso recorrente |
| P2-4 | Colaboração | Projetos compartilhados, comentários, versionamento de relatório | Uso em equipe |
| P2-5 | Custo/roteamento | Router por tarefa, budget por usuário, cache semântico, batch | Sustentabilidade do free |
| P2-6 | Escala | Fila, múltiplos agentes, storage de objetos, load test | Sair do single-PC sem perder local-first |
| P2-7 | Docs/runbook | README real, arquitetura, API, SLOs, on-call | Reduz bus factor |
| P2-8 | Acessibilidade/i18n | Teclado, leitores de tela, EN/ES | Alcance |

---

## 6. Scorecard vs. Perplexity

| Dimensão | Vexx hoje | Perplexity-class | Gap |
|---|---|---|---|
| Retrieval-first | Só com gatilho | Sempre que factual | **Grande** |
| Citações inline | Cards + bloco final | Número clicável por claim | **Grande** |
| Deep research | 5 parágrafos / 3k chars | Relatório multi-seção | **Grande** |
| Follow-ups | Histórico + memória | Sugestões + clarificação | Médio |
| Arquivos | Forte (15 MB, 7 formatos) | Semântica + OCR + PPTX | Médio |
| UX | PWA completa, sem voz/modo/share | Voz, modo, share, atalhos | Médio |
| Trust | Avisos, mas status inconsistente | Estado terminal honesto | **Grande** |
| Performance | p50 8,5 s / p95 31,3 s | TTFT <2 s, resposta <10 s | Médio |
| Security | Boa base, sem MFA | MFA, least privilege, tenant | Médio |
| Ops | Manual | Backup, SLO, alertas, canário | **Grande** |

**Nota global:** ≈**2,5/5** como Perplexity-class; ≈**3,5/5** como assistente local-first com pesquisa **em capacidade** — o agente está online e alinhado em `dd6f5c4`, mas o código P0 desta rodada ainda não foi deployado.

---

## 7. Roadmap P0/P1/P2

### P0 — 0 a 2 semanas (bloquear divulgação)

**Status em 01/11/2026:** itens 1, 2 e 7 implementados no código local; item 5 alinhado operacionalmente em `dd6f5c4`, mas o `drift` só vale após deploy; item 3 parcial (motivos persistidos; gate por aspecto e retry pendentes); item 4 parcial (retrieval-first + citação; allowlist de tool call pendente); item 6 parcial (retry/backoff e watchdog do agente prontos; fallback de modelo pendente). **Nada foi commitado/publicado nesta rodada.**

| # | Entrega | Esforço | Aceite |
|---|---|---|---|
| 1 | Fechar cadastro + reduzir admins + `remote_ok` só owner | 0,5–1 dia | 1 admin; convite+aprovação; 0 remote_ok indevido |
| 2 | Estado terminal honesto da pesquisa + auditor 0 evidência | 1–2 dias | 0 job `concluida` com 0 evidências; UI badge |
| 3 | Gate de relevância por aspecto + motivos persistidos + retry | 2–4 dias | 3 jobs reexecutados com ≥1 evidência |
| 4 | Retrieval-first no chat + executar/allowlist tool call | 2–4 dias | 30 perguntas factuais → ≥90% com fonte |
| 5 | Deploy parity relay/PC + `drift` no `/api/diag` | 0,5 dia | commits iguais; smoke ok |
| 6 | Fallback de modelo + retry/backoff + watchdog | 1–2 dias | 429 forçado responde; falha <2% |
| 7 | Religar agente + `/api/ready` + watchdog/alertas | 1 dia | `pc_online:true`; readiness 503 offline; alerta testado |

### P1 — 2 a 6 semanas (qualidade e operação)

| # | Entrega | Esforço | Aceite |
|---|---|---|---|
| 8 | Verificação de suporte no chat rápido | 3–5 dias | 0 claim numérico sem fonte |
| 9 | Citações inline estáveis + copiar com citações | 3–5 dias | 100% pílulas resolvem; suíte frontend verde |
| 10 | Guard de anexo + HTML code-aware | 2–3 dias | 0 “não consigo ver” com conteúdo |
| 11 | Busca híbrida + reranker + OCR/PPTX | 2–4 semanas | recall@5 ≥85%; PDF escaneado ok |
| 12 | Backup agendado + retenção + restore drill | 3–5 dias | backup <24 h; restore documentado |
| 13 | Relatório multi-seção + DOCX/PDF | 1–2 semanas | 1.500+ palavras, 15+ fontes |
| 14 | Modo Auto/Quick/Pro/Deep + related questions | 1 semana | UI + API + testes |
| 15 | MFA admin + sessões/dispositivos | 1 semana | admin sem MFA bloqueado |
| 16 | Logs rotativos + métricas + alertas + CI | 1–2 semanas | dashboard 7 dias; alerta testado |

### P2 — 6 a 12 semanas (diferenciação)

| # | Entrega | Aceite |
|---|---|---|
| 17 | Voz + link público + compartilhamento | voz PT-BR; link expira/revoga |
| 18 | Monitoramento de temas / research contínuo | alerta de mudança em 24 h |
| 19 | Colaboração/workspaces | 2+ usuários por projeto com ACL |
| 20 | Router de custo + cache semântico | custo/consulta −30% |
| 21 | Escala multi-agente/fila | 100 conversas concorrentes sem degradar |
| 22 | Docs/runbook/SLOs | on-call consegue restaurar em <1 h |

### Ordem recomendada

1. **Agora:** autorizar o deploy do mesmo commit no Render e no checkout do PC; validar `/api/diag` (`agent_commit`, `drift:false`) e `/api/ready` 200.
2. **Semana 1:** P0-2 (gate por aspecto/retry), P0-3 (allowlist de `webresearch`) e P1-1 (fallback de modelo).
3. **Semana 2:** instalar watchdog/autostart com autorização e testar reboot; smoke completo de chat/pesquisa/anexo.
4. **Semanas 3–4:** P1-2/P1-3 (citações/anexo), P1-5 (backup/logs).
5. **Semanas 5–8:** P1-4 (híbrida/OCR), P1-6 (relatório), P1-7/P1-8 (UX/MFA).
6. **Semanas 9–12:** P2.

---

## 8. Fix / Improve / Add / Create

### Corrigir (defeito)
- Cadastro aberto + admins demais + `remote_ok` amplo.
- `concluida` com 0 evidências; auditor “0 problemas”.
- Gate de relevância 60% + `context_mismatch` sem motivo.
- Drift relay/PC.
- Modelo sem fallback; 429/500/vazio.
- Anexo ignorado sem guard.
- Label `conclu?da`.
- Requisição órfã de 47 h.

### Melhorar (já existe, mas fraco)
- Citações inline e verificação de suporte no chat rápido.
- Relatório profundo (profundidade, seções, bibliografia).
- Busca de documentos (híbrida, reranker).
- Performance (paralelismo, TTFT, cache, watchdog).
- Observabilidade (métricas, logs, alertas, SLO).
- UX (modo, related questions, estados vazios).
- Segurança (MFA, least privilege, CSP).

### Adicionar (não existe)
- OCR, PPTX/ODT/ODS/EPUB.
- Embeddings/reranker.
- Voz.
- Link público com expiração/revogação.
- MFA e gestão de dispositivos.
- Monitoramento de temas/research contínuo.
- Colaboração/ACL.
- Router de custo.

### Criar (novo processo/artefato)
- Golden set de 50–100 perguntas com fontes esperadas e critérios.
- Harness de avaliação de resposta (faithfulness, citation precision, recall).
- Runbook de incidente e restore.
- SLOs + dashboard + alertas.
- Automação de backup/GC.
- Staging + canário + rollback.
- Relatório de release com commit relay/PC.

---

## 9. Testes e CI

### 9.1 Suíte completa

**Comando:** `C:\Users\efrai\AppData\Local\Programs\Python\Python313\python.exe -m pytest -q`  
**HEAD auditado:** `a2caf6e` (worktree principal, 30/10/2026)  
**Resultado:** **2330 passed, 3 failed, 4 skipped, 2 warnings — 619,92 s (10 min 19 s)**

**Reexecução após P0-1/P0-2 (01/11/2026):** `C:\Users\efrai\AppData\Local\Programs\Python\Python313\python.exe -m pytest -q` no mesmo HEAD com as mudanças locais → **2337 passed, 4 failed, 4 skipped, 2 warnings — 607,30 s**. A falha adicional (`test_real_pythonw_wss_reconnect_named_pipe_stop_and_wal`) foi artefato de duas suítes executadas em paralelo e passou isolada em 7,12 s; restam exatamente as 3 falhas já classificadas abaixo.

| Teste | Classificação | Causa | Ação |
|---|---|---|---|
| `test_bench_experiencia_real.py::test_bateria_experiencia_real_completa` | Falha externa | O caso `geral_sem_resultados_honesto` recebeu resultado real de `dicio.com.br` para “assunto”; o teste assume que o provedor voltará vazio | Isolar de rede ou marcar como `external`; não é regressão do produto |
| `test_frontend_smoke.py::test_render_markdown_no_node` | Teste desatualizado | O commit `a2caf6e` trocou `class="citation"` por `class="citation-pill"`; o harness ainda exige a classe antiga (`FAIL real-citation`). Todos os outros 33 checks passam | Atualizar a expectativa do teste para `citation-pill` + `data-url` |
| `test_frontend_smoke.py::test_chat_imagens_csp_e_scroll_ancorado` | **Regressão real** | O popover de citação novo usa `onerror="this.style.display='none'"` inline (`public/app.js:3420`). O CSP do app (`script-src 'self'`) bloqueia handlers inline, então o fallback do favicon não executa | Remover o handler inline; usar listener de `error` em captura, como já é feito nas imagens do chat |

**Leitura:** a suíte continua grande e majoritariamente verde (99,87% dos testes executados), mas **o HEAD não está verde**. Uma falha é ambiental; duas foram introduzidas pelo próprio commit de citações — uma expectativa de teste não atualizada e uma violação de CSP que o teste existente corretamente detectou. Isso reforça o P1-2: a camada de citações novas foi entregue sem atualizar contrato de teste e sem respeitar a política de CSP já adotada.

### 9.2 O que a suíte cobre bem

- Auth/CSRF/rate limit/sessão.
- Pesquisa: orçamento, checkpoint, retomada, ranking, gates, evidências.
- P0-2: job sem evidência lida não conclui; auditor falha com `NO_EVIDENCE`; motivos de rejeição persistem.
- P0-3: classificador factual determinístico, golden set 30/30, controles 21/21 e citação inline obrigatória quando há fonte aberta.
- P0-4/P0-5: hello autenticado, drift de commit, `/api/ready`, cache `stale` do auth config, alerta offline, lock de instância e watchdog.
- Documentos: extração, chunking, FTS, owner-scope.
- Arquivos: versionamento, path guard, download.
- Frontend: `node --check`, testes de contrato JDUI, alguns E2E locais.

### 9.3 Lacunas de teste

- Sem teste de carga/concorrência real.
- Sem E2E autenticado em produção no CI.
- Sem cobertura de métricas/alerta/backup/restore (o alerta offline tem teste unitário, não de implantação).
- Sem teste de “modelo ignora anexo”.
- Sem teste de fallback de modelo 429/500/vazio.
- Citação inline coberta por unidade/harness; falta E2E com modelo real em produção.
- Watchdog tem teste unitário, mas instalação/reboot reais ainda não foram exercitados.

### 9.4 CI atual

```yaml
# .github/workflows/tests.yml
pytest -q tests
node --check public/app.js
```

Falta: `ruff`, `mypy`, `pip-audit`, cobertura, Playwright, build, deploy staging, smoke de produção.

**Estado atual:** o CI ficaria vermelho no HEAD `a2caf6e` por duas falhas de frontend (uma expectativa desatualizada e uma violação real de CSP); a terceira falha é externa. O commit foi publicado com o contrato de frontend quebrado; falta tornar esse job um gate obrigatório e separar testes que dependem de rede.

---

## 10. Plano de verificação pós-correção

### 10.1 Golden set (mínimo)

| Categoria | Exemplos | Critério |
|---|---|---|
| Factual estável | “capital da França”, “quem escreveu Dom Casmurro” | ≥1 fonte, citação inline |
| Temporal | “preço do dólar hoje”, “últimas notícias” | fonte com data, aviso de atualização |
| Comparação | “asyncio.TaskGroup vs gather” | ≥2 páginas lidas, ≥1 evidência |
| Científica | “baterias de estado sólido: métodos e limitações” | ≥1 estudo primário, limitações |
| Documento | “resuma este PDF”, “o que é este HTML” | conteúdo usado ou limitação explícita |
| Anexo hostil | PDF escaneado, HTML grande, DOCX com tabela | erro honesto ou extração correta |
| Follow-up | “e o preço?”, “compare com X” | mantém escopo e fontes |
| Segurança | prompt injection em página/anexo | não obedece instrução externa |

### 10.2 Métricas de aceite

| Métrica | Baseline | Meta |
|---|---:|---:|
| Jobs com ≥1 evidência | 2/5 (40%) | ≥90% |
| Jobs `concluida` com 0 evidência | 3/5 | 0 |
| Chat factual com fonte | não medido | ≥90% |
| Citação inline resolvida | não medido | 100% |
| Falha de IA | 18/171 (10,5%) | <2% |
| p95 latency | 31,3 s | <15 s |
| Backup <24 h | manual | 100% |
| Arquivos órfãos | 8.849 vs 3 docs | 0 após GC |
| Admins | 5 | 1 owner + MFA |
| Suíte | ver 9.1 | 100% verde (excl. externo documentado) |
| Produção online (`pc_online=true`) | offline em 31/10 | 100% com alerta de queda |
| Readiness (`/api/ready`) | não existe | 503 quando PC/SQLite/commit falham |

### 10.3 Testes de segurança

- CSRF sem token → 403.
- Origin cruzada → 403.
- Sessão revogada → 401 em <1 min.
- Upload 16 MB → 413/422.
- ZIP bomb → 422.
- SSRF `127.0.0.1`, `169.254.169.254`, DNS rebinding → bloqueado.
- Path traversal em `file_id`/`doc_id` → 404/422.
- Admin sem MFA → 403.
- `remote_ok=0` → screen/input negado.

---

## 11. Apêndice — evidências

### 11.1 Snapshot do banco vivo (29–30/10/2026)

| Item | Valor |
|---|---:|
| Mensagens | 328 (174 user / 154 assistant) |
| Sessões não revogadas | 45 (todas expiradas em 31/10; sem GC) |
| Jobs de pesquisa | 5 |
| Evidências | 12 |
| Eventos de pesquisa | 297 |
| Documentos / chunks | 3 / 8 |
| Arquivos gerados | 0 |
| Usuários | 5 (5 admin) |
| AI requests | 171 (151 completed, 18 failed, 2 cancelled) |
| SQLite | 4,06 MB + WAL 0,64 MB |
| `quick_check` | `ok` |

### 11.2 Estado da produção em 31/10/2026, 22:34 -03

| Item | Valor |
|---|---|
| `/api/health` | `{"status":"ok","configured":true}` |
| `/api/diag` | `{"pc_online":false,"agente_ha":-1,"commit":"a2caf6eb8b77","instance":"065044bf"}` |
| `/api/auth/config` | `{"modo":"fechado","exigir_aprovacao":true,"agent_online":false}` (fallback) |
| Config real no SQLite | `modo_cadastro=aberto`, `exigir_aprovacao=0` |
| Processo do agente | Ausente (nenhum `pythonw.exe`/`pc_agent.py`) |
| Última requisição de IA | 29/10/2026 18:06 UTC |
| Último job de pesquisa | 29/10/2026 02:35 UTC |
| Sessões | 47 no total; 45 não revogadas, todas expiradas |

### 11.3 Jobs ao vivo

| Job | Objetivo | Modo | Status | Evidência | Outcome |
|---|---|---|---|---|---|
| `rj-9a764b4ecfc6` | Efeitos do café na saúde | pro | concluida | 6 | ausente |
| `rj-d9eb104b5c1c` | Efeitos do café na saúde | pro | concluida | 6 | ausente |
| `rj-dd1e6bb3e790` | Baterias de estado sólido | rápida | concluida | 0 | partial |
| `rj-80157b50e470` | Baterias de estado sólido | rápida | concluida | 0 | partial |
| `rj-eb925b36e847` | asyncio TaskGroup vs gather | profunda | concluida | 0 | partial |

### 11.4 Referências de código

| Tema | Arquivo:linha |
|---|---|
| Gatilho de pesquisa | `pc_agent.py:1463-1479` |
| Chamada de pesquisa no chat | `pc_agent.py:2148-2200` |
| Anexo | `pc_agent.py:2061-2080`, `docs_agent.py` `contexto_documento` |
| Fontes/citações | `pc_agent.py` `anexar_fontes`, `public/app.js:442-589` |
| Gate de relevância | `search_orchestrator.py:247-327` |
| Rejeição no agente | `research_agents.py:674-700` |
| Status terminal | `research_agents.py:2296-2318` |
| Síntese | `research_synthesis.py:1-30`, `518-665` |
| Drift/readiness | `server.py` (`drift_agente`, `estado_prontidao`, `/api/diag`, `/api/ready`), `pc_agent.hello_agente` |
| Fallback | `pc_agent.py:374-423`, `hermes_bridge.py:419` |
| Segurança | `server.py:124-212`, `julia_auth.py:135-169`, `research.py:95-174` |
| Admin | `admin_http.py` |
| Arquivos | `files_agent.py:252-314` |

### 11.5 Comandos de reprodução (read-only)

```powershell
# saúde do relay
Invoke-WebRequest https://vexx-ai.onrender.com/api/health
Invoke-WebRequest https://vexx-ai.onrender.com/api/diag
Invoke-WebRequest https://vexx-ai.onrender.com/api/auth/config

# suíte
.venv\Scripts\python.exe -X utf8 -m pytest tests -q

# banco (exemplo)
sqlite3 "$env:USERPROFILE\.julia-mobile\memory.sqlite3" "select status,count(*) from research_jobs group by status;"
```

---

## 12. Conclusão

O Vexx tem uma **fundação de confiança** que muitos produtos de pesquisa não têm: o dado fica no PC, cada rota é owner-scoped, a pesquisa tem orçamento e proveniência, e os arquivos são versionados. O que impede o salto para Perplexity-class não é falta de features; é **honestidade de estado** e **qualidade do caminho padrão**:

- o chat precisa buscar por padrão quando a pergunta é factual;
- a pesquisa precisa falhar de forma explícita, não “concluir” vazia;
- a citação precisa ser inline, clicável e verificada;
- o relatório precisa ser um relatório;
- a operação precisa sobreviver a um disco morto e a um 429.

Em 31/10/2026, o relay estava no ar, mas o agente do PC não: `/api/health` respondia `ok` e `/api/diag` respondia `pc_online:false`. Antes de qualquer evolução, o Vexx precisa voltar a ficar online e o monitoramento precisa enxergar isso.

**Atualização em 01/11/2026:** o agente voltou a ficar online (PID `16540`, `dd6f5c4`) e o banco vivo foi endurecido. P0-1 a P0-5 têm implementação local testada, mas ainda **não commitada/publicada**; a produção continua rodando `dd6f5c4`. O próximo passo é autorizar o deploy do mesmo commit nos dois lados e validar `/api/ready` e `drift:false` em produção.

Se os P0 forem fechados e os P1 forem executados na ordem acima, o Vexx deixa de ser “um chat com busca” e passa a ser um **assistente de pesquisa local-first confiável** — que é uma categoria mais defensável do que copiar o Perplexity.
