# JULIA Product JDUI (V4.9.1)

Cinco componentes reais para resultados de compra, no contrato
`JULIA-ui-message/v1`. Validação espelhada Python (`jdui.py`) ↔ JS
(`public/jdui.js`); render só com funções registradas (nenhum JS do modelo).

## Componentes

| Componente | Props | Uso automático |
|---|---|---|
| `productcard` | `{produto, sources?}` | 1 produto: card detalhado |
| `productgrid` | `{title?, items[1..6], sources?}` | vários: grade ordenável |
| `productcompare` | `{title?, items[2..4], sources?}` | comparação: tabela (menor preço destacado) |
| `productdetails` | `{produto, sources?}` | specs completas + ofertas |
| `productgallery` | `{title?, imagens[{url, legenda?}][1..8], sources?}` | galeria com thumbs |

### Esquema `produto`

`nome*` (160), `marca`, `modelo`, `variante`, `imagem` (https, sem
credenciais), `preco` (texto exibido, ex. `"R$ 1.299,99"` ou
`"Preço não confirmado"`), `preco_valor` (número|null, p/ ordenar),
`moeda`, `loja`, `url`, `specs` (objeto, máx 12), `avaliacao` (0–5|null),
`n_avaliacoes`, `disponibilidade`
(`em_estoque|sem_estoque|estoque_limitado|pre_venda|desconhecida`),
`verificado_em` (data da consulta — preço é histórico),
`ofertas[{loja, preco, url}]` (máx 6, outras lojas),
`sources` (provenance até 20 refs).

Valores fora de escala (`preco_valor` ≤ 0 ou ≥ 1e9, avaliação fora de
0–5) são anulados, nunca exibidos. `javascript:` e URLs com credenciais
viram `""`.

## Interatividade (tudo funcional, sem recarregar)

- **Abrir oferta ↗**: link `target=_blank rel=noopener noreferrer`.
- **Ampliar imagem**: clique abre lightbox local (fecha no clique).
- **Comparar**: botão chama `ctx.onChat("Compare <nome> com as outras opções")`.
- **Ordenar** (grid): menor preço (nulos por último) · avaliação · nome A–Z.
- **Especificações** (card): expandir/ocultar, estado persistido por slot.
- **Outras lojas**: chips com links por oferta.
- **Fontes**: `renderProvenance` (Referências) em todos os componentes.
- **Sem foto**: placeholder estilizado (imagem some via `onerror`).

Estado (`ordem`, `detalhes`, `idx` da galeria) persiste via
`ctx.saveState`/`loadState` + `/api/ui-state` (idempotente por `k`).

## Estilo (Minimal Premium)

Classes `jdui-pcard/-pmedia/-pimg/-pbody/-pnome/-pmarca/-ppreco/-ploja/
-paval/-pdisp/-pchips/-pchip/-pthumbs/-pthumb/-lightbox` em
`public/styles.css`: preço em `--purple` 18px, badge de disponibilidade
por cor (verde/vermelho/âmbar), grade 1 col → 2 col ≥ 560px, tabelas em
`jdui-scrollx` (mobile), `lazy loading` + `referrerpolicy=no-referrer`,
alvos ≥ 42px, `prefers-reduced-motion` herdado.

## Exemplo

```jdui
{"version":"JULIA-ui-message/v1","blocks":[{
  "type":"ui","component":"productgrid",
  "props":{"title":"Celulares até R$ 1.000","items":[{
    "nome":"Galaxy A15 8GB RAM 256GB","marca":"Samsung",
    "imagem":"https://cdn.loja.com/a15.jpg","preco":"R$ 899,00",
    "preco_valor":899.0,"moeda":"BRL","loja":"lojaexemplo.com",
    "url":"https://www.lojaexemplo.com.br/a15",
    "specs":{"RAM":"8 GB"},"avaliacao":4.6,"n_avaliacoes":210,
    "disponibilidade":"em_estoque","verificado_em":"16/10/2026"}],
   "sources":[{"id":"S1","title":"Loja X","url":"https://www.lojaexemplo.com.br/a15"}]}}]}
```

## Segurança do renderer

`textContent` (escape automático, nunca `innerHTML` com dado do modelo),
`URL_OK` espelhado, sem `eval`, sem `img` sem validação, sem autoplay.
Blocos inválidos/desconhecidos caem em fallback sem travar o chat.
