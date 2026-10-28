# V5.9.12 — estado de continuidade

Base `40f9531`, branch `codex/v598-autonomous-research`. Não alterar produção, SQLite real, outras aplicações ou identidade Lucas. Sem push/deploy desta etapa. Arquivos anteriores não rastreados preservados.

Commits: `4b9441b` congela holdout; `ef97dfc` preserva atribuição DOM/tabela e corrige consultas/fallback; `53d4154` separa conclusão final de claims provisórios, corrige DOI e OpenSearch; `1fee389` mantém campos curtos citáveis e normalização JSON restrita; `3938bee` adiciona cobertura semântica com spans literais e vínculo de fonte, na revisão já existente.

**Etapa de integração concluída, objetivo universal ainda em andamento.** Final QA em `3938bee`: Gerdau e WEG COMPLETE com LLM/revisão/citações e reload; Natura PARTIAL por semantic_review_invalid; Nvidia BLOCKED por rate_limit. Todos os resultados preservados. Não houve loop até PASS; versões intermediárias e falhas estão nos artefatos. As duas conclusões são da categoria empresas, sem alegação universal.

Final: 1804 passed/4 skipped/2 warnings,459,36s,exit0. Focados finais142; catálogo165. Search34/Shopping59/Experience16. Intermediária: três falhas1785passes corrigidas; outra1790passes. Um pytest próprio supersedido foi interrompido (exit15), explicitamente não contado como PASS.

Chrome real320/390/1280 sem overflow, link real aberto, MD/CSV exportados. IndexedDB12/12IDs únicos, quatro resultados. QA descartável fechado: pre-terminal,pre-catalog,pre-semantic,verified com SQLite/runtime removidos e nenhum processo associado. Browser v5912 fechado. Nenhum serviço ativo desta tarefa precisa ser mantido.

Holdout16 em `53d4154`: três casos com entrada marcada lida, dois com passagem, uma cobertura completa de recuperação (Toyota), sem modelo nessa trilha. Mediana48,78s; máximo138,148s. Alterações posteriores não tiveram nova rodada live do holdout. Não ajustar aos resultados nem alegar ganho causal contra outro conjunto. Replays same-HTML Gerdau/Sega melhoraram vínculos, história não.

**Próximo passo exato já autorizado:** corrigir seleção e uso de seções no corpus de desenvolvimento, não nos nomes do holdout. `native-dev-history.json` é B live final: encontrou Wikipedia para Guerra do Contestado, leu1727chars, reteve zero evidências. Headers reais existem: Antecedentes, Consequências. `_SECTION_TERMS` e `offer` em `web_extract._document_windows` só priorizam ocorrências lexicais no corpo; selecionaram confrontos/tifo/rendição. HTML capturado em `qa-artifacts/v5912/raw/sha256('B|dev-history|evaluation')[:20]/`. A API OpenSearch respondeu normalmente; não atribuir essa perda a falta de provedor.

Avaliar com testes genéricos antes de implementar: priorização por headings pertinentes; preservar H1/ancestralidade real com offsets/hash; contexto de seção continua PARTIAL até verificação semântica real. Não transferir causa/consequência para outra entidade, nem promover associação a causalidade. Caso se considere usar revisão para contexto parcial, criar negativos de condicionais, battery_and_card, fonte não lida, autoridade oficial, contradição e objetivo não decomposto. Não relaxar o requisito atual de vínculo fonte→requisito sem prova. Não aumentar tetos nem inserir URLs esperadas.

Pendências menores: source cards podem repetir URL em registros distintos; títulos JSON-LD podem ser descrições. Gerdau teve dois registros da mesma URL, não duas publicações independentes. Vazio HTTP200 com reasoning_present observado; reasoning não usado e causa histórica não estabelecida.

Relatório: `RELATORIO_VEXX_AI_V5.9.12_RESEARCH_COMPLETION.md`. Sumários/manifest em `qa-artifacts/v5912/`; capturas/payloads/logs privados ignorados. Lógica final validada em3938bee, ferramentas/documentação fechadas em commit posterior.
