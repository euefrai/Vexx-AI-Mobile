# V5.9.9.4 — progresso local

Base verificada: 921f27b, branch codex/v598-autonomous-research, worktree
vexx-v598-dev. Nenhuma alteração rastreada prévia; artefatos antigos não rastreados
preservados. Produção/main não modificados.

Fases 01–04: corpus e critérios congelados antes de alterações no matcher.
Baseline sintético DEV: TP8 FP2 FN5 TN59; precisão0,8 recall0,6154; dois parciais
promovidos indevidamente. VALIDATION: TP4 FP0 FN0 TN30, sem parciais nessa divisão.
Métricas não são estimativas da precisão na internet.

Próximo: corrigir vinculação sujeito/predicado, limites de nomes/variantes,
contexto adjacente e condições de suporte parcial; testar preservação multipassagem.
Depois: instrumentação dos provedores, comparação congelada e E2E isolado.

Não fazer push/deploy, reiniciar produção ou usar SQLite/credenciais reais.
