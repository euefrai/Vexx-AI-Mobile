# JÚLIA Research — Progresso por fase (V4.4)

- ✅ FASE 1 — Auditoria e baseline. HEAD `83b9bfd`, tree limpo; suíte 157/157.
- ✅ FASE 2 — Diagnóstico Hermes. `/models` OK (423); inferência bloqueada no
  provedor (`vazia` no preferencial, 404 em slugs). Provedor, não código.
- ✅ FASE 3 — Fallback e erros. 402/422, `tentar_modelos`, `chat_stream_fb`,
  circuit breaker (bug real corrigido), `JULIA_AI_FALLBACKS`, `gerar_texto` em
  todos os caminhos LLM. 8 testes novos.
- ✅ FASE 4 — Streaming confiável. Verificado ponta a ponta; sucesso vazio
  impossível; teste + pin no smoke.
- ✅ FASE 5/6 — Ferramentas (`research.py`): busca DDG html+lite (parsers
  2026 validados ao vivo: 6 resultados reais), recuperar, extrair.
- ✅ FASE 7 — Proveniência: ids S1.., acesso, validador de citações, runs.
- ✅ FASE 8 — Aprofundada: split determinístico, merge/dedupe, divergências,
  interrupção, run persistido.
- ✅ FASE 9 — Grounding: wrapper anti-instrução, falha honesta, sem consenso
  inventado.
- ✅ FASE 10 — Memória: só termos de tópico com gatilho (teste anti-vazamento).
- ✅ FASE 11/12 — Learning + JDUI: grounding no prompt educacional, reuso
  "com essas fontes", transforms determinísticos (gráfico/tabela/dashboard/
  cards), gráfico-evolução preexistente intacto.
- ✅ FASE 13 — UX: zero frontend novo (links markdown + chat minimalista);
  status ao vivo AUSENTE (declarado).
- ✅ FASE 14 — Segurança, testes e docs (este arquivo + relatório).

Pendências: inferência Hermes real (provedor), status de progresso ao vivo,
segundo provedor de busca, pin TOCTOU DNS, E2E em aparelho físico.
