# JÚLIA Context Checkpoints 2.0 (V4.7)

Checkpoint = linha `research_jobs` (+`ajustes`: restrições, prioridades,
métricas) + `evidence` + `research_events`. Cobre: objetivo, restrições,
plano versionado, tarefas, evidências, fontes, decisões, contradições,
próxima ação, eventos, cancelamento.

Retomada testada após: reinício do agente (re-`executar`, pula feitas),
queda de rede (polling/SSE reconecta com `apos_seq`), fechar navegador
(estado no PC; painel reanexa), falha de provedor (erros registrados),
interrupção manual (volta do ponto), pausa (espera segura). Limite de
contexto do modelo: N/A sem inferência (registrado quando houver).

Idempotência: etapas feitas puladas por id; evidências por URL única por
busca; replan limitado; sem reinício do zero. Retenção medida
(`test_checkpoint_retencao`, Quality Lab).
