# JÚLIA Learning — Testes (resultados reais)

Comando: `py -m pytest tests/ -q` (CPython 3.14, Windows).
Baseline final: **146 passed, 1 failed** — a falha é
`test_ai.py::test_e2e_ai_completo_com_processos_reais` (URLError: conexão
recusada — exige Hermes/PC ao vivo; ambiental, pré-existente, sem relação
com a V4.2).

## Novos testes V4.2 (todos passando)

- `tests/test_remoto.py::test_gate_agente_nega_sem_grant` — conta sem grant:
  `screen_error`/`input_error` `sem_permissao`, sem vazar imagem.
- `tests/test_remoto.py::test_gate_agente_permite_grant_e_local` — local
  sempre; grant liga/desliga; bloqueio revoga mesmo com grant.
- `tests/test_learn_api.py` (6 testes) — contrato relay↔agente com funções
  reais: fluxo prova completo (gabarito nunca vaza no GET), isolamento
  entre donos (404 + stats zeradas), validação 422/401/404, `bloqueada`→403,
  planos (CRUD, preserva feitos), cards + recommend + flag + mistakes.
- `tests/test_learning.py` — `+7 testes`: round-trip assessment idempotente,
  fluxo tentativa (incl. `finalizada`), planos, SM-2, recomendações e
  `sem_dados`, sinalizar sem reescrever história, `criar_reforco`,
  fence de reforço, `linha_desempenho` no prompt (com/sem dados, por dono).
- `tests/test_jdui.py::test_componentes_educacionais` — `exam/studyplan/
  flashcards/studyprogress` válidos; ids maliciosos rejeitados.
- `tests/test_frontend_smoke.py::test_estudos_ligado_e_com_cache_offline` —
  aba, ids, endpoints e fallback offline ligados.

## Cobertura por requisito (§15)

Geração estruturada, validação, correção objetiva/discursiva (assistida),
pontuação, prova interrompida (tentativa aberta), histórico, SM-2, planos e
atualização, contexto/memória ausente, datas, stats sem/com dados, SQLite,
isolamento, acesso indevido, JDUI, regressão chat/admin: ✅ via arquivos acima
+ suíte pré-existente intacta (nenhum teste eliminado; imports `JULIA_auth`
corrigidos para `julia_auth`).

## Lacunas de teste (declaradas)

- Hermes real em chat (só mocks/fakes; e2e exige ambiente ao vivo).
- Aparelho real (teclado virtual, rolagem, foco, acessibilidade).
- Reconexão/sync idempotente de respostas offline (fila ainda não existe).
