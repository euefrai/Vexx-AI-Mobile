# RELATÓRIO JÚLIA 4.2 — Intelligent Learning Engine

## 1. Estado real encontrado (auditoria)

- Informado: commit `2eb25b5`, "Júlia 102 + Studio 30 testes".
- Real: HEAD `b5a9a5d` (bem à frente: renomeações Vexx, relay Tailscale,
  diagnósticos, FASE 1/2 parciais). Suíte real: `tests/` com 100+ testes
  (números "102/30" não conferem com o repositório; baseline medido:
  **125 passed + 4 falhas**, das quais 3 eram imports quebrados
  `import JULIA_auth` vs arquivo `julia_auth.py` — corrigidos sem alterar
  lógica — e 1 ambiental).
- Preservado: memória V4.1, contas V4.1.5, painel admin, JDUI, Hermes,
  extensão Júlia e Fajulto Studio intocados. Sem push/deploy.

## 2. Segurança (§2) — achado crítico e correção

- **Achado:** `screen` (observação da tela) livre para qualquer conta
  autenticada; só `input` exigia grant (`pc_agent.py`, "ver a tela é livre").
  Com contas de amigos, isso expõe o PC hospedeiro por mera autenticação.
- **Correção (só o necessário):** `resposta_screen()`/`resposta_input()`
  com gate `JULIA_auth.pode_remoto()` no agente; `sem_permissao` → 403 no
  relay; bloqueio de conta derruba ambos mesmo com grant; `learn_*` todo
  atrás de `dono_bloqueado()`. Bloqueio no agente, não só na UI.
- **Janela de revogação:** `REVOGA_TTL = 60 s` no relay + revogação de
  sessões no SQLite ao bloquear. Pior caso: sessão revogada vale até 60 s
  no relay. Aceito e documentado (reduzir o TTL = mais polling; pendente).
- Testes: `test_gate_agente_*`, `test_relay_remoto_negado_vira_403`,
  `test_relay_sid_revogado_bloqueia_dados` (pré-existentes, verdes).

## 3. O que foi implementado

`JuliaLearningEngine` (`learning.py`, stdlib): questões validadas
(4 tipos), correção determinística, discursiva assistida, tentativas com
história imutável, planos (CRUD + atualização que preserva feitos),
flashcards + SM-2 puro, stats reais, `recomendar` (regras, `sem_dados`
honesto), `criar_reforco` ("só o que errei"), `sinalizar_questao`.
17 endpoints `/api/learn/*` (sempre com `owner`; 403/404/409 mapeados).
Chat: `sintetizar_prova`, `sintetizar_reforco`, `linha_desempenho` no prompt.
JDUI: `studyplan`, `flashcards`, `studyprogress` (espelho py/js validado).
"Meus Estudos": consulta + cache IndexedDB offline + estados vazios.

## 4. Bugs reais encontrados pelos testes novos

1. `criar_assessment`: 7 placeholders p/ 6 colunas (nunca exercitado antes).
2. `desempenho_por_assunto`: discursiva pendente (`-1`) distorcia taxa.
3. Questões sem assunto próprio ficavam sem assunto (agora herdam o da prova).

## 5. Resultados

`py -m pytest tests/ -q`: **146 passed, 1 failed** (e2e exige Hermes ao vivo;
ambiental e pré-existente). Nenhum teste eliminado. No app, nenhuma
dependência nova; no ambiente do PC/agente: `tzdata` (dados IANA — sem ela,
o Windows rejeita fusos válidos e quebra o relógio local) e `pillow`/`mss`
nos testes (já deps de runtime).

## 6. Limitações e próximos passos

Ver `docs/JULIA_LEARNING_PROGRESS.md` (pendências 1–5): E2E em aparelho real,
aula canônica (FASE 5), fila offline de respostas, e2e Hermes ao vivo, TTL.
Offline: consulta funciona do cache; prova/correção/conteúdo novo exigem o
PC — afirmado na UI ("Conecte-se…"), nunca prometida IA offline.
