# Orçamento de leitura

Limites de páginas, buscas, workers, tokens e replanejamentos não foram aumentados. Lookup SQLite ocorre antes de submeter trabalho à rede. Reuso não cobra slot; nova tentativa efetiva de leitura cobra, inclusive quando falha. Cache pode ser reavaliado com orçamento de páginas zerado; nenhuma nova leitura é submetida nesse caso.

| Replay idêntico | Leituras/slots antes | Depois | Evitadas | Evidências antes → depois |
|---|---:|---:|---:|---:|
| API, texto extraído | 12 | 8 | 4 | 3 → 2 |
| WEG, texto extraído | 12 | 8 | 4 | 0 → 0 |
| API, HTML e extrator real | 12 | 6 | 6 | 0 → 0 |
| WEG, HTML e extrator real | 12 | 5 | 7 | 0 → 0 |
| Chibata, HTML e extrator real | 10 | 7 | 3 | 0 → 0 |
| API semeada, HTML | 4 | 4 | 0 | 1 → 1 |

Nos três replays HTML de desenvolvimento: 34 → 18 leituras, redução de 16 (47,1%). São chamadas dentro de um replay local sem rede; não são 16 downloads externos economizados em produção. Zero evidências finais nesses três: economia operacional sem ganho de resposta demonstrado.

`FROZEN_MISSING` é falta no corpus congelado, separada de erro real da fonte: API HTML 2/2 antes/depois, WEG 0/0, história 2/2, semeado 3/3; textos API 4/4 e WEG 6/6. Não excluir essas tentativas do custo. Contagens, URLs distintas, durações, cache e SQLite: `qa-artifacts/v5997/replay-summary.json`.
