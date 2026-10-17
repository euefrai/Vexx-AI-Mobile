# Júlia — Validação de Fontes, Links e Imagens (V5.5)

Data: 17/10/2026 · Refere-se a `source_check.py`, `shopping.py`,
`web_extract.py`, `jdui.py`/`public/jdui.js`. Visão geral em
[JULIA_RESEARCH_INTELLIGENCE_3.md](JULIA_RESEARCH_INTELLIGENCE_3.md).

Regra central: **um link ou uma imagem só é apresentado com o veredito do
que realmente aconteceu na verificação** — e veredito reprovado nunca é
escondido, só explicado. Sem navegador, sem JavaScript, stdlib pura, sem
contornar bloqueio.

## 1. Vocabulário de vereditos (`source_check.VEREDITOS`)

| Veredito         | Significado                                                        |
|------------------|--------------------------------------------------------------------|
| `verificado`     | abriu, tipo certo, conteúdo corresponde ao esperado                 |
| `parcial`        | abriu e corresponde, mas falta parte do esperado                    |
| `reprovado`      | não abriu (404/410), tipo errado, listagem no lugar de produto, conteúdo sem relação |
| `nao_verificado` | rede/bloqueio/limite: **não deu para checar** (nunca vira "ok")     |

## 2. Verificação de link (`validar_link`)

Ordem de checagem:

1. **SSRF**: `research.url_segura` em cada URL e em **cada redirect**
   (`_baixar_bytes`); destino não público/privado é reprovado na hora.
2. **Abertura**: timeout padrão 8 s, teto 1,5 MB, UA identificável.
3. **Status HTTP**: `401/403/429` → bloqueado (sem bypass);
   `404/410` → reprovado ("página não existe"); outros `4xx/5xx` →
   `nao_verificado` com o status registrado.
4. **Tipo de recurso** (`esperado.tipo`): `pagina/html`, `json`,
   `documento`, `produto`, `imagem` — content-type incompatível reprova.
5. **Conteúdo binário** (`\x00` nos primeiros 2000 chars) → reprovado.
6. **Extração real** (`web_extract.extrair_pagina`) → título, canônica,
   trecho usado e sinais.
7. **Domínio** (`esperado.dominio`): abriu em outro domínio → reprovado.
8. **Produto × listagem** (ver §3): listagem → `listagem_nao_produto`;
   sem sinais de produto → `sem_sinais_produto`.
9. **Correspondência** (`esperado.termos`): nenhum termo citado →
   `nao_corresponde`; alguns citados → `correspondencia_parcial` (parcial).
10. **Ilegível**: página vazia/JS sem texto → `parcial` (`ilegivel`).

Códigos de erro de rede/bloqueio e o veredito resultante (`_MAPA_ERRO`):

| Código          | Veredito          | Motivo                                     |
|-----------------|-------------------|--------------------------------------------|
| `ssrf`          | `reprovado`       | URL não pública/bloqueada (SSRF)           |
| `rede`          | `nao_verificado`  | falha de rede na verificação               |
| `bloqueado`     | `nao_verificado`  | provedor recusou (bot-wall/CAPTCHA); sem bypass |
| `http`          | `nao_verificado`  | HTTP de erro (404/410 → `reprovado`)       |
| `tamanho`       | `nao_verificado`  | recurso grande demais para verificar       |
| `redirect`      | `nao_verificado`  | redirect inválido/em excesso               |
| `tipo_bloqueado`| `reprovado`       | tipo de arquivo bloqueado                  |

`validar_muitos(itens, workers≤6)` valida em paralelo preservando a ordem;
`resumo_vereditos` conta por veredito (para relatórios/progresso).

### Sem download duplicado

`avaliar_pagina(pagina, url, consulta, esperado, http, ctype, bytes)` avalia
uma página **já baixada** com as mesmas regras — usado por `shopping.py`
para não baixar de novo, e por testes sem rede.

## 3. Sinais: produto × listagem × anúncio (`classificar_sinais`)

Pontuação determinística com **evidências listadas** (nada de heurística
caixa-preta):

**Pró-produto**: JSON-LD `Product` (+3), JSON-LD `Offer/AggregateOffer` (+1),
`og:type=product` (+2), meta de preço `product:price:amount` etc. (+2), URL
com caminho de produto (`/produto/`, `/dp/`, `/item/`...) (+1), verbo de
compra na página ("adicionar ao carrinho", "comprar agora") (+1), preço único
visível (+1).

