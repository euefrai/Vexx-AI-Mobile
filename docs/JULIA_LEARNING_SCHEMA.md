# JULIA LEARNING — Schema (V4.2 FASE 2)

Módulo `learning.py` (stdlib). Tudo com `owner_id`; IDs client-side estáveis
(reenvio = `INSERT OR IGNORE`, nunca duplica).

## Tabelas
- `learning_plans(id, owner, titulo, objetivo, assunto, prazo_iso, min_dia)`
- `plan_items(id, plan_id, owner, titulo, tipo, ordem, feito, feito_em)`
- `assessments(id, owner, titulo, assunto, origem, created_at)`
- `questions(id, assessment, owner, enunciado, tipo, opcoes JSON, gabarito,
  explicacao, dificuldade, assunto, ordem)` — tipos: multipla, vf, curta,
  discursiva (esta exige `criterios` 10+ chars; nunca auto-corrigida).
- `attempts(id, assessment, owner, iniciada/finalizada, nota, total)`
- `answers(attempt, question, owner, resposta, correta)` — PK composta.
- `flashcards(id, owner, frente, verso, assunto)` + `reviews(flashcard, owner,
  proxima_iso, intervalo_d, facilidade, acertos, erros)`.
- `study_events(owner, tipo, ref_id, detalhe, ts)` — linha do tempo p/ stats.

## Regras
- Correção objetiva **determinística** (`corrigir_objetiva`): índice/letra
  para multipla/vf, igualdade normalizada para curta. Discursiva levanta
  `discursiva` (avaliação assistida, explícita).
- SM-2 simplificado e **puro** (`proxima_revisao`): 1→6→×facilidade; erro
  reseta p/ 1 dia e −0.3 (mín 1.3). Mesma entrada = mesma saída.
- Stats só de dados reais (`resumo_progresso`, `desempenho_por_assunto`);
  sem dados → zeros/lista vazia (estado vazio útil, sem invenção).
