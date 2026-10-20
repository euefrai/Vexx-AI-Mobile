# VEXX AI V5.7.3 — Relatório de Confiabilidade (Trust Hardening)

- **Data:** 2026-10-19
- **Base inicial:** `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`
- **Commit de código/testes:** `63e12c00370c6b13b328e6836d5b3af9b7b45ff6`
- **Entrega final:** commits documentais seguintes; hash em
  `qa-artifacts/v573/final-head.txt`
- **Branch:** `main` local
- **Push/deploy:** **não realizados**
- **Reinício de produção:** **não realizado** (PID `24356` preservado)
- **Decisão:** **`READY_WITH_LIMITATIONS`**

## 1. Objetivo

Endurecer o Vexx AI V5.7.3 para que o assistente não:

1. invente identidade, empresa, fundador, sede, país, preço ou vínculo
   comercial da Vexx AI;
2. exiba chamadas internas de ferramenta como resposta;
3. anexe fontes sem relação demonstrável com o pedido;
4. perca ofertas de shopping já verificadas;
5. transforme comparação sem evidência em fato;
6. publique “concluído” antes de persistir o estado terminal;
7. repita, reordene ou perca eventos de pesquisa no SSE;
8. mostre no stream uma identidade/comparação errada e depois a corrija no
   `ai_done`;
9. transforme 429 / 404 / timeout / vazio / interrupção em sucesso falso;
10. conclua um evento de agenda por texto ambíguo (“concluído”) em vez de
    comando explícito.

A identidade canônica foi **preservada**, não apenas bloqueada: `Lucas`
(`Luccas Trawman` quando o nome completo for pedido). “Vexxia” é corrigido
para o nome canônico; a Vexx AI permanece descrita apenas como o produto/app.

## 2. Sumário executivo

| Incidente | Correção principal | Evidência |
|---|---|---|
| Identidade corporativa inventada | fatos canônicos + limitador por frase + resposta direta determinística | 6 novos + suíte existente |
| “Vexxia” exibido no stream | correção canônica + `_GuardaStreamResposta` | teste de stream |
| `<tool_call>` vazando | sanitizador incremental no adaptador e barreira final | 8 testes |
| Chamada dividida/incompleta | buffer de marcador + JSON balanceado + erro de protocolo | 4 testes |
| Fonte irrelevante anexada | gate assunto → fonte no research e no digest | 3 testes |
| Ofertas verificadas perdidas | fallback preserva `shop_res`; cards reais têm precedência | 2 testes |
| Follow-up sem contexto buscando fora | `followup_sem_contexto` + vocabulário genérico | 3 testes |
| Comparação sem evidência | Evidence Graph + neutralização `UNVERIFIED` | 6 testes |
| `research_completed` antes do status | `salvar_job` antes do evento terminal | teste de ordem |
| SSE duplicado/fora de ordem/replay | `ResearchSSECursor` | 2 testes + integração |
| 429/404 sem fallback honesto | mapeamento `rate_limit` / `modelo-nao-encontrado` | 2 testes |
| 404/latência/timeout | erros tipados; sem resposta artificial | suíte existente + novos testes |
| Evento concluído por engano | comando explícito; texto ambíguo não altera | teste de evento |

**Regressão:** `929 passed, 4 skipped` na suíte completa; **38** regressões
novas em `tests/test_trust_v573.py`; benchmarks **34/34**, **59/59** e
**16/16**; smoke integrado real **7/7**; Chrome real desktop + mobile
emulado **OK**.

## 3. Rótulos de evidência

| Rótulo | Significado |
|---|---|
| `DETERMINISTIC_FIXTURE` | teste unitário com dados controlados; não é opinião do modelo |
| `LOCAL_E2E` | stack local isolado (relay + agente + SQLite temporário) |
| `EXTERNAL_E2E` | rede/provedor externo real usado pelo stack local |
| `CHROME_E2E` | Chrome real via CDP, desktop e viewport mobile emulado |
| `MODEL_INFERENCE` | resposta real do modelo `poolside/laguna-s-2.1:free` |
| `PRODUCTION_OBSERVATION` | leitura pública de produção; **não** valida este diff |

Nada foi executado contra o serviço publicado usando o código novo. O
`/api/diag` de produção continua apontando para o commit antigo.

## 4. Incidentes e correções

### I1 — Identidade corporativa inventada

**Sintoma:** o modelo afirmava empresa criadora, fundador, sede ou país da
Vexx AI, ou adotava “Vexxia” como nome próprio.

