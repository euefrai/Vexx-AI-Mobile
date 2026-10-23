# V5.9.7 — evidência e conclusão

- Documentos distintos com texto vazio deixaram de ser classificados como duplicatas apenas por compartilharem o hash do vazio. Mesma URL continua sendo sinal de duplicidade.
- `verificar_claim` exclui fonte explicitamente não lida e metadados de feed. A presença da quantidade exata num snippet não sustenta a afirmação.
- `research_outcome` agora considera fontes lidas, lacunas, pendências, auditoria, vereditos e redação assistida. Separação entre execução terminada e resposta suficiente: `complete`, `partial`, `blocked`.
- Erro de provedor na síntese/revisão deixa o job interrompido, com código permitido e evidências preservadas. Reexecutar automaticamente não repete a chamada; retomada explícita permite uma tentativa nova sem repetir downloads concluídos.
- A visão JDUI explica cobertura parcial e bloqueio recuperável. Fallback extrativo continua identificado.

Provas controladas: `tests/test_research_completion_v597.py`, inclusive interrupção por 429, checkpoint restaurado, leitura reutilizada, retomada explícita, snippet não comprobatório e documentos vazios independentes. Não são testes de inferência externa.

Prova de modelo externo: `live-model-official/official.json`, uma chamada ao modelo gratuito configurado `poolside/laguna-s-2.1:free`. A resposta não passou na verificação de quantidade (`quantity_mismatch`), portanto zero síntese assistida aprovada. O trecho oficial continuou disponível. Não se afirma raciocínio científico validado nem correção semântica universal.

Replanejamento adaptativo, orçamento, ausência de ganho, independência editorial e incompatibilidade de unidades/condições já existiam; foram preservados e cobertos pela suíte. Não se conta sua mera presença como uma melhoria nova desta versão.
