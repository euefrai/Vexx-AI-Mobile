# Seis cenários autenticados reais

Chrome real, conta de teste do harness `serve_admin_qa_v5981.py --research-live`, relay e PC Agent de desenvolvimento, SQLite temporário. Nenhuma URL semeada nos seis cenários. Política sem fallback pago; modelo gratuito configurado `poolside/laguna-s-2.1:free`. Produção não foi usada. Evidência: `qa-artifacts/v5997/e2e-summary.json`.

| Cenário | Tempo observado | DISCOVERY_STATUS | READ_STATUS | EVIDENCE_STATUS | MODEL_STATUS | JDUI_STATUS | OVERALL_STATUS |
|---|---:|---|---|---|---|---|---|
| A Object.assign | 27,217 s | candidatos reais | 3 fontes lidas | parcial | BLOCKED timeout | resultado parcial, 3 cards, reload OK | BLOCKED |
| B WEG | 11,139 s | busca executada | 0 evidências lidas persistidas | insuficiente | síntese LLM não executada | aviso/resultado persistido, reload OK | INSUFFICIENT |
| C Chibata | 15,747 s | busca executada | 0 evidências lidas persistidas | insuficiente | síntese LLM não executada | aviso/resultado persistido, reload OK | INSUFFICIENT |
| D Saúde em Irecê | 15,812 s | candidatos, filtros não comprovados | 0 evidências lidas persistidas | insuficiente | síntese LLM não executada | 6 cards descobertos, reload OK | INSUFFICIENT |
| E Visitantes em Jequié | 20,759 s | busca executada | 0 evidências lidas persistidas | insuficiente | síntese LLM não executada | limitação persistida, reload OK | INSUFFICIENT |
| F toSorted / sort multifonte | 10,737 s | busca executada | 0 evidências lidas persistidas | insuficiente | síntese LLM não executada | limitação persistida, reload OK | INSUFFICIENT |

READ_STATUS descreve registros lidos retidos, não ausência de tentativas HTTP. Todos tiveram SSE HTTP 200 e duas mensagens de assistente (início e resultado); IDs/texto permaneceram após reload. A recarregou durante o job. `completed_flow` no harness indica encerramento técnico, não aprovação científica. Cards de D são descobertas, não fontes lidas ou evidência de notícia correta.

A preservou evidências com `provider_code=timeout`, job interrompida e `synthesis_llm=false`. Não tratar texto extrativo como síntese real. As lacunas, orçamento de síntese e etapas estão no JSON; subconsultas internas completas desses seis não foram capturadas pelo navegador e não são inferidas. Não houve síntese estruturada fundamentada aprovada: **Gate G BLOCKED**, pesquisa completa não aprovada.
