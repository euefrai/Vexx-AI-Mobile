# Auditoria comparativa dos provedores

Artefato: `qa-artifacts/v5995/provider-audit.json`. 14 adaptadores existentes, 22 chamadas limitadas, sem LLM. Consultas equivalentes nos provedores gerais; consultas próprias para verticais. Cada linha preserva consulta, parâmetros efetivamente enviados, HTTP observado, redirecionamento, URL final, duração, posição, título/snippet curto e hash do corpo quando disponível. Status ausente continua null; uma consulta suprimida pelo circuito não é uma nova resposta HTTP.

| Adaptador | Observação real | Primeira etapa responsável conhecida |
|---|---|---|
| DuckDuckGo | Primeira chamada HTTP 202/bot wall; próximas suprimidas pelo circuito | Disponibilidade/bloqueio, não classificação de conteúdo. Sem bypass. |
| Bing RSS | HTTP 200; mistura homepage, login, lojas/homônimos, portais genéricos e fontes pertinentes | Qualidade/ranking da descoberta varia; homepage oficial pode ser candidato de navegação, não resposta. Não atribuir todo 200 ao classificador. |
| Marginalia | HTTP 200; desafio de espera não reconhecido e licença CC retornada como fonte | Adaptador: detecção e extração de boilerplate. Corrigido com parser inerte e bloqueio explícito. |
| Wikipedia OpenSearch | HTTP 200 e vazio para consultas longas/multifacetadas | Compatibilidade da consulta com autocomplete por título; não prova indisponibilidade geral. |
| Bing News | Vazio nesta consulta | Descoberta sem resultado, não prova ausência de notícias. |
| Google News | 4 resultados com títulos de saúde em Guanambi | Metadados pertinentes; leitura, data, originalidade e suporte ainda precisam ser conferidos. |
| Stack Exchange | 4 resultados sobre Object.assign | Candidatos técnicos, sem promoção automática a resposta. |
| Hacker News | Vazio | Cobertura do índice para a consulta limitada. |
| Crossref / PubMed / Open Library | 4 resultados por chamada | Metadados acadêmicos/bibliográficos; não equivalem a texto integral ou leitura do estudo. PubMed fez duas requisições. |
| Banco Mundial | HTTP 200 com pobreza para `Brazil population` | Adaptador envia `q` não documentado ao catálogo. Corrigido para código específico e verificação do ID. |
| BCB | 1 resultado PTAX | Consulta de série conhecida; não universalizar cobertura financeira. |
| Commons | 4 resultados de imagens | Mídia/metadados, sem evidência textual automaticamente lida. |

O endpoint de catálogo e a consulta por código estão descritos na [documentação oficial Indicator API Queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries) e nas [estruturas de chamada](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures). O adaptador deixou de usar a busca textual não documentada. O teste live posterior retornou `SP.POP.TOTL`, HTTP 200, uma requisição; é descrição do indicador, não o valor da população.

Nenhuma tentativa posterior ao bloqueio conhecido do Marginalia executou scripts ou seguiu o token `sst`. Não foi repetida uma bateria para contornar proteção. Parsers/circuitos têm regressões controladas em `test_search_reliability_v5995.py` e nas suítes existentes.

Cobertura: amostra pequena e não aleatória; não mede ranking global nem recall de provedor. HTTP 200, snippet e originalidade presumida são insuficientes para evidência final. Não foi auditada toda página de cada resultado.
