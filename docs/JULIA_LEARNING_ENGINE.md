# JÚLIA Learning Engine (V4.2) — Arquitetura

O chat continua sendo o centro. O Learning Engine é o **substrato determinístico**
sob a conversa: guarda, corrige, agenda e mede. O modelo (Hermes) gera conteúdo;
o código valida, persiste e calcula. Nada educacional é "resposta genérica
classificada como sistema": cada capacidade tem dados estruturados + testes.

## Camadas

```
Celular (public/)                Relay (server.py)              PC (pc_agent.py)
─────────────────                ─────────────────              ──────────────────
chat + fences JDUI  ──/api/ai──▶ exchange{ai,…} ──▶ ai_completa()
  quiz/exam/studyplan/                           ├─ sintetizar_prova() (LLM+validação)
  flashcards/studyprogress                        ├─ sintetizar_reforco() (determinístico)
  "Meus Estudos" (consulta)                       └─ linha_desempenho() no prompt
exame/plano/cartão  ──/api/learn/*──▶ exchange{learn_*,owner} ─▶ learning.*
"Meus Estudos" ◀── cache IndexedDB (META, chave learn:<uid>:<nome>)
```

## Regras de ouro

1. **Correção objetiva é código, não modelo.** `corrigir_objetiva()` no PC;
   o frontend recebe só `{"correta": true|false}`. Discursiva nunca auto-corrige
   (`avaliacao: "assistida"` explícito).
2. **Gabarito nunca trafega para o aluno.** `GET assessments/{id}` omite
   `gabarito`/`explicacao`; só `learn_result.erradas[].gabarito_texto` após
   finalizar — e só das erradas.
3. **Sem dados, sem invenção.** Stats vazias → zeros/listas vazias;
   `recomendar` → `sem_dados`; reforço → mensagem honesta; gráficos mostram
   estado vazio útil.
4. **Isolamento por dono.** Toda tabela tem `owner_id`; todo relay passa
   `owner`; conta bloqueada é barrada em todo `learn_*` no agente.
5. **História imutável.** Tentativas finalizadas rejeitam respostas;
   `sinalizar_questao` registra evento, não edita o passado.
6. **Offline honesto.** Consulta (planos, cartões, enunciados) funciona do
   cache; prova, correção e conteúdo novo exigem o PC (sem "IA offline" falsa).

## Fluxos principais

- **Quiz no chat:** IA emite fence `quiz` (inline, corrigido no aparelho,
  `POST /api/learn/avulso` registra) ou `exam` (prova formal no PC).
- **Prova:** `sintetizar_prova` (LLM→`validar_questao`→`criar_assessment`) ou
  pedido direto; aluna responde/navega/finaliza; `erradas` + `refazer`.
- **Reforço:** "simulado com o que errei" → `intencao_reforco` →
  `criar_reforco` (questões originais, origem `reforco`).
- **Plano:** chat orienta (memória: objetivo/prazo via eventos); CRUD em
  `/api/learn/plans*`; `atualizar_plano` preserva concluídos.
- **Flashcards:** `criar_flashcards` → `cards/due` → `review` (SM-2).
- **"Em que estou errando?":** `linha_desempenho()` injeta números reais no
  prompt (só em pergunta de estudo, só do próprio dono).
- **"Meus Estudos":** `GET stats|plans|cards/due|mistakes|recommend` + cache.

## JDUI educacional (espelho `jdui.py` ↔ `public/jdui.js`)

`quiz`, `exam` (existentes) + `studyplan` (`{plan_id}` → itens marcáveis),
`flashcards` (`{assunto?}` → fila do-dia com flip + :'acertei/errei'),
`studyprogress` (`{}` → resumo + por assunto + recomendações).
Validação estrita nos dois lados; bloco inválido cai em fallback, nunca trava.

## Memória V4.1 (origem preservada, sem mistura entre donos)

- Objetivos/datas de prova: eventos e fatos confirmados (prompt + planos).
- Dificuldades: **só** de resultados reais (`answers`), nunca inferência livre.
- `study_events` é a memória educacional auditável (prova finalizada,
  item concluído, revisão, questão sinalizada).
- Toggle de aprendizado e FTS por dono, como na V4.1.

## Segurança (§2)

- `screen` **e** `input` exigem `remote_ok` (grant do admin) — `sem_permissao`
  no agente → 403 no relay. Dono `local` sempre; bloqueado nunca.
- Revogação: `revogacao_ok` em toda rota; lista do PC com TTL 60 s
  (janela documentada; bloqueio também revoga sessões no SQLite).
- Bloqueios aplicados no agente (`pode_remoto`, `dono_bloqueado`), não só na UI.

Ver também: `JULIA_LEARNING_SCHEMA.md`, `JULIA_LEARNING_PROGRESS.md`,
`JULIA_LEARNING_TESTS.md`, `RELATORIO_JULIA_4.2.md`.
