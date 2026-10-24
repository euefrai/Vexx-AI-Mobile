# VEXX AI V5.9.7 — Research Completion & Interactive Evidence

**Decisão: GO_WITH_LIMITATIONS.** Melhorias de leitura, conclusão recuperável e estado JDUI implementadas. Não se anuncia Deep Research científica completa: zero síntese assistida aprovada nesta avaliação externa.

HEAD inicial local: `7beb67b6bc21b6d572449a149f3f254784cce64f`. Remoto inicial atualizado por fetch: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`. Os cinco commits V5.9.6 anteriores foram preservados.

HEAD final publicado e confirmado por `ls-remote`: `0814864e0e20bcb94f22a0b4fe861b205c15ed7c`. Push fast-forward realizado. GitHub Actions [40010107263](https://github.com/euefrai/Vexx-AI-Mobile/actions/runs/40010107263) terminou com sucesso. Deploy automático observado: relay informa `0814864e0e20`, health/configured OK e PC online. Novos assets confirmados por HTTP; research/jobs, research/stream e ui-state mantêm 401 sem sessão. Recibo completo: `qa-artifacts/v597/publication-receipt.json`.

Esta atualização pós-publicação e o recibo foram salvos localmente; não foi feito um segundo push apenas de documentação que provocaria outro deploy. O código publicado e validado permanece no SHA acima.

## Correções

- RSS deixa de consumir slots reservados a páginas. Traces distinguem abrir, extrair, rejeitar e aceitar uma fonte.
- Metadados reais de NewsArticle/Article têm prioridade sobre WebSite; `@type` em lista funciona, sem inventar data de publicação.
- Fontes vazias diferentes não são duplicatas; snippet explicitamente não lido não sustenta claim.
- Resultado considera leitura, lacunas, auditoria e síntese. Bloqueio do provedor preserva evidências e permite retomada explícita; sem retry automático após 429.
- PDF interrompe extração no limite da pesquisa, preserva páginas e reconhece apenas seções efetivamente extraídas.
- Painéis preservam detalhes por owner/job via IndexedDB e ignoram respostas atrasadas. Tabelas rolam internamente no mobile.

Principais arquivos: `research_agents.py`, `research.py`, `evidence_graph.py`, `web_extract.py`, `academic_research.py`, `docs_agent.py`, `research_view.py`, `pc_agent.py`, `public/app.js`, `public/jdui.js`, `public/styles.css`. Testes de regressão, dataset e dois harnesses adicionados. Três testes antigos ajustados para limites explícitos do PDF e isolamento da configuração de inferência; nenhuma funcionalidade ou asserção removida.

## Evidências e testes

- Baseline: **1.374 passed, 4 skipped**. Final: **1.385 passed, 4 skipped**, dois avisos de depreciação, 180,76 s.
- Search **34/34**, Shopping **59/59**, Experience **16/16**. Quality Lab: precision@5 **0,266667**, recall/MRR/nDCG **1**, duplicação **0**.
- Doze perguntas externas: **1/12** com fonte lida aceita; **0/12** respostas inteiramente confirmadas. Descoberta de mídia genérica não melhora essa contagem.
- Testes diretos separados: **1/1** notícia original de Salvador lida; **2/2** PDFs OA parcialmente lidos. Não são novas descobertas completas, estudos integralmente analisados ou comparação experimental aprovada.
- Modelo gratuito configurado: **uma chamada** no caso oficial; resposta rejeitada por `quantity_mismatch`. Fallback extrativo preservado.
- Chrome real: proveniência, reload, troca de dono/pesquisa, IndexedDB, 320 px e zoom CSS 200%. Sem overflow da página ou fallback de renderização no escopo observado. Harness de componentes, sem login do aplicativo. API/relay/agente, SSE e cancelamento foram testados separadamente na suíte.
- Scan de padrões de segredo em **241 arquivos**, zero ocorrência. Nenhum valor de cookie/token/chave registrado. Logs de falhas intermediárias preservados para auditoria.

## Commits e operação

`4778d0b`: leitura limitada, evidências e conclusão recuperável. `79cae34`: JDUI persistente e guards assíncronos. Commit de documentação/artefatos e estado final de publicação constam em `docs/v5.9.7/RELEASE_DECISION.md` e no histórico Git.

Sem alteração da identidade Lucas, clima, extensão Júlia, Fajulto Studio, 3D, permissões remotas, autenticação ou dados reais. PC Agent de produção preservado; a validação do código novo ocorreu em processos isolados. Não se confunde push/deploy do relay com recarga automática do agente Python.

Detalhes e pendências: `docs/v5.9.7/SOURCE_RECOVERY.md`, `EVIDENCE_QUALITY.md`, `SCIENTIFIC_READING.md`, `JDUI_RESULTS.md`, `BENCHMARK.md`, `PROGRESS.md`. Artefatos: `qa-artifacts/v597/assessment.json` e logs/JSONs citados. Próximo avanço: descoberta original em Ubatã e trechos científicos pertinentes, mantendo restrições de data, local, unidades e suporte.
