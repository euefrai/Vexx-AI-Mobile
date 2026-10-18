# V5.7 — Pesquisa: Precisão e Resultados Inteligentes — Progresso e contexto

Objetivo: elevar a qualidade real das pesquisas (precisão, cobertura, links
exatos, imagens corretas, interpretação de conteúdo, respostas visuais),
reutilizando Search Orchestrator V5.5, Research Agents, Evidence Graph,
Shopping, Intent Engine, JDUI, memória, SSE e Document Intelligence.
Sem deploy/push, sem mudar identidade/modelo/credenciais do Lucas, sem tocar
na extensão da Júlia ou no Fajulto Studio, sem contornar CAPTCHA/bot-wall,
sem GitHub Intelligence, sem inventar fontes/preços/imagens/testes.

## FASE 1 — Auditoria real (concluída)

Estado de partida: `HEAD 4854496` (V5.6), árvore limpa exceto
`qa-artifacts/followups/failure.png` (staged pelo usuário; intocado).
Baseline da área de pesquisa: `266 passed, 4 skipped` (subconjunto
search/research/shopping/source/web/intent/evidence/structured/academic/units);
baseline completo V5.6: 670 passed, 4 skipped.

Método: leitura de código (subagente de exploração com linha exata) + sondas
reais de rede executadas contra os módulos (`search_orchestrator`,
`search_providers`, `shopping`, `source_check`, `research`) com orçamentos
curtos. Nada foi alterado antes das reproduções.

### Problemas reproduzidos (com evidência)

| # | Problema | Evidência real | Causa raiz |
|---|---|---|---|
| P1 | Consulta em forma de pergunta recebe lixo lexical e é declarada "ok" | `pesquisar('como funciona o freio ABS')` → 6/6 resultados de dicionário sobre a palavra "funciona"; `correspondencia 0.333`; `estado ok`; `consultados: bing` — Wikipedia (escolhida) nunca consultada; `pesquisa_rapida` entregava 3 páginas de dicionário como "fontes lidas e utilizáveis" | `_ESTOPO` sem verbos de pergunta ("funciona" contava como termo de correspondência); `_util_para_pedido` aprova por qualquer termo; early-stop após o 1º provedor; recuperação enxuta só disparava com `correspondencia ≤ 0.15` |
| P2 | Shopping pode misturar variantes e expor página de loja como "produto" | `buscar_web_v55('notebook lenovo ideapad 3i 8gb 512gb')` → Magalu/Casas Bahia/KaBuM **categorias** + "Gemini Notebook" (rel. 10.3); em `shopping.pesquisar`, `criterios.marcas=['lenovo']` mas produtos Asus Vivobook e Dell Alienware aparecem; `marca` extraída como "KaBuM!" | Filtro por marca não descarta marca desconhecida/errada; relevância de índice geral fraca; card JDUI tem fallback para a URL da página analisada (`shopping.py:1292-1293`/`1372`, `jdui.js:1998-2001`) — `url_item` só quando existe |
| P3 | ~~Mojibake nos títulos do Bing~~ **descartado** | `repr`/`unicode_escape` mostram `\xe7\xe3` íntegros e nenhum `U+FFFD`; o "�" era só o console do Windows | Artefato da auditoria, não do produto |
| P4 | Bloqueios de loja confirmados | MLB API → `ResearchErro 403`; Magalu → 403 bot-wall; KaBuM listagem → `reprovado/sem_sinais_produto`; Wikipedia ABS → `parcial` (termos) | Esperado/sem bypass; validação honesta funcionando |
| P5 | Sinônimos pt-PT × pt-BR derrubam veredito | `validar_link(pt.wikipedia.org/wiki/Freio_ABS, termos=['ABS','freio'])` → `parcial: não menciona "freio"` (artigo usa "travagem") | Checagem de termos por substring, sem equivalência de variante |
| P6 | Erro interno mascarado como indisponibilidade | chamada com assinatura errada (sonda) → `erro: provedor_indisponivel`, `etapas: ["busca indisponível (TypeError)"]` | `except Exception` genérico vira `codigo` igual a provedor; melhoria de honestidade (baixo impacto) |

### Também confirmado no código (subagente de exploração)

- `anexar_fontes` decide por substring `"Fontes:" not in texto`
  (`pc_agent.py:2046-2050`) → risco de duplicar ou omitir o bloco.
- `run_reuso` de "essas fontes" não confere o tópico da run anterior
  (`pc_agent.py:1977-1986`).
- `imagem_veredito` chega ao JDUI (`jdui.js:334`) mas não é renderizado no
  card (`jdui.js:1979-2014`).
- `source_check` só é consumido pelo shopping; a pesquisa geral não gera
  veredito de link/imagem.
- SSE de pesquisa corta em 360 s (`server.py:1927-1929`) vs. modo
  investigativa 300 s + replan.
