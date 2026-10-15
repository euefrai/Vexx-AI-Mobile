# RELATÓRIO JÚLIA 4.7 — Evidence Hardening & Live Research 2.0

## 1. Auditoria

HEAD `b6578cf` (fix primeira-resposta) + V4.6 íntegra; baseline **225
passed, 2 skipped**; rebrand paralelo preservado (fiação verificada).

## 2. V4.6.1 — Evidence Hardening (FUNCIONAL)

- `units.py`: 8 dimensões, 30+ unidades, temperatura com offset, rejeição de
  ambíguas/desconhecidas, testes de conversão e incompatibilidade.
- SUPPORTED agora exige quantidade exata convertida + entidade/propriedade
  em comum (≥2 tokens) + datas/base compatíveis. TDP≠consumo (teste),
  30%-sem-data vira ressalva (teste), comparado ausente barra (teste).

## 3. V4.7 — Live Research 2.0 (FUNCIONAL)

- SSE push real (tailer no worker → fan-out por owner → backlog + live +
  pings + fechamento) com polling fallback idêntico; E2E real verde
  (relay+agente+DDG, ~16 s, eventos ordenados, evidências com URLs).
- Painel: 12 fases, filtros, timeline capada, evidências expansíveis,
  fontes, erros, cancelar/pausar/retomar/resultado.
- Intervenção estruturada (6 ops) via API e chat; versionamento sem
  reexecutar feitas; incompatíveis invalidados e listados.
- Follow-ups de investigações agendados; métricas por provedor; pausa
  segura; checkpoints 2.0 com `ajustes`; testes de corrida.
- Hermes re-sondado: inferência segue BLOQUEADA (sem paid, sem credenciais).

## 4. Arquivos

- Criados: `units.py`, `tests/test_units.py`, `tests/test_research_e2e.py`,
  `pytest.ini` (marca `e2e_real`), 7 docs, este relatório.
- Modificados: `evidence_graph.py`, `research_agents.py`, `pc_agent.py`
  (tailer, intents, grafo), `server.py` (SSE, intervene, pause),
  `public/{app.js,index.html,styles.css}` (painel), testes, roadmap.

## 5. Testes

Suíte final: **233 passed, 0 failed, 2 skipped** (skips = LLM real,
BLOQUEADA; inclui E2E relay+agente+DDG reais). Segurança e regressões
verdes; mocks vs real separados (fixtures locais; DDG/Hermes só em sondas
manuais + E2E DDG). Nenhum teste eliminado; nada mascarado.

## 6. Pendências honestas

- Verificação semântica LLM: BLOQUEADA. Repetição numérica idêntica com
  contexto ainda sustenta (limite). Sem conversão implícita além da tabela.
- Push em TestClient só chega ao fechar o stream (testado assim);
  navegadores recebem incremental (padrão SSE).
- Aparelho físico, 2º provedor ao vivo, fila de prioridades: pendentes.
