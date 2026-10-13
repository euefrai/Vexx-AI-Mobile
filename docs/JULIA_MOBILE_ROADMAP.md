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

## V4.4 — PESQUISA E CONFIABILIDADE
- Provedores intercambiáveis, extração de página, comparação de fontes,
  citação discreta, "pesquisado agora" vs "conhecimento do modelo" explícito.

## V4.5 — AGENTES
- Perfis (professora/pesquisadora/organizadora/criativa/analista) como
  system prompts + ferramentas autorizadas compartilhadas; fila e limites de
  consumo do Hermes; aprovação para ações sensíveis.

## V4.6 — COMUNIDADE/MULTI-CONTA
- Cadastro, isolamento total, compartilhamento explícito (prompts, quizzes,
  interfaces), biblioteca, moderação. Só após V4.0 de isolamento.

## Explicitamente FORA
- Fórmulas KaTeX (sem parser próprio confiável; reavaliar com lib leve).
- Edição in-place de mensagem e ramificação (custo alto, valor baixo p/ V4.0).
- Compartilhar respostas p/ link público (exige backend persistente — V4.6).