- Autolink imprime URL crua (`app.js:413-419`).

## FASE 2 — Search Orchestrator 4.0 (concluída — incrementos 1–6)

### Incremento 1 — reformulação de pergunta e correspondência honesta (concluído)

Mudanças em `search_orchestrator.py`:

1. `_ESTOPO` ganhou verbos/funcionais de pergunta ("funciona", "faz", "serve",
   "significa", "existe", "foi", "era"…) — não provam correspondência temática.
2. `consulta_conteudo()` (nova): remove apenas a moldura de pergunta
   ("como funciona", "o que é", "quanto custa"…) e artigos iniciais; devolve
   `""` quando não sobra termo distintivo — nunca inventa consulta.
3. `pesquisar()`: quando um provedor devolve resultados sem correspondência
   (ou vazio), tenta **a mesma fonte** uma vez com a consulta reformulada
   antes de trocar de provedor (etapa registrada: `nome (consulta reformulada '…')`).
4. `pesquisar()`: consulta enxuta passa a ser declarada também com
   `correspondencia < 0.5` (antes só `≤ 0.15`).
5. `pesquisar_com_recuperacao()`: `correspondencia < 0.5` também dispara a
   rodada de recuperação (investigar em vez de fingir ok).

Testes: `tests/test_search_orchestrator_v57.py` (7 casos, sem rede) cobrindo
stopword de pergunta, reformulação conservadora, retry na mesma fonte,
provedor vazio reformulado, enxuta declarada e recuperação melhorando
correspondência fraca. Suíte focada da área: verde (ver seção de evidências).

Prova antes/depois (rede real, 2026-10-17):

- Antes: `pesquisar_com_recuperacao('como funciona o freio ABS')` →
  `correspondencia 0.333`, `estado ok`, top-8 = dicionários de "funciona";
  `etapas: ["bing: 6 resultados (como funciona o freio ABS)"]`.
- Depois: `correspondencia 1.0`, `estado ok`, topo = Moura (sistema de freios),
  Kalatec, **Wikipédia — Freio**, Dicio/Freio, Justos; lixo antigo rebaixado
  ao fim (nunca apagado); `etapas` inclui
  `bing (consulta reformulada 'freio ABS'): 6 resultados`.

Contratos preservados: consulta original continua a primeira tentativa;
nenhum resultado é apagado (apenas rebaixado/descartado por dedupe);
`variantes` não mudou; estados continuam no vocabulário V5.5.

### Incremento 2 — duplicatas e republicações (concluído)

`deduplicar()` agora, além da URL canônica, sinaliza **republicações**:
título praticamente idêntico (Jaccard ≥ 0.9, ≥ 4 termos) entre URLs
distintas → a versão posterior vira descarte com motivo
(`republicação de <url>`) e a mantida ganha `republicacoes: [urls]`.
Títulos curtos (< 4 termos) nunca entram na regra. Nada é apagado:
tudo fica em `descartes` com a origem (base para o Evidence Graph).
Testes: 2 casos novos em `tests/test_search_orchestrator_v57.py`.

### Incremento 3 — conteúdo desatualizado em consultas temporais (concluído)

Quando a consulta tem recorte temporal (ano explícito, ex.: "eleições 2026",
ou classe temporal do intent), cada item com **ano conhecido** ganha
`ano` + `desatualizado`; a regra é a **única** do `evidence_graph`
(`fonte_desatualizada`: ano ≤ alvo−2, **sem data conhecida NÃO acusa**) e o
item velho é apenas rebaixado (penalidade ≤ 4.5), nunca apagado. O relatório
da busca ganha `temporal` e `desatualizados: [urls]`; a rodada de
recuperação preserva o recorte temporal no re-rank. Consulta sem recorte
temporal não muda nada.

Testes: 3 casos novos (sinalização + ordem, sem data não acusa, consulta
sem recorte não marca). Benchmark ganhou o grupo `desatualizado` (2 casos).

### Incremento 4 — erro interno nunca mascarado (P6, concluído)

`pesquisa_rapida` rotulava qualquer exceção da busca como
`erro: provedor_indisponivel` — um bug interno (ex.: `TypeError`) parecia
problema de provedor. Agora: exceção com `codigo` (provedor/rede) continua
`provedor_indisponivel`; exceção sem `codigo` vira `erro_interno` com a
causa real na etapa (`erro interno na busca (TypeError)`). Estado segue
`indisponivel` (a busca realmente não aconteceu).

Testes: `tests/test_research_v57.py` (3 casos).

### Incremento 5 — parada por ganho real de informação (concluído)

Critério de parada novo, baseado em **informação nova** (domínio novo e/ou
tema do pedido coberto a mais), não em quantidade:

