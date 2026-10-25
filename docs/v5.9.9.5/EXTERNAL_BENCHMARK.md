# Comparação externa e replay separado

`benchmarks/search_reliability_v5995_holdout.json`: 16 perguntas novas, congeladas antes da implementação, cobrindo empresas, autores, programação, produto, notícias locais, eventos, cursos, lugares, ambiguidade e pergunta sem dado público garantido. Conjuntos anteriores permanecem intactos como diagnóstico.

Baseline da aplicação 31b063c; candidato de recuperação d8157fd congelado com hashes antes de abrir resultados. Mesma pergunta/hash de dataset e relógio do pedido preservados. Rede/índice variam; isto não é experimento causal com ambiente idêntico.

| Contagem observada | Baseline | Candidato |
|---|---:|---:|
| Perguntas | 16 | 16 |
| Leituras abertas | 47 | 44 |
| Leituras marcadas elegíveis pelo motor | 0 | 3 |
| Perguntas com essas flags | 0 | 1 |
| Chamadas observadas | 87 | 84 |
| Fetches observados | 173 | 162 |
| Mediana em segundos | 8,358 | 7,061 |

As três leituras se concentram em Object.assign: artigo técnico, índice MDN e referência MDN. Há trechos pertinentes realmente recuperados, mas uma flag DIRECT_ANSWER não garante cobertura semântica inteira nem verificação do autor/originalidade. Não houve síntese/chat neste benchmark. Não aceitar uma página genérica ou outro atributo como resposta para aumentar contagem.

Replay congelado, sem rede: os mesmos 47 textos únicos retornados pelo baseline, reclassificados pelo motor final, passam de 0 para 2 flags de elegibilidade. Não mede nova descoberta, navegação, síntese ou recall global. Dados resumidos em `external-comparison.json`.

Após freeze houve correções por probe real e suíte (prompt/academia); documentadas em `post-freeze-changes.json`. Não se rebatizou o teste observado como cego do código final. Capturas brutas locais não são redistribuídas; manifesto com hashes e resumos versionados. Não houve ajuste usando exemplos selados.

**Decisão: NO_GO.** Ganho em 1/16 não é melhora consistente universal. Sem gold independente não há estimativa defensável de precisão/recall da população. Nova otimização deve começar por causa observada no planejamento e um novo teste independente congelado.
