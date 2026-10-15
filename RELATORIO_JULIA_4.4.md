# RELATÓRIO JÚLIA 4.4 — Inference Reliability & Research Engine

## 1. Baseline e auditoria

HEAD `83b9bfd`, suíte inicial **157 passed, 0 failed** (E2E determinístico
após V4.3.1). V4.3/Learning/aulas/offline/admin/memória preservados; sem
push/deploy; sem bancos/serviços pagos; extensão e Studio intocados.

## 2. Inference reliability (V4.3.1)

Diagnóstico real (16/10, sondas executadas, quota zero): `/v1/models` OK com
423 modelos; `laguna-s-2.1:free` devolve corpo vazio; demais slugs 404 no
proxy. **Falha de provedor.** Implementado: códigos 402/422, `tentar_modelos`
(backoff, para em auth, erro original com modelo único), `chat_stream_fb`
(troca só pré-1º-delta), circuit breaker 4×120 s, `JULIA_AI_FALLBACKS`,
`model_usado` auditável em todos os caminhos. Streaming verificado ponta a
ponta: sucesso vazio impossível por construção (bridge → agente → SSE → app).

## 3. Research Engine (V4.4) — FUNCIONAL

`research.py` + integração no prompt + transforms. Rápida e aprofundada com
orçamentos; proveniência completa; citações validadas; cache SQLite por dono
com TTL e flag; memória só como termos; runs por conversa; transforms sem
números inventados. Parser DDG validado **ao vivo** (6 resultados reais);
queda do provedor degrada com mensagem honesta.

## 4. Arquivos

- Criados: `research.py`, `tests/test_research.py` (8 testes),
  `docs/JULIA_{RESEARCH_ENGINE,RESEARCH_SECURITY,INFERENCE_RELIABILITY,
  RESEARCH_PROGRESS}.md`, este relatório.
- Modificados: `hermes_bridge.py` (erros, fallback, breaker),
  `pc_agent.py` (config, `gerar_texto`, research no prompt, transforms,
  remoção da busca legada duplicada), `open_db` (+tabelas research),
  `server.py` (nada — pesquisa via chat), `tests/test_ai.py` (+8),
  `tests/test_avaliacao.py` (T5 no novo caminho), `tests/test_frontend_smoke.py`
  (pin anti-sucesso-vazio), `.env.example` (`JULIA_AI_FALLBACKS`),
  `docs/JULIA_MOBILE_ROADMAP.md`.

## 5. Testes

Suíte final: **174 passed, 0 failed, 0 ignorados** (inclui E2E com processos
reais). Mocks vs real separados: `test_research.py` usa fixtures HTTP locais (SSRF de verdade
contra os casos bloqueados); rede real usada só em sondas manuais
documentadas (DDG OK, Hermes inferência BLOQUEADA). Nenhum teste eliminado;
falhas nunca mascaradas (T7 preservado via erro transparente).

## 6. Classificação e pendências

FUNCIONAL: fallback, streaming, busca, proveniência, grounding, memória,
transforms, segurança testada. PARCIAL: status de progresso ao vivo (só
narrativa final). AUSENTE: 2º provedor, pin DNS. BLOQUEADA: inferência
Hermes real (provedor), E2E em aparelho físico.
