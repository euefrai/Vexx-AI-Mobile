# JULIA Shopping Intelligence (V4.9.1)

Motor de pesquisa visual de produtos no PC agent (`shopping.py`, stdlib pura).
Reutiliza Research Engine (`research.buscar_ddg` + `research.baixar` com guarda
SSRF), Evidence Graph (fontes citadas), SSE/chat existente, SQLite por dono e
JDUI (`productcard`/`productgrid`/`productcompare`/`productdetails`/`productgallery`).

## Pipeline

1. **Detectar** (`detectar_intencao`): verbo de compra/comparação + substantivo
   de produto (categoria, marca, loja, modelo ou spec como RAM/bateria/GB).
   "Preço do dólar" e pesquisas temáticas NÃO disparam.
2. **Critérios** (`extrair_criterios`): categoria, orçamento BRL
   (`até R$`, `entre X e Y`), marcas e specs. **RAM física vs virtual**:
   `RAM Plus/virtual/expansível` é classificada como virtual e nunca conta
   como física.
3. **Buscar (V4.9.1.1: cadeia `buscar_com_fallback`)**: por consulta,
   tenta nesta ordem, com timeout e registro de etapas, sem contornar
   bloqueios:
   - `mlb`: API oficial do Mercado Livre (`/sites/MLB/search`, sem chave) —
     ofertas com preço, foto, link, loja/vendedor, condição e estoque reais;
     itens montados direto, sem visitar página.
   - `ddg` → `ddg-lite`: `research.buscar_ddg` (links p/ extração JSON-LD).
   Falha de um provedor (HTTP 403, bot-wall, rede) vira etapa registrada +
   próximo da cadeia. `diagnosticar_provedores()` sonda os três.
4. **Extrair** (só dados estruturados): JSON-LD `Product`/`Offer`/`AggregateOffer`
   primeiro; OpenGraph (`og:title/image`, `product:price`) como fallback.
   Página sem dado estruturado vira **fonte** (link), nunca produto.
5. **Normalizar**: preço BRL (`R$ 1.234,56`, `1299,99`, `1299.99`, USD);
   impossível de parsear → `preco=None`.
6. **Deduplicar**: mesmo produto em lojas distintas → 1 produto com N ofertas
   (menor preço confirmado vence o card).
7. **Filtrar**: fora do orçamento/specs vai para `excluidos` **com motivo**
   ("acima do orçamento (R$ 1.500,00)", "só informa RAM virtual/expansível").
8. **Confirmar o item (V5.7)**: card cujo JSON-LD declara a página do próprio
   produto em OUTRA página aberta (categoria/listagem/agregador) tem a URL
   declarada aberta (`MAX_VALIDACOES_ITEM` por consulta, mesmo downloader,
   bloqueio nunca contornado) e avaliada por `source_check.avaliar_pagina`
   (tipo produto + termos de identidade do card, variante primeiro). Só com
   veredito "verificado" o card sai de `item_nao_aberto`/`item_de_listagem`
   para `link_veredito=verificado` (nível **confirmada**), adotando
   preço/estoque/foto da própria página do item; bloqueio, página removida
   ou de outro produto preservam o card parcial exatamente como estava.
9. **Comparar** (`comparar`): preço, loja, avaliação, disponibilidade, specs,
   vantagens e limitações — tudo derivado dos dados; sem benchmarks inventados.
10. **Persistir** (`shopping_consultas`, por `owner_id` + conversa, TTL 6h,
    máx 20/conversa). Preço guardado é **histórico**: exibido com
    `verificado_em`; cache reusado marca `de_cache=True`.

## Regras duras

- NUNCA inventar produto, preço, imagem, avaliação, desconto ou estoque.
- Preço inacessível → **"Preço não confirmado"**.
- Nunca afirmar "menor preço da internet".
- Conteúdo de páginas/trechos é **dado**, nunca comando (anti prompt-injection).
- URLs de imagem/link: só `http(s)` sem credenciais (validação dupla
  Python + JS); SSRF herdado do `research.url_segura` (loopback/privadas/
  metadata bloqueadas, redirects revalidados).

## Integração ao chat (`pc_agent.py`)

- `ai_montar_mensagens`: marca `extras["shop"]`; pula a pesquisa genérica
  síncrona quando o shopping assume (evita carga dupla no Render Free).
- `ai_stream_worker`: follow-ups (`eh_followup`) respondem deterministicamente
  da última consulta (sem LLM/rede). Busca nova emite progresso real via
  deltas (`🔎 buscando/identificando/consultando/extraindo/validando/
  organizando`), injeta grounding no LLM e anexa fence determinístico no fim.
