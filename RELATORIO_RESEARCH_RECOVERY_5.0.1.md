# Relatório Research Recovery 5.0.1

## Status: PESQUISA RECUPERADA (parcial por ambiente)

## 1. Causas identificadas (reproduzidas no fluxo real)

- **DuckDuckGo bot-wall**: `html`/`lite` retornam HTTP 202 com página de
  desafio (~14KB, 0.3s, sem exceção e sem `result__a`). `buscar_ddg`
  devolvia `[]` silencioso; `pesquisa_rapida` registrava "busca:
  0 resultados" e entregava 0 fontes → `bloco_falha` → com Hermes
  bloqueado, falha total no chat. **Externo** (rede/IP), não bug interno.
- **Cadeia que parava no vazio**: `research_agents.buscar_com_fallback`
  retornava na primeira lista vazia — Lite/Wikipedia/acadêmico nunca eram
  tentados. **Bug interno**, corrigido.
- **Sync DDG-only**: `pesquisa_rapida` (caminho do chat) só conhecia DDG.
- **Sem resposta sem LLM**: `BridgeErro` + fontes virava erro vazio,
  mesmo com evidências em mãos.
- **MLB API** (`api.mercadolibre.com`): HTTP 403 por IP. **Externo**.
- Nenhum CAPTCHA/bot-wall foi contornado; bloqueios viram falha
  registrada + próximo provedor.

## 2. Correções

- `research.py`: `_baixar_json` (SSRF/revalidado/teto, só JSON),
  `buscar_wikipedia` (opensearch oficial, marcada `tipo=enciclopedia`),
  `buscar_com_fallback` (ddg→lite→wikipedia; vazio alterna; circuit
  breaker 5min por provedor; sem cache negativo — só salva com fontes),
  `pesquisa_rapida` usa a cadeia por padrão (+ `origem`/`etapas`),
  `extrair_texto_html` pula nav/header/footer/aside,
  `resumo_deterministico` (digest honesto sem LLM).
- `research_agents.py`: fallback continua no vazio; `ProvedorWikipedia`;
  incluída em `provedores_reais()`.
- `pc_agent.py`: com fontes e sem inferência, chat stream e completo
  entregam o digest (links+trechos) em vez de erro; sem fontes, o erro
  original é preservado (teste t7 intacto).

## 3. Provedores testados (HTTP real observado aqui)

| Provedor | Status | Observado |
|---|---|---|
| DDG html/lite | BLOQUEADO | 202 bot-wall, 0 resultados |
| MLB API | BLOQUEADO | 403 |
| Wikipedia opensearch+artigos | FUNCIONAL | 200, E2E passa |
| OpenAlex | FUNCIONAL | 200, E2E passa |
| SearXNG | NÃO CONFIGURADO | sem `JULIA_SEARXNG_URL` (declarado, não finge) |

Wikipedia/OpenAlex **não** substituem busca geral nem preços; resultados
vêm tipados e o Shopping continua em cadeia própria (MLB→DDG→vazio
honesto, E2E ao vivo segue BLOQUEADO).

## 4. Testes (`tests/test_research_recovery.py`, 14)

Unitários com fixtures (202/403/429/timeout/vazio/parser/circuito/
digest/isolamento), E2E local (HTTP loopback real + `baixar`/parse reais),
E2E ao vivo (Wikipedia + OpenAlex passam aqui). t7 e suíte intactos:
regressão total `not e2e_real` **422 passed**, 10 deselected (`e2e_real`),
só 2 warnings pré-existentes (2 testes academic atualizados p/ nova lista
de provedores, gate intacto).

## 5. Arquivos / limitações / pendências

- Modificados: `research.py`, `research_agents.py`, `pc_agent.py`
  (+digest); novo teste; este relatório. Identidade, memória, modelos,
  extensão e Fajulto intactos. Sem push.
- Limites: trechos podem trazer ruído residual; acadêmico no sync-chat
  só via jobs (flag); semântica depende do Hermes (bloqueado).
- Pendências: revalidar DDG/MLB em outra rede; configurar SearXNG
  autorizado se desejado; E2E ao vivo de preços quando houver provedor.
