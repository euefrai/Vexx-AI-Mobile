# V5.9.7 — avaliação

Data: 23/10/2026. Dataset: `benchmarks/research_completion_v597.json`. Consolidação: `qa-artifacts/v597/assessment.json`.

Doze perguntas únicas em pipelines reais com rede e SQLite temporário. Onze executadas em `live-final`; a variante Salvador sem região em `live-model-city`. Modelo desabilitado nas onze para separar recuperação de inferência. A variante Salvador não fez inferência por falta de fonte aceita.

Somente documentação oficial teve fonte lida aceita: **1/12 cenários**. Imagens retornaram cinco itens pertinentes de descoberta; leitura de imagens não foi alegada. **0/12 respostas inteiramente confirmadas; 0/12 sínteses assistidas aprovadas**. Mídia genérica não promove sucesso: os dez cenários restantes ficaram indisponíveis quanto ao dado solicitado.

Testes diretos externos, separados desse denominador: **1/1 artigo original lido** a partir de URL descoberta antes; **2/2 PDFs parcialmente lidos** a partir de URLs OA da V5.9.6. Não contam como novas descobertas completas.

Modelo real: uma rodada adicional de documentação, uma chamada gratuita; síntese rejeitada por quantidade incompatível. Não houve troca para modelo pago. Latências por caso, chamadas solicitadas, slots e URLs estão nos JSONs. Contagens de providers/slots não medem todos os redirects HTTP nem custo monetário ou qualidade universal.

Benchmarks congelados preservados: Search **34/34**, Shopping **59/59**, Experience **16/16**. Quality Lab: precision@5 **0,266667**, recall/MRR/nDCG **1**, duplicação **0**; fixture local, não precisão factual da web.

Baseline completo: **1.374 passed, 4 skipped**, 145,38 s. Logs das falhas intermediárias foram mantidos. Duas falhas eram testes determinísticos herdando o modelo local; passaram a desabilitar inferência explicitamente. O teste de PDF foi adaptado para conferir os novos argumentos de limite e manter a prova de erro do parser. Nenhum teste removido nem asserção de funcionalidade enfraquecida.

Suíte final e gate estão em `RELEASE_DECISION.md`; o último log aprovado, não uma tentativa intermediária, sustenta o número entregue.
