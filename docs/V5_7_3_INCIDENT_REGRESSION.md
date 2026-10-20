# VEXX AI V5.7.3 — Regressão de incidentes

- **Data:** 2026-10-19
- **Base inicial:** `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`
- **Commit de código/testes:** `63e12c00370c6b13b328e6836d5b3af9b7b45ff6`
- **Escopo:** incidentes observados no V5.7.2/V5.7.3 e reproduzidos antes da
  correção.
- **Regra:** nenhum incidente foi encerrado apenas por “parece corrigido”.
  Cada linha tem teste determinístico, E2E ou observação explicitamente
  rotulada.
- **Decisão:** `READY_WITH_LIMITATIONS`.

## 1. Matriz de incidentes

| ID | Incidente | Reprodução | Causa raiz | Correção | Regressão | Status |
|---|---|---|---|---|---|---|
| I1 | Identidade corporativa inventada | pergunta direta sobre fundador/empresa/sede; resposta gerada | identidade só no prompt; sem fatos canônicos | fatos canônicos + limitador + `cmd_identidade` | 7 testes | **FIXED (local)** |
| I2 | “Vexxia” como nome próprio | pedido de identidade / injeção de contexto | modelo podia adotar nome do produto | correção canônica + guard de stream | 3 testes | **FIXED (local)** |
| I3 | `<tool_call>` exibido | conteúdo completo e streaming | texto do provedor virava resposta | sanitizador incremental + adaptadores | 8 testes | **FIXED (local)** |
| I4 | Chamada dividida/incompleta | chunks partidos, JSON inválido | parser só reconhecia marcador completo | buffer + JSON balanceado + erro tipado | 4 testes | **FIXED (local)** |
| I5 | Execução não autorizada | chamada interna no texto | risco de tratar texto como comando | nenhuma execução; remoção + erro de protocolo | testes de protocolo | **FIXED (local)** |
| I6 | Fonte irrelevante | notebook + resultado de clima/investimento | nenhum gate assunto → fonte | `fontes_relevantes` + gate de intenção | 3 testes | **FIXED (local)** |
| I7 | Fonte encontrada, não lida | comparação com trecho de índice | snippet tratado como leitura | `lida=False` bloqueia suporte | 3 testes | **FIXED (local)** |
| I8 | Oferta verificada perdida | falha do modelo após shopping | fallback descartava `shop_res` | fallback preserva ofertas | 1 teste + smoke | **FIXED (local)** |
| I9 | Card real escondido | fence de produto alheio | fence existente impedia injeção | cards da ferramenta têm precedência | 1 teste + Chrome | **FIXED (local)** |
| I10 | Follow-up sem contexto | “agora só os mais baratos” | busca externa genérica | `followup_sem_contexto` | 3 testes | **FIXED (local)** |
| I11 | Preço/produto inventado | resultado vazio / falha externa | resumo sem produto | nota honesta, sem preço/fence | 1 teste + smoke | **FIXED (local)** |
| I12 | Comparação sem evidência | “40% mais rápido” sem benchmark | verificador não neutralizava comparação | Evidence Graph + `UNVERIFIED` | 6 testes | **FIXED (local)** |
| I13 | `research_completed` cedo | polling no instante do evento | `salvar_job` depois de `emitir` | status persistido antes | 1 teste | **FIXED (local)** |
| I14 | SSE duplicado/fora de ordem | push 4→3→3→5 | sem cursor por `seq` | `ResearchSSECursor` | 3 testes | **FIXED (local)** |
| I15 | Replay após reconexão | `apos_seq` + backlog | deduplicação ausente | cursor + backlog autoritativo | integração | **FIXED (local)** |
| I16 | Vazamento no stream | identidade/comparação antes do `ai_done` | correção só no texto final | `_GuardaStreamResposta` | 4 testes | **FIXED (local)** |
| I17 | 429/404 como sucesso | HTTPError 429/404 | mensagem genérica/fallback | `rate_limit` / `modelo-nao-encontrado` | 2 testes | **FIXED (local)** |
| I18 | Chrome login aparente | primeira execução E2E | crash do network service do Chrome | reexecução limpa | `CHROME_E2E` | **ENV LIMITATION** |

## 2. Evidência por incidente

### I1/I2 — Identidade

**Antes:** respostas podiam afirmar empresa criadora, fundador, sede, país ou
preço; “Vexxia” podia ser adotado como nome.

**Depois:**

- `assistant_identity.IDENTITY_RULES` e `PRODUCT_IDENTITY_FACTS` definem os
  únicos fatos canônicos.
- `limitar_afirmacoes_nao_suportadas()` neutraliza a frase ofensora e preserva
  o restante.
- `cmd_identidade()` responde direto, sem inferência, para identidade e dados
  comerciais não confirmados.
