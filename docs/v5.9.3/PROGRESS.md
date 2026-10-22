# V5.9.3 — progresso

HEAD inicial 78dae77, árvore limpa. Skills diff-code-writer e token-efficient aplicadas. Sem push/deploy. Sem agentes paralelos.

Baseline: Quality Lab v2 avalia documentos locais sintéticos, unidade documento recuperado por consulta, macro média, P@K com denominador K fixo, recall pelos IDs com relevância positiva e nDCG graduado. Não mede a busca web. Gabarito inclui frutas parcialmente relevantes, por isso recall baixo nesse caso não implica automaticamente falha de assunto.

Defeitos observados: FTS limitado antes do reranking; republicação acima de original; palavras em contexto errado elevam relevância; consultas locais com “de” não extraem cidade; eventos aceitam turismo genérico; registros acadêmicos retornam abstract sem tentar PDF OA declarado.

Pendente: medir baseline/holdout antes de alterar; ranking/contratos verticais e recuperação; testes focados; fontes externas limitadas; JDUI/Chrome; suíte completa somente no final; relatórios/evidências finais.
