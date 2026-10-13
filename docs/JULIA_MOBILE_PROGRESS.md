# Júlia Mobile — Progresso (retomada entre sessões)

## V4.0 — FUNDAÇÃO ✅ (2026-10-13)
- [x] Auditoria: sessão `{"user"}` única; zero `owner` no agente; contexto sem
      orçamento; sem arquivar/fixar/exportar/regenerar/continuar. Baseline: 59 passed.
- [x] Docs: ARCHITECTURE, ROADMAP, PROGRESS.
- [x] owner_id em 8 tabelas (migração preserva dados) + ownership em todos os
      handlers + `owner` em todo RPC do relay + 6 testes de isolamento.
- [x] Chat pro: arquivar/fixar (drawer), exportar .md/.json local, regenerar
      (ai_reset), continuar (ai_continue, mesmo reply_id), busca no histórico.
- [x] Contexto orçado (12k chars, recentes primeiro) + REGRAS_CONFIANCA sempre
      no system + resultados rotulados (memória/docs/pesquisa com data).
- [x] 8 testes de avaliação conversacional. Suíte: **77 passed**.
- [x] Relatório abaixo em RELATORIO_JULIA_4.0.md.

## Decisões
- Dono padrão `'local'`; migração via `ADD COLUMN` idempotente (não reescreve banco).
- Exportar é 100% local (download), sem servidor.
- Regenerar = apaga reply + re-solicita IA (idempotência preservada).
- Continuar = append à mesma reply (só se `truncada` ou texto longo).
- Sem KaTeX/branch/share-link na V4.0 (ver ROADMAP).

## V4.1 — MEMORY INTELLIGENCE ✅ (2026-10-13)
- [x] DB: memories tipada (tipo/assunto/status/origem/valido_ate) + memory_events
      + memory_settings + FTS5 opcional. Migração preserva dados.
- [x] Extração: candidatos tipados; sensível/temporal-ambíguo → proposta +
      pergunta; explícito ("lembre-se") passa mesmo pausado.
- [x] Temporal PT-BR sem ano inventado; relativo resolvido; confirmação gera evento.
- [x] Recuperação híbrida FTS+overlap+recência, só confirmadas, com proveniência
      e eventos ("faltam N dias") no prompt, dentro do orçamento.
- [x] Painel: busca, badges, corrigir, pendências confirmar/descartar, toggle
      aprendizado, eventos. Endpoints com owner + testes.
- [x] 9 testes de fluxo do spec. Suíte: **86 passed**.
- [x] Relatório em RELATORIO_JULIA_4.1.md.

## Decisões V4.1
- Proposta (não salvamento) para sensível e data ambígua; confirmação explícita
  ("pode guardar"), nunca "sim" solto.
- Datas explícitas/relativas salvam direto + criam evento; sem ano → pergunta.
- FTS5 com fallback overlap (sem embeddings pagos).
- Correção = upsert + antiga no memory_facts (nunca sobrescreve silencioso).
