# Recall, filtros e preservação

O recall foi melhorado em pontos de perda demonstráveis, sem declarar uma taxa universal: metadados permanecem no filtro final, até doze candidatos atravessam a pesquisa rápida e feeds não ocupam as seis posições de leitura de artigos. Imagens Commons são metadados visuais, sem tentativa inútil de ler seu binário como HTML.

`candidate_report` preserva até 24 referências com ID SHA256 estável por URL canônica, URL, título, provedor, consulta, data, tipo, estado, leitura, motivos e trecho curto. Contabiliza candidatos omitidos; não grava páginas inteiras. O cache SQLite existente guarda esse diagnóstico com TTL e limite JSON. O comportamento anterior de pular cache grande sem truncar evidências foi preservado.

Datas explícitas de hoje/ontem e última semana são resolvidas no fuso do pedido. Notícias mantêm local/região/tópico nas variantes e replanejamentos. A validação final conserva data de publicação e distingue data de acontecimento. Estado de feed/snippet não vira leitura de artigo. Janela em dias segue o contrato calendário existente; precisão por hora exige timestamp suficiente.

Descartes continuam explicáveis por ENTITY_MISMATCH, SOURCE_MISMATCH, TEMPORAL_MISMATCH, INCOMPLETE_EVIDENCE, INDEX_PAGE e TOPIC_MISMATCH, além do diagnóstico de relevância. Um candidato encontrado e rejeitado para resposta continua rastreável no reservoir. Isso não prova que a entidade ocorreu no local citado em toda página; ainda há limites semânticos e homônimos.

O ganho de regressão é específico: notícia válida com data mantida atravessa o filtro, cidade/data incompatíveis continuam rejeitadas e originais posteriores a seis feeds alcançam o leitor. Métricas de recall/precisão sobre toda a web não são calculadas sem julgamentos independentes. O reservoir do caminho rápido não é uma nova tabela universal de candidatos de todos os jobs; eventos/evidências do controlador continuam sendo a persistência profunda.
