# VEXX AI V5.9.2 — Adaptive Deep Search & Universal Research

Entrega local em 22/10/2026. HEAD inicial **cccd8b5**; código funcional final em **74f3b22**. HEAD de entrega: commit que contém este relatório, identificável por `git log -1`. Sem push, deploy ou reinício de produção. Identidade Lucas, 3D, extensão e Fajulto Studio preservados.

## Resultado

Deep Search existente incorpora evidências recuperadas nas conclusões, preserva restrições do pedido e distingue descoberta de leitura. Câmbio diário/histórico real integrado ao fluxo atual. JDUI com fontes mais claras, gráfico legível e retomada após reload. Cobertura universal **parcial**: sem tarifas de transporte verificadas nem cobertura suficiente de notícias locais/agenda futura.

## Causas e correções

1. Replanejamento deixava verificação/síntese/auditoria concluídas: novos dados não alteravam resposta. Agora invalida somente derivados e expõe síntese persistida no resumo público.
2. Recuperação perdia assunto, modelos curtos, unidades e limites. Preserva restrições; resolve datas relativas uma vez, com fuso/parâmetros persistidos.
3. Snippet explicitamente não lido sustentava afirmação. Verificação, independência e síntese exigem evidência elegível; abstracts identificados como abstracts.
4. Diferença numérica virava contradição definitiva. Investigação aberta usa REQUIRES_VERIFICATION/INCONCLUSIVE até verificar.
5. Leituras repetidas gastavam recursos e falhas não eram cobradas ao orçamento. Reutilização por URL, reserva de tentativas, saldo de buscas e parada sem ganho limitam custo.
6. Pedido de moeda caía em busca sem conversão. Adaptador Frankfurter/ECB usa host fixo, downloader seguro, cache, Decimal e validação de par/data/valores; sem inventar horário ou preencher dias.
7. Resultado de eventos com tabelas excedia limite do cache JSON e derrubava resposta válida. Somente JSONLimitError no cache opcional é tratado, com diagnóstico; resposta íntegra e armazenamento estrito preservados.
8. Reload perdia acompanhamento e callbacks antigos podiam pintar outra investigação. Âncora por proprietário, validação de sessão, replay e vínculo do stream ao job corrigem o fluxo.
9. Escopo das fontes pouco claro e datas sobrepostas no gráfico mobile. Campos validados, links seguros, quatro rótulos e datas completas acessíveis corrigem apresentação.
10. Barra de pesquisa permanecia visível após encerramento, com Cancelar sem função. O ciclo de stop agora oculta a barra; layout ativo permite quebra de linha, evitando ações sobrepostas. Chrome verifica estado inicial e encerrado. A checagem reproduziu SSE parado na sequência 11 enquanto servidor já concluído; reconciliação HTTP periódica durante job ativo recupera os eventos/estado final, com limite de uma consulta pendente. Reproduzido antes do reparo em `terminal-stall-reproduction.json`.

Reaproveitados ResearchAgentSystem, SQLite/checkpoints/eventos, ResearchContextStore, Search Orchestrator, leitores seguros, EvidenceGraph, JDUI e live_data. Sem novo motor paralelo, serviço pago ou código arbitrário.

## Pesquisas reais

Sete sondas, parâmetros e comparação em [UNIVERSAL_BENCHMARK](docs/v5.9.2/UNIVERSAL_BENCHMARK.md).

