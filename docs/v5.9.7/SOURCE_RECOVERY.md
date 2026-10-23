# V5.9.7 — recuperação de originais

## Causas corrigidas

- O analista reservava slots de página para itens `feed_metadata`, apesar de não abrir esses itens. Agora os feeds continuam como descoberta não lida, separados do orçamento de páginas; candidatos originais recuperados são priorizados nas notícias.
- O extrator escolhia `WebSite` antes de `NewsArticle` no JSON-LD. A notícia perdia título e publicação, apesar de ambos existirem no HTML. Agora os tipos de artigo têm prioridade, inclusive quando `@type` é uma lista. Removida a travessia dupla de `@graph`.
- Traces registram abertura, extração, rejeição e persistência, com URL sem query/fragmento/credenciais, escopo, caracteres e trecho limitado. Abertura física não se confunde com evidência aceita.

## Prova externa

`qa-artifacts/v597/direct-original.json`: artigo do Bahia Notícias sobre a estudante localizada em Salvador. A URL foi descoberta pela busca real anterior desta rodada, depois submetida diretamente ao leitor existente. Texto extraído: 1.067 caracteres; publicação declarada no próprio artigo: `2026-10-21T06:40:00.000-03:00`.

O teste direto com consulta sobre Salvador aceitou uma fonte lida. Não representa sucesso novo de descoberta completa. Na consulta que exige Salvador **e Bahia**, a página continua rejeitada por `SOURCE_MISMATCH`: o trecho não comprova a região adicional. Não se usou o nome do publicador como prova geográfica.

Ubatã: zero artigo original aceito no fluxo completo. RSS, títulos e resultados genéricos não foram promovidos a notícia lida. Salvador e Recife também não tiveram resposta completa no fluxo de busca avaliado. Os JSONs guardam as razões e os traces; o resultado permanece indisponível, em vez de preenchido com suposições.

Não houve decodificação opaca do Google, URL inventada, bypass de CAPTCHA, autenticação ou paywall.
