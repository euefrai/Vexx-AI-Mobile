# V5.9.6 — benchmark profundo

Data: 23/10/2026. Dataset `benchmarks/deep_retrieval_v596.json`; avaliação detalhada em `qa-artifacts/v596/assessment.json`.

Estados: CONFIRMED exige atendimento no escopo declarado; PARTIAL possui informação recuperada mas resposta incompleta; UNAVAILABLE não recupera o dado específico; FAILED indica erro interno; BLOCKED indica impedimento externo. Links e mídia genérica não promovem sucesso.

| Categoria | Estado | URLs descobertas | Fontes lidas* | Mídias descobertas** | Latência s |
| --- | --- | ---: | ---: | ---: | ---: |
| science | UNAVAILABLE | 24 | 0 | 7 | 4.948 |
| technology | PARTIAL | 13 | 0 | 8 | 9.411 |
| products | UNAVAILABLE | 6 | 0 | 0 | 8.94 |
| news_local | PARTIAL | 15 | 0 | 0 | 5.953 |
| news_national | UNAVAILABLE | 18 | 0 | 8 | 5.745 |
| events | UNAVAILABLE | 6 | 0 | 8 | 9.849 |
| flights | UNAVAILABLE | 7 | 0 | 8 | 2.765 |
| bus | UNAVAILABLE | 12 | 0 | 8 | 4.911 |
| documentation | PARTIAL | 6 | 1 | 0 | 1.762 |
| videos | UNAVAILABLE | 10 | 0 | 0 | 3.582 |
| images | CONFIRMED | 12 | 0 | 5 | 2.216 |
| pdfs | PARTIAL | 17 | 2 | 8 | 10.371 |
| comparison | BLOCKED | 28 | 2 | 15 | 30.625 |
| scarce | UNAVAILABLE | 6 | 0 | 8 | 5.327 |

* Leitura inclui resumos quando marcados como tais. `full_text_sources` no JSON separa texto completo com extração limitada. Zero artigo local original lido. ** Mídias genéricas/não analisadas são contagem de descoberta, sem aprovação de pertinência; somente o caso images confirmou cinco imagens pertinentes e carregadas.

As 14 perguntas e suas restrições, fontes/trechos, síntese, schema JDUI, chamadas observadas e motivo de falha estão nos JSONs individuais apontados por `artifact`. Custo registra tentativas de provedor, slots de página e chamadas de modelo, não custo monetário nem número total de redirects/requests HTTP. Tempos são amostras pontuais, não SLA.

## Separação de provas

- FIXTURE: contratos, segurança, vídeo estruturado, seções científicas, UTF-8 fragmentado e benchmarks congelados. Não contam como oferta/artigo/vídeo real encontrado.
- FROZEN_REPLAY: 13 capturas comerciais reais da V5.9.5 reavaliadas sem rede, em `commercial-replay.json`. O novo caso LIVE_EXTERNAL comercial é notebook Lenovo 16 GB até R$ 3.000; zero oferta confirmada. Não foi alegado novo teste externo de 13 categorias comerciais.
- LIVE_EXTERNAL: 13 categorias com modelo desabilitado explicitamente; repetições dirigidas após correções foram preservadas. News local inclui RSS com datas antigas/recentes, sem artigo original; feed não satisfaz o pedido.
- REAL_MODEL: dois diagnósticos limitados (160/1.800 tokens) e investigações registradas separadamente. A aceitação final recuperou dois PDFs mas a síntese recebeu rate_limit; sem retry posterior. Probe de 184 chunks não aprova resposta científica.
- CHROME_E2E: componentes com capturas públicas reais, não aplicação autenticada. Galeria, comparação, documentos/fontes, CSV, link e fallback testados. SSE é replay; cancelamento real de job coberto separadamente em pytest. Nenhum vídeo real foi exibido para simular cobertura.

## Antes/depois e preservação

Imagens pertinentes entregues: 0 → 5. Anúncio Lenovo de título 8 GB: RAM antes desconhecida/aceito parcial, agora conflito e excluído do pedido 16 GB. Inferência com limite curto: 0 chunks; orçamento normal: 184 chunks. Recuperação final da comparação: dois PDFs limitados; sem síntese experimental aprovada. Ofertas/tarifas confirmadas e artigos locais lidos permanecem zero.

Benchmarks congelados: Search 34/34, Shopping 59/59, Experience 16/16. Quality Lab: precision@5 0,266667, recall/MRR/nDCG 1, duplicação 0; preservado em relação ao baseline. Isso mede fixture de documentos, não precisão universal da web.

As rodadas `live-final` e `live-model-deep-final` encontraram uma regressão interna de schema e não são resultados aprovados. Logs foram preservados; somente artefatos apontados pela avaliação consolidada sustentam a aceitação final. Não se modificaram gabaritos para melhorar métricas.
