# V5.9.9.8 — progresso

Estado: diagnóstico concluído, correções limitadas aplicadas, **NO_GO para publicação**.

Base: cc60042, branch codex/v598-autonomous-research. Holdout congelado em 8a6cfcc; correções em 5ffb476; ferramentas em 12ce7a8. Sem push/deploy. Produção não modificada.

Ledger:
- web_extract.py:_paragrafos/passage_candidates — parágrafo curto e whitespace causavam perda literal.
- evidence_graph.py:requirement_coverage — corte sequencial de 32 vínculos eliminava facetas raras; distribuição por requisito corrigida.
- research_agents.py:agente_analista — grafo agora recebe passagens selecionadas com todos os requisitos associados.
- research_agents.py:buscar_com_fallback + search_orchestrator.py:_context_mismatch — candidatos genéricos não interrompem fallback de APIs qualificadas; índices de referência continuam elegíveis.
- retrieval_trace.py:record — contadores limitados, sem texto privado.

Encerrado ambiente temporário: supervisor/filho ausentes, SQLite/runtime removidos pelo próprio harness. Nenhum PC Agent real encerrado.

Próximo passo exato: reproduzir, em desenvolvimento, a perda de seções tardias do manual Nikon (peso/bateria após posição 11.500), projetar seleção por seções sob o mesmo teto e preservar identidade do documento sem convertê-la em afirmação. Separadamente, diagnosticar extração de entidade/requisito em perguntas de linguagem natural. Congelar NOVO holdout antes de implementar; não otimizar contra as 12 perguntas já abertas. Capturar de forma local e privada a resposta rejeitada pelo validador numérico antes de propor correção na síntese. Não aumentar timeout nem relaxar citações com base nestes resultados.