**Causa:** a identidade personalizada era apenas um prompt; não havia fonte
canônica dos fatos do produto nem barreira determinística por frase.

**Correção:**

- `assistant_identity.py`: fatos canônicos explícitos; ausência de empresa,
  fundador, sede, país, data, investidores e dados comerciais declarada como
  **não confirmada**.
- `limitar_afirmacoes_nao_suportadas()` substitui somente a frase ofensora por
  uma limitação, preservando o restante da resposta e empresas de terceiros.
- `cmd_identidade()` responde identidade/produto sem chamar o modelo, inclusive
  CNPJ, preço, site, assinatura e “quanto custa”.
- `_RX_DOMINIO_REAL` mantém pesquisas legítimas (“Pesquise quem fundou a Vexx
  AI”) fora do bloqueio determinístico.

**Testes:** `test_identity_limiter_neutraliza_empresa_inventada`,
`..._dados_comerciais_inventados`, `..._corrige_autonome_e_preserva_pesquisa_alheia`,
`test_cmd_identidade_responde_produto_sem_inventar_empresa`,
`..._nao_bloqueia_pesquisa_sobre_produto`,
`..._dados_comerciais_sem_fonte_viram_limitacao`.

### I2 — Chamada interna de ferramenta exibida

**Sintoma:** `<tool_call>...` aparecia no chat; em stream, o marcador podia
chegar dividido entre chunks; JSON incompleto podia virar texto comum.

**Causa:** o conteúdo textual do provedor era tratado como resposta final.

**Correção:**

- `tool_protocol.py`: `Sanitizador` incremental, detecção de marcador
  completo/dividido, JSON balanceado, múltiplas chamadas, payload ausente e
  JSON inválido. Uma chamada **nunca é executada**; ela vira erro de protocolo
  e é removida.
- `hermes_bridge.py` e `providers.py`: sanitização nos caminhos completo,
  streaming e fallback; distinção entre resposta vazia (`vazia`) e resposta
  que continha apenas protocolo (`protocolo_ferramenta`).
- `pc_agent._texto_seguro()` permanece como última barreira para caminhos
  alternativos.
- Menções literais dentro de código inline ou bloco de documentação são
  preservadas: o requisito de não vazar chamada não pode quebrar documentação.

**Testes:** os 8 testes `test_tool_call_*` e `test_mencao_literal_*`,
`test_bridge_*tool_call*`.

### I3 — Fonte irrelevante anexada

**Sintoma:** após 429 ou fallback, uma resposta sobre notebooks citava clima,
investimentos ou páginas sem relação.

**Causa:** qualquer resultado do provedor era aceito; não existia gate
“pedido → fonte”. O digest determinístico repetia todos os resultados.

**Correção:**

- `research.termos_assunto()` reutiliza o vocabulário do Search Orchestrator e
  remove termos genéricos de follow-up.
- `research.fontes_relevantes()` exige termo demonstrável no título, trecho,
  texto lido ou URL; sem termo, não anexa nada.
- `intencao_pesquisa()` só dispara busca se houver assunto não-genérico.
- `resumo_deterministico()` descarta fontes desconectadas e devolve limitação
  honesta em vez de citar o que não serve.
- A mesma filtragem é aplicada ao reuso de pesquisa anterior.

**Testes:** `test_gate_de_pesquisa_exige_assunto_nao_generico`,
`test_fontes_relevantes_rejeitam_clima_para_notebook`,
`test_digest_nao_cita_fonte_desconectada`.

### I4 — Ofertas verificadas perdidas

**Sintoma:** modelo falhava (429/vazio) ou produzia um fence de produto
alheio; os cards reais já validados desapareciam.

**Causa:** o fallback só usava texto do modelo; `_shopping_aplicar` podia ser
ignorado quando já existia qualquer fence JDUI.

**Correção:**

- `_fallback_sem_inferencia()` preserva `shop_res` e monta cards/nota com os
  produtos verificados.
- `_shopping_aplicar()` remove fences de produto gerados pelo modelo, mas
  **injeta** o fence real da ferramenta antes de fences não relacionados.
- `shopping.resumo_texto()` sem produto não inventa preço.
- `shopping.followup_sem_contexto()` impede que “agora mostre só os mais
  baratos” vire nova busca sem assunto; com dados guardados, a continuação
  ordena localmente.