- Pesquisas legítimas (“Pesquise quem fundou a Vexx AI”) não são bloqueadas.

**Testes:**

- `test_identity_limiter_neutraliza_empresa_inventada`
- `test_identity_limiter_neutraliza_dados_comerciais_inventados`
- `test_identity_limiter_corrige_autonome_e_preserva_pesquisa_alheia`
- `test_cmd_identidade_responde_produto_sem_inventar_empresa`
- `test_cmd_identidade_nao_bloqueia_pesquisa_sobre_produto`
- `test_cmd_identidade_dados_comerciais_sem_fonte_viram_limitacao`
- `test_evento_concluido_so_com_comando_explicito`

**Rótulo:** `DETERMINISTIC_FIXTURE`; o caminho real de geração aparece nos
testes de stream/Chrome.

### I3/I4/I5 — Protocolo de ferramenta

**Antes:** uma chamada completa aparecia como resposta; marcador dividido
escapava; JSON inválido podia virar texto; não havia distinção entre resposta
vazia e resposta só-protocolo.

**Depois:**

- `tool_protocol.Sanitizador` mantém buffer de marcador e JSON.
- Chamada completa, dividida, múltipla ou sem payload é removida.
- JSON incompleto/inválido é erro de protocolo, não tentativa de execução.
- Código/documentação com `<tool_call>` literal é preservado.
- `hermes_bridge`/`providers` classificam `vazia` versus
  `protocolo_ferramenta`.
- Nenhum caminho executa a ferramenta sugerida pelo modelo.

**Testes:** os 8 primeiros testes de `tests/test_trust_v573.py`
(`test_tool_call_*`, `test_mencao_literal_*`, `test_bridge_*`).

### I6/I7 — Relevância e leitura de fontes

**Antes:** resultados de clima/investimentos podiam ser anexados a notebook;
trecho de snippet podia sustentar comparação mesmo sem página aberta.

**Depois:**

- `research.termos_assunto()` remove instruções genéricas.
- `research.fontes_relevantes()` exige termo demonstrável.
- `intencao_pesquisa()` não busca sem assunto.
- `resumo_deterministico()` devolve limitação honesta se todas as fontes forem
  descartadas.
- `_evidencias_verificaveis()` marca `status`/`lida`; `lida=False` é excluído
  pelo `verificar_claim()` para suporte factual.

**Testes:**

- `test_gate_de_pesquisa_exige_assunto_nao_generico`
- `test_fontes_relevantes_rejeitam_clima_para_notebook`
- `test_digest_nao_cita_fonte_desconectada`
- `test_fonte_encontrada_mas_nao_lida_nao_sustenta_comparacao`
- `test_fonte_lida_sem_suporte_nao_vira_fato`
- `test_fonte_lida_com_suporte_sustenta_comparacao`

### I8/I9/I10/I11 — Shopping

**Antes:** falha do modelo apagava ofertas verificadas; fence alheio impedia o
card real; follow-up sem contexto buscava de novo; resultado vazio podia gerar
resumo/preço.

**Depois:**

- `_fallback_sem_inferencia()` usa `shop_res` verificado.
- `_shopping_aplicar()` remove fence de produto do modelo e injeta o fence real.
- `shopping.followup_sem_contexto()` detecta anáfora sem assunto.
- `shopping.resumo_texto()` sem produto não inventa.
- Smoke real: 3 ofertas confirmadas dentro do orçamento; continuação local
  R$ 150 → 200 → 300; falha externa sem preço/fence.

**Testes:**

- `test_fallback_preserva_ofertas_verificadas_quando_modelo_falha`
- `test_shopping_aplicar_nao_esconde_card_por_fence_alheio`
- `test_resumo_shopping_sem_produto_nao_inventa`
- `test_followup_shopping_sem_contexto_nao_dispara_busca`
- `test_ai_completa_followup_sem_contexto_nao_chama_modelo`

**E2E:** `qa-artifacts/v573/smoke-integrado-20261019-222528.json`
(`EXTERNAL_E2E`); Chrome `CHROME_E2E`.

### I12 — Comparações

**Antes:** “As tuplas são 40% mais rápidas” podia aparecer sem benchmark.

**Depois:**

- `detectar_comparacao()` extrai a comparação.
- `classificar_afirmacoes()`/`verificar_claim()` exigem suporte.
- `_validar_comparacoes()` troca não suportado por texto `UNVERIFIED` e
  registra laudo.
- Fonte não lida não sustenta; fonte lida sem trecho compatível também não.
- Comparação suportada por trecho lido permanece.

**Testes:** os seis testes de comparação em `tests/test_trust_v573.py`.

### I13/I14/I15 — Pesquisa e SSE

**Antes:** evento terminal podia chegar antes do status persistido; push ao
vivo podia duplicar/inverter; reconexão não tinha cursor.

