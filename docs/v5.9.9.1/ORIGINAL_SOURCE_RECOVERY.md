# Original Source Recovery

Reutilizados manchete/publicador, links do HTML e RSS/Atom declarados. Sem decodificação opaca do Google, feed adivinhado, bypass, novo crawler ou API paga. O transporte mantém validações DNS/SSRF/redirect/tipo/bytes existentes.

Seleção agora considera índice/homepage, data explicitamente incompatível, candidato de recuperação original, pertinência e diversidade entre opções equivalentes. Metadados incompletos não proíbem leitura. O teto permanece em seis leituras e três workers, a partir de até doze candidatos. O corte anterior a esse pool ainda é uma limitação; não há uma nova tabela universal de candidatos de todos os jobs.

O nome do veículo é retirado antes de comparar links e feeds. Duplicatas e links de homepage não consomem os dois candidatos de artigo recuperado. Extração usa o URL final para resolver metadados relativos; URL de descoberta continua preservado. `publicado_em` e `atualizado_em` são campos separados. Não se segue automaticamente canonical externo como se tivesse sido lido.

Caso STF/Angola: a mesma URL era o sétimo candidato e não tinha leitura no baseline. Depois foi selecionada, com 2782 caracteres extraídos. Continua rejeitada por publicação insuficiente; uma notícia sobre autoridade angolana também não comprova ocorrência territorial em Angola. No HTML foram observadas data em hora-atualizacao e legenda do evento; nenhuma foi promovida a publicação. `source-reading-gain.json`, `stf-date-diagnostic.json` e fragmento público preservam a evidência.

Na medição final, dois candidatos carregaram método explícito de recuperação no publicador e ambos foram lidos; nenhum foi elegível. Essa contagem não inclui todos os artigos encontrados diretamente nem comprova originalidade editorial. O baseline não tinha esse campo, portanto a contagem comparativa fica nula. Cache antigo é refeito pela versão5.9.9.1, sem apagar dados reais.

Estados internos existentes permanecem compatíveis. O diagnóstico acrescenta selected/returned/extracted_chars/final_url/content_state/recovery_method/losses. READ_PARTIAL representa extração efetiva, sem promessa de leitura integral ou validação de todas as afirmações.

A ancoragem técnica nova reconhece classes qualificadas com CamelCase e os modelos identificados pelo filtro existente; não é um extrator universal de entidades. Funções qualificadas minúsculas e identidade semântica ampla continuam pendências.