**Testes:** `test_fallback_preserva_ofertas_verificadas_quando_modelo_falha`,
`test_shopping_aplicar_nao_esconde_card_por_fence_alheio`,
`test_resumo_shopping_sem_produto_nao_inventa`,
`test_followup_shopping_sem_contexto_nao_dispara_busca`,
`test_ai_completa_followup_sem_contexto_nao_chama_modelo`.

### I5 — Comparação sem evidência

**Sintoma:** “X é 40% mais rápido que Y” virava fato sem benchmark.

**Causa:** o modelo podia afirmar comparações e o verificador não tinha um
caminho específico para detectá-las/neutralizá-las.

**Correção:**

- `evidence_graph.detectar_comparacao()` extrai sujeito, métrica e comparado.
- `classificar_afirmacoes()` usa Evidence Graph; sem suporte, a classificação
  é `UNVERIFIED`/`HYPOTHESIS`.
- `pc_agent._validar_comparacoes()` troca a afirmação por texto neutro com
  `UNVERIFIED` e registra laudo por afirmação.
- Fonte apenas **encontrada**, sem leitura, tem `lida=False` e não sustenta
  comparação; fonte lida mas sem suporte também não vira fato.
- Comparação com trecho lido e quantidade compatível pode permanecer como
  `FACT`/`DERIVED_FROM_DATA`.

**Testes:** `test_comparacao_curta_sem_evidencia_e_neutralizada`,
`test_comparacao_com_evidencia_nao_e_neutralizada`,
`test_fonte_encontrada_mas_nao_lida_nao_sustenta_comparacao`,
`test_fonte_lida_sem_suporte_nao_vira_fato`,
`test_fonte_lida_com_suporte_sustenta_comparacao`,
`test_classificacoes_explicitas_sem_presuncao`.

### I6 — “Concluído” antes do estado terminal

**Sintoma:** o SSE podia entregar `research_completed` enquanto o status
persistido ainda estava em andamento; quem recarregasse via polling veria um
estado inconsistente.

**Causa:** `salvar_job()` era chamado depois de `emitir()`.

**Correção:** `research_agents.executar()` persiste o status terminal
(`concluida`, `interrompida` ou `falhou`) **antes** de emitir o evento
terminal. O `research_completed` é emitido pelo orquestrador, não inferido de
texto do modelo.

**Teste:** `test_research_completed_so_depois_do_status_persistido`.

### I7 — SSE duplicado, fora de ordem ou replay

**Sintoma:** eventos repetidos, invertidos ou reentregues após reconexão;
lacuna podia manter a conexão aberta.

**Correção:** `server.ResearchSSECursor` ordena por `seq`, deduplica, aceita
replay a partir de `apos_seq` e libera pendências em ordem no evento terminal
ou no timeout. O backlog continua autoritativo; push ao vivo é apenas
acelerador.

**Testes:** `test_sse_cursor_dedup_fora_de_ordem_e_replay`,
`test_sse_cursor_terminal_com_lacuna_libera_em_ordem` e a integração
`test_sse_entrega_ordenada_com_replay_e_fechamento` (4→3→3→5 → 3,4,5).

### I8 — Correção visível só no `ai_done`

**Sintoma:** o stream mostrava “Vexxia” ou uma comparação errada; o texto final
era corrigido depois, causando salto/contradição visual.

**Correção:** `_GuardaStreamResposta` segura apenas frases com token de risco
(identidade/comparação), valida e emite a versão segura; texto sem risco
continua fluindo imediatamente (TTFT preservado). `_complemento_stream()`
completa o que foi exibido sem duplicar prefixo quando cards/fontes são
inseridos no início.

**Testes:** `test_stream_guard_nao_exibe_vexcia_antes_do_done`,
`test_stream_guard_nao_exibe_comparacao_sem_evidencia`,
`test_stream_guard_mantem_ttft_em_texto_sem_risco`,
`test_complemento_stream_evita_repetir_prefixo`.

### I9 — Falhas externas tratadas como sucesso

**Sintoma:** 429/404/timeout/vazio/interrupção podiam gerar resposta vazia,
produto inventado ou “concluído”.

**Correção:** erros tipados (`rate_limit`, `modelo-nao-encontrado`, `timeout`,
`indisponivel`, `vazia`, `protocolo_ferramenta`); fallback só quando há
conteúdo verificável; sem produto, a mensagem é honesta e sem preço/fence.
Stream interrompido preserva apenas o que já foi recebido e sinaliza parcial.

