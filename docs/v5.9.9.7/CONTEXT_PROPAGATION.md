# Propagação de contexto

`query_intelligence.discovery_scope` mantém a pergunta original, job, etapa e requisitos em ContextVar, restaurado em `finally`. O orquestrador reaplica as restrições após a transformação linguística em cada consulta normal, retry e recuperação editorial dentro desse escopo. Busca rápida fora da pesquisa mantém seu comportamento.

O teste usa “Compare dois notebooks Lenovo com 16 GB de RAM, excluindo usados”: quantidade, memória e exclusão devem chegar a todas as chamadas internas observadas. Isso cobre o ponto real de chamada do provedor no orquestrador; não prova que toda implementação externa preserve a consulta depois de recebê-la.

Registro limitado a 120 consultas: `Q-*`, texto efetivamente passado, provedor, etapa, estratégia e requisitos `R-*`. Candidatos `C-*` recebem rank e proveniência. Evidências novas e reutilizadas persistem a união limitada de Q/R, sem substituir o documento original por um fragmento de subconsulta. IDs Q referenciados e não registrados: zero nos replays candidatos.

No replay Object.assign, as consultas externas antes/depois são iguais: `Object.assign Sintaxe ou assinatura`, `Object.assign Valor retornado`, `Object.assign Comportamento da operação`. O replay deliberadamente devolve o mesmo pool a cada uma; não mede a qualidade das consultas. O teste de retries verifica a correção contextual separadamente.

Ledger: `query_intelligence.py:15` escopo; `research_agents.py` busca/proveniência; `search_orchestrator.py` chamadas internas; `tests/test_retrieval_efficiency_v5997.py:33` regressão. Consultas externas reais e hashes: `qa-artifacts/v5997/external-summary.json`.
