# Avaliação independente do conjunto, não do julgador

Quinze consultas congeladas antes das alterações no motor (`2c6a324`). Perguntas e benchmarks anteriores não foram alterados. Os resultados novos não foram inspecionados durante a otimização. Após abrir o holdout, nenhum algoritmo/consulta será ajustado para pontuá-lo melhor. `holdout-judgments.json` contém critérios, URLs, escopo lido, artefatos e julgamentos por caso. O revisor é o agente Codex lendo os trechos, não painel humano independente nem o próprio flag de elegibilidade do motor.

**Resultado central: não demonstrou melhora consistente suficiente para publicar.** O motor marcou duas leituras elegíveis tanto antes como depois. Esse número sozinho é enganoso: a página geral de WebAssembly não traz a operação memory.grow solicitada, e a página de história geral do baseline não sustenta o pedido específico sobre Chibata. A rodada final encontrou um artigo com uma passagem específica sobre a causa da Revolta da Chibata; as consequências não estavam no trecho limitado. É um ganho parcial em um caso, não quinze pesquisas concluídas.

| Casos | Julgamento do conteúdo devolvido |
|---|---|
| 01–03 notícias | Portais/cidade/turismo, sem artigo pertinente lido que satisfaça tema/localidade/período |
| 04 pessoa, 05 empresa | Moldura biografia/história ainda domina; pessoa/empresa e fonte primária não recuperadas adequadamente |
| 06 WebAssembly | Contexto geral; operação específica e documentação requerida não recuperadas |
| 07 Chibata | Antes: catálogo genérico. Depois: passagem sobre causa em artigo abrangente; cobertura parcial, sem conclusão sobre consequências |
| 08 cultura, 09 lugar, 10 evento | Outras acepções de obra/parque/ouro, sem identidade/requisitos pedidos |
| 11 SQLite | Home/download não substituem documentação de WAL/checkpoint/leitores |
| 12 produto | Marca/especificações genéricas não provam modelo/peso/bateria |
| 13 imagens | Seis registros Commons com origem e direitos declarados em ambas as rodadas; metadados, sem análise visual no probe |
| 14 vídeo, 15 PDF | Páginas genéricas, sem vídeo específico ou PDF pertinente lido |

O julgamento dos trechos específicos passou de zero para um caso parcialmente útil; o caso de mídia manteve os mesmos metadados. Não se calcula recall absoluto, precisão factual global ou índice de respostas completas: não há oráculo de todas as URLs relevantes nem síntese executada nessas quinze sondas. Rejeições incorretas e relevantes perdidos no conjunto inteiro permanecem desconhecidos; exemplos auditados não são denominadores universais.

As métricas mecânicas completas, inclusive latência/chamadas, estão em `comparison.json`. Contam-se separadamente fontes devolvidas abertas, pool de candidatos, respostas brutas e metadados de mídia. Fetches observados não equivalem a todos os redirects/pacotes ou downloads binários. A rede é viva, portanto mudanças agregadas não têm atribuição causal garantida. O relógio do parser final é ancorado no baseline; o aplicativo continua em tempo real.

Próximo experimento: separar atributos requeridos das entidades em pedidos compostos, detectar resposta de provedor que ignora termos centrais, preservar caminhos para documentação/links específicos efetivamente descobertos e validar exclusões/tempo antes da composição. Usar o conjunto atual apenas como diagnóstico e congelar outro holdout antes de otimizar novamente. Não transformar contexto geral em evidência elegível para inflar resultado.
