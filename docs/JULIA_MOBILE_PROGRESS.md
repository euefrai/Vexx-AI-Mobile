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

## V4.2 — LEARNING ENGINE ✅ (2026-10-14)
- Learning Engine (`learning.py`): questões, correção determinística, tentativas,
  planos, flashcards SM-2, stats reais, recomendações, reforço. 17 endpoints
  `/api/learn/*` com owner; JDUI `exam/studyplan/flashcards/studyprogress`;
  aba "Meus Estudos". Relatório em RELATORIO_JULIA_4.2.md. Suíte: 146 passed.

## V4.2.1 — ESTABILIZAÇÃO ✅ (2026-10-15)
- E2E `test_e2e_ai_completo_com_processos_reais`: causa era boot flaky
  (sleep fixo + logs descartados), não bug. Readiness com polling, logs dos
  filhos em falha, marcador `e2e_real` + skip sem uvicorn. Verde e determinístico.
- Hermes real em 15/10: `/v1/models` OK, inferência BLOQUEADA no provedor
  (resposta vazia / modelo não encontrado). Nenhuma quota gasta.
- Aulas canônicas: `lessons`/`lesson_sections`, schema validado, CRUD, progresso
  por seção, síntese via LLM validada, renderer `lesson`, intents nos 2 caminhos.
- Fila offline educacional: outbox no IndexedDB (`SAVED`), `queueLearn` no ctx
  JDUI, respostas com ts do aparelho, correção sempre no servidor, conflito
  404/409 descarta sem reenvio, finalização exige conexão (anti-fraude).
  Idempotência servidor: `INSERT OR REPLACE` por (tentativa, questão).

## V4.3 — ADVANCED JDUI ✅ (2026-10-15)
- Novos componentes (espelho py/js + testes): `chart` (line/bar/pie/area/scatter,
  SVG puro, tooltips, fonte obrigatória conceitual, estados vazios),
  `dashboard` (métricas + 1 gráfico), `compare` (lado a lado com destaque),
  `lesson`, `conversor` (calculator + `OPS.conversao`, sem eval).
- Tabela com filtro local; diagrama com zoom, grupos, ícones e seleção persistida.
- `update_of`: patch in-place só de presentational (chart/table/dashboard/compare/
  diagram/checklist/cards/tabs/accordion/form/calculator/studyplan/flashcards);
  `exam/quiz/studyprogress` rejeitam (imutável), erro logado, bloco mantido.
- Gráfico de evolução 100% factual (`learn_history` → SVG, modelo só explica).
- PresentationEngine: regras chart/compare/dashboard/conversor + catálogo atualizado.
- Segurança: NaN/Inf/oversize/depth/URLs/XSS/componentes desconhecidos testados
  py + node. CSS responsivo 320–768 (sem libs). Suíte: **157 passed, 0 failed**.
- Relatório em RELATORIO_JULIA_4.3.md. Pendentes: E2E em aparelho físico,
  inferência Hermes real, TTL 60 s, fila offline só p/ respostas (revisão de
  cards e finalização exigem conexão).
