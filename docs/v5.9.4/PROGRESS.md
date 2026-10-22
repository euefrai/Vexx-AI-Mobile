# V5.9.4 — progresso

HEAD inicial: `24ba58b`. Sem push, deploy ou alteração de produção.

- A: baseline reproduzido em `qa-artifacts/v594/baseline.json`: cidade inteira vazia no geocodificador, cumprimento consumido como cidade, barra rejeitada e fallback de documento de outra conversa.
- B–E: corrigidos intenção, contexto limitado às mensagens anteriores da requisição, geocodificação com UF/país/cadastro IBGE, relógio do sistema, cooldown 429 e seleção de documentos da própria conversa.
- G: reutilizados cards JDUI validados no schema existente, com fontes, estimativa/previsão e data/fuso.
- Checkpoints: 42, depois 57, depois 92 testes passaram; matriz nova contém 35 casos parametrizados. Primeira matriz nova revelou duas expectativas de fixture incorretas (homônimo internacional sem país e card sem type=ui); corrigidas e reexecutadas.
- F/H em execução: pesquisa 34/34, shopping 59/59, experiência 16/16. QualityLab congelado preservou nDCG@10 0,982614 e recall 0,916667. Chrome já apresentou clima real de Ubatã/BA, previsão e horário; execução final e suíte completa em andamento.
- Nenhuma inferência real de modelo foi necessária para os dados ao vivo. O worker de pesquisa usa fonte fictícia claramente identificada, sem substituir os adaptadores meteorológicos reais.

Próximo passo: concluir Chrome/SSE/reload, inspecionar screenshots, finalizar suíte completa e relatório com limitações/licenças e evidências.
