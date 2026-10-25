# Universal Retrieval Benchmark V2

Vinte consultas de avaliação da V599 preservadas; gabaritos congelados intactos. Baseline fresco precedeu mudanças. Dados em `retrieval-comparison-metrics.json`, `baseline-losses.json`, `selection-losses.json` e `delivery-evaluation-losses.json`.

| Medida | Baseline71e978e | Seleção359e354 | Final7011908 |
|---|---:|---:|---:|
| Casos | 20 | 20 | 20 |
| Pool preservado, soma por caso | 193 | 196 | 194 |
| Retornos brutos, incluindo duplicatas | 316 | 328 | 320 |
| Leituras no pool | 91 | 88 | 91 |
| Abertas entre as fontes devolvidas | 54 | 54 | 54 |
| Elegíveis lidas entre as devolvidas | 11 | 11 | 12 |
| Chamadas de provedor | 114 | 114 | 111 |
| Fetches de descoberta/recuperação/leitura | 214 | 214 | 212 |
| Mediana de segundos | 5,771 | 5,700 | 6,064 |

Final: 4ok/3parciais/11sem correspondência/1ilegível/1shopping sem estado padronizado no probe. O aumento agregado em empresa/Embraer não é atribuído causalmente ao patch: a seleção isolada não aumentou elegibilidade e resultados externos variam. O teste de aspas não trouxe ganho e não entrou no produto. Não há comparação estatística controlada, TTFT medido por essa tabela, precisão factual ou recall absoluto.

## Holdout

`source_recovery_v5991_holdout.json`: 12 perguntas independentes, sem gabarito factual fabricado e sem ajuste a partir das respostas. SHA registrado nos arquivos de caso. Rodada final7011908: **0 elegíveis/12 casos**,33 aberturas devolvidas, 110candidatos no pool, 60 chamadas de provedor, 121 fetches, mediana5,847 s. Onze sem correspondência e uma ilegível. Rodada anterior teve uma elegível em Rio Branco; não foi selecionada como resultado final mais favorável. A cobertura ampla continua reprovada.

`tools/bench_source_recovery_v5991.py` reutiliza o probe/motor V599, SQLite em memória, seis leituras, três workers e orçamento existente; limite65 s por subprocesso. Nenhum LLM no benchmark de recuperação. Amostra julgada por agente é estreita e rastreável, sem status de verdade independente.

## Inferência e recursos

REAL_MODEL separado: poolside/laguna-s-2.1: free, 130 chunks ordenados, HTTP200/SSE, fonte Python lida, reprodução literal/citação falhou. Estado PARTIAL; Deep Research não aprovado. Prefixo de transporte limitado a64KB; somente contagens de campos/eventos, sem raciocínio privado exportado.

Snapshot isolado de relay+backend QA: 152,14 MB de RSS somada. Não inclui Chrome/produção, pico de toda a execução nem delta contra baseline. CPU cumulativa por processo consta no artefato; não é perfil de aparelho físico. Latências/chamadas variam com rede e bloqueios. Tetos do produto não foram ampliados em conjunto.
