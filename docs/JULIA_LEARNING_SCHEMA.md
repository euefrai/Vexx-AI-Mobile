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
- `desempenho_por_assunto` ignora discursivas pendentes (`correta=-1`):
  não entram nem no numerador nem no denominador.
- Questões sem `assunto` herdam o assunto da avaliação (`criar_assessment`).
- Reforço (`criar_reforco`, origem `reforco`) reutiliza enunciado/gabarito/
  explicação originais; sem erros recentes → `sem_dados` (o chat informa).
- `sinalizar_questao` só registra `study_events`; nunca reescreve tentativas.
- Planos: `atualizar_plano` preserva concluídos por match de título normalizado.
- Recomendações (`recomendar`) exigem ≥3 respostas por assunto; sem dados →
  `{"recomendacoes": [], "motivo": "sem_dados"}`. Sem diagnósticos pessoais.

## Operações (todas com `owner`, todas atrás do gate `learn_*` de bloqueio)
- Planos: `criar_plano` (idempotente por `plan_id`), `obter_plano`
  (+`progresso`), `concluir_item`, `atualizar_plano`, `listar_planos`.
- Flashcards: `criar_flashcards` (agenda inicial = hoje), `revisoes_pendentes`,
  `revisar_flashcard` (SM-2 + evento). Datas determinísticas; sem notificação.
- `questoes_erradas` (base do reforço e do "refazer as que errei").
- `criar_assessment` idempotente por `assessment_id` (reenvio não duplica).

## HTTP (relay `server.py` → agente `pc_agent.py`, sempre com `owner`)
- `GET /api/learn/assessments/{id}` (sem gabarito) · `POST /api/learn/attempts`
- `POST /api/learn/answer` · `POST /api/learn/finish` · `POST /api/learn/avulso`
- `GET /api/learn/stats` · `POST /api/learn/plans` · `GET /api/learn/plans`
- `GET /api/learn/plans/{id}` · `POST /api/learn/plans/item`
- `POST /api/learn/plans/update` · `POST /api/learn/cards`
- `GET /api/learn/cards/due` · `POST /api/learn/cards/review`
- `GET /api/learn/recommend` · `POST /api/learn/flag` · `GET /api/learn/mistakes`
- Erros: `bloqueada`→403, `ausente`→404, `finalizada`→409, resto→503.
- Conta bloqueada é barrada no agente (`dono_bloqueado` em todo `learn_*`).
