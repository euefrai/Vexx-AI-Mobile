# Contrato implementado e limites

`query_intelligence.retrieval_context` reaproveita `topic_profile` e `answer_requirements`, devolvendo pergunta original, pedido de pesquisa, entidade, requisitos, proteção conservadora de escopo, preferência documental e apresentação.

`context_subqueries` mantém restrições juntas e expande atributos explícitos. `constrain_discovery(..., lock_context=True)` é aplicado pelo agente de busca e no replanejamento. Objetivo do job é a autoridade; um `request` com outra pergunta é reconstruído. Nenhum contexto global de usuário é criado.

A remoção visual só reconhece comandos finais delimitados, sem apagar palavras dentro de títulos como Cards Bonitos ou Museu de Imagens do Inconsciente. Não há promessa de interpretação universal.

Ainda faltam: vínculo persistido query→requirement/source/job completo, propagação às consultas internas dos adaptadores, aliases generalizados, teste conversacional autenticado e tratamento completo de consultas longas. Para manter compatibilidade, a recuperação compacta de pesquisa rápida continua sem o lock estrito.
