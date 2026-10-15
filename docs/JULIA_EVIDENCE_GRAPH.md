# JÚLIA Evidence Graph (V4.6)

`evidence_graph.py` + tabelas `eg_nodes`/`eg_edges` (SQLite, indexadas, sem
banco externo). IDs estáveis (`kind:sha16`).

## Entidades e relações

Nós: `source` (consultada), `document` (conteúdo recuperado, com hash),
`claim` (afirmação + condições), `evidence` (referencia `evidence`),
`run` (reservado). Relações: SUPPORTS, PARTIALLY_SUPPORTS, CONTRADICTS,
MENTIONS, DERIVED_FROM, DUPLICATES, REPLACES, REQUIRES_VERIFICATION.

SUPPORTS só por quantidade exata; similaridade gera MENTIONS/DERIVED_FROM/
DUPLICATES (estrutural, provisório). Sem validador aplicável: `REQUIRES_
VERIFICATION` — nunca rótulo factual.

## Proveniência por evidência

IDs, URL original e final, título, autor/publicador (quando a página informa;
vazio quando não — nunca inventado), acesso (sempre), publicação (só se
conhecida), trecho, localização, hash do conteúdo, contexto ±120 chars,
afirmação, estado, método. Reacesso compara hash (versão consultada × atual).
Trechos limitados (nada de páginas inteiras).

## Memória do grafo

`fontes_que_sustentam`, `contradicoes_do_job`, `estudos_originais` (raízes
sem DERIVED_FROM entrando), `diff_pesquisas` (novas/removidas/alteradas por
URL canônica) — base das perguntas "de onde veio", "quem confirma",
"o que mudou".
