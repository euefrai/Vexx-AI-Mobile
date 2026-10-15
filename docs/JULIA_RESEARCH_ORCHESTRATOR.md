# JÚLIA Research Orchestrator (V4.5)

Estado por pesquisa (`research_jobs`): `research_id`, `owner_id` (sempre do
servidor, nunca do cliente), `conversation_id`, `objective`, `plan_version`,
`status` (criada/em_andamento/concluida/interrompida/falhou/cancelada),
`created_at`, `updated_at`, `search_budget`, `time_budget`, `model_budget`
(orçamentos por modo em `MODOS`), `completed_steps`, `pending_steps`
(derivados do plano), `findings` (`achados`), `unresolved_questions`
(`pendencias`), `errors`.

## Ciclo

PESQUISAR → LER → EXTRAIR → ANALISAR → IDENTIFICAR LACUNAS → REPLANEJAR
(máx 1 rodada, sem repetir feitas, releitura reaberta) → VERIFICAR →
SINTETIZAR. Encerra com evidências suficientes ou limites (tempo, orçamento,
cancelamento, erro fatal). Cada passo persiste antes do próximo: sobrevive a
reinício; retomada pula feitas (idempotente por etapa).

## Orçamentos por modo

- `rapida`: 2 buscas, 3 páginas, 30 s · `pro`: 4/6/60 s ·
  `profunda`: 8/12/120 s · `investigativa`: 12/20/300 s.
- Seleção: manual (`modo`) ou automática por complexidade (regras em
  `selecionar_modo`). Valores de engenharia, não garantias.
- Concorrência: 1 job ativo por dono (409 honesto), teto global de 2 workers;
  leitura de páginas sequencial (PC limitado).

## Regras

Sem buscas redundantes (consultas vistas + URLs dedupadas); replanejar
preserva válidos; objetivo editável gera novo job (histórico preservado);
`deve_parar` verificado entre passos (cancelamento real).
