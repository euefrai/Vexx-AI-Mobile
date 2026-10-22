# V5.9.3 — Precision / Universal Benchmark 3.0

Execução em 22/10/2026, sem push/deploy. JSON reproduzível: `qa-artifacts/v593/universal-v3.json`, gerado por `tools/report_precision_v593.py`. Capturas de rede e replays determinísticos estão separados. Nenhuma inferência foi executada.

## Definições do Quality Lab v2

O dataset congelado `benchmarks/research_quality_v2.json` contém **12 documentos sintéticos e 8 consultas**. Unidade: documento recuperado por consulta, convertido de chunks pelos nomes dos arquivos. Os números principais são médias macro entre consultas; não representam precisão universal ou precisão da busca web.

- P@K: quantidade de IDs relevantes únicos no top K dividida por **K**, mesmo quando retorna menos de K.
- Recall@K: IDs relevantes recuperados / total de IDs com grau positivo no gabarito.
- nDCG@K: ganho `2^grau - 1`, desconto `log2(posição + 1)`, normalizado pelo ranking ideal.
- MRR: inverso da posição do primeiro documento com grau positivo; não distingue original de republicação quando ambos têm grau positivo.
- Precisão dos retornados (micro, adicional): total de acertos relevantes / documentos efetivamente retornados, somando consultas. Não substitui P@K.

O gabarito tem 13 pares consulta/documento positivos. Assim, o teto de P@5 neste dataset é **0,325**, e de P@10 é **0,1625**. O caso de frutas inclui maçã/laranja como relevância parcial; os dois falsos negativos remanescentes não foram artificialmente adicionados à resposta para elevar recall.

| Medida | Antes | Depois |
|---|---:|---:|
| P@5 macro | 0,275 | 0,275 |
| P@10 macro | 0,1375 | 0,1375 |
| Recall macro @5/@10 | 0,916667 | 0,916667 |
| nDCG @5/@10 | 0,925589 | 0,982614 |
| MRR @5/@10 | 1 | 1 |
| Precisão micro dos documentos retornados @5 | 11/13 = 0,846154 | 11/11 = 1 |
| Consultas com pelo menos um relevante | 8/8 | 8/8 |

Ganho: dois documentos fora de contexto saíram da consulta temporal e republicações explicitamente declaradas ficaram abaixo do texto original. Os 11 acertos foram preservados. Esse ganho de precisão dos retornados não é uma elevação de P@5.

SHA-256 do dataset v2: `4e4f5f2e773800a3c05537432f280513c7f7bd487dd8a395e77bc66d19e93e8f`.

## Conjunto adicional congelado

`benchmarks/precision_holdout_v593.json`: **3 consultas, 18 candidatos**, criado antes das mudanças e mantido sem ajustes de gabarito. É um holdout sintético pequeno, não uma avaliação cega externa. A reprodução fixa o relógio de consultas em 22/10/2026; o baseline foi executado nessa mesma data. Não houve ajuste posterior por saídas individuais.

| Medida macro | Antes | Depois |
|---|---:|---:|
| P@5 | 0,4 | 0,4 |
| P@10 | 0,2 | 0,2 |
| nDCG@10 | 0,843401 | 1 |
| Precisão dos candidatos elegíveis | 0,388889 | 1 |
| Recall dos candidatos elegíveis | 0,666667 | 1 |

P@K avalia todos os candidatos ranqueados; elegibilidade avalia o subconjunto aceito pelo filtro. Ambos são apresentados para não esconder o trade-off. Nenhum desses números é precisão universal. Hash do holdout: `8adc5b7f0b7d70580d7fcfe9e7702d8e7bf1b84f23b1db9aca451b7d02401115`.

Reprodução: `python tools/precision_eval_v593.py --output <novo.json>`. Os arquivos `precision-before.json`, `precision-after.json` e `metrics-comparison.json` guardam resultados por consulta, métricas e hashes.

## Diagnóstico dos erros

| Classe | Evidência / tratamento |
|---|---|
| FALSE_POSITIVE | Dois documentos acadêmicos entravam pela palavra genérica trial na consulta temporal; removidos quando há cobertura forte do assunto |
| FALSE_NEGATIVE | Dois documentos de frutas com grau parcial não recuperados; gabarito preservado, sem expansão artificial |
| RANKING_ERROR | Republicação acima do original em dois casos; reranking antes do corte e declaração explícita de cópia |
| INTENT_MISMATCH | Acessório confundido com produto; turismo confundido com evento ou rota |
| SOURCE_MISMATCH | Guia turístico menciona cidades/voos incidentalmente; agora exige contexto de transporte no título ou itinerário estruturado |
| TEMPORAL_MISMATCH | Publicação fora da janela, evento fora da data; publicação não prova ocorrência |
| ENTITY_MISMATCH | Modelo incorreto, cidade/estado homônimo e rota incompatível |
| INCOMPLETE_EVIDENCE | Sem data do evento, inventário, página original ou texto científico suficiente; resultado permanece parcial |

