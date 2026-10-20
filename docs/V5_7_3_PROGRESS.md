# VEXX AI V5.7.3 — Progresso por checkpoint

- **Data:** 2026-10-19
- **Base inicial:** `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`
- **Commit de código/testes:** `63e12c00370c6b13b328e6836d5b3af9b7b45ff6`
- **HEAD final da entrega:** commit documental seguinte; hash em
  `qa-artifacts/v573/final-head.txt`
- **Branch:** `main` local; sem push, sem deploy, sem reiniciar produção.
- **Formato:** AUDITAR → REPRODUZIR → CORRIGIR → TESTAR → DOCUMENTAR.
- **Decisão:** `READY_WITH_LIMITATIONS`.

## Checkpoint A — Estado inicial e preservação do trabalho

O working tree já estava sujo com mudanças de V5.7.2/V5.7.3. Nada foi
resetado, limpo ou descartado. Foram preservados:

- alterações rastreadas em `assistant_identity.py`, `evidence_graph.py`,
  `hermes_bridge.py`, `pc_agent.py`, `providers.py`, `research.py`,
  `research_agents.py`, `search_orchestrator.py`, `server.py`, `shopping.py`,
  `tests/test_research.py` e `tests/test_research_agents.py`;
- `tool_protocol.py` e `tests/test_trust_v573.py` (novos);
- `RELATORIO_PUBLICACAO_VEXX_AI_V5.7.2.md` e artefatos `prod-*` da publicação
  anterior (mantidos fora deste commit);
- artefatos de QA desta rodada em `qa-artifacts/v573/`.

O SHA inicial foi registrado: `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`.
A produção permaneceu intocada durante toda a rodada (PID `24356`).

## Checkpoint B — Protocolo de ferramenta

### Reprodução

Foram cobertos: chamada completa, marcador dividido entre chunks, JSON
incompleto, JSON inválido, múltiplas chamadas, chamada sem payload, resposta
que contém **apenas** protocolo, e menção literal em documentação/código.

### Correção

- Novo `tool_protocol.py` com `Sanitizador` incremental e `sanitizar_texto()`.
- Marcador pode chegar em partes; o sanitizador segura o sufixo ambíguo.
- JSON é balanceado por chaves/strings; incompleto ou inválido gera erro de
  protocolo, nunca “conserto” seguido de execução.
- Chamadas múltiplas são removidas e registradas.
- Código inline/bloco cercado com `<tool_call>` é preservado.
- `hermes_bridge.py` e `providers.py` aplicam o sanitizador em resposta
  completa, streaming e fallback.
- Resposta vazia (`vazia`) é distinta de “só chamada interna”
  (`protocolo_ferramenta`); nenhuma chamada é executada.

### Testes

`tests/test_trust_v573.py`: `test_tool_call_*` (5), `test_mencao_literal_*`,
`test_bridge_*` (3). A suíte existente de bridge/providers também passou.

## Checkpoint C — Identidade canônica e fatos do produto

### Causa raiz

A identidade era apenas instrução de prompt. O modelo podia inventar empresa,
fundador, sede, país ou dados comerciais, e “Vexxia” podia aparecer no stream
antes de uma correção final.

### Correção

- `assistant_identity.py` ganhou bloco de fatos canônicos: Vexx AI é o
  produto/app; o assistente é **Lucas**; empresa/fundador/sede/país/preços não
  são confirmados.
- `limitar_afirmacoes_nao_suportadas()` neutraliza a **frase** ofensora, não a
  resposta inteira; empresas de terceiros e pesquisas legítimas permanecem.
- Correção de “Vexxia” para o nome canônico.
- `cmd_identidade()` responde perguntas diretas sem LLM, incluindo CNPJ, preço,
  site oficial e assinatura.
- `_RX_DOMINIO_REAL` impede que “Pesquise quem fundou a Vexx AI” seja tratado
  como pergunta identitária bloqueada.
- `pc_agent._texto_seguro()` é a barreira final; o guard de stream cobre o
  caminho incremental.

### Testes

Sete testes de identidade/limites, incluindo dados comerciais inventados,
preservação de terceiros e pesquisa legítima.

## Checkpoint D — Relevância de fonte e digest

### Causa raiz

O fallback após 429 podia citar resultados de clima/investimentos para um
pedido de notebook; o digest determinístico não filtrava assunto.

### Correção

- `research.termos_assunto()` reutiliza `search_orchestrator._termos_correspondencia`.
- `fontes_relevantes()` exige correspondência em título/trecho/texto lido/URL.
- `intencao_pesquisa()` exige assunto não-genérico.
- `resumo_deterministico()` não cita fonte descartada: devolve limitação honesta.
- Reuso de pesquisa anterior passa pelo mesmo gate.
- `search_orchestrator` recebeu vocabulário de follow-up genérico (“agora”,
  “mostre”, “resultados”, “mais baratos”) para não autorizar busca externa.

### Testes

`test_gate_de_pesquisa_exige_assunto_nao_generico`,
`test_fontes_relevantes_rejeitam_clima_para_notebook`,
`test_digest_nao_cita_fonte_desconectada`.

## Checkpoint E — Shopping verificado e follow-up

### Causa raiz

- Falha de inferência descartava ofertas já verificadas.
- Um fence de produto gerado pelo modelo podia esconder/substituir o card real.
- Follow-up sem contexto (“agora só os mais baratos”) podia disparar busca
  externa sem assunto e receber resultados irrelevantes.