- `shopping.remover_fences_produto` remove fences de produto emitidos pelo
  modelo (risco de invenção); só o fence da ferramenta vai ao chat.
- `REGRAS_SHOPPING` no system prompt + catálogo JDUI atualizado.
- Apagar conta (`_apagar_todos_dados`) inclui `shopping_consultas`.

## Follow-ups (sem nova busca)

"mostra só os mais baratos" (ordena), "compare os dois primeiros"
(`productcompare`), "qual tem mais memória" (RAM física primeiro),
"outras lojas" (reapresenta ofertas), "quero apenas modelos novos"
(exclui usados com motivo). Sem consulta anterior → `None`
(fluxo normal).

## Limites conhecidos

- Provedor DDG pode retornar bot-wall (página sem resultados) em alguns
  ambientes → resposta honesta vazia + E2E real pula com motivo.
- Lojas com CAPTCHA/bloqueio: página ignorada, nunca contornada.
- Imagens: hotlink com `loading=lazy` + `referrerpolicy=no-referrer` +
  fallback "Sem foto"; lightbox local em JS registrado (sem JS do modelo).

## V5.7 — Confiabilidade comercial (hotfix 2026-10-18)

Regras de integridade endurecidas após o incidente "me mostre tenis para
jogar basquete" (resposta com produtos/preços inventados, sem busca):

