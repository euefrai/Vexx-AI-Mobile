# V5.9.9.9 — progresso e continuidade

Base 8ccbbe0; branch codex/v598-autonomous-research. Commits locais bc3bc27 (congelamento), 51b8291 (retrieval), 2b1e457 (números), 3c269ac (QA/regressões). Sem push/deploy.

Implementação concluída nesta rodada: seleção limitada de seções/janelas no texto já disponível; linhas de tabela e offsets; contexto/IDs/grafo/cache; parser “qual o peso”; equivalência decimal conservadora e guardas de unidade/moeda/identificador; captura privada de LLM.

Verificações: Nikon recuperou bateria/peso tardios em 767 caracteres; sete HTMLs pareados 2→3 com passagens elegíveis; holdout independente 2/12 úteis (APIs), uma fonte só contextual; LLM isolado aprovado, autenticado vazio/blocked. Chrome/cards/exports/reload validados; foco intermitente pendente. QA/browser encerrados; supervisor/filho ausentes, SQLite/runtime temporários removidos.

Testes: etapas 1707 e 1731 passaram; suíte com três casos finais teve 1733 passed/1 failed/4 skipped (reconexão Windows 15s), recheck isolado passou sem mudar teste. Suíte final sem QA/navegador: 1734 passed, 4 skipped, 2 warnings, 550,47 s. Falha anterior preservada em validation-summary.json; causa da intermitência não demonstrada.

Ledger:
- web_extract.py:_document_windows — varre extração/elementos/gaps, até 8 janelas/8.000 caracteres, até 1.100 por trecho.
- evidence_graph.py:_passage_support — tabela sob heading real com entidade exata é parcial; variante diferente não herda.
- research_agents.py:agente_analista — propagação de passagens/scan/contexto e nós de seção.
- research.py:RETRIEVAL_VERSION — 5.9.9.9, isolamento do cache mantido.
- research_synthesis.py:numeric_values/quantities/technical_identifiers — equivalência conservadora; revisão não removida.
- research_view.py:source_card — contexto real compacto.

Decisão NO_GO. Próximo passo exato: retomar o diagnóstico de consultas/ranking dos provedores existentes em desenvolvimento e congelar NOVO holdout antes de alterar query/ranking, diagnosticar B sem URL e capturar contexto da falha intermitente de foco/inicialização. Não adaptar aos 12 casos abertos. Não ampliar timeouts/bytes/texto nem retirar validação para melhorar números.