**Depois:**

- `salvar_job()` antes de `research_completed`.
- `ResearchSSECursor` deduplica por `seq`, aceita `apos_seq`, libera pendências
  no terminal/timeout.
- Backlog é autoritativo; push é aceleração.
- Teste de integração usa 4→3→3→5 e exige 3,4,5.

**Testes:**

- `test_research_completed_so_depois_do_status_persistido`
- `test_sse_cursor_dedup_fora_de_ordem_e_replay`
- `test_sse_cursor_terminal_com_lacuna_libera_em_ordem`
- `test_sse_entrega_ordenada_com_replay_e_fechamento`

### I16 — Guard de stream

**Antes:** “Vexxia”/comparação aparecia no delta e era corrigida no `ai_done`.

**Depois:** `_GuardaStreamResposta` bufferiza apenas frases de risco, valida e
emite; `_complemento_stream()` evita repetir prefixo quando o texto final
insere cards/fontes. Texto sem risco mantém TTFT.

**Testes:**

- `test_stream_guard_nao_exibe_vexcia_antes_do_done`
- `test_stream_guard_nao_exibe_comparacao_sem_evidencia`
- `test_stream_guard_mantem_ttft_em_texto_sem_risco`
- `test_complemento_stream_evita_repetir_prefixo`

### I17 — Erros externos

**Antes:** HTTP 429/404 podiam cair em mensagem genérica ou fallback não
honesto.

**Depois:** `rate_limit` para 429, `modelo-nao-encontrado` para 404,
`timeout`/`indisponivel`/`vazia`/`protocolo_ferramenta` tipados. Sem produto
verificável, o fallback é uma limitação explícita.

**Testes:**

- `test_bridge_mapeia_429_sem_declarar_sucesso`
- `test_bridge_mapeia_404_como_indisponivel`
- regressões existentes de vazio/timeout/indisponível.

## 3. Incidente de harness Chrome (não é incidente de produto)

A primeira execução de `tools/chrome_e2e_v572.py` falhou no login:

- `/api/login` retornou **200**;
- `/api/session` retornou **401** depois;
- a interface continuou no overlay;
- o Chrome registrou crash do **network service** (`exit_code 1`);
- artefato: `qa-artifacts/v573/chrome/chrome-e2e-20261019-221928.json`.

A segunda execução, após limpeza do processo, passou:

- login pela interface, chat real, card real, desktop/mobile;
- artefato: `qa-artifacts/v573/chrome/chrome-e2e-20261019-222056.json`.

Conclusão: a falha inicial foi de estabilidade do navegador sem interface
(headless), não de autenticação da aplicação. O harness **não** é imune a esse
crash; a limitação está declarada no release readiness.

## 4. Evidência agregada

| Evidência | Arquivo | Rótulo |
|---|---|---|
| Suíte completa | saída do pytest (929 passed, 4 skipped) | `DETERMINISTIC_FIXTURE` |
| Trust V5.7.3 | `tests/test_trust_v573.py` (38) | `DETERMINISTIC_FIXTURE` |
| Pesquisa | `qa-artifacts/v573/bench-pesquisa-v57-2026-10-19.json` (34/34) | `DETERMINISTIC_FIXTURE` |
| Shopping | `qa-artifacts/v573/bench-shopping-v4-20261019.txt` (59/59) | `DETERMINISTIC_FIXTURE` |
| Experiência | `qa-artifacts/v573/bench-experiencia-20261019.txt` (16/16) | `DETERMINISTIC_FIXTURE` + Node |
| Smoke integrado | `qa-artifacts/v573/smoke-integrado-20261019-222528.json` (7/7) | `LOCAL_E2E` + `EXTERNAL_E2E` |
| Chrome sucesso | `qa-artifacts/v573/chrome/chrome-e2e-20261019-222056.json` | `CHROME_E2E` |
| Chrome falha inicial | `qa-artifacts/v573/chrome/chrome-e2e-20261019-221928.json` | `CHROME_E2E` (harness) |
| Produção | `/api/health`, `/api/diag` | `PRODUCTION_OBSERVATION` |

## 5. O que não foi validado

- Código novo no serviço publicado (produção continua em `ed0d44fd`).
- Reinício do PC Agent de produção (PID `24356` preservado).
- Mobile físico Android/iOS (somente emulação de viewport).
- Estabilidade permanente dos provedores externos.
- Matriz de modelos pagos/alternativos.

## 6. Conclusão

Todos os incidentes de código reproduzidos nesta rodada têm correção local e
teste de regressão associado. O único failure de execução foi o crash do
network service do Chrome, reproduzido como limitação de harness e contornado
por reexecução limpa. A classificação permanece **`READY_WITH_LIMITATIONS`**
até existir validação no ambiente publicado.
