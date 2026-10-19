# VEXX AI V5.7.2 — Progresso por checkpoint (Final Acceptance)

- **Base:** `HEAD 772ec3a` (V5.7 FINAL), árvore limpa no início.
- **Commit de entrega:** `e98d316` (local, sem push/deploy).
- **Data:** 2026-10-19.
- **Regras:** sem push/deploy, sem reiniciar produção, sem credenciais novas,
  sem modelo pago, sem tocar motor 3D/extensão Júlia/Fajulto Studio, sem
  Apify/redes sociais, sem mascarar resultados.
- **Formato:** ANALISAR → REPRODUZIR → CORRIGIR → TESTAR → DOCUMENTAR.
- **Rótulos de evidência:** MOCK · LOCAL REAL · EXTERNO REAL · BLOQUEADO.

## Checkpoint A — Estado, ambiente e escopo

- `git status` inicial: árvore limpa em `772ec3a`.
- Python 3.14.4; `websockets 17.2` (com `websockets.sync.client`) disponível.
- `playwright`, `trafilatura`, `httpx`, `requests` **ausentes** — nenhuma
  dependência nova foi instalada.
- Portas ocupadas no início: 8000 (relay local), 8645 (Hermes), 5173 (dev),
  5000 (produção local em `0.0.0.0`). **Nenhuma delas foi tocada**; todo o E2E
  usou portas livres e SQLite temporário.
- Escopo alterado nesta versão: `shopping.py`, `web_extract.py`, `research.py`,
  `tools/smoke_externo_v57f.py`, 4 testes novos, 2 ferramentas de evidência.
  Sem mudanças em `server.py`, `pc_agent.py`, `public/*`, motor 3D ou extensão.

## Checkpoint B — Preço numérico e filtros

### Causa raiz

1. O parsing de preço usava float e heurística de separador; valores como
   `R$ 2.974,15` podiam virar `2.974` ou `2974.15` de forma inconsistente.
2. O smoke media `res["produtos"][...]["preco_valor"]`, mas o produto interno
   usa a chave `preco`; o card JDUI é que expõe `preco_valor`. A métrica
   `com_preco_numerico` era **falsa negativa**.
3. Sem preço interpretável, o item podia escapar do filtro de orçamento.

### Correção

- `shopping.normalizar_preco` reescrito com `decimal.Decimal`:
  - regra “o último separador é o decimal”;
  - grupos de 3 dígitos são milhar (`2.974` → 2974; `2.974,15` → 2974.15;
    `1,299.00` → 1299.00);
  - `$`/`US$` → moeda `USD`; `R$` → `BRL`; moeda preservada com proveniência;
  - inválido/ambíguo → `None` (nunca “chuta” número).
- Filtros (`aplicar_filtros` + `separar_alternativas`):
  - `≤ R$ 500`, `R$ 1.000–2.000`, `> R$ 3.000` (e teto explícito do pedido);
  - **sem preço** → `preco_nao_confirmado`, fora do conjunto principal e
    devolvido como alternativa explícita;
  - **moeda diferente de BRL** → `moeda_diferente`;
  - variante incompatível não entra no conjunto principal;
  - promocional sem comprovação não é promovido.
- Métrica do smoke corrigida para
  `shopping._jdui_produto(p)["preco_valor"]`.

### Testes e evidência

- `tests/test_precos_filtros_v572.py`: **12/12**.
- Suítes de shopping (`test_shopping*.py`): **182 passed, 2 skipped**.
- Smoke externo real (2026-10-19): **2/2 ofertas com preço numérico**
  (R$ 28,60 e R$ 68,32, KaBuM).
- Smoke integrado: 1 oferta confirmada (R$ 134,29) e exclusões corretas
  (R$ 304,23 — 1% acima do teto; R$ 466,66 — acima).
- Exemplos verificados: `R$ 2.974,15` → `2974.15`; `R$ 110,12` → `110.12`;
  `US$ 99.90` → `99.90` com moeda `USD`; `"Preço não confirmado"` → `None`.

## Checkpoint C — Extração de conteúdo principal

### Causa raiz

- `melhor_bloco` pontuava contêineres por volume total; o `body`/container
  global sempre vencia o artigo, trazendo menu/sidebar junto.
- O texto do bloco incluía boilerplate e perdia marcação inline
  (negrito/itálico/links).
- O título podia ser a “headline-descrição” da Wikipédia, não o título real.

### Correção (sem Trafilatura)

