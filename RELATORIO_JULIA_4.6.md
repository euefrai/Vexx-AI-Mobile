# RELATÓRIO JÚLIA 4.6 — Evidence Intelligence & Verification Engine

## 1. Auditoria

HEAD `4edec85` (V4.5) + 1 arquivo modificado alheio (`public/index.html`,
rebrand Vexx em paralelo — fiação do painel live verificada intacta).
Baseline: **198 passed, 1 skipped**. V4.0–V4.5 preservadas; sem push/deploy.

## 2. Entregas por fase

- FASE 2/3: `evidence_graph.py` — nós/arestas tipadas, IDs estáveis,
  proveniência (canônica, hash, contexto), tudo por owner com índices.
- FASE 4/5: claims v2 (split + condições; ausentes registradas) e
  verificação 2.0 (quantidade-exata; resto provisório/UNVERIFIED; método
  sempre registrado).
- FASE 6: independência (canônica, hash, Jaccard, citação literal;
  domínio≠independência).
- FASE 7: contradições por dimensão (valor/unidade/data/contexto) com
  follow-ups e status em_aberto; sem reconciliação inventada.
- FASE 8: auditor 2.0 (fantasmas, superlativos, sem-evidência, BLOQUEADA).
- FASE 9/13: agentes integrados + 7 eventos live novos (reais; agentes LLM
  continuam não fingidos).
- FASE 10/12: 5 perguntas de memória do grafo (funcionam sem LLM) + fence
  de evidências (cards) — reuso, sem workspace novo.
- FASE 11/12: componente `evidencegraph` (espelho py/js, zoom/filtro/seleção,
  teto 30 nós) + cards; popover global: AUSENTE (declarado).
- FASE 14: 16 benchmarks congelados + Quality Lab; LLM-real = skip.
- FASE 15/16: segurança (§17 intacta; grafo privado por owner), 7 docs.

## 3. Arquivos

- Criados: `evidence_graph.py`, `tests/test_evidence_graph.py` (7),
  `tests/test_evidence_benchmarks.py` (15+1 skip), 6 docs, este relatório.
- Modificados: `research_agents.py` (verificador v2, independência,
  investigações persistidas, auditoria, resumo), `pc_agent.py` (tabelas,
  intents de memória, fence de grafo), `jdui.py`/`jdui.js` (evidencegraph),
  testes (forma de veredito + casos novos).

## 4. Testes

Suíte final: **221 passed, 0 failed, 2 skipped** (skips = inferência LLM
real, BLOQUEADA no provedor). Bugs achados pelos testes: reconciliação de
unidades sem conversão, SUPPORTED sem ressalvas, contagem zerada de breaker
(V4.5), sintaxe JS (pipeline travava). Nenhum teste eliminado; falhas nunca
mascaradas.

## 5. Riscos e pendências honestas

- Verificação semântica real: BLOQUEADA (provedor). Léxico ≠ verdade.
- Repetição com números idênticos ainda sustenta (limite documentado).
- Conversão de unidades não implementada (inconclusivo honesto).
- Datas de publicação raramente disponíveis (só acesso afirmado).
- E2E com LLM + aparelho físico: pendentes.

## 6. Correção pós-V4.6 — primeira tentativa de IA (16/10/2026)

Sintoma: toda mensagem falhava de primeira com "mensagem não encontrada,
sincronize" e só respondia após retries. Causas encontradas e corrigidas:

1. Corrida sync→IA: o auto-disparo para pendentes não exigia confirmação do
   PC, e qualquer falha silenciosa de confirmação gerava `sem_mensagem`.
   Correção em duas camadas: (a) pedido de IA leva o texto junto
   (`text`/`created_at` em `/api/ai` e `/api/ai/stream`); o agente persiste
   (INSERT OR IGNORE, mesmas regras do sync, dono da sessão) antes de
   responder — atômico, funciona de primeira; (b) auto-disparo só para
   mensagens com `status === 'synced'`.
2. `ai_requests` com PK global: um dono sobrescrevia o estado de IA do
   outro (busy/replay vazavam). Migração para PK `(owner_id,
   user_message_id)` com dados preservados.
3. `messages` com PK global em `id`: segundo dono com mesmo id tinha a
   linha descartada (INSERT OR IGNORE) e caía em `sem_mensagem`.
   Migração para PK `(owner_id, id)` (colunas e índices preservados).

Suíte após a correção: 225 passed, 0 failed, 2 skipped (LLM real).
