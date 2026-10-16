# JULIA Advanced JDUI (V5.2)

27 componentes validados em espelho Python (`jdui.py`) ↔ JS
(`public/jdui.js`), render só com funções registradas.

## Novos em V5.2

- **sources** `{title?, items[1..10{titulo*, url, dominio, data,
  trecho, status}]}` — cards de fontes com badge
  Encontrada/Aberta/Utilizada, links `noopener`, provenance.
- **video** `{titulo?, url*, thumb?, duracao?, fonte?}` — allowlist
  YouTube/Vimeo (Python+JS); link-card com play, sem iframe.
- **roadmap** `{title?, stages[1..12{id*, title*, desc?, status,
  data?, marco?}]}` — barra de progresso real (done/total), expandir
  detalhes (estado persistido), marcos ◆, só leitura (progresso nunca
  é escrito pelo frontend).

## Melhorias em existentes

- **table**: botão CSV corrigido (`ctx` faltava → ReferenceError);
  ordenação por teclado (Enter/Espaço, `tabindex`, aria); paginação
  12/página com contador (estado persistido); filtro mantido.
- **chart**: tooltips, legenda, fonte, estado vazio (já existiam;
  verificados no QA).
- **diagram**: zoom, filtro, seleção expansível, teclado (existiam).
- **productcompare**: tabela em `scrollx` (mobile).

## Segurança e performance

`textContent` sempre; `URL_OK` espelhado; CSV com guarda `'=+-@`;
imagens `lazy` + `no-referrer` + fallback; sem timers/animações
contínuas; DOM limitado (paginação); `:focus-visible` visível;
`prefers-reduced-motion` herdado. Multiusuário: estado por slot
(`message_id`/componente) + `/api/ui-state` por dono.

## QA

Harness Node (validação+render+cliques) + QA visual em Chrome headless
real: 6 componentes, zero erros JS (screenshot em relatório).
3D: não implementado nesta versão (roadmap V5.3–V5.5).