**Pró-listagem**: URL de busca/categoria (`/busca/`, `/categoria/`,
`/resultados/`...) (+3), texto de listagem ("resultados para", "ordenar
por", "N produtos encontrados") (+2), mais de 6 preços na página (+2),
título de listagem (+2).

Decisão: `eh_produto` só com **≥3 pontos de produto, mais pontos que
listagem e algum dado estruturado real** (JSON-LD/og:type/preço em meta).
`eh_listagem` com ≥3 pontos de listagem. Indícios de anúncio/classificado
são registrados à parte (`anuncio`), sem gravidade automática.

## 4. Verificação de imagem (`validar_imagem`)

- Baixa a imagem (teto 2,5 MB) e detecta o **formato real pela assinatura
  binária** (PNG, JPEG, GIF, WEBP, BMP, SVG) — content-type sozinho não basta.
- Dimensões lidas do próprio arquivo: PNG (IHDR), GIF, JPEG (SOF), WEBP
  (VP8/VP8L/VP8X), BMP. Sem PIL.
- Vereditos: `< 16 px` → reprovado (rastreador/ícone); `< 64 px` → parcial
  (pequena para card); sem dimensões → parcial; senão `verificado`.
- Conteúdo que não é imagem → reprovado (`nao_e_imagem`).

## 5. Integração no shopping

- `montar_produto` carrega os campos de verificação no produto:
  `link_veredito`, `link_codigo`, `link_motivo`, `item_de_listagem`,
  `url_item` (link do **item**, não da página analisada) e `imagem_veredito`.
- **Página de listagem/categoria**: nenhum item vira card — exceto quando o
  JSON-LD do item traz a URL da própria página; nesse caso entra marcado
  `item_de_listagem=True` e link `nao_verificado` (a página do item não foi
  aberta), nunca "verificado".
- **Alternativas**: produto fora do pedido só vira alternativa se estiver a
  **≤ 25% acima do teto** e com **diferenças explícitas** (`diferencas`):
  preço % acima, RAM física/virtual, armazenamento, condição usado/novo.
  O resto vai para `excluidos` com motivo.
- **Imagens**: `verificar_imagens` valida até 3 por busca (3 workers).
  Reprovada → a imagem é limpa (o card mostra "sem foto" em vez de imagem
  quebrada); não verificada → mantida, com registro no campo.
- **Resumo**: `resultado["verificacao"]` = contagem de vereditos de links e
  imagens dos produtos + alternativas exibidos.

## 6. Apresentação honesta no JDUI

- `jdui.py` valida os campos na whitelist (`VEREDITOS_LINK`; inválidos →
  `""`); `public/jdui.js` espelha a validação (paridade garantida por teste
  com node harness).
- Selo no card (`productSelo`):

| Situação                              | Selo exibido                          |
|---------------------------------------|---------------------------------------|
| `verificado`                          | ✓ Link verificado                     |
| `parcial`                             | Verificação parcial                   |
| `reprovado`                           | Link reprovado                        |
| `nao_verificado`                      | Link não verificado                   |
| `item_de_listagem` (qualquer veredito)| Link de listagem (item não aberto)    |

- O motivo do veredito vai no `title` do selo (tooltip) — não desaparece.
- CTA do card: `Abrir oferta ↗` normalmente; **`Abrir link ↗`** quando o link
  foi reprovado (muda o rótulo porque "oferta" seria mentira).
- `resumo_texto` marca no chat "· _link não verificado_" quando aplicável.

## 7. O que a validação nunca faz

- Nunca contorna CAPTCHA/bot-wall/403 (bloqueado → `nao_verificado`, segue
  a vida; sem truques de UA/referer).
- Nunca aprova página de busca/categoria como produto.
- Nunca aceita imagem por "aparência de URL" (só pelo conteúdo real).
- Nunca inventa título, preço, dimensão, disponibilidade.
- Nunca transforma falha de rede em "ok" — `nao_verificado` fica registrado
  até ser verificado de verdade.

## 8. Testes

- `tests/test_source_check.py` (17): SSRF, 404 vs bloqueado, listagem ×
  produto, formatos reais de imagem, dimensões, JSON, domínio errado,
  correspondência, resumo de vereditos, `validar_muitos` em ordem.
- `tests/test_shopping_v55.py` (15): item de listagem com/sem URL do item,
  alternativas com `diferencas`, imagem reprovada limpa o card, resumo de
  verificação, fences JDUI.
- `tests/test_jdui_v55.py` (5): whitelist Python/JS em paridade, selo
  renderizado no node harness, CTA para link reprovado.

Fatos reais observados ao vivo (17/10/2026, sem bypass): Kabum responde
normalmente e o Bing descobre páginas de produto dela; Mercado Livre API
respondeu 403 no período; DDG responde CAPTCHA. Todos esses casos caem nos
vereditos acima — nenhum vira "verificado" por engano.
