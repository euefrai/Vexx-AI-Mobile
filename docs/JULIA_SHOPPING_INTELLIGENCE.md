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
8. **Comparar** (`comparar`): preço, loja, avaliação, disponibilidade, specs,
   vantagens e limitações — tudo derivado dos dados; sem benchmarks inventados.
9. **Persistir** (`shopping_consultas`, por `owner_id` + conversa, TTL 6h,
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
