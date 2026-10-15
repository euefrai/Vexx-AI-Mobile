# JÚLIA Research Agents (V4.5) — papéis e contratos

Papéis são **funções** em `research_agents.py`, não instâncias de modelo.
Todos leem/escrevem o mesmo estado persistido (`research_jobs`,
`research_events`, `evidence`) e emitem telemetria.

| Papel | Função | Produz |
|---|---|---|
| Orchestrator | `executar` | ordem, orçamentos, replan (1 rodada), finalização |
| Planner | `montar_plano`/`replanejar` | etapas busca→ler→analisar→verificar→sintetizar→auditar |
| Search | `agente_busca` | achados (consulta original + variação, dedupe) |
| Analyst | `agente_analista` | evidências com score de relevância |
| Fact Checker | `agente_verificador` | vereditos SUPPORTED/PARTIAL/CONTRADICTED/UNVERIFIED/INSUFFICIENT |
| Contradiction | `detectar_divergencias` (research.py) | pares com assimetria de negação |
| Synthesizer | `agente_sintetizador` | relatório extrativo (LLM=BLOQUEADA, declarado no texto) |
| Auditor | `agente_auditor` | citações fantasmas |

Regras: sem agente decorativo (cada um persiste algo verificável);
verificação LLM marcada BLOQUEADA, nunca validada; cobertura é léxica
(documentada em `avaliar_job`), nunca nota de verdade.
