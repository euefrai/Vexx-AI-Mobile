# Relatório Júlia 4.9.1 — Shopping Intelligence & Visual Results

## Status: ENTREGUE (com 1 ressalva de ambiente)

Pesquisa visual de produtos funcional, integrada ao chat e ao JDUI, sem
recriar o sistema: reusa Research Engine (DDG + `baixar` com SSRF),
Evidence Graph (fontes), SSE/deltas, SQLite por dono e registry JDUI.

## Auditoria (fase 1)

- Git: `main` em `4524b2f`; durante esta sessão o usuário commitou
  `8239274` e `c70c26c` (snapshots do working tree + trabalho próprio de
  identidade — `assistant_identity.py`, NÃO tocado aqui, conforme a regra
  de não implementar a personalidade nesta fase).
- V4.9 parcial confirmada (lab só com fixture sintética; Hermes bloqueado).
  Nada da V4.9 foi alterado além do necessário.
- Modelo principal e extensão Fajulto Studio: intocados. Sem push/deploy.
- Achado: `test_jdui_v43_no_node` (falha conhecida da V4.9 por edição local
  de UI) **passa agora** nesta árvore.
- UX Minimal Premium preservada (só acréscimos `jdui-p*`).

## Entregue

- `shopping.py` (novo): intenção, critérios (orçamento BRL, marcas, specs,
  **RAM física vs virtual**), busca DDG dupla, extração JSON-LD + OpenGraph,
  normalização de preços, dedupe multi-loja, filtros com motivos de exclusão,
  comparação determinística, persistência por dono (TTL 6h), fences JDUI
  determinísticos, follow-ups, `remover_fences_produto`.
- `jdui.py`: validadores `productcard/productgrid/productcompare/
  productdetails/productgallery` + registro.
- `public/jdui.js`: validação espelhada + 5 renderers (lazy img, fallback
  sem foto, lightbox, ordenar, expandir specs, comparar via onChat, ofertas,
  provenance). Correção de robustez: sem `lastChild` (harness).
- `public/styles.css`: bloco `jdui-p*` Minimal Premium + responsivo.
- `pc_agent.py`: `import shopping`, tabelas no `open_db`, limpeza no
  `_apagar_todos_dados`, `REGRAS_SHOPPING`, catálogo JDUI, regra
  `productgrid`, `extras["shop"]` (pula pesquisa genérica dupla), follow-up
  determinístico + busca com progresso real + fence da ferramenta no worker.
- `tests/test_shopping.py`: 34 testes (32 mock + 2 `e2e_real`).
- Docs: `docs/JULIA_SHOPPING_INTELLIGENCE.md`,
  `docs/JULIA_PRODUCT_JDUI.md`; roadmap atualizado (abaixo).

## Medido

| Verificação | Resultado |
|---|---|
| `test_shopping.py` (mocks+Node) | **32 passed** |
| Foco regressão (jdui, v43, interactive, chatpro, avaliacao, research, isolamento, docs, frontend) | **85 + 45 passed** |
| Suíte completa (`-k "not e2e_real"`) | **364 passed**, 6 deselected, só 2 warnings pré-existentes |
| E2E real DDG direto | **skip** — DDG retorna bot-wall (página 14KB sem `result__a`) |
| E2E real `pesquisar` | **skip** honesto (provedor sem resultados; pipeline coberta por mocks + fixtures JSON-LD) |
| Extração JSON-LD real (fixture Product/Offer/AggregateRating) | preço 1299.99 BRL, imagem https, aval 4.6 (210) |
| SSRF | loopback recusado no pipeline; `javascript:`/credenciais anuladas |
| Prompt-injection | prosa maliciosa da página não vaza para resposta/cards |

## Ressalva (honesta)

Extração de página real de loja **não foi verificada ponta a ponta** neste
ambiente (DDG com bot-wall; nenhuma loja declarada como suportada).
O sistema, por desenho, responde vazio honesto nesse caso em vez de
inventar — comportamento testado. Revalidar o E2E ao vivo quando o
provedor responder com resultados.

## Roadmap (atualizado em `docs/JULIA_MOBILE_ROADMAP.md`)

- **V4.9.1 — Shopping Intelligence** (este relatório).
- **V5.0 — Advanced Memory & Luccas Trawman Identity**.
- **V5.1 — Intent & Understanding Engine**.
- **V5.2 — Advanced Visual JDUI**.
- **V5.3–V5.5 — Interactive 3D**.

## Uso

"Luccas, encontre os melhores notebooks até R$ 2.000." → deltas `🔎 …`,
texto com preços/lojas verificados + `productgrid` com fotos, links,
avaliações e data de verificação; "compare os dois primeiros" e
"mostra só os mais baratos" reusam a consulta sem nova busca.