1. Na cadeia de consultas do `pesquisar`: se a consulta anterior não trouxe
   domínio nem tema novo e já há resultado útil, a próxima consulta **não
   roda** — etapa `parada por ganho zero: consulta anterior sem domínio nem
   tema novo` (orçamento não é gasto à toa).
2. Na recuperação (`pesquisar_com_recuperacao`): o ganho da rodada extra é
   medido e declarado em `ganho_informacao`
   (`dominios_novos`/`temas_novos`/`ganho_real`) + etapa
   `recuperação com ganho novo: …` ou `recuperação sem ganho novo: …` —
   nunca fingir melhora só porque a rodada rodou.

Nada é apagado; junk continua em `achados`. Consultas com 1 única rodada
(ou sem repetição de domínio/tema) mantêm o comportamento anterior.

Testes: 4 casos novos em `tests/test_search_orchestrator_v57.py`; benchmark
ganhou o grupo `ganho` (2 casos).

### Incremento 6 — índice geral reclassificado + recuperação dirigida (concluído)

Último item declarado da FASE 2. Detecção conservadora de página de
índice/listagem (`_pagina_de_indice`): título ("Resultados para…",
"Índice de…", "Busca…", "Category/Categoria:") ou caminho
(`/search`, `/busca`, `/resultados`, `/categoria|category`, `/tag(s)`,
`/indice|índice`, `/directory`). Regras:

1. A página de índice é **sinalizada** (`pagina_de_indice`) e **demovida**
   (−2; termos ecoados na querystring não valem ponto de conteúdo) —
   nunca apagada; resultado expõe `indice_geral: [urls]`.
2. Se a rodada inteira (topo) for só índices: etapa honesta "1ª rodada só
   com páginas de índice geral (N sinalizada(s)); fontes primárias não
   alcançadas", lacuna correspondente e a recuperação pede o assunto
   direto (enxuta) — fontes primárias continuam vindo primeiro pela
   cadeia congelada de provedores por classe (sem reordenação).

Testes: 2 casos novos; benchmark ganhou o grupo `indice` (3 casos).

## FASE 3 — Providers & Retrieval Reliability (concluída; pendências declaradas)

### Auditoria e baseline (2026-10-18)

- HEAD `b51a823`, árvore limpa; suíte 712 passed / 4 skipped; benchmark
  congelado 34/34. Baseline re-verificado por subconjunto (search/providers:
  52 passed).
- Mapa dos módulos: `search_providers.py` (11 provedores oficiais/keyless +
  dispatcher `buscar` + `disponiveis` + `diagnosticar`), `research.py`
  (HTTP/SSRF `baixar`, DDG HTML/Lite, circuito 300 s, `registrar_status`/
  `status_provedor`, cache TTL, `buscar_web_v55`), `search_orchestrator.py`
  (cadeia por classe, ranking, recuperação), `web_extract.py` (artigo,
  metadados, JSON-LD, canônica, links, tabelas + gates opcionais
  trafilatura/extruct), `source_check.py` (vereditos de página/imagem/loja),
  `academic_research.py` (OpenAlex + Crossref, `_RateGate`, retry 429 com
  backoff), `research_agents.py` (ProvedorDDG, ProvedorSearXNG via
  `JULIA_SEARXNG_URL`, cadeia legada ddg → searxng → wikipedia [→ academic]).
- **Já existente e verificado no código** (não recriar): fallback entre
  provedores; circuito por provedor (5 min, `research._circuito`); retry de
  consulta reformulada; cache de páginas com TTL; dedupe canônico +
  republicações; registro de status por provedor; classificação de erros
  (`rede`/`bloqueado`/`http`/`formato`/`tipo`/`tamanho`/`vazio`); SearXNG
  opcional (sem instância autorizada aqui → indisponível declarado);
  OpenAlex/Crossref no caminho acadêmico (nunca como oferta comercial).
- **Lacunas reais identificadas (incrementos desta fase)**:
  1. Métricas cumulativas por provedor (hoje só último status + contagem
     da rodada) — chamadas/ok/vazio/erros por código/latência.
  2. Cobertura de testes de classificação HTTP (202/403/429/5xx/timeout/
     página vazia) no caminho de provedores.
  3. Extração web: **imagens referenciadas** não são extraídas (nem
     jsonld/og/img) — campo inexistente em `web_extract`.
  4. Descoberta de fonte primária (fabricante vs loja; estudo original vs
     notícia; produto vs categoria) — parcial (shopping já prefere
     `url_item` e sela listagem); falta sinal para busca geral.
  5. E2E externo de provedores re-sondado + métricas antes/depois.

### Incremento 1 — métricas por provedor + classificação HTTP (concluído)

- `search_providers.py`: métricas cumulativas por provedor no dispatcher
  `buscar` (`_METRICAS`): chamadas, ok, vazio, resultados, erros por código
  e latência média; acessores `metricas()`/`_reset_metricas()` (aditivo, não
  muda `buscar`/`diagnosticar`).
