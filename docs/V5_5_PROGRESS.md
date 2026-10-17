# V5.5 — progresso

Implementação e QA local em andamento (início 16/10/2026, esta sessão em
17/10/2026), a partir de `cbbf4de` (V5.4.3). **Sem push/deploy.**

## Fases entregues (commits locais)

| Fase | Commit    | Entrega |
|------|-----------|---------|
| 1/2  | `b97493e` | Núcleo de busca: `search_providers.py` (11 provedores oficiais), `search_orchestrator.py`, `web_extract.py`; `research._buscar_orquestrado`; `pc_agent` liga por `JULIA_WEB_SEARCH` |
| 3    | `549a34f` | Shopping verificado: `source_check.py`; link/imagem com veredito; etapa web por último na cadeia; alternativas ≤ +25% com `diferencas`; `url_item` nos cards |
| 4    | `c050d4d` | Agentes: `ProvedorOrquestrado` ("web") por último; recuperação/lacunas de busca no replanejamento (busca+ler+analisar); divergência com conversão de unidades; fontes desatualizadas (informativo) |
| 5    | `75f5168` | JDUI: selo honesto do link no card (verificado/parcial/reprovado/listagem), motivo no tooltip, CTA "Abrir link ↗" para reprovado, overflow dos cards corrigido |
| 6    | `79517e1` | 22 testes congelados do núcleo (`tests/test_search_core_v55.py`); URL inválida fora do dedupe; "quanto custa" → produto; "até R$" não é pedido de data |
| 6.1  | `8c58bff` | Pós-docs: correspondência sem genéricos + resgate de provedor quando o índice devolve lixo + consulta enxuta na recuperação (caso real do smoke) |

## Prova executada

- **Suíte completa: 607 passed, 4 skipped** (~3 min 03 s) — era 528/4 antes
  do V5.5; **+79 testes novos**, nenhum removido.
  - `test_search_core_v55.py`: 28 · `test_source_check.py`: 17 ·
    `test_shopping_v55.py`: 15 · `test_research_v55.py`: 11 ·
    `test_jdui_v55.py`: 5 · `test_evidence_graph.py`: +3.
- Probes ao vivo (sem bypass): "fone bluetooth até R$ 500" → 4 produtos
  todos `verificado`, 3 imagens reais verificadas, fase "verificando"
  visível; "notebook 16gb ram até R$ 3000" → 7,3 s, 1 alternativa com link
  verificado e diferenças explícitas.
- Smoke pós-docs (17/10/2026, provedores reais): "preço do fone bluetooth"
  e "preço fone bluetooth até R$ 500" voltavam lixo do índice (carros/SP,
  metrô, CEAGESP) marcado como `ok` — agora: lixo registrado, provedor
  trocado, recuperação com consulta enxuta e estado honesto; no shopping,
  "preço fone bluetooth até R$ 500" → **4 produtos KaBuM `verificado`**
  dentro do orçamento em ~2,2 s; query já boa ("fone bluetooth até R$ 500")
  segue no caminho rápido (~0,5 s).
- `node --check` ok em `public/jdui.js` e `public/app.js`.

## Documentos desta entrega

- [JULIA_RESEARCH_INTELLIGENCE_3.md](JULIA_RESEARCH_INTELLIGENCE_3.md) —
  arquitetura completa, orçamentos, env vars, decisões OSS, limitações.
- [JULIA_ADAPTIVE_SEARCH.md](JULIA_ADAPTIVE_SEARCH.md) — classificação,
  variantes, provedores, lacunas, recuperação, estados.
- [JULIA_SOURCE_VALIDATION.md](JULIA_SOURCE_VALIDATION.md) — vereditos de
  link/imagem, sinais produto × listagem, integração JDUI.
- `../RELATORIO_JULIA_5.5.md` — relatório da entrega com limitações.

## Pendente (honesto)

- Smoke online separado dos provedores (marcado `e2e_real`, opcional, não
  bloqueia a entrega) — rede real não é pré-requisito do CI local.
- Instância SearXNG autorizada (`JULIA_SEARXNG_URL`) continua **não
  configurada**; o provedor responde "indisponível" honesto até existir.
- Verificação semântica de afirmações segue BLOQUEADA (depende de LLM).
- Nada apontado para produção: `render.yaml` intocado; commits só locais.
