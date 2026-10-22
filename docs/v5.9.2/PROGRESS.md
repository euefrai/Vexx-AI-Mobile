# V5.9.2 — progresso em 22/10/2026

HEAD inicial cccd8b5, checkout limpo. Código final: 74f3b22; HEAD de entrega é o commit que contém este documento. Sem push/deploy/reinício de produção. Skill token-efficient aplicada.

Implementação e validação local concluídas:

- Baseline externo de sete casos; reproduzidas síntese obsoleta e evidência não lida sustentando afirmação.
- Recuperação invalida derivados, preserva assunto/modelos/unidades, respeita orçamento, reutiliza leituras e interrompe rodada sem ganho. Síntese do checkpoint exposta no resumo.
- Evidência separa descoberta/leitura/abstract; divergência numérica aberta não prova contradição.
- Contrato compartilhado de rotas, datas persistidas, localidades e moedas; câmbio diário/histórico Frankfurter/ECB integrado ao fluxo existente.
- Fontes/JDUI, zoom, gráfico mobile, replay/reload autenticado e proteção contra callbacks de outra pesquisa. Revisão final corrigiu barra persistente após stop e ações sobrepostas; novo Chrome verifica estados inicial/final. Watchdog de status a cada cinco segundos durante job ativo recupera SSE parado após reconexão; sem consultas sobrepostas, com limpeza no stop/troca.
- Suíte final: 1059 passed, 4 skipped, 2 warnings, 255,57 s. Cinco regressões da primeira execução corrigidas sem alterar testes antigos; falhas preservadas em full-suite-first.txt.
- Pesquisa 34/34, shopping 59/59, experiência 16/16 reexecutados após reparos. Novos contratos 32/32, sem medir qualidade de recuperação.
- Chrome real: reload em execução, interrupção/reconexão SSE, 43 eventos ordenados, fontes, imagem/zoom/Escape, exportação e câmbio externo pelo chat. Desktop 1280/mobile emulado 390/320; zero erros registrados. Gráfico com 22 pontos e quatro rótulos sem sobreposição.

Cobertura externa parcial: zero tarifas/inventário confirmados, notícias insuficientes, eventos somente contexto. Ciência com três abstracts/DOIs, sem full text demonstrado. Sem inferência de modelo no E2E. Ver relatório, UNIVERSAL_BENCHMARK e JDUI_RESULTS.

Próximo passo exato: melhorar descoberta por fontes oficiais/específicas para notícias locais e transporte e repetir as sete sondas externas, sem compras/reservas/contorno de bloqueios. Outras pendências: precisão de ranking, vídeo/aparelho físico/modelo real. Não afirmar cobertura completa com base em fixtures.