- `_traduzir`: classificação ampliada (OSError/TimeoutError/ConnectionError
  → `rede`) sem alterar códigos existentes.
- Testes: `tests/test_providers_v57.py` — métricas (ok/vazio/erro/latência),
  classificação HTTP 403/429 → `bloqueado`, 5xx → `http`, timeout → `rede`,
  202 com corpo vazio → resposta vazia honesta, provedor desconhecido.

### Incremento 2 — imagens referenciadas na extração (concluído)

- `web_extract.py`: `extrair_imagens()` — JSON-LD (`image`/`imageObject`),
  `og:image`/`twitter:image` e `<img src>` (absolutizadas, sem `data:`,
  dedup, teto); `extrair_pagina()` passa a expor `imagens: [urls]`
  (aditivo).
- Testes: `tests/test_web_extract_v57.py` — og, jsonld, img relativo,
  dedup e rejeição de `data:`.

### Incremento 3 — origem declarada pela página (concluído)

- `research._fonte_de`: nova marca `origem_declarada` — quando o
  `rel=canonical` da página lida aponta para **outro domínio** (agregador/
  cópia declara o original). Vem da própria página: declarado, nunca
  verificado e nunca usado para trocar o link; mesma origem/subdomínio não
  gera marca.
- `research.bloco_grounding`: com a marca, a fonte ganha no bloco do Lucas
  "página declara a origem em X" (evidência, não promoção).
- `source_check.avaliar_pagina`: mesmo sinal no veredito (`origem_declarada`),
  aditivo e só quando divergente.
- Testes: `tests/test_fontes_origem_v57.py` — canônica externa marca;
  mesmo domínio/subdomínio/vazio silencia; usa a URL final da recuperação;
  marca no grounding; veredito com e sem divergência.

### Incremento 4 — origem declarada exibida na JDUI (concluído)

- Fluxo completo: fonte da pesquisa → `research_agents.registrar_evidencia`
  (já guardava a fonte inteira em `original`; leitura agora inclui
  `origem_declarada`) → `pc_agent.fence_de_fontes` passa o campo (≤120) →
  validadores `jdui.py` e `public/jdui.js` (paridade) → cartão de fontes
  mostra "original declarado: X" na mesma linha de domínio/data, sem
  componente novo e sem CSS novo.
- Testes: `tests/test_jdui_fontes_v57.py` — schema aceita/limita/normaliza
  vazio; fence end-to-end com e sem a marca; harness Node valida schema e
  render no `jdui.js` (4 casos).

### Incremento 5 — métricas na medição contínua (concluído)

- `search_providers.diagnosticar()`: cada linha ganha `metricas` do
  provedor (chamadas/ok/vazio/erros/latência média até o momento da sonda).
- `research.metricas_provedores()` (novo): junta o acumulado do dispatcher
  ao último `registrar_status` por provedor — leitura pura para relatórios,
  sem I/O e sem mudar a busca. Persistência entre reinícios fica declarada
  como fora de escopo (memória do processo; sem novo dashboard).
- Testes: 2 casos em `tests/test_providers_v57.py` (sonda com métricas;
  junção métricas+último status).

### Incremento 6 — republicação: base mais antiga com data declarada (concluído)

- `search_orchestrator.deduplicar`: quando as duas versões do mesmo título
  declaram data (pubDate/ISO em `data` ou `meta.publicado_em`), a **mais
  antiga** fica como base e a outra vira republicação registrada — resolve
  o "primeiro visto vence" que contrariava o próprio docstring. Sem data
  conhecida, ou em empate, mantém a ordem de chegada (contrato preservado);
  nada é apagado (descarte com motivo + `republicacoes`).
- Testes: 2 casos novos (troca pela mais antiga com datas; sem data/empate
  mantém o primeiro visto). Benchmark congelado segue 34/34.

### Sonda E2E real de provedores (2026-10-18)

Artefato: `qa-artifacts/v57/fase3-provedores-2026-10-18.json`.
Método: `sp.diagnosticar("freio abs", timeout=8)` + `research.buscar_ddg`
(ddg e ddg-lite) + `OpenAlexWorksProvider` / `CrossrefWorksProvider`
(rede real, fontes permitidas, sem bypass).

| Provedor | Estado | Resultados |
|---|---|---|
| bing | ok | 2 |
| stackexchange | ok | 1 |
| worldbank | ok | 2 |
| wikipedia | ok | 2 |
| openlibrary | ok | 2 |
| commons | ok | 2 |
| pubmed / bing-news / hn / marginalia / bcb | vazio (responderam; nada utilizável para a consulta) | 0 |
| ddg / ddg-lite | rede (URLError neste host) | — |
| openalex (acadêmico) | ok | 2 |
| crossref (acadêmico) | ok | 2 |