Trafilatura foi avaliada, mas **não está instalada** e não foi adicionada como
dependência. Foi feita uma reescrita determinística no estilo readability:

- `melhor_bloco`: propagação de pontuação `1.0/0.8/0.6`, bônus para
  `article/main/[role=main]`, multiplicador por link-density e penalização
  `body/#root ×0.35`.
- `_texto_bloco`: pula nós de `_IGNORAR` (nav/menu/sidebar/rodapé/etc.).
- `_texto_bloco_inline`: preserva `strong`, `em`, `a` no texto extraído.
- `_titulo_plausivel`: rejeita título que é descrição/headline; usa
  `h1`/`title`/OG de forma conservadora.
- Removidos `_contar_tags`/`_pontuar` (código morto).

### Testes e evidência

- `tests/test_web_extract_v572.py`: **5/5**.
- 59 testes focados de extração/pesquisa: verdes.
- Ao vivo:
  - Wikipédia: título `Fotossíntese – Wikipédia, a enciclopédia livre`,
    `div.mw-parser-output`, 1.200 chars, sem “Menu principal”/“Ir para o
    conteúdo” (smoke integrado).
  - docs.python.org: `5. Data Structures`, 1.200 chars, conteúdo principal.
- Página bloqueada (Magalu) continua classificada como `bloqueado`, sem
  conteúdo inventado.

## Checkpoint D — Latência do shopping (instrumentar antes de otimizar)

Etapas medidas: descoberta/busca, ondas de validação, `_validar_itens_declarados`
e `verificar_imagens`.

| Medição | Resultado |
|---|---|
| Notebook ≤ R$ 3.000 (4 ofertas) | **7,99–8,73 s** (busca ~3,7 s; onda 4,2–5,0 s); 4 ofertas todas > R$ 3.000, excluídas; 0 produtos — honesto |
| Fone ≤ R$ 300 | **10,07 s** (2 ondas; 0 ofertas naquele momento) |
| `_validar_itens_declarados` | **1,04 s / 2 páginas** (paralelo) |
| `verificar_imagens` | **0,42–0,82 s / 2** (paralelo) |
| Smoke externo final | **11,7 s** com 2 ofertas confirmadas |
| Smoke integrado (fone) | **6,17–11,59 s** com 1–2 ofertas |

Nenhuma otimização especulativa foi aplicada: o cache de página não ajuda no
fluxo real e os 41,5 s observados na V5.7 eram variância externa. Nenhuma
verificação foi reduzida; SSRF, limites de download e rate limiting seguem
ativos.

## Checkpoint E — Hermes (descoberta, inferência, streaming, grounding)

Modelo usado: `poolside/laguna-s-2.1:free` (free path, custo 0). Nenhum modelo
pago foi ativado; `JULIA_AI_MODEL`/`JULIA_AI_FALLBACKS` não foram definidos.

| Etapa | Resultado |
|---|---|
| MODEL_DISCOVERY | `/v1/models` 200; **428 modelos**; modelo configurado presente |
| INFERENCE | **5,81 s**; “A capital do Brasil é Brasília.”; custo 0 (`free_path`) |
| STREAMING | **5,51 s**; **38 deltas**; resposta consistente |
| GROUNDED_ANSWER | **27,15 s**; fontes todamateria/brasilescola/biologianet; resposta com equação/cloroplastos; artefato `qa-artifacts/v572/grounded-fotossintese.json` |

### Defeito crítico encontrado e corrigido

A consulta crua (“Explique a fotossíntese e apresente fontes.”) ia ao buscador
com o verbo “explique”, trazendo dicionário da palavra em vez de artigos do
tema. Correção: `research.consulta_de_pesquisa` + `_RX_PEDIDO_PESQUISA`
(pedido fora, tema fica; limpeza conservadora). Teste
`tests/test_consulta_pesquisa_v572.py`: **4 falhas antes → 4/4 depois**.

### Observações honestas

- `max_tokens` muito baixo (~40) em modelo de raciocínio devolve corpo vazio
  (99 reasoning tokens); o app usa 1500 e funciona. Não é defeito do bridge.
- Um **429** externo foi observado às 15:27; o app devolveu erro honesto
  (“Provedor com limite excedido”). Após ~60 s a execução seguinte passou 7/7.
- `/v1/models` 200 não foi confundido com inferência: as quatro etapas foram
  exercitadas separadamente.

## Checkpoint F — Paridade JDUI Python × JS

- Auditoria: o JS já renderizava imagem + selos honestos (`parcial`,
  `não verificada`) e “original declarado: …”; o Python já expunha o mesmo
  contrato (`jdui.py`).
