# Arquivos e fatos

Ledger relativo à worktree:

- `query_intelligence.py:77` → parser existente; `:144` → contrato de objetivo/restrições; `:174` → aliases de espaçamento sem fundir variantes.
- `evidence_graph.py:233` → vínculos, cache obsoleto e métricas; `:327` → compactação preserva documento/passagem.
- `research_synthesis.py:354` → estado das fontes efetivamente oferecidas e catálogo literal antes da validação/revisão.
- `pc_agent.py:4575` → catálogo habilitado no redator real, sem trocar modelo/timeouts.
- `research_agents.py` → proveniência usa contrato; cobertura incompleta conserva resultado parcial; budgets/replanejamento existentes preservados.
- `research.py:414` → anúncios; snippet DDG limitado ao resultado, anúncio filtrado antes do limite.
- `search_orchestrator.py:236` → SEARCH_ADVERTISEMENT; guarda de alias restrita, sem confundir orçamento/RAM com modelo.
- `web_extract.py:391` → tipo estruturado genérico não vira título.
- `public/index.html:448` → placeholder confirmado em 320 px.

Testes: `test_coverage_contract_v5911.py`, `test_quote_catalog_v5911.py`, `test_provider_boundaries_v5911.py`; contrato atualizado em `test_research_synthesis.py`, preservando negativos de escopo/conteúdo não lido.

Dados: `benchmarks/coverage_v5911_holdout.json` congelado; `coverage_v5911_dev.json` separado. Nenhum benchmark antigo editado.

Ferramentas novas em `tools/`: `diagnose_coverage_v5911.py`, `replay_coverage_v5911.py`, `replay_provider_v5911.py`, `setup_qa_v5911.cjs`, `qa_ui_prepare_v5911.cjs`, `summarize_coverage_v5911.py`.

Ferramentas adaptadas mantendo defaults: `probe_source_quality_v5998.py`, `probe_discovery_v5910.py`, `contrast_synthesis_v5910.py`, `collect_v5910.py`, `verify_shutdown_v5910.py`, `qa_discovery_v5992.cjs`, `qa_ui_v5910.cjs`, `qa_ui_extra_v5910.cjs`.

`.gitignore` protege capturas/runtime privados. Documentação em `docs/v5.9.11/`, relatório na raiz, sumários/screenshots compactos em `qa-artifacts/v5911/`. Lista exata: `git diff --name-only 0959e8c..HEAD`. Arquivos não rastreados de versões anteriores não integram a entrega.