Métricas reais do dispatcher: 11 chamadas, 6 ok, 5 vazio, nenhum bloqueio;
latências 0,0–1033 ms. "Vazio" = o provedor respondeu e não trouxe resultado
utilizável — não é sucesso, e permanece registrado assim.

### Status das lacunas da auditoria

1. Métricas por provedor — **resolvido** (incremento 1).
2. Testes HTTP 202/403/429/5xx/timeout/vazio — **resolvido** (incremento 1).
3. Imagens referenciadas — **resolvido** (incremento 2).
4. Fonte primária — **resolvido no que tem evidência real**: sinal de origem
   declarada (incremento 3) agora exibido na JDUI (incremento 4),
   republicação mantendo a base mais antiga quando há data declarada
   (incremento 6) e preferência por página de produto da FASE 4; sem
   reordenação da cadeia congelada. Fica pendente declarado o caso "notícia
   que só cita um estudo publicado em outro lugar" (títulos diferentes —
   exigiria leitura cruzada de páginas, sem base de teste congelada).
5. E2E externo — **resolvido** (tabela acima). "Antes/depois" de latência
   não é atribuível a estes incrementos (camadas passivas: métricas e
   campos aditivos); a mudança de comportamento continua coberta pelo
   benchmark congelado 34/34. Medição contínua agora legível em
   `diagnosticar()`/`metricas_provedores()` (memória do processo).

## FASE 4 (V5.7) — Product Research Accuracy — em andamento

Missão: precisão da pesquisa de produtos (identidade, URLs, preços, imagens,
ofertas, filtros, evidências e JDUI). Sem novos provedores, sem serviços
externos, sem redesign; contratos congelados preservados; nunca inventar
preço/disponibilidade/imagem/evidência.

### Etapa 1 — auditoria + incidente reportado pelo usuário (imagem placeholder)

Confirmado em produção (prints do usuário): resposta com duas imagens
`loremflickr.com` quebradas → chip "🖼️ imagem indisponível — abrir link"
piscando (a repintura do streaming recria o HTML a cada chunk) e pulando o
scroll do chat.

Causa (dupla):

1. `pc_agent.py` — a diretiva de `intencao_imagem` mandava o modelo "colar o
   comando de imagem" com URL placeholder, e `anexar_fontes` inseria a imagem
   fake no texto quando o modelo não a incluía.
2. `public/app.js` — `renderMarkdown` renderizava a URL loremflickr como
   `<img>`; quando falhava, `imagemChatFalhou` trocava por chip com link +
   botão de retry (alimentando um novo ciclo de render).

Correção (nunca placeholder em nenhuma camada):

- `pc_agent.py`: diretiva de imagem agora é honesta (pede imagem real ou
  admite ausência; proibido placeholder); `_RX_IMG_PLACEHOLDER` remove o
  placeholder se vier do modelo/contexto antigo — e nunca o insere.
- `public/app.js`: `renderMarkdown` ignora imagens `loremflickr.com`
  (inclusive em mensagens antigas já salvas); o botão "imagem não apareceu —
  gerar de novo" e o handler `data-img-retry` foram removidos. O chip
  "imagem indisponível" permanece só para imagens reais que quebrarem.
- Testes: `test_interactive.py` (contrato novo: nunca placeholder) e
  `test_frontend_smoke.py` (`img-loremflickr-removida`) atualizados.
- Suíte completa: 735 passed / 4 skipped (sem regressões).

### Etapa 2 — auditoria da pesquisa comercial (mapa e problemas confirmados)

Pipeline mapeado (sem novos provedores): `extrair_criterios` →
`_consultas_produto` → busca com fallback (MLB → DDG → web) →
`_recuperar_ofertas` (JSON-LD/OG + `source_check`) → `aplicar_filtros` →
`separar_alternativas` → `deduplicar` → `verificar_imagens` → fence JDUI →
`resumo_texto`/`bloco_para_llm`.

Problemas confirmados com evidência objetiva:

1. **A busca descartava a referência pedida.** `_consultas_produto` montava
   só categoria + marcas + specs: "celular galaxy s24 até R$ 3000" virava
   `['celular comprar oferta', 'celular preço até 3000']`; "tênis adidas
   pro model 2.0" virava `['tenis comprar oferta', ...]` — modelo e marca
   caíam fora. Os resultados genéricos dos prints do usuário vêm daí.
2. **Sem checagem de versão/edição.** "iPhone 15 Pro" aceitava o padrão;
   "AirPods Pro" aceitava "AirPods 3"; "Adidas Pro Model" aceitava
   Superstar.
3. **Sem checagem de modelo.** "Galaxy S24" aceitava S23; "iPhone 15"
   aceitava "iPhone 14"; "RTX 4060" aceitava "RTX 3060".
4. **"Pro Max" contaminava o orçamento.** `_extrair_orcamento` casava o
   "max" da edição e transformava o "256GB" seguinte em teto (R$ 256) —
   todo produto real virava "acima do orçamento".
