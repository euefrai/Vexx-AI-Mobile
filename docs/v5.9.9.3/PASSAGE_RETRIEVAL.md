# Passagens literais

`web_extract.passage_candidates` segmenta apenas o texto de extração devolvido, com limites existentes de 8000 caracteres e até quarenta candidatos. Prefere parágrafos/frases, mantém tokens/números/unidades inteiros e não trata o ponto espaçado de um nome de API como fim de frase. Cada passagem tem ID derivado do texto/URL/início, `text_span` relativo à extração devolvida, URL e seção/página somente quando explicitamente disponíveis. Não são offsets de bytes HTML nem paginação inventada.

Em documentos longos, o extrator seleciona uma janela limitada do texto já extraído ao redor da operação pedida, sem aumentar bytes/páginas. Não se declara leitura integral. `evidence_graph.requirement_coverage` exige entidade e relação no contexto da passagem. Uma empresa citada numa frase não herda a fundação de outra empresa numa frase diferente; negação não confirma o atributo positivo.

Até três passagens literais ficam no registro de cada evidência, com referências compactas no checkpoint e vínculos estruturais no grafo existente. O prompt recebe passagens inteiras até o limite anterior de 1800 caracteres por fonte. Limites dos intervalos são enviados separadamente e uma citação que atravessa passagens não contíguas é rejeitada. Suporte lexical não equivale a verdade e frases com anáfora/paráfrases podem ficar sem classificação suficiente.
