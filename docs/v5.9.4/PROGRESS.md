# V5.9.4 — progresso

HEAD inicial: `24ba58b`. Sem push, deploy ou alteração de produção.

- A: baseline reproduzido em `qa-artifacts/v594/baseline.json`: cidade inteira vazia no geocodificador, cumprimento consumido como cidade, barra rejeitada e fallback de documento de outra conversa.
- B–E: corrigidos intenção, contexto limitado às mensagens anteriores da requisição, geocodificação com UF/país/cadastro IBGE, relógio do sistema, cooldown 429 e seleção de documentos da própria conversa.
- G: reutilizados cards JDUI validados no schema existente, com fontes, estimativa/previsão e data/fuso.
- Checkpoints: 42, depois 57, depois 92 testes passaram; matriz nova inicial continha 35 casos parametrizados (40 ao final). Primeira matriz nova revelou duas expectativas de fixture incorretas (homônimo internacional sem país e card sem type=ui); corrigidas e reexecutadas.
- F/H em execução: pesquisa 34/34, shopping 59/59, experiência 16/16. QualityLab congelado preservou nDCG@10 0,982614 e recall 0,916667. Chrome já apresentou clima real de Ubatã/BA, previsão e horário; execução final e suíte completa em andamento.
- Nenhuma inferência real de modelo foi necessária para os dados ao vivo. O worker de pesquisa usa fonte fictícia claramente identificada, sem substituir os adaptadores meteorológicos reais.

- H: E2E completo aprovado; screenshots desktop/mobile inspecionados. Tabela meteorológica ajustada e conferida a 320/390 px. Regressões resolvidas sem retirar verificações: 88 testes, depois 80, depois 122 (inclui motor 3D).
- Suíte integral intermediária: 1126 passed, 4 skipped, 2 warnings. Revisão final reproduziu captura indevida de pedido 3D pela nova rota geográfica e filtro indevido de código IBGE; corrigidos em `f8c2508`. Consulta real pelo código 2932309 confirmou Ubatã/BA.
- Commits de código: `43b524c`, `786d1d1`, `f8c2508`.

## Concluído

Suíte integral final posterior a todas as correções: **1129 passed, 4 skipped, 2 warnings em 255,76 s**. Benchmark de intenção 16/16, matriz nova 40 casos, benchmarks congelados 34/34 + 59/59 + 16/16 e QualityLab preservados. Último Chrome aprovado no código `f8c2508`: stack real, clima/IBGE/câmbio reais, pesquisa fixture identificada, reload/SSE/43 eventos e telas 1280/390/320. Temperatura atual e faixa da previsão conferem com a resposta pública da API. Git diff --check aprovado.

Entrega arquivada em commit local de documentação/QA posterior aos três commits de código. Sem push, deploy ou alteração de produção. Não há implementação/teste pendente nesta rodada; continuam os limites registrados no relatório (licença não comercial, ausência de inferência real e de histórico original da captura, ambiente local/mobile emulado).
