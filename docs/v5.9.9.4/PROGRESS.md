# V5.9.9.4 — progresso local

Base verificada: 921f27b, branch codex/v598-autonomous-research, worktree
vexx-v598-dev. Nenhuma alteração rastreada prévia; artefatos antigos não rastreados
preservados. Produção/main não modificados.

Fases 01–04: corpus e critérios congelados antes de alterações no matcher.
Baseline sintético DEV: TP 8 FP 2 FN 5 TN 59; precisão 0,8 recall 0,6154; dois parciais
promovidos indevidamente. VALIDATION: TP 4 FP 0 FN 0 TN 30, sem parciais nessa divisão.
Métricas não são estimativas da precisão na internet.

Implementação e avaliação local concluídas; aceitação **NO_GO**.
Aplicação final a91c113; commits de calibração beab357, direção f5f1561 e ordem
DOM a91c113; freezes e8f9443/13b3013/76e6af3. Nenhum gabarito anterior alterado.

Corpus125 exemplos sintéticos (108 DEV/VALIDATION+17 operacionais selados).
Nova avaliação externa em ondas12/8/6; conjuntos anteriores67 casos medidos
separadamente. Os conjuntos abertos são diagnósticos. Não ajustar para maquiar
precision/recall; não há gold humano independente.

Testes finais:1595 passed,4 skipped,2 warnings; Search 34/34,Shopping 59/59,Experience 16/16.
Chrome/SSE/reload/IndexedDB/CSV/links/cancelamento/negativo de transporte
executados em runtime temporário. Nenhuma pesquisa completa com modelo
aprovada; duas chamadas isoladas responderam e foram rejeitadas.

Próximo passo exato: montar casos anotados com HTML público/passage/span e
expectativa por requisito para (1) alternativas de exercício versus gabarito,
(2) cabeçalho+lista causal com antecedente válido e (3) documento técnico com
nome qualificado e idioma/contexto. Reproduzir por que context_mismatch e a
seleção descartam os trechos úteis, antes de flexibilizar qualquer filtro.
Congelar nova avaliação independente antes de nova mudança semântica.
Depois investigar contrato JSON da síntese gratuita com a evidência intacta,
sem aceitar saída inválida nem repetir o provedor indefinidamente.

Não fazer push/deploy, reiniciar produção ou usar SQLite/credenciais reais.
