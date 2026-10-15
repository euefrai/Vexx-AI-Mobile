# JÚLIA Research Evaluation (Quality Lab, V4.5)

`avaliar_job(db, owner, job_id)` — métricas determinísticas com metodologia
declarada em `metodo` (sem nota de verdade):

cobertura (overlap sub↔trecho), subs, evidências, fontes únicas e
independentes (domínios), contradições, parciais, não-verificadas,
sustentadas, atualidade (`acessado_em`), latência (criado→atualizado),
buscas, páginas, replans, erros, pendências.

## Casos (`tests/test_research_quality.py`)

factual simples · informação falsa (não confirmada, zero sustentadas) ·
contraditórias/duplicadas · desatualizadas (atualidade via acesso; publicação
só quando conhecida) · longa/interrupção/reconexão/cancelamento · falha de
provedor (pendências, cobertura 0) · falha de modelo/LLM-real (skip
declarado BLOQUEADO) · multiusuário · prompt injection (dado, não comando) ·
citações sem suporte (auditor) · checkpoint/retomada (retenção) ·
cancelamento durante execução.

## Separação

unitários (funções puras) · simulados (fixtures HTTP/provedores falsos,
marcados pelo prefixo Fake) · busca real (sondas manuais documentadas, fora
da suíte) · LLM real (skip BLOQUEADO) · E2E (chat determinístico sem LLM em
`test_cmd_pesquisa_memoria`; fluxo agêntico completo com LLM real: BLOQUEADO
até o provedor voltar).
