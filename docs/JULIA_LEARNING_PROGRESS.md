# JÚLIA Learning — Progresso por fase (V4.2)

Legenda: ✅ concluído · 🟡 parcial · ⬜ não iniciado. Nada aqui é aspiração:
cada ✅ tem teste executado (ver `JULIA_LEARNING_TESTS.md`).

- ✅ **FASE 1 — Auditoria, segurança e baseline.** Estado real divergia do
  informado (HEAD `b5a9a5d`, não `2eb25b5`; FASE 1/2 já iniciadas).
  Achado crítico: `screen` livre para qualquer conta autenticada.
  Correção: `resposta_screen`/`resposta_input` com gate `pode_remoto` no agente
  + 403 no relay; testes `test_gate_agente_*`. Janela de revogação auditada
  (TTL 60 s; bloqueio revoga sessões). Baseline: 146 passed, 1 falha ambiental.
- ✅ **FASE 2 — Banco educacional e schemas.** `learning.py` + 9 tabelas com
  `owner_id`, índices, migrações idempotentes, IDs estáveis (`INSERT OR IGNORE`).
  Correção: placeholder 7×6 em `criar_assessment` (achado via teste novo).
- ✅ **FASE 3 — Quizzes e correção determinística.** Validação estrutural,
  `corrigir_objetiva`, discursiva como assistida, 17 endpoints
  `/api/learn/*` com `owner`, testes de contrato + isolamento + 403/404/409.
- ✅ **FASE 4 — Provas e simulados.** `sintetizar_prova` (LLM validada),
  navegar/corrigir/finalizar/refazer/reattempt, `criar_reforco` determinístico
  + `intencao_reforco` nos dois caminhos (completa e stream).
- 🟡 **FASE 5 — Aulas e explicações estruturadas.** Chat com memória +
  `linha_desempenho`; fences `tabs`/`accordion`/`table` para progressão.
  Falta: formato canônico de "aula" com ações contextuais (reexplicar,
  aprofundar, simplificar) como intents de primeira classe.
- ✅ **FASE 6 — Planos de estudo.** CRUD + `concluir_item` +
  `atualizar_plano` (preserva feitos) + renderer `studyplan`.
- ✅ **FASE 7 — Flashcards e revisão.** CRUD + `revisoes_pendentes` +
  `revisar_flashcard` (SM-2 puro) + renderer `flashcards`. Sem notificação
  (sem infraestrutura de agendamento — não prometido).
- ✅ **FASE 8 — Estatísticas e adaptativo.** `resumo_progresso`,
  `desempenho_por_assunto`, `recomendar` (regras ≥3 respostas, `sem_dados`
  honesto), renderer `studyprogress`, prompt com números reais.
- ✅ **FASE 9 — Memória V4.1.** Leitura owner-scoped (`linha_desempenho`,
  eventos de prova no prompt); `study_events` como memória educacional;
  reforço "só o que errei" sobre dados do próprio dono.
- 🟡 **FASE 10 — JDUI, UX e E2E.** 3 componentes + "Meus Estudos" (consulta,
  cache offline, estados vazios) + smoke tests. Falta: E2E em aparelho real
  (teclado virtual, rolagem, foco) e teste Hermes real do reforço em chat.
- 🟡 **FASE 12 — Offline-first.** Leitura offline via IndexedDB (`SAVED` p/
  itens, `META/learn:<uid>:` p/ estudos); escrita/execução exige PC.
  Falta: fila de sincronização idempotente de respostas offline.

## Pendências honestas (próximos passos)

1. E2E mobile real (Android/iOS) dos fluxos exam/studyplan/flashcards.
2. Aula canônica estruturada (FASE 5) com intents de reexplicação.
3. Fila offline de respostas com idempotência fim-a-fim.
4. `test_e2e_ai_completo_com_processos_reais` exige Hermes ao vivo (ambiental).
5. Reduzir TTL de revogação (60 s) se o relay aguentar polling mais curto.
