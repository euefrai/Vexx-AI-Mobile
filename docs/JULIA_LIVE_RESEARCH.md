# JÚLIA Live Research (V4.5)

`JuliaResearchActivityStream` = tabela `research_events` + polling
`GET /api/research/status?job_id=&apos_seq=` (dedupe por `seq` no cliente).

## Eventos reais (só operação confirmada)

`research_created`, `plan_created`, `plan_updated`, `step_started`,
`search_started` (via step), `search_completed`, `source_discovered` (via
achados), `source_opened`, `extraction_completed`, `evidence_registered`,
`claim_verification_started` (via step), `claim_verified`,
`contradiction_found` (via divergência), `agent_started`/`agent_completed`
(não emitidos — sem agentes LLM ativos; declarar, não fingir),
`answer_started`, `answer_delta` (só no chat SSE, não na pesquisa),
`research_completed`, `research_failed`, `research_cancelled`.

Cada evento: id, `seq`, timestamp, research id, agente, tipo, status,
descrição curta, metadados seguros (sem trechos longos, sem segredos),
referência ao resultado (ids).

## Transporte (§12)

Polling 2 s só com painel/job ativo (para em final/offline/10 min).
Reconexão: `apos_seq` reenvia o que faltou, sem repetir ferramentas (poll é
leitura). Isolamento por dono em todas as rotas. PC desliga = worker morre;
estado persiste; retomar continua (sem promessa de execução contínua).
Render não armazena nada definitivo.

## Interface (§11)

Barra compacta (fases: Pesquisando/Analisando/Verificando/Montando +
`feitas/total`) só quando há job; Detalhes expande etapas, fontes (links
reais), erros e botão de resultado; Cancelar chama o backend de verdade.
Sem sidebar permanente; sem raciocínio privado do modelo (só operações).