- `tests/test_jdui_visual_v572.py` (render Node + paridade Python): **2/2**.
- `origem_declarada` **nunca** ganha selo de fonte verificada.
- Estilo Minimal Premium preservado; nenhum componente novo.

## Checkpoint G — Chrome real (desktop + mobile emulado)

- Chrome **155.0.8059.82**, via CDP + `websockets` (sem Playwright).
- Stack isolado: `uvicorn server:app` + `pc_agent.py`, SQLite temporário,
  portas livres; Hermes real local; nenhuma porta de produção usada.
- Login pela interface; chat real com streaming:
  **4,04 s / 197 chars** (“Fotossíntese é o processo…”).
- Card JDUI injetado pelo mesmo `/api/sync` do app, com produto **real** da
  KaBuM (fetch + extração): **R$ 110,12**, imagem **verificada**, link
  **parcial**, fonte com **“original declarado: Manual do fabricante”**.
- Desktop 1280×900 (inner 1264): **sem overflow horizontal** (1264/1264).
- Mobile emulado 390×844 (DPR 2, touch): **sem overflow** (390/390).
- Console: 1 erro esperado de **401 antes do login** (checagem de sessão) e
  2 `ERR_ABORTED` de reload; **nenhuma exceção JS**.
- Screenshots: `qa-artifacts/v572/chrome/desktop-chat.png`,
  `desktop-card.png`, `mobile-card.png`; JSON de evidência
  `chrome-e2e-20261019-150401.json`.
- **Isto é emulação de viewport, não teste em Android/iOS físico.**

## Checkpoint H — Smoke integrado e regressão

### Smoke integrado (7/7) — artefato `smoke-integrado-20261019-152951.json`

| Cenário | Rótulo | Resultado |
|---|---|---|
| Produtos (“fone bluetooth até R$ 300”) | EXTERNO REAL | 1 oferta confirmada R$ 134,29; card JDUI válido; alternativas R$ 304,23 (1% acima) e R$ 466,66 excluídas; 11,59 s |
| Pesquisa geral (fotossíntese) | EXTERNO REAL + LLM REAL | 3 fontes lidas (biologianet/brasilescola/todamateria), resposta 1.393 chars, sem tool call; 19,19 s |
| URL direta (Wikipédia) | EXTERNO REAL | título correto, 1.200 chars, sem resíduos de menu; 1,83 s |
| Comparação técnica (docs.python.org) | EXTERNO REAL + LLM REAL | 2 turnos: doc oficial lida (2.212 chars) e comparação listas×tuplas (2.282 chars); 28,01 s |
| Continuação (“agora os mais baratos”) | LOCAL REAL (dados guardados) | ordem R$ 150 → 200 → 300; fence válido; tentativa externa vazia foi honesta; 0,02 s |
| Falha externa | LOCAL REAL + DNS REAL | DNS inválido + provedor indisponível → aviso honesto, sem preço/fence inventados; 0,01 s |
| Entrega no frontend | FRONTEND DELIVERY | Chrome E2E ok (ver Checkpoint G) |

Uma execução anterior (15:27) falhou **apenas** no cenário de pesquisa por um
**429 externo**, registrado honestamente em
`smoke-integrado-20261019-152738.json`; a reexecução passou 7/7.

### Regressão

- Suíte completa: **891 passed, 4 skipped** (102,51 s).
- Benchmarks congelados: **pesquisa 34/34**, **shopping 59/59**.
- Bateria de experiência real: **16/16**.
- Testes novos V5.7.2: **23/23** (12 + 5 + 4 + 2).
- Smoke externo real: **2/2 ofertas confirmadas com preço numérico**, 3/3
  fontes lidas, Wikipédia aberta, Magalu bloqueada honestamente.
- Nenhum teste removido, nenhum skip artificial, fixtures congeladas intactas.

## Checkpoint I — Release readiness

Ver `docs/V5_7_2_RELEASE_CHECKLIST.md`. Resumo: sem mudança de contrato
relay×agente, sem migração de schema, sem dependência nova, sem mudança de
estáticos/SW; publicação e rollback documentados. Nada foi pushado ou
deployado.

## Decisão

**READY_WITH_LIMITATIONS** — código pronto para publicação autorizada, com
limitações ambientais/cobertura declaradas (serviço publicado não testado por
proibição; mobile emulado; provedores externos variáveis; um 429 externo
tratado honestamente). Não há bloqueador de código conhecido.
