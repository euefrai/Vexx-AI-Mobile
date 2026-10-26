# Trace 2.0

Opt-in local, ContextVar, máximo de 1.000 eventos, lock e fechamento do sink para impedir anexos tardios. Não grava corpo de página, credenciais, cookies, tokens ou prompts. Referências de URL/job/etapa são hashes. Q/C/R/P e D têm formatos validados. Campos não observados ficam vazios ou null; não estimar métricas ausentes.

Eventos: criação/envio/retorno de consulta; descoberta/rank/provedor; seleção/slot; fetch/HTTP/redirect/body; cache hit/miss/stale/reuse; documento já lido/duplicata exata; extração/rejeição; suporte parcial/direto e passagem selecionada; lacuna/replanejamento; síntese e terminal. Guarda duração observada e snapshots de orçamento quando fornecidos.

`requested_requirement_ids` indica intenção. `requirement_support` e IDs suportados são derivados dos vínculos reais de passagens, não de todos os requisitos da pergunta. Isso corrige um trace que podia atribuir suporte não observado. Artefatos antigos dessa execução são marcados `legacy_support_bindings_not_verified`; não usar seus IDs para afirmar cobertura direta.

`JDUI_DELIVERED` significa **SQLITE_PERSISTED_FOR_SYNC**, não confirmação de render no navegador. A prova de reload/IndexedDB está na QA separada. `SYNTHESIS_COMPLETED` com motivo EXTRACTIVE não é inferência de modelo.

Trace protegido real de replay e registro de consultas: `qa-artifacts/v5997/trace-example.json`. Resumos de perdas/eventos nos JSONs external/replay. A versão final acrescenta eventos de lacuna e duplicata; parte das capturas precede esse complemento. Não alegar trace integral de todos os leitores alternativos, cortes físicos do provedor ou entrega SSE ao cliente.