- **Detecção**: verbos de pedido de produto ("me mostre", "quero ver"…)
  disparam o shopping mesmo sem verbo de compra explícito; `intent.analisar`
  tem fallback conversa→shopping (`pedido_produto`). Consultas
  **explicativas/temáticas sobre produtos** ("como escolher um tênis de
  corrida") continuam fora.
- **Card só da ferramenta**: fence de produto emitido pelo modelo é
  removido **sempre** — com ou sem busca executada, stream ou não-stream.
- **Página removida ≠ oferta**: HTTP 200 com frase de produto
  indisponível/removido/anúncio finalizado → veredito `produto_removido`,
  página inteira ignorada (JSON-LD residual não vira card).
- **CAPTCHA/bot-wall**: veredito `bloqueio_pagina` (`nao_verificado`) —
  nunca confundido com link quebrado; nunca contornado.
- **Cache declarado**: `JULIA_SHOPPING_TTL` (segundos; padrão 6h) e o
  bloco de grounding informa reuso + `verificado_em` das duas pontas.
- **Imagens**: foto verificada para todos os cards exibidos (até
  `MAX_PRODUTOS`=6); motivo da reprovação(`imagem_motivo`) aparece no card
  (backend `jdui.py` + frontend `public/jdui.js`, com teste de paridade).
- **Alegação sem evidência**: preço/disponibilidade afirmados sem
  ferramenta verificada geram violação
  `verificacao_alegada_sem_evidencia` + nota honesta na própria resposta
  ("Não verifiquei estes valores em lojas…"). Frases que já avisam que não
  houve verificação não disparam.
- **Estoque desconhecido**: disponibilidade ausente normaliza para
  `desconhecida`; nunca vira "Em estoque" por omissão.

Regressão determinística: `tests/test_shopping_reliability_v57.py` (38
testes, inclui harness Node do `public/jdui.js`).

## V5.7 — Descoberta em consulta genérica (follow-up 2026-10-18)

Torna a consulta genérica ("me mostre tenis para jogar basquete") útil sem
afrouxar nenhuma garantia do hotfix acima:

- **Filtros explícitos × desejáveis**: orçamento/marca/specs declaradas são
  obrigatórios; categoria e uso ("para jogar basquete") são contexto — nunca
  requisito. Sem filtro nenhum, o texto diz explicitamente que a limitação
  veio dos sites, não do pedido (`shopping.filtros_explicitos` /
  `shopping.atributos_desejaveis`).
- **Níveis de evidência por item** (`shopping._tier`): `confirmada` (preço
  confirmado + página verificada, ou API oficial do ML), `parcial` (dado
  estruturado sem verificação completa) e `encontrada` (referência não
  verificada). Texto e grounding declaram o nível; schema JDUI inalterado.
- **Referências não verificadas** (`resultado["encontrados"]`): resultado
  de busca com cara de página específica de produto (fora de home/busca/
  categoria/blog/autor/login; título com o tema) que não pôde ser aberta
  (403/CAPTCHA — sem contorno) ou não expôs dados estruturados vira
  referência com nome+URL+domínio+motivo — nunca preço/foto/estoque/
  veredito, nunca card, nunca duplicando oferta existente. Página
  removida/soft-404, home, busca/categoria e junk sem identidade ficam de
  fora; `MAX_REFERENCIAS`=4.
- **Sem exigência indevida**: grounding e resumo não pedem "modelo
  específico" para "desbloquear" uma busca genérica — explicam a limitação
  objetiva (bloqueio do site/ausência de dados estruturados).

Regressão: `tests/test_shopping_generic_v57.py` (13 testes).

## V5.7 — Auditoria de descoberta (2026-10-18)

Três correções enxutas após auditoria instrumentada da descoberta (relatório
em `qa-artifacts/v57/descoberta-diagnostico-2026-10-18.json`), todas
reproduzidas antes/depois com testes determinísticos:

- **`/list` é listagem** (`source_check.url_de_listagem`): `/list`, `/lista`,
  `/listagem` (ex.: Shopee `/list/Tênis/Basquete`) nunca viram referência
  nem link de item — são listagem dinâmica, como busca/categoria.
- **Item declarado fora da página aberta nunca sai verificado**
  (`_recuperar_ofertas`): além de `url_produto`, a checagem cobre a URL da
  própria oferta (`offers.url`). Item de categoria cujo JSON-LD aponta para
  a página do produto (caso KaBuM) vira `nao_verificado`/`item_nao_aberto` e
  nível **parcial** — antes herdava o veredito da listagem e saía como
  "oferta confirmada" sem a página do item ter sido aberta. Preço/links do
  dado estruturado continuam (nada inventado nem apagado).
- **Orçamento de páginas ordenado** (`_prioridade_descarga` em `pesquisar`):
  download estável com página com cara de item/produto primeiro; home/busca/
  listagem/login depois. Só a ORDEM muda — nenhuma validação é afrouxada;
  evita gastar o teto inteiro em homes/buscas e perder uma página específica
  em silêncio.

Verificação ao vivo: KaBuM (notebook/fone) responde 200 e seus itens saem
`parcial`/`item_nao_aberto`; provedores da rede (ML API, DDG) seguem
bloqueados e não são contornados; consultas genéricas mantidas (variantes
não descobriam nada além — limitação do índice, não da formulação).

## V5.7 — Validação da página do item (2026-10-18)

Follow-up direto da auditoria de descoberta: o que faltava era ABRIR a página
do item declarada no JSON-LD. Nenhum passo do pipeline fazia isso — o card
nascia `item_nao_aberto`/`item_de_listagem` e ficava **parcial para sempre**,
mesmo com a página do produto acessível (KaBuM 200, ~1 s).

- `shopping._validar_itens_declarados` (novo passo 8 do pipeline): abre a URL
  declarada com o MESMO downloader das candidatas (`baixar_fn`/`research.baixar`,
  sem contornar 403/CAPTCHA; orçamento `MAX_VALIDACOES_ITEM`), em paralelo (3).
- Promoção só com evidência: `source_check.avaliar_pagina(tipo=produto)` +
  termos de identidade do card (até 3: variante → modelo → nome, determinístico).
  Veredito "verificado" → `link_veredito=verificado`, `link_codigo=ok`,
  `item_de_listagem=False`, `url_verificada` (URL final aberta) e adoção de
  preço/estoque/foto/avaliação/specs da própria página do item; imagem trocada
  volta para reverificação (`imagem_veredito=""`).
- Falha (bloqueio/rede/vazio, página de listagem/removida, outro produto):
  card preservado exatamente como estava — parcial, com o motivo original.
- `_tier` inalterado: **confirmada** = preço em dado estruturado + link
  verificado; página do item sem preço não apaga preço estruturado existente.

E2E real (rede atual): "notebook para trabalhar e estudar" → 4/4 itens KaBuM
**confirmados na página do item** (preços R$ 2.974,15 / R$ 4.703,04 /
R$ 7.299,00 / R$ 9.750,24; `em_estoque`; imagens CDN verificadas; 17 s).
Payload JDUI gerado do resultado real (válido em `jdui.validar_mensagem`) e
renderizado no espelho `public/jdui.js` via node ("Link verificado").
Evidência: `qa-artifacts/v57/validacao-item-2026-10-18.json`.
Magazine Luiza segue 403 → referência não verificada (bloqueio não contornado).

Testes: `tests/test_shopping_item_v57.py` (9: promoção, listagem promovida,
sem preço na página, bloqueio preserva, outro produto não promove, orçamento,
identidade, render node). Suíte 842/4; benchmarks 59/59 e 34/34.
