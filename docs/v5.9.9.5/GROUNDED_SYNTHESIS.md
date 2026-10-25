# Síntese ancorada — resultado não atingido

Status da rodada: **SOURCE_INSUFFICIENT** nas duas pesquisas autônomas; **SYNTHESIS_REJECTED** nos dois probes isolados. Nenhum SUCCESS_VERIFIED.

Pesquisas novas no chat: WebAssembly.Table.grow com sintaxe/retorno/limitações e Intel com fundadores/data/produtos. Não receberam URLs prontas. Houve descoberta/plano, tentativas de leitura e persistência de resultado parcial; zero evidências utilizáveis, portanto o LLM de síntese não foi chamado nesses jobs. Não trocar a pergunta por uma trivial nem chamar fallback extrativo de síntese real aprovada.

Diagnóstico separado: fonte MDN lida a partir de URL explícita isola inferência. As duas saídas do modelo gratuito foram rejeitadas por IDs e JSON. Esse probe não mede descoberta autônoma. A entrega controlada com URL explícita demonstra cards/persistência, sem inferência LLM, e também não é E2E autônomo.

O plano real revela perda anterior ao provedor: frentes `qual sintaxe`, `valor retornado`, `que ano` e instruções de apresentação sem a entidade. `research_agents._subconsultas_unicas` usa a divisão genérica e não ancora esses fragmentos nos requisitos já disponíveis. Primeira correção futura: manter assunto/restrições por frente usando o parser existente e filtrar instruções de apresentação, com testes contrastivos antes de novo conjunto independente.

Jobs com 12 slots de página e hashes de falhas não permitem concluir que toda perda veio de uma etapa posterior específica. Instrumentação limitada de candidato/leitura precisa melhorar para atribuição causal completa. Registros reais preservados em `runtime-public-research-traces.json`.
