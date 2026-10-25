# Corpus público curto e rastreável

`benchmarks/real_evidence_v5995.json`: 20 registros, cada um com pergunta/requisito, entidade/atributo/relação, trecho literal de até 420 caracteres, URL/título, estado de leitura, justificativa, snapshot, offset no texto retornado e hashes. Não são páginas inteiras. O coletor registra uma âncora ausente como lacuna, em vez de fabricar o trecho.

11 DEVELOPMENT, 6 VALIDATION, 3 SEALED_HOLDOUT. Agrupamento por documento/URL normalizada, inclusive variantes de idioma MDN. Não se comprovou ausência de toda duplicação por sindicação; não chamar esta divisão de experimento humano cego.

Rótulos presentes: DIRECT_SUPPORT 5, PARTIAL_SUPPORT 2, WRONG_ATTRIBUTE 3, WRONG_ENTITY 3, WRONG_RELATION 1, TOPIC_ONLY 1, INSUFFICIENT_CONTEXT 2, UNREAD 3. **Faltam casos públicos revisados de CONTRADICTORY e IRRELEVANT**; a taxonomia completa não está demonstrada pelo tamanho do corpus.

Todas as anotações são MODEL_PROPOSED, pelo mesmo agente que implementa. Não há HUMAN_REVIEWED independente nem ground truth certificado. `annotation-review.json` registra `real-15` como UNVERIFIED: o trecho literal mostra infobox/landmarks, enquanto a localização mais precisa aparece no título externo ao trecho. O rótulo original foi preservado. Não usar esse item para alegar recall parcial.

O corpus sintético anterior permanece separado. Nenhum trecho selado foi usado para regras específicas. Capturas externas brutas do benchmark ficam locais e têm manifesto de hashes; relatórios e corpus curto são versionados. Próximo passo: revisão independente e ampliação equilibrada antes de nova calibração/novo holdout.
