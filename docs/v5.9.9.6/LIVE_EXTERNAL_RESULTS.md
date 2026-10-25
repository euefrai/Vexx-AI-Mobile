# Diagnóstico externo real, resultado NO_GO

Caso `ctx-01`: Como usar Math.hypot, qual a sintaxe e o valor retornado?

| Medida | Baseline | Candidata |
|---|---:|---:|
| Buscas cobradas | 3 | 3 |
| Páginas cobradas | 12 | 12 |
| Registros com texto lido | 4 | 0 |

Baseline carrega os módulos históricos query_intelligence/research/research_agents de `39644ca` em subprocesso isolado. Não é restauração integral de todo o release. Candidata usa arquivos locais; leituras ocorreram em horários diferentes, sem respostas congeladas. Não inferir causalidade ou recall global dessa comparação.

As consultas candidatas mantêm Math.hypot; baseline enviava dois fragmentos genéricos. Porém a candidata rejeitou as 12 extrações por relevância e terminou parcial. As quatro evidências anteriores não foram revisadas como gold factual. Nenhuma síntese com modelo real foi executada.

Artefatos: `qa-artifacts/v5996/live-ctx01-before.json` e `live-ctx01-after.json`. `ctx-01` foi inspecionado e só poderá ser usado como diagnóstico daqui em diante, não como holdout novo.

Após este probe, foram corrigidos o ID opcional no trace, a análise de request incompatível e a conservação da faceta nova no replanejamento. O JSON externo não representa uma nova execução dessas alterações finais; não há alegação de melhoria posterior.

## Casos adicionais e DEV

`ctx-02` Bosch: três buscas, 12 slots, zero evidências utilizáveis, interrompida. `ctx-03` Revolta da Vacina: duas buscas, 12 slots, uma fonte lida; estado técnico concluída não equivale a síntese fundamentada aprovada. Ambos sem modelo, sem gold e sem par baseline. Restam cinco perguntas externas não executadas.

DEV da pergunta original Object.assign, com capturas privadas limitadas e trace de transporte: três buscas, 12 slots, três evidências armazenadas; apenas sintaxe com passagem. Retorno/comportamento continuam sem cobertura. Sete leituras foram rejeitadas por entidade. O resultado é diagnóstico de desenvolvimento e não teste independente. Capturas de extração ficam ignoradas em `dev-private`; manifesto público contém hashes, não páginas completas.
