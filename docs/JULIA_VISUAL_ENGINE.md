# JULIA Visual Engine (V5.2)

Seleção automática de apresentação a partir do Intent Engine + dados
realmente disponíveis. Nunca força visual em resposta simples; nunca
inventa dados para preencher um componente.

## Mapa intenção → apresentação

| Pedido | Componente | Origem dos dados |
|---|---|---|
| Produtos | productcard/grid/compare | Shopping Engine (verificados) |
| Comparação 2–4 itens | productcompare / compare | dados da conversa |
| Estatísticas/números | chart (bar/line/pie/area/scatter) | trechos (research) ou tabela anterior |
| Explicação técnica | diagram / evidencegraph | conteúdo validado |
| Processo/projeto | roadmap (stages, progresso real) | conteúdo (sem progresso fictício) |
| Pesquisa | sources/cards/table/dashboard | última run/job (reuso, sem rebucar) |
| Estudos | quiz/checklist/lesson/flashcards | Learning Engine |
| "Mostre as fontes" | sources (status) | evidências do job |

## Transformações determinísticas (sem LLM, sem nova pesquisa)

`fence_transformacao_visual`: "transforme em gráfico" usa a última
`tabela` da conversa (coluna numérica ≥2 valores; `_num_celula` entende
`R$ 1.234,56`, `12%`, `1,234.5`); "em tabela/cards/dashboard" usa a
última run (`fence_de_pesquisa`); sem dados → texto honesto.
`fence_de_fontes` expõe status encontrada/aberta/utilizada.
`fence_tabela_para_grafico` é puro e determinístico (mesma entrada,
mesma saída).

## Regras

- `update_of` permitido: chart, table, dashboard, compare, diagram,
  checklist, cards, tabs, accordion, form, calculator, sources, roadmap,
  productgrid. Imutáveis: exam, quiz, studyprogress.
- Fences inválidos somem (nunca JSON bruto); parciais de stream esperam.
- Vídeo: somente link-card YouTube/Vimeo (CSP bloqueia iframe; sem
  autoplay, sem embed arbitrário). Imagem genérica jamais passa por
  foto de produto (placeholder "Sem foto" explícito).