5. **Milhar sem separador era truncado.** "R$ 7000" → 700 (regex exigia
   grupos de milhar com ponto).
6. **Marcas esportivas ausentes da lista** (adidas/nike/mizuno): pedido com
   essas marcas não filtrava outra marca.

### Incremento 1 — identidade do produto + busca com referência (concluído)

`shopping.py`:

- `_tiers_no_texto`/`_tiers_expandidos`: versão/edição (pro, pro max, plus,
  ultra, mini, lite, max). "pro" como contração de "para o" em pt-BR
  ("notebook pro meu filho") NÃO vira versão (guarda de palavras); "no max"
  de orçamento não vira edição.
- `_tokens_modelo`/`_numeros_familia`/`_conflito_modelo`/
  `_modelo_mencionado`: modelo "irmão" com número diferente (s23 ≠ s24,
  rtx3060 ≠ rtx4060) e família divergente (iphone 14 ≠ 15) são rejeitados
  com motivo. Anúncio que NÃO indica o modelo pedido não é promovido a
  correspondência: vira alternativa explícita ("modelo não indicado").
  Sem token no anúncio, nenhum conflito numérico é inventado; anúncio que
  cita o pedido nunca é rejeitado por número extra.
- `aplicar_filtros`: códigos novos `versao_diferente`, `modelo_diferente`,
  `modelo_nao_confirmado`; `separar_alternativas` explica cada um como
  diferença ("versão pro max (pedido: pro)", "modelo s23 (pedido: s24)").
- `_consultas_produto` + `_termo_referencia`: a referência pedida entra nas
  consultas ("Adidas pro model 2.0 comprar oferta"); orçamento não duplica
  ("s24 comprar oferta" + "s24 preço até 3000"); frases de pedido
  (me mostre/preço/imagem/link) e conectivos não poluem a busca; sem
  referência, mantém o formato anterior.
- `_extrair_orcamento`: "pro max" neutralizado; capacidade/medida
  (GB/TB/mAh/Hz/mm/pol) nunca vira teto; "R$ 7000" não é mais truncado.
- `_MARCAS`: + adidas, nike, mizuno.

Avaliação (conjunto comercial NOVO e separado do congelado,
`benchmarks/shopping_v4_v1.json`, só fixtures locais, sem lojas reais):

- **antes** (shopping.py do commit `6c8de06`): 20/39 aprovados (51,3%)
  — conjunto da época; ver Incremento 2 para os totais atuais.
- **depois**: 55/55 (100%) — o nº de subchecagens cresce quando a rejeição
  correta acontece (códigos + diferenças da alternativa).
- Reprodução: `python tools/bench_shopping_v4.py` (não grava por padrão;
  `--salvar` grava artefato). Artefatos:
  `qa-artifacts/v57/bench-shopping-v4-antes.json` e
  `qa-artifacts/v57/bench-shopping-v4-2026-10-18.json`.
- Testes: `tests/test_shopping_fase4.py` (25 casos, inclui controles
  negativos: contração "pro", pedido sem modelo, capacidade ≠ orçamento).
- Benchmark congelado `pesquisa_v57_v1` segue **34/34** (inalterado;
  os casos congelados não passam pela extração nova por contrato).

Pendências declaradas desta etapa: família de GPU cruzada (pedir "rtx 4060"
e aceitar "gtx 1650" não é detectado — sem falso positivo pelo caminho
atual); chips Apple ("M2" × "M3") ficam fora dos tokens (evita colisão com
m²/genérico); "airpods max 3000" é tratado como orçamento (ambíguo por
natureza; documentado).

### Incremento 2 — preço honesto: faixa e múltiplas ofertas (concluído)

Problema confirmado na auditoria: `_ofertas_de` ignorava
`AggregateOffer.lowPrice/highPrice` quando não havia ofertas aninhadas
(o produto ficava sem nenhum preço), e com N ofertas `montar_produto`
adotava a PRIMEIRA — o preço de UMA variante era apresentado como se
fosse o preço único do produto.

Correção (`shopping.py`):

- `_ofertas_de`: `AggregateOffer` sem ofertas aninhadas usa
  `lowPrice`/`highPrice`; o menor vira preço e o teto fica em
  `preco_alto`. Sem números válidos → nenhuma oferta (nunca inventa;
  preço ausente ≠ zero).
- `montar_produto`: com múltiplas ofertas/faixa, expõe o MENOR preço em
  `preco` (filtros e ordenação seguem usando o mínimo) e o texto vira
  "a partir de R$ X" com `preco_a_partir_de: true`; a disponibilidade
  passa a ser a do preço exibido. Oferta única e ofertas de mesmo preço
  permanecem exatas — nenhuma mudança de comportamento nesses casos.