## Avaliação A–L

| Grupo | Evidência desta versão | Resultado / limite |
|---|---|---|
| A Produtos | LIVE_RETRIEVAL de geladeira, ferramenta e livro; DETERMINISTIC de sete famílias | Zero ofertas externas confirmadas. Sete pipelines JSON-LD → filtros → JDUI aprovados com dados sintéticos |
| B Aéreo | LIVE_RETRIEVAL Salvador → São Paulo +30 dias | Nenhuma tarifa/disponibilidade confirmada; falso positivo turístico identificado e rejeitado em replay |
| C Rodoviário | LIVE_RETRIEVAL Salvador → Feira, Salvador → Itabuna, Itabuna → Salvador | Sem tarifa/assento/horário verificado; rota direta não presumida |
| D Notícias municipais | LIVE_RETRIEVAL Ubatã/Salvador/Feira | Manchetes datadas encontradas em RSS; original não lido, fatos não confirmados |
| E Notícias regionais | Contrato DETERMINISTIC cidade+estado e LIVE_RETRIEVAL de fontes locais/regionais | Menção regional não prova ocorrência municipal; sem E2E de cobertura regional completa |
| F Eventos | LIVE_RETRIEVAL Recife | Turismo não aceita evento; nenhuma agenda/data/ingresso confirmado |
| G Moedas | LIVE_RETRIEVAL e BROWSER_E2E USD/BRL | Referência diária/histórico, sem preço negociável ou horário da taxa inventado |
| H Ciência | LIVE_RETRIEVAL baterias, semicondutores e Transformer | Três abstracts pertinentes para cada um dos dois primeiros; PDF Transformer acima de 2 MiB; sem full text útil confirmado |
| I Documentação | LIVE_RETRIEVAL FastAPI/Django | Duas fontes úteis lidas; contratos adicionais para Python/asyncio |
| J Deep Research | DETERMINISTIC de recuperação, contradição, proprietário/checkpoint; BROWSER_E2E worker real com fonte fixture | Síntese/evidências/reload/SSE exercitados, sem inferência real |
| K Imagens/vídeos | BROWSER_E2E de bytes locais, imagem/zoom; contratos e renderer de vídeo | Sem novo vídeo externo assistido/transcrito/analisado |
| L Documentos/arquivos | Experiência 16/16 e BROWSER_E2E exportação | Documento/planilha locais e download de arquivo; não valida todos os PDFs externos |

## Capturas externas e replays

`live-before.json`: seis sondas pré-mudança. `live-after.json`: 16 sondas após o primeiro incremento. `air-repair.json`, `bus-repair.json` e `transformer-repair.json`: repetições pontuais após correções concretas; nenhum loop para insistir em site bloqueado.

O snapshot aéreo chegou a aceitar um guia turístico como pertinente. A inspeção do conteúdo demonstrou falso positivo. O snapshot foi preservado e a revisão determinística no benchmark o rejeita; **não conta como rota verificada**.

Notícias: o snapshot retornou estado páginas ilegíveis para metadados de RSS. A correção mantém o estado público compatível `parcial` e informa que só encontrou manchetes. Três replays, usando exclusivamente fontes capturadas, demonstram esse estado sem nova chamada externa. Não são novas leituras de artigos.

Ciência: uma tentativa de PDF RSC foi bloqueada; Transformer excedeu o limite de download. Um PDF de outro assunto foi efetivamente extraído e identificado, mas rejeitado por irrelevância; não conta como evidência científica útil. A filtragem prévia agora evita esse gasto quando os metadados já não correspondem ao assunto, demonstrado por teste. Limite HTML/PDF de 2 MiB preservado.

Shopping: geladeira chegou a extrair quatro produtos de catálogo, mas os itens exibidos não atingiram confirmação/condições; diagnóstico registra orçamento, variantes, disponibilidade de página e bloqueios. Ferramentas/livros sofreram falta de dados estruturados, listagens e bloqueios. Links de licença Creative Commons encontrados no trajeto agora são excluídos dos candidatos de produto. Nenhuma validação foi relaxada.

Tempos são snapshots, sem controle de cache/rede. Baseline: aéreo 11,957 s, ônibus 5,675 s, Ubatã 8,955 s, Salvador 6,229 s, eventos 6,355 s, ciência 1,252 s. Tempos posteriores por consulta estão no JSON; não se declara aceleração global. Para ciência, contar abstracts, páginas e PDFs separadamente.

REAL_MODEL: probe loopback `/models` não forneceu catálogo JSON válido; nenhuma inferência executada. PROVIDER_BLOCKED e limites de recurso ficam nos diagnósticos, não viram sucesso.
