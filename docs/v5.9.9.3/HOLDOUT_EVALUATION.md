# Avaliação answer-aware

**Ganho consistente de respostas fundamentadas não demonstrado. Não aprovar publicação.** Vinte perguntas/critério foram congelados em `1f5ff18`, antes das correções, e não foram modificados. Baseline de rede nesse commit (motor da V5.9.9.2); rodada posterior em `af400f1`, relógio ancorado por pergunta ao baseline. O conjunto só foi aberto depois do congelamento do motor. A correção posterior de interface qualificada (`86462e9`) veio de QA independente; este conjunto não é apresentado como avaliação independente desse último ajuste.

| Medida mecânica | Antes | Depois (`af400f1`) |
|---|---:|---:|
| Casos | 20 | 20 |
| Leituras elegíveis pelo motor / casos | 2 / 2 | 1 / 1 |
| Leituras devolvidas | 59 | 57 |
| Candidatos no pool | 207 | 193 |
| Chamadas de provedor | 116 | 116 |
| Fetches observados | 218 | 209 |
| Mediana de duração (s) | 5,827 | 5,656 |
| Recuperação pelo mecanismo explícito de original | 0 | 0 |

São contadores, não precisão, recall ou respostas completas. O último contador não conta toda página primária efetivamente aberta: a página do fabricante apareceu, sem receber a marca específica desse mecanismo. A pequena diferença de latência não comprova ganho causal; índices, rede e carga variam. O probe não executa LLM/chat e exclui parte dos downloads binários/redirects da contagem de fetches.

## Revisão dos trechos

`holdout-judgments.json` registra os vinte critérios, URLs e motivos. O revisor foi o agente lendo extrações limitadas, **não um painel humano independente**. Contagens de âncoras do material auxiliar não são julgamento de pertinência.

- **aa-01:** o motor ainda aceita calendário genérico no pedido de criação da Embrapa. O parser não reconheceu essa relação; falso positivo preservado.
- **aa-02:** em vez de jogos sem relação, o depois abriu páginas Tramontina. Há ano declarado de fundação e categorias de produtos no conteúdo lido. Os fundadores não foram recuperados. O classificador rejeitou até os dados parciais úteis; não há prova de entrega fundamentada desse caso ao chat.
- **aa-08:** o antes considerava Array genérico suficiente, embora `toSorted` estivesse ausente do trecho. O depois rejeitou essa fonte como resposta completa. Uma página Array em inglês foi lida com descrição específica do retorno e da imutabilidade de `toSorted`, mas ficou fora das três fontes devolvidas. Não há assinatura/parâmetros completos ou resposta final confirmados.
- **aa-06:** depois houve manchetes de feed, sem leitura de artigo que validasse simultaneamente assunto/localidade/publicação. Descoberta não conta como resposta.
- **Demais:** entidades, datas, exclusões, documentação das duas operações, documento PDF, vídeo individual, galeria e regras do parque não foram sustentados pelos trechos devolvidos. Casos/detalhes estão no JSON, sem inventar conflitos ou dados indisponíveis.

A revisão encontrou zero→um caso com texto parcial útil entre as leituras devolvidas, mais um caso com passagem parcial lida mas não devolvida. **Isso não equivale a duas perguntas respondidas.** Nenhuma resposta completa foi confirmada neste probe. O motor reconheceu aspectos em seis perguntas, onze requisitos, todos sem suporte marcado no resultado final; isso também não mede acurácia de extração. Há entidades mal extraídas e requisitos explícitos não reconhecidos.

## Regressão em replay histórico

`frozen-replay.json` reclassifica apenas leituras devolvidas únicas de extrações V5.9.9.2, mesmo texto/relógio, sem nova descoberta: históricos vinte, 56 leituras, flags 12→11; antigos quinze, 41 leituras, 2→0. O filtro recusa o falso positivo geral de WebAssembly, mas também perde a passagem parcialmente útil de Chibata. Não se chama essa redução de ganho global de precisão. O replay não mede o novo planejamento, navegação nem latência de rede.

Próxima etapa necessária: corpus de passagens com relações/entidades anotadas, análise da fidelidade das respostas dos provedores e tratamento de anáfora/variação linguística sem aceitar apenas assunto. Os vinte casos agora servem apenas para diagnóstico. Congelar outro conjunto antes de otimizar e medir novamente; não ampliar heurísticas usando o conjunto aberto nem afrouxar filtros para elevar flags.
