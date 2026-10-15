# JÚLIA Research Orchestrator (V4.5)

## V4.8 lifecycle integration

`research_agents.py` now initializes the owner/job-scoped hypothesis and
continuous-context stores alongside the original job tables. The plan reports
per-step dependencies, integer priority, and a stopping rule. Replanning is
limited to one extra round, records its reason, retains completed outputs, and
reopens only the affected reader when a source search is repeated. Search,
reading, analysis, verification, synthesis, and audit continue to use the
existing orchestrator roles.

At execution time the job looks up up to four owner-scoped document chunks and
up to five relevant confirmed memories. Document chunks become evidence with
`document://` provenance; memory remains labeled private context and is never
treated as evidence or sent to an external search provider. Sensitive memory
is excluded. The existing research event/SSE pipeline carries truthful
`document_context_retrieved`, `memory_context_retrieved`,
`hypotheses_updated`, and checkpoint lifecycle events.

Checkpoint snapshots preserve the actual plan, source/evidence records,
document-chunk provenance, hypotheses, results, pending steps, and next action.
The existing 1 MiB limit still applies and no semantic compaction is claimed.
Completed searches can restore their stored results after a process restart.
Owner-scoped report, hypothesis, and deletion endpoints use the same PC relay;
deletion is rejected while a background worker is active.

Every automatically generated hypothesis remains `open`. The deterministic
claim checker can associate explicit evidence IDs, but does not infer
diagnoses, causes, or semantic truth. Reports cite only source IDs backed by
stored evidence. LLM composition and semantic reasoning remain unavailable
without a live inference provider.

The chat path supports an explicit `analisar tabular chart` or
`analisar tabular compare` command. It requires a job and document ID from the
same owner and conversation, reopens only the saved CSV/TSV/JSON original,
checks its stored size and extracted-content hash, and then runs bounded
deterministic analysis. Successful results and provenance are persisted in
the job/checkpoint and can be included as document-cited observations in a
report. JDUI blocks are emitted only after the visualization adapter validates
the actual result. Missing/ambiguous columns, units, unsupported data, absent
or truncated originals, and incompatible units return a limitation instead;
no synthetic data is generated.

Example: `analisar tabular chart job=<job-id> doc=<doc-id> x=month y=amount
series=team unit=unit period="2026 Q1" methodology="meter readings"`. Use
`unit=none` only when the data intentionally has no declared physical unit.
Comparison uses `analisar tabular compare` with `group=... value=...
baseline=... unit=...`. JSON must have the tabular `columns`/`rows` shape
accepted by `structured_analysis`; other JSON shapes are rejected.

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
