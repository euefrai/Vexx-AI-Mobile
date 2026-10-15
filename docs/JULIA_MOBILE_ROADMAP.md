# Júlia Mobile — Roadmap 4.x

Princípios: conversa primeiro; sem IDE; sem Supabase/Firebase; sem pagos
obrigatórios; offline-first; nada simulado; cada versão com testes.

## V4.0 — FUNDAÇÃO (em execução)
- [ ] Fundação multiusuário: `owner_id`, ownership no backend, testes de isolamento.
- [ ] Chat profissional: arquivar, fixar, exportar (.md/.json), regenerar,
      continuar resposta truncada, busca no histórico. Sem botões decorativos.
- [ ] Contexto com orçamento + grounding (origens rotuladas, anti-invenção).
- [ ] Suíte de avaliação conversacional (8 testes do spec).
- [ ] Relatório V4.0 honesto (FUNCIONAL/PARCIAL/AUSENTE/BLOQUEADO).

## V4.1 — MEMÓRIA INTELIGENTE
- Tipos: trabalho/episódica/semântica/temporal/assunto (+social com autorização).
- Pipeline: identificar → classificar → pedir autorização quando sensível →
  normalizar → deduzir → persistir com proveniência/versão → recuperar → corrigir.
- Comandos: ver, corrigir, exportar, desativar, apagar. Temporais sem ano
  inventado. Testes de contradição e de "não inventar memória".

## V4.2 — EDUCAÇÃO
- Planos de estudo (assunto/objetivo/data/tempo/nível), checklist com progresso,
  flashcards + revisão espaçada, simulados, correção determinística do objetivo,
  histórico de desempenho. JDUI: plano, prova, flashcard, painel.

## V4.3 — JDUI AVANÇADO
- Atualizar interface sem perder estado; `chart` SVG a partir de dados reais
  (nunca série inventada); dashboards; `since` incremental no ui-state.

## V4.4 — PESQUISA E CONFIABILIDADE ✅ (2026-10-16)

- Inference reliability: códigos 402/422, `tentar_modelos` (preferencial +
  fallbacks explícitos, backoff, para em auth, erro original com 1 modelo),
  `chat_stream_fb` (troca só antes do 1º delta), circuit breaker por base,
  `JULIA_AI_FALLBACKS`. E2E determinístico. Hermes real: inferência bloqueada
  no provedor (ver JULIA_INFERENCE_RELIABILITY.md); quota zero em testes.

- Research Engine (`research.py`): buscar DDG (html+lite, parsers 2026) →
  recuperar páginas → extrair → divergências → runs persistidos; SSRF
  bloqueado em cada redirect; teto 2 MB/10 s/só-texto; cache SQLite por dono;
  citações [S1] validadas; grounding com wrapper anti-instrução; memória só
  como termos de tópico; transforms determinísticos (gráfico/tabela/dashboard/
  cards) sobre runs; reuso "com essas fontes". Sem frontend novo (links
  markdown). Status "pesquisando…" ao vivo: AUSENTE (stream é canônico).
  Docs + RELATORIO_JULIA_4.4.md. Suíte: ver relatório.

## V4.5 — DEEP RESEARCH AGENTS & LIVE RESEARCH ✅ (2026-10-16)
- `research_agents.py`: orchestrator, planner, 7 papéis, evidence store,
  verificação determinística, síntese extrativa + auditoria.
- Jobs em background (1/dono, teto 2), 5 rotas relay, painel live Minimal
  Premium com polling, comandos de memória sem LLM, fence de evidências.
- Quality Lab com métricas + casos; LLM-real = skip BLOQUEADO.
- Relatório em RELATORIO_JULIA_4.5.md.



## V4.6 — EVIDENCE INTELLIGENCE ✅ (2026-10-16)
- Grafo de evidências (SQLite, IDs estáveis), claims v2 com condições, verificação 2.0 com método registrado.
- Independência de fontes, contradições por dimensão, auditor 2.0, 16 benchmarks congelados.
- Componente evidencegraph + memória do grafo (5 perguntas sem LLM). Verificação semântica: BLOQUEADA.
- Relatório em RELATORIO_JULIA_4.6.md.

## V4.7 — AGENTES
- Perfis (professora/pesquisadora/organizadora/criativa/analista) como
  system prompts + ferramentas autorizadas compartilhadas; fila e limites de
  consumo do Hermes; aprovação para ações sensíveis.

## V4.8 — COMUNIDADE/MULTI-CONTA
- Cadastro, isolamento total, compartilhamento explícito (prompts, quizzes,
  interfaces), biblioteca, moderação. Só após V4.0 de isolamento.

## Explicitamente FORA
- Fórmulas KaTeX (sem parser próprio confiável; reavaliar com lib leve).
- Edição in-place de mensagem e ramificação (custo alto, valor baixo p/ V4.0).
- Compartilhar respostas p/ link público (exige backend persistente — V4.6).
