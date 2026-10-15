# JÚLIA Research Events (V4.7)

Tipos reais (cada um corresponde a operação confirmada no backend):

`research_created`, `plan_created`, `plan_updated`, `step_started`,
`search_completed`, `source_opened`, `extraction_completed`,
`evidence_registered`, `evidence_linked`, `source_dependency_detected`,
`claim_identified`, `claim_verified`, `claim_verification_completed`,
`contradiction_investigated`, `audit_started`, `audit_completed`,
`research_completed`, `research_failed`, `research_cancelled`.

Não emitidos (sem agentes LLM ativos — declarado, não fingido):
`agent_started`, `agent_completed`, `answer_delta` (só no chat SSE).

Campos: id (seq por job), timestamp, research id, agente, tipo, status,
descrição curta, metadados seguros (trecho ≤300 e url só em
`evidence_linked`; resto é contagem/ids), referência ao resultado.

Persistência no PC (`research_events`, índice por job+seq); replay por
`apos_seq`; dedupe por `seq`; retomada após reconexão sem reexecutar.