**Testes:** `test_bridge_mapeia_429_sem_declarar_sucesso`,
`test_bridge_mapeia_404_como_indisponivel`, regressões existentes de
`vazia`/timeout/indisponível.

### I10 — Evento concluído por texto ambíguo

**Sintoma:** “teste visual concluido” podia ser interpretado como comando de
conclusão, encerrando um evento de agenda sem pedido explícito.

**Causa:** o parser de comandos de memória aceitava “concluído” solto como
intenção suficiente.

**Correção:** a conclusão exige comando explícito (“concluir evento …”); texto
ambíguo permanece apenas texto e o evento continua ativo.

**Teste:** `test_evento_concluido_so_com_comando_explicito`.

## 5. Arquivos alterados (código)

| Arquivo | Papel |
|---|---|
| `tool_protocol.py` (novo) | sanitizador incremental de chamadas internas |
| `hermes_bridge.py` | sanitização, distinção vazio × protocolo, streaming |
| `providers.py` | mesma barreira no adaptador alternativo |
| `assistant_identity.py` | fatos canônicos, limitador, identidade direta |
| `evidence_graph.py` | comparação, classificação, fonte não lida |
| `pc_agent.py` | gate de identidade, digest, shopping, comparação, stream guard |
| `research.py` | termos de assunto, filtro de fontes, digest honesto |
| `research_agents.py` | status terminal antes do evento |
| `server.py` | `ResearchSSECursor` e rota SSE |
| `shopping.py` | follow-up sem contexto e ofertas verificadas |
| `search_orchestrator.py` | vocabulário genérico de follow-up |
| `tests/test_trust_v573.py` (novo) | 38 regressões determinísticas |
| `tests/test_research.py` | fixture de título coerente com o novo gate |
| `tests/test_research_agents.py` | push duplicado/fora de ordem no SSE |

## 6. Evidência de regressão

| Verificação | Resultado | Rótulo |
|---|---|---|
| Suíte completa | **929 passed, 4 skipped** | `DETERMINISTIC_FIXTURE` |
| Trust V5.7.3 | **38/38** | `DETERMINISTIC_FIXTURE` |
| Benchmark pesquisa | **34/34** | `DETERMINISTIC_FIXTURE` |
| Benchmark shopping | **59/59** | `DETERMINISTIC_FIXTURE` |
| Experiência real | **16/16** | `DETERMINISTIC_FIXTURE` + Node |
| Smoke integrado | **7/7** | `LOCAL_E2E` + `EXTERNAL_E2E` |
| Chrome desktop 1280×900 | sem overflow; card real | `CHROME_E2E` |
| Chrome mobile 390×844 emulado | sem overflow | `CHROME_E2E` |

Nenhum teste foi removido, nenhum skip artificial foi criado e nenhuma
fixture de resposta foi enfraquecida. A única alteração de fixture existente
foi dar um título coerente (“Café”) à fonte usada no teste de grounding; o
gate novo corretamente rejeitava o título genérico “T”.

### Cobertura existente preservada

A suíte completa também cobre os cenários que não precisaram de teste novo:
memória conflitante (`test_correcao_vence_e_preserva_historico`,
`test_contraditorios_multiplos_usuarios_e_reinicio`), injeção de contexto
(`test_contexto_local_validado_e_injetado_so_quando_enviado`,
`test_orcamento_memoria_no_prompt`), dados ausentes (limitação de identidade),
datas divergentes e fontes conflitantes (Evidence Graph/benchmarks) e
instruções maliciosas em página externa (`test_research`). Nenhum desses
testes foi removido ou afrouxado.

## 7. Evidência E2E

### Smoke integrado (`qa-artifacts/v573/smoke-integrado-20261019-222528.json`)

| Cenário | Resultado |
|---|---|
| Produtos “fone bluetooth até R$ 300” | 3 ofertas confirmadas: R$ 28,60 / R$ 68,32 / R$ 134,29; cards JDUI válidos; 10,55 s |
| Pesquisa geral (fotossíntese) | 3 fontes lidas; resposta real; sem tool call; 25,36 s |
| URL direta (Wikipédia) | fonte `aberta`; 1.200 chars; sem resíduos de menu; 1,05 s |
| Comparação (docs.python.org) | documentação oficial; 2 turnos; sem tool call; 32,96 s |
| Continuação “mais baratos” | ordenação local R$ 150 → 200 → 300; fence válido; 0,00 s |
| Falha externa | DNS inválido + provedor indisponível → nota honesta, sem preço/fence |
| Entrega no frontend | checagem do smoke aponta para artefato histórico V5.7.2; a entrega V5.7.3 foi validada separadamente no Chrome abaixo |

