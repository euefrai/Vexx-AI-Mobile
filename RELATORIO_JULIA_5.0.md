# Relatório Júlia 5.0 — Advanced Memory & Lucas Identity

## Status: ENTREGUE

Identidade consistente do Lucas, memória com confirmação visível no chat,
recuperação com orçamento, Project Memory e continuidade determinística —
tudo funcionando **sem LLM** (Hermes segue bloqueado).

## Fase 1 — Auditoria

- Base existente e testada antes de modificar: identity (6), memoria41,
  docs_memoria, avaliacao, isolamento, learning — **77 passed**.
- Confirmado funcionando: `assistant_identity.py` centralizado e aplicado
  nos 3 caminhos (`ai_config`, `ai_montar_mensagens`, `ai_continuar`);
  memórias tipadas + FTS5, eventos, ui-state, workspace, `recover_interrupted_ai`.
- Gaps encontrados: sem respostas determinísticas de identidade; `pergunta`
  do `analisar_memoria` descartada (propostas silenciosas); re-save idêntico
  gerava churn; sem orçamento de memória; projetos nunca injetados; sem nota
  de continuidade; exemplos viravam falsas memórias.

## Funcionalidades implementadas

- **Identidade** (`assistant_identity.py` + `cmd_identidade` nos fluxos
  stream e completo): "qual seu nome" → Lucas; "nome completo" → Luccas
  Trawman; "você é humano?" → IA sem fingir humanidade; vocativo isolado
  com outro nome → correção educada única; terceiros e saudações intactos.
- **Confirmação no chat**: `pergunta_memoria` sai do `_ai_preparar` e é
  anexada à resposta (sensível/temporal-ambíguo); "pode guardar" confirma.
- **Higiene**: re-save idêntico é no-op (sem churn no `memory_facts`);
  correção explícita sobrescreve com histórico preservado; marcadores de
  exemplo/hipótese ("suponha", "imagine"…) nunca viram memória.
- **Recuperação**: bloco de memórias capado em 1500 chars; `bloco_projetos`
  injeta projetos ativos + trechos reais dos chats ligados (com orçamento).
- **Continuidade**: `cmd_projeto` — resumo de projeto único (radicais:
  "montando" casa com "montagem"), pergunta honesta em empate, lista
  projetos sem match, "onde paramos?" (pendências + pesquisa + compras +
  foco); nota CONTINUIDADE quando o contexto corta mensagens.
- Restart: `recover_interrupted_ai` verificado (parcial preservada, libera).

## Bugs corrigidos

- `IndentationError` introduzido num edit (def + docstring coladas).
- `NameError: _sem_acentos` (não existe no pc_agent; NFKD inline).
- Testes: conv/owner/id curtos, mock sem `latencia_s`, mids < 8 chars.
- Achado lateral: merge workspace com mesmo milissegundo + `change_id`
  menor é descartado pelo LWW (semântica correta; teste tornado
  determinístico).

## Arquivos alterados

- `assistant_identity.py` (regra anti-antropomorfismo), `pc_agent.py`
  (identidade, pergunta, no-op, orçamento, projetos, continuidade),
  `tests/test_memoria50.py` (novo, 22 testes).

## Testes

- Novo `test_memoria50.py`: **22 passed** (identidade, confirmação,
  falsas/duplicadas/contradições, orçamento, projetos, restart,
  isolamento, continuidade).
- Regressão total `not e2e_real`: **394 passed** (372 + 22 novos),
  8 deselected (`e2e_real`), só 2 warnings pré-existentes.

## Bloqueado / limitações / pendências

- LLM real (Hermes) segue bloqueado: respostas longas/nuanceadas de
  identidade e extração de fundo dependem dele; o determinístico cobre o
  essencial offline.
- Recuperação é léxica (FTS+overlap+radicais), não semântica.
- Resumo de projeto usa últimos trechos, não sumarização abstrativa.
- Pendência: revalidar E2E ao vivo de shopping quando o provedor permitir.