- 100 USD = **502,33 BRL**, taxa **5,0233** de **21/10/2026**, consultada em 22/10. Referência diária ECB via [Frankfurter](https://frankfurter.dev/), sem spread/impostos; não preço negociável em tempo real. Histórico: **22 observações reais**.
- Salvador–São Paulo em 21/11 e Salvador–Feira em 29/10: pedido preservado; **zero tarifas/inventário confirmados**.
- Notícias locais/comparação recente: **insuficientes**. Recife até 05/11: uma página contextual, sem agenda/ingresso confirmado.
- Ciência: três abstracts Crossref/DOIs para baterias; sem full text/inferência. Captura anterior ao reparo da falsa lacuna de notícias, explicitado no benchmark.
- Nenhuma nova oferta comercial confirmada. Snapshot V5.9.1 de 0/3 é histórico; shopping 59/59 não prova estoque/preço externo.

Tempos são snapshots, não comparação estatística controlada. Ganho de moedas vem da consulta estruturada no lugar da busca web.

## Validação

- Suíte completa: **1059 passed, 4 skipped, 2 warnings**, 255,57 s (`qa-artifacts/v592/full-suite.txt`).
- Primeira suíte: cinco falhas/1054 aprovados. Reparados textos legados de fontes/síntese, recuperação após resultado irrelevante e contrato de planos compactos. Testes antigos/gabaritos inalterados. Log inicial preservado; reparo focado **66 passed**.
- **24 testes novos**: recuperação do pipeline com fixture, limites/proprietário, evidência não lida, datas, moedas inválidas/velhas/futuras, par, série, cache e paridade JDUI Python/JS.
- Benchmarks congelados reexecutados no código final: pesquisa **34/34**, shopping **59/59**, experiência **16/16**. Quality Lab v2 inalterado: precision 0,275 / recall 0,916667 / nDCG 0,925589.
- Contratos universais: **32/32**, preservação de parâmetros A–L; não medem recuperação real.
- Chrome com serviços locais/banco temporário: reload durante execução, SSE interrompido/reconectado, 43 eventos ordenados, fontes, imagem/zoom/Escape, download 200/1983 bytes e câmbio externo pelo chat persistido após reload. Desktop 1280 e mobile emulado 390/320; zero erros registrados. Gráfico com 22 pontos/quatro rótulos sem sobreposição.
- Screenshots inspecionadas; [JDUI_RESULTS](docs/v5.9.2/JDUI_RESULTS.md) detalha provas/limites. Sem inferência real de modelo, aparelho físico, vídeo assistido ou compra/reserva.

Warnings finais são depreciações de `mss.mss` e timeout de TestClient/httpx2. Quatro skips preservados, sem converter em sucesso. Aviso de escape no script de QA corrigido para string raw, sem mudar expressão JS.

## Arquivos e commits

- `dbb08c9`: recuperação adaptativa, evidência/checkpoint e testes.
- `a552300`: parâmetros/datas, busca temporal e moedas.
- `a0087ef`: fontes/JDUI, mídia e retomada; QA.
- `237ed62`: contratos legados e gráfico mobile.
- `71bfedc`: encerramento da barra de pesquisa e layout ativo.
- `74f3b22`: reconciliação de SSE sem progresso a cada cinco segundos, somente durante job ativo, sem consultas sobrepostas; timers removidos no stop/troca. Nova validação Chrome/suíte completa. Commit de entrega: documentação/evidências e comparação reproduzível.

Principais arquivos: `research_agents.py`, `research.py`, `search_orchestrator.py`, novo `query_intelligence.py`, `live_data.py`, `research_view.py`, `jdui.py`, `public/app.js`, `public/jdui.js`, `public/styles.css`. Testes/ferramentas `tests/*v592.py`, `tools/*v592.py`; provas `qa-artifacts/v592/`; retomada em `docs/v5.9.2/PROGRESS.md`.

## Segurança e pendências

Mantidos proprietário/permissões, SSRF/downloader, limites, circuit breaker, escape/URLs seguras e validação JDUI. Fixture identificada/banco temporário, sem dados de produção. Busca de padrões de tokens/chaves nos artefatos sem ocorrências; não é auditoria independente de segredos.

Pendentes: descoberta por fontes específicas/oficiais em transporte/notícias/eventos, E2E real de demais categorias, precisão do ranking, inferência de modelo, full text científico, vídeo e aparelho físico. Parser conservador com vocabulário/gramática limitados, janelas até 366 dias. Cache profundo não recebeu o tratamento opcional da pesquisa rápida. Não declarar suporte universal completo.