> O smoke integrado tem o caminho `frontend_delivery` acoplado a
> `qa-artifacts/v572`; ele **não** foi usado como prova do Chrome V5.7.3. A
> prova de frontend desta versão é o artefato novo em `qa-artifacts/v573`.

### Chrome V5.7.3 (`qa-artifacts/v573/chrome/chrome-e2e-20261019-222056.json`)

- Chrome **155.0.8059.85**, CDP, stack isolado, SQLite temporário.
- Login pela interface: **OK**.
- Chat real com streaming: **5,03 s**, **250 chars**.
- Card real KaBuM **R$ 110,12**; imagem **verificada**; link **parcial**.
- Desktop 1280×900: `scrollWidth 1264 = clientWidth 1264`.
- Mobile emulado 390×844, DPR 2: `scrollWidth 390 = clientWidth 390`.
- Console: 1 `401` esperado antes do login; 2 `ERR_ABORTED` de reload;
  nenhuma exceção JS.
- **Limite:** viewport mobile emulado, não Android/iOS físico.

A primeira tentativa de Chrome desta rodada falhou no login porque o
**network service do Chrome** caiu (`exit_code 1`), não por 401 da aplicação;
o POST `/api/login` já havia retornado 200. O artefato da falha foi preservado
em `chrome-e2e-20261019-221928.json`; a reexecução limpa passou. Isso é
limitação de estabilidade do harness, não da autenticação.

## 8. Segurança, contratos e desempenho

- Nenhuma dependência nova; `requirements.txt` e `render.yaml` intocados.
- Nenhuma migração de schema; nenhuma tabela/campo novo.
- Nenhuma chamada de ferramenta emitida pelo modelo é executada; o texto é
  removido e classificado como erro de protocolo.
- SSRF, limites de download, RBAC, CSRF, rate limiting e headers de segurança
  seguem cobertos pela suíte completa; nenhum teste de segurança removido.
- O stream guard só bufferiza frases com termo de risco; texto normal mantém
  TTFT (teste dedicado).
- Benchmarks de qualidade não mostram regressão: 34/34, 59/59, 16/16.

## 9. Limitações e o que NÃO foi provado

1. **Produção não foi atualizada nem reiniciada.** O PID `24356` continua no
   commit antigo; `/api/diag` observado em `2026-10-19` retornou
   `pc_online: true`, `commit: ed0d44fd8b40` (`PRODUCTION_OBSERVATION`). Isso
   não valida as correções deste diff.
2. **Nenhum smoke autenticado no serviço publicado** foi executado, porque
   isso exigiria o código novo em produção.
3. **Provedores externos continuam variáveis** (403/bot-wall/429). Não foram
   contornados nem classificados como `PASS`.
4. **Mobile é emulação de viewport**, não aparelho físico.
5. A primeira execução do Chrome falhou por crash do network service do
   navegador; a reexecução passou, mas o harness não é imune a esse crash.
6. O smoke integrado usa o modelo free local; não foi testada uma matriz de
   modelos pagos nem todos os provedores alternativos.
7. A semântica de recarga durante um job terminal é coberta pelo status
   persistido + cursor/replay, mas **não** foi exercitada uma recarga real de
   navegador no E2E.

## 10. Reprodução

```powershell
$py = "C:\Users\efrai\Documents\julia-mobile-v0.2-offline-sqlite\.venv\Scripts\python.exe"
& $py -m pytest -q
& $py -m pytest -q tests/test_trust_v573.py
& $py tools/bench_pesquisa_v57.py
& $py tools/bench_shopping_v4.py
& $py tools/bench_experiencia_real.py
& $py tools/smoke_integrado_v572.py
& $py tools/chrome_e2e_v572.py
```

Os harnesses usam portas livres, SQLite temporário e perfil Chrome temporário;
não tocam portas de produção. O smoke/Chrome exige rede e Hermes local.

## 11. Decisão final

**`READY_WITH_LIMITATIONS`** — o código local está pronto para uma publicação
autorizada, com regressão verde, E2E local/externo e Chrome real. Não é
`READY` de produção porque o serviço publicado permanece no commit antigo, o
PID de produção não foi reiniciado e provedores externos não são estáveis.
Essas são limitações de cobertura/ambiente, não falhas conhecidas do código.