- `deduplicar`: o qualificador acompanha a oferta mais barata.
- Camadas de exibição (resumo, bloco do LLM, fence JDUI) herdam
  `preco_texto` — sem mudança de schema.

Evidência: benchmark comercial ampliado com a seção `precos` (59
verificações no total): **antes** (código de `6c8de06`) 22/43 (51,2%) →
**depois** 59/59 (100%). Testes novos em `tests/test_shopping_fase4.py`
(6 casos, total 31 no arquivo): oferta única exata; múltiplas distintas →
menor + "a partir de"; mesmo preço → exato; lowPrice/highPrice → faixa;
AggregateOffer sem preço não inventa; dedupe mantém o qualificador.
Benchmark congelado `pesquisa_v57_v1` segue **34/34**.

### Incremento 3 — métricas de descarte por código (concluído)

`_resumo_verificacao` agora também reporta `descartes_por_codigo` (por que
cada anúncio foi derrubado sem virar produto nem alternativa: preço,
usado, armazenamento, marca, versão, modelo...) e `alternativas_por_codigo`
(motivo pelo qual cada alternativa "quase passou"). Aditivo e
retrocompatível: chamadas antigas sem as listas continuam devolvendo
apenas `links`/`imagens`; sem dashboard e sem persistência nova — os
números vivem no `resultado` já salvo por consulta. Testes novos em
`tests/test_shopping_fase4.py` (33 no arquivo): contagem por código e
saída antiga intacta.

## FASE 7 — JDUI (incremento 1 concluído)

1. `public/jdui.js` — `productImgSelo`: selo honesto de imagem no card.
   `verificado` não ganha selo; `parcial` → "Imagem não confirmada";
   `nao_verificado` → "Imagem não verificada"; `reprovado` (imagem foi
   removida pelo shopping) → "Sem foto confirmada" com o motivo no
   `title`. Nunca apresentar foto não verificada como confirmada.
2. `public/app.js` — `rotuloUrl`: autolink de texto passa a exibir
   host + caminho curto (ex.: `moura.com.br/blog/sistema-de-freios`) com
   `title` contendo a URL completa; o `href` continua a URL inteira.
   Fim das URLs cruas gigantes quebrando o layout do chat.
3. Verificação: `node --check` nos dois arquivos + suíte JDUI
   (`test_jdui*.py`) 34/34 verde.
4. `pc_agent.anexar_fontes` — o teste por substring `"Fontes:" not in texto`
   foi trocado por `_ja_tem_fontes_markdown`: o bloco estruturado só é
   omitido quando já existe **cabeçalho** "Fontes:" (com ou sem `#`/`**`)
   seguido de linha com link http em até 1500 caracteres. Menção solta à
   palavra no meio da resposta não esconde mais as fontes reais; lista real
   do modelo não é duplicada.
   Testes: `tests/test_pc_agent_fontes_v57.py` (7 casos).

## FASE 4 — Links, produtos e imagens (incremento 1 concluído)

Prioridade da missão ("corrigir links errados e produtos misturados").
Mudanças em `shopping.py`:

