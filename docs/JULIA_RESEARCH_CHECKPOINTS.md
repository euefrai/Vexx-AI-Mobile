# JÚLIA Research Checkpoints (V4.5)

Checkpoint = a linha `research_jobs` + `evidence` + `research_events`.
Tudo que a retomada precisa, sem depender de resumo:

objetivo, plano atual + versão, etapas feitas/pendentes/falhadas, fontes,
evidências com status, contradições, decisões (replans), estado das
ferramentas (orçamentos usados), próxima ação (primeira pendente).

Retomar = `executar` no mesmo `job_id` (pula feitas; `plan_version` não
regride; `achados` só crescem — testado). Resumo compacto de contexto:
`_resumo` (etapas, contagens, pendências) — auxiliar, nunca substituto dos
registros. Troca de modelo/contexto não reinicia nada (estado é dado, não
prompt). Sem promessa de continuidade perfeita: retenção medida no Quality
Lab (`test_checkpoint_retencao`).