- Resultado vazio podia ganhar resumo artificial.

### Correção

- `_fallback_sem_inferencia()` preserva produtos verificados e monta cards/nota.
- `_shopping_aplicar()` remove fence de produto do modelo e injeta o fence real
  da ferramenta, mesmo quando já existe um fence não relacionado.
- `shopping.followup_sem_contexto()` detecta anáfora/instrução sem assunto.
- Continuação com dados guardados ordena localmente; tentativa externa vazia é
  honesta.
- `shopping.resumo_texto()` sem produto não inventa preço.

### Testes

Cinco testes de fallback/card/follow-up/resumo; smoke real encontrou 3 ofertas
confirmadas dentro do orçamento.

## Checkpoint F — Comparações e Evidence Graph

### Causa raiz

Comparações quantitativas podiam ser afirmadas sem benchmark; fonte apenas
encontrada no índice podia ser tratada como prova.

### Correção

- `evidence_graph.detectar_comparacao()` extrai sujeito/métrica/comparado.
- `classificar_afirmacoes()` usa evidência real; sem suporte → `UNVERIFIED`.
- `pc_agent._validar_comparacoes()` neutraliza a frase e registra laudo.
- `_evidencias_verificaveis()` propaga `status` e `lida`; fonte
  `encontrada`/sem `texto_lido` não sustenta afirmação (`lida=False`).
- Fonte `aberta` mas sem suporte também não vira fato.
- Comparação com trecho lido e quantidade compatível permanece suportada.

### Testes

Seis testes de comparação, incluindo fonte não lida, fonte lida sem suporte e
fonte lida com suporte.

## Checkpoint G — Conclusão de pesquisa e SSE

### Causa raiz

- `research_completed` era emitido antes de `salvar_job()`; polling podia ver
  status ainda em andamento.
- Push ao vivo podia duplicar, inverter ou reentregar eventos; reconexão não
  tinha cursor determinístico.
- Lacuna de `seq` podia manter a conexão aberta.

### Correção

- `research_agents.executar()` persiste o status terminal antes do evento.
- `server.ResearchSSECursor` ordena/deduplica por `seq`, parte de `apos_seq` e
  libera pendências no terminal ou no timeout.
- A rota SSE usa backlog autoritativo + push ao vivo; não confia na ordem do
  WebSocket.
- Teste de integração alterado para enviar 4→3→3→5 e exigir 3,4,5.

### Testes

`test_research_completed_so_depois_do_status_persistido`,
`test_sse_cursor_dedup_fora_de_ordem_e_replay`,
`test_sse_cursor_terminal_com_lacuna_libera_em_ordem`,
`test_sse_entrega_ordenada_com_replay_e_fechamento`.

## Checkpoint H — Guard de stream e complemento

### Causa raiz

O cliente podia ver “Vexxia”/comparação errada durante o stream e receber texto
corrigido só no `ai_done`, causando contradição visual.

### Correção

- `_GuardaStreamResposta` mantém frases com tokens de risco até a pontuação,
  aplica identidade/comparação e só então emite.
- Texto sem risco continua fluindo imediatamente (TTFT).
- `_complemento_stream()` calcula o delta restante sem repetir o prefixo já
  exibido, inclusive quando cards/fontes entram no início.
- O worker usa o guard no `emitir`, e o caminho final continua passando por
  `_texto_seguro` e `_validar_comparacoes`.

### Testes

Quatro testes de guard/complemento.

## Checkpoint I — Regressão, benchmarks e E2E

### Suíte

- Completa: **929 passed, 4 skipped**.
- Trust V5.7.3: **38/38**.
- Benchmarks: pesquisa **34/34**, shopping **59/59**, experiência **16/16**.

### Smoke integrado (`qa-artifacts/v573/smoke-integrado-20261019-222528.json`)

**7/7** checagens: produtos, pesquisa geral, URL direta, comparação técnica,
continuação, falha externa e checagem de frontend. A última lê um artefato
histórico V5.7.2; a prova V5.7.3 de frontend é o Chrome abaixo.

### Chrome V5.7.3 (`qa-artifacts/v573/chrome/`)

- Desktop 1280×900 e mobile emulado 390×844, sem overflow.
- Login pela interface, chat real 5,03 s / 250 chars, card real R$ 110,12.
- Primeira tentativa falhou porque o **network service do Chrome** caiu; o
  `/api/login` retornou 200. Reexecução passou. Os dois artefatos foram
  preservados.
- O JSON bruto aponta para caminhos `qa-artifacts/v572/...` porque foi gerado
  antes de restaurar a pasta histórica; as imagens novas estão em
  `qa-artifacts/v573/chrome/` e o `LEIA-ME.md` local explica a cópia.

## Checkpoint J — Publicação local e limitações

- Código/testes commitados localmente em `63e12c0`; nenhum push/deploy.
- Documentos e evidências V5.7.3 no commit seguinte.
- Produção observada apenas por `/api/health` e `/api/diag`: `pc_online: true`,
  commit antigo `ed0d44fd8b40`. Não é validação do diff.
- PID `24356` não foi reiniciado.
- Nenhuma credencial, modelo pago, provider, framework ou componente fora do
  escopo foi alterado.

## Decisão

**`READY_WITH_LIMITATIONS`** — código local pronto para publicação autorizada,
com E2E local/externo e Chrome; produção não validada porque o serviço
publicado permanece no commit antigo e não pode ser reiniciado nesta rodada.
