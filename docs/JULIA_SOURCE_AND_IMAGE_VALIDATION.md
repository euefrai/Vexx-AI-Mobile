# Júlia — Validação de fontes, links e imagens (V5.7)

Escopo: como a Júlia decide que um link é uma página de produto/item, que
uma imagem é a foto do item e que uma página lida é fonte utilizável —
sempre com veredito explícito, sem inventar e sem contornar bloqueios.

Base: `source_check.py` (V5.5) + integração `shopping.py`/JDUI + leitura
determinística (`web_extract.py`).

## 1. Vereditos (vocabulário)

Todo item validado carrega `veredito` + `codigo` + `motivo`:

| veredito | significado |
|---|---|
| `verificado` | passou em todos os sinais aplicáveis |
| `parcial` | página/imagem utilizável com ressalva explicada |
| `nao_verificado` | rede/bloqueio — **não** é aprovação nem reprovação |
| `reprovado` | não é página do item / não é imagem válida |

### Códigos de imagem (`validar_imagem`)

- `reprovado`: `nao_e_imagem`, `imagem_minuscula`, http 404/410;
- `parcial`: `formato_desconhecido`, `imagem_pequena`, `sem_dimensoes`;
- `verificado`: `ok`.

### Códigos de página/link (`avaliar_pagina`)

- `reprovado`: `tipo_inesperado`, `binario`, `dominio_inesperado`,
  `listagem_nao_produto`, `sem_sinais_produto`, `nao_corresponde`;
- `parcial`: `ilegivel`, `correspondencia_parcial`;
- `verificado`: `ok`.
- `validar_link` ainda registra `http_404`/`http_410` (reprovado) e os
  demais erros de rede como `nao_verificado` (`_MAPA_ERRO`).

## 2. Regras V5.7 no shopping

1. **Link do item** (`_link_do_produto`): `url_item` > `url_final` > `url`.
   Quando o item veio de uma **listagem** (categoria/busca), isso é dito:
   `item_de_listagem` → selo "link do item veio de listagem (página do item
   NÃO aberta)". Homepage/categoria nunca é apresentada como página do
   produto aberto.
2. **Marca é critério obrigatório**: produto de outra marca vira
   `marca_diferente` (alternativa explícita "outra marca: asus
   (pedido: lenovo)"); sem marca confirmável vira `marca_nao_confirmada`.
   Nunca aparece como se fosse o pedido.
3. **Specs pareadas**: "8gb 512gb" em notebook/celular/tablet vira
   `ram_fisica_gb=8` + `armazenamento_gb=512`; `_armazenamento_aparente`
   usa o maior GB ≥ 64 (em "16GB RAM + SSD 512GB" o armazenamento é 512,
   nunca a RAM).
4. **Imagens**: `verificar_imagens` valida até 3 imagens por busca.
   - `reprovado` → a imagem é **removida** do produto (o card mostra o
     selo "Sem foto confirmada" com o motivo);
   - `parcial`/`nao_verificado` → a imagem fica, com aviso no card.
5. **Proposta ao usuário**: candidatos com `item_de_listagem` ou veredito
   `nao_verificado`/`reprovado` não entram como "produtos" (vão para a
   trilha de ressalva/alternativas) — `shopping.py:1551`.

## 3. Pesquisa geral (além do shopping)

Página encontrada ≠ página lida. Estados das fontes no relatório:
`encontrada` → `aberta` (URL buscada com guarda SSRF, redirect seguro, teto
2 MB/10 s, cache SQLite por dono) → `utilizada` (fundamentou a resposta).
O link exibido é o `url_final` após redirects (ex.:
`pt.wikipedia.org/wiki/Freio_ABS` → `.../Sistema_de_travagem_antibloqueio`).
Nenhuma página é aberta sem passar por `research.baixar`/`sp._baixar`.

Na V5.7 a leitura também melhorou o trecho de proveniência: janelas de
referência/bibliografia (`Consultado em`, `Cópia arquivada`, `ISBN`, `doi:`,
`«»`, `↑`) são descontadas em `melhor_trecho` — o trecho mostrado é conteúdo
do corpo do artigo, não citação.

## 4. Bloqueios externos observados (2026-10-17) — sem bypass

| Fonte | Resultado real | Registro honesto |
|---|---|---|
| DuckDuckGo (html/lite) | CAPTCHA | `bloqueado` |
| Mercado Livre (API) | HTTP 403 | `bloqueado` |
| Magalu | HTTP 403 (bot-wall) | `bloqueado` |
| KaBuM (listagem) | página sem sinais de produto | `reprovado / sem_sinais_produto` |
| Amazon BR | HTTP 503 | `bloqueado` |
| Mojeek / Brave / Startpage / Yahoo / searx.be | indisponíveis | `indisponivel` |
| Semantic Scholar | HTTP 429 | `bloqueado` |

Nada foi contornado (sem IP/auth/CAPTCHA bypass). O valor da V5.7 é o
registro correto: quando a fonte bloqueia, o relatório diz que bloqueou e
não simula verificação.

## 5. Testes e evidências

- `tests/test_shopping_v57.py` — marca obrigatória, specs pareadas, selos
  (8 casos); trio de shopping: 66 passed.
- `tests/test_source_check*.py` — vereditos/códigos (baseline V5.5).
- `tests/test_web_extract_v57.py` — trecho não vem de referências.
- Benchmark `tools/bench_pesquisa_v57.py`, grupos `produtos`, `specs` e
  `links` (12 casos) — 34/34 global.
- Prova real do shopping (2026-10-17): pedido Lenovo → produtos Lenovo com
  link `verificado`/`url_item`; Asus e Dell como alternativas explícitas com
  "pedido: lenovo".