1. `aplicar_filtros`: marca pedida agora é critério obrigatório — produto de
   outra marca vira `marca_diferente` (alternativa explícita "outra marca: X,
   pedido: Y"); sem marca confirmável vira `marca_nao_confirmada`. Nunca
   aparece como se fosse o pedido.
2. `separar_alternativas`: os dois códigos de marca entram como alternativa
   com a diferença escrita; nunca escondida.
3. `extrair_criterios`: par "8gb 512gb" (formato típico de anúncio de
   notebook/celular) passa a virar `ram_fisica_gb`/`armazenamento_gb` — só
   nessas categorias e com faixas sãs (RAM 2–64, armazenamento 64–8192).
4. `_marca_conhecida`: marca do anúncio pela primeira ocorrência (marca do
   anúncio, senão nome) — "Dell Alienware … NVIDIA RTX" é Dell, não Nvidia.
5. `_armazenamento_aparente`: maior valor em GB ≥ 64 — "16GB RAM + SSD 512GB"
   não vira "armazenamento 16GB" (era o valor da RAM).

Evidência real (rede, 2026-10-17), pedido "notebook lenovo ideapad 3i 8gb 512gb":

- Antes: produtos = Asus Vivobook + Lenovo IdeaPad Slim 3 + Dell Alienware +
  Lenovo LOQ (marcas misturadas); `criterios.specs` só `flag_novo`.
- Depois: produtos = **Lenovo IdeaPad Slim 3 e Lenovo LOQ** (link `verificado`,
  `url_item`); alternativas = Asus ("outra marca: asus (pedido: lenovo)") e
  Dell ("outra marca: dell"); `specs` = RAM 8GB + armazenamento 512GB.
- Card JDUI já usa `_link_do_produto` (url_item > url_final > url) e carrega
  `link_veredito`/`imagem_veredito`/`item_de_listagem` — coberto por teste.

Limitação honesta documentada: `marca` do anúncio às vezes vem do vendedor
("KaBuM!"); por isso a marca é confirmada também pelo nome do produto, e o
selo de link já distingue verificado / parcial / REPROVADO / não verificado.

Testes novos: `tests/test_shopping_v57.py` (8 casos, sem rede).

## FASE 5 — Leitura e trechos (incremento 1 concluído)

Problema real reproduzido (2026-10-17): em artigos com seção de referências
(pt.wikipedia.org/wiki/Freio_ABS), o `trecho_usado` exibido vinha de
"Consultado em … Cópia arquivada …" — citações mencionam o tema em frases
curtas e ganhavam o ranking de palavras-chave do `melhor_trecho`.

Correção em `web_extract.py`:

1. `_penalidade_citacoes()` (nova): janelas com marcadores de referência
   (consultado em, cópia arquivada, acesso em, ISBN, doi:, `«»`, `↑`)
   perdem pontos no `melhor_trecho` (3 por marcador, teto 30) — referência
   não é conteúdo.
2. Após a correção, a mesma página real passa a entregar trecho do corpo
   ("as rodas estarão travadas. Dessa maneira, o ABS irá reduzir
   significativamente as chances de derrapagem…").

Testes: `tests/test_web_extract_v57.py` (4 casos, sem rede) — trecho não vem
de referências, fallback sem termos, escolha por termo preservada e teto da
penalidade.

## FASE 9 — Benchmark independente (concluído)

`benchmarks/pesquisa_v57_v1.json` (fixtures congeladas, 34 casos) +
`tools/bench_pesquisa_v57.py` (runner determinístico, provedores injetados,
sem rede) + `tests/test_bench_pesquisa_v57.py` (wrapper pytest que exige
aprovação total). Grupos: reformulação (8), termos de correspondência (4),
fluxo junk→reformulação na mesma fonte (1), republicações (2), marca/specs
de shopping (5), specs pareadas (2), links do card (5), conteúdo
desatualizado em consulta temporal (2), ganho real de informação (2),
índice geral (3).

Resultado 2026-10-18 (offline): **34/34, taxa global 1.0** (inclui os grupos
`desatualizado`, 2 casos); artefato
`qa-artifacts/v57/bench-pesquisa-v57-2026-10-18.json` (o de 2026-10-17 fica
como histórico, 27 casos). Sondas reais no mesmo
artefato: `como funciona o freio ABS` → `correspondencia 1.0`, `estado ok`,
top3 = bemotors/deltafiat/karhub (artigos de freio ABS), etapas com
`bing (consulta reformulada 'freio ABS'): 6 resultados`.

Como comparar antes/depois: o baseline "antes" está na FASE 1 acima
(6/6 dicionário, correspondência 0.333) e a reprodução é
`python tools/bench_pesquisa_v57.py --real` no commit anterior vs. atual.

### Próximos incrementos planejados (FASE 2)

Nenhum item da lista declarada restante — todos implementados nos
incrementos 1–6 (reformulação, correspondência, republicações,
desatualizado, P6, parada por ganho, índice geral). Candidato futuro (não
prometido): preferência de fontes primárias por classe além da cadeia
congelada de provedores.

## Evidências (comandos)

- Suíte da área (baseline e regressões): `pytest -q tests` (filtro
  search/research/shopping/source/web/intent/evidence/structured/…).
- Sondas reais usadas na auditoria: scripts temporários em
  `%TEMP%\opencode\v57_probe*.py` (introspecção + rede); páginas do Bing RSS
  salvas em `%TEMP%\opencode\bing2_*.xml` para inspeção.
- Após o incremento 1: `test_search_orchestrator_v57.py` 7/7 verde e
  `pesquisar_com_recuperacao` real com correspondência 1.0 (saída acima).
- FASE 9 (benchmark): `python tools/bench_pesquisa_v57.py` (offline 34/34;
  `--real` acrescenta sondas de rede) e `pytest -q tests/test_bench_pesquisa_v57.py`.
- FASE 5 (trecho): `pytest -q tests/test_web_extract_v57.py` 4/4; prova real
  no mesmo probe da Wikipédia (trecho do corpo do artigo).
- FASE 3 (incrementos 1–6): suíte da área verde — `test_providers_v57.py`
  (métricas + diagnóstico), `test_fontes_origem_v57.py` (origem declarada),
  `test_jdui_fontes_v57.py` (card de fontes; inclui harness Node) e
  `test_search_orchestrator_v57.py` (republicação com/sem data); sonda real
  de provedores em `qa-artifacts/v57/fase3-provedores-2026-10-18.json`;
  suíte completa **735 passed / 4 skipped**; benchmark congelado
  re-verificado offline **34/34**.
