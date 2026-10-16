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
3. **Buscar**: 2 consultas DDG (principal + faixa de preço), até 6 URLs únicas.
   Sem chave, sem loja única.
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
"outras lojas" (reapresenta ofertas). Sem consulta anterior → `None`
(fluxo normal).

## Limites conhecidos

- Provedor DDG pode retornar bot-wall (página sem resultados) em alguns
  ambientes → resposta honesta vazia + E2E real pula com motivo.
- Lojas com CAPTCHA/bloqueio: página ignorada, nunca contornada.
- Imagens: hotlink com `loading=lazy` + `referrerpolicy=no-referrer` +
  fallback "Sem foto"; lightbox local em JS registrado (sem JS do modelo).
