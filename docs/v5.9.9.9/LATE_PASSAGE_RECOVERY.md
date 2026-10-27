# Recuperação tardia

Nikon: mesmos bytes públicos da captura V5998. Baseline 8ccbbe0 perde bateria/peso na janela inicial de 7.998 caracteres. Nova seleção examina 12.375 caracteres normalizados e 104 elementos; retém 767 caracteres em quatro trechos, três após posição 8.000. Entre eles: bateria EN‑EL15c, peso 710 g com bateria/cartão e variante 630 g apenas corpo. Qualificadores não foram removidos.

Os quatro source_spans foram comparados literalmente à extração normalizada da mesma captura, com SHA; text_spans conferem com a saída retornada. IDs estáveis em repetição controlada. source_span nunca é offset de HTML bruto.

A identidade vem do heading real “Nikon Z f Digital Camera”. Linhas de tabela sem sujeito explícito permanecem PARTIAL_SUPPORT. Variante ZX II não herda escopo de ZX no teste negativo. Heading sem valor não vira fato.

Regressões controladas: começo/meio/fim, seções curtas, código, linhas de tabela, texto sem bloco, empresa e história; fonte sem resposta/entidade errada continua sem suporte. São fixtures declaradas. Nenhuma constitui descoberta autônoma. late-passage-summary.json traz offsets/contadores; CONTROLLED_REPLAY.md traz o par de bytes.
