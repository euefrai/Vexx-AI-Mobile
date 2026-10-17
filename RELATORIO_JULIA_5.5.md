# Relatório Júlia V5.5 — Research Intelligence 3.0

Data: 17/10/2026 · Commits locais `b97493e`, `549a34f`, `c050d4d`, `75f5168`,
`79517e1` · **Sem push/deploy**

## Pedido

Evoluir a Júlia (V5.4.3 → V5.5) para que a assistente **pesquise melhor**:
encontre informação real relevante, **verifique fontes/links/imagens**, leia
sites/páginas, investigue alternativas e apresente resultados com qualidade
no JDUI. Prioridade: **corrigir buscas quebradas e links errados primeiro**.
Sem recriar o Research Engine (evoluir os módulos existentes), sem apagar
dados, sem mexer em modelos/identidade Lucas/credenciais, sem tocar na
extensão Júlia nem no Fajulto Studio, sem resultados fictícios e **sem
contornar proteções de sites** (CAPTCHA/bot-wall).

## Entregas

### 1. Núcleo de busca real (commit `b97493e`)

- **`search_providers.py` (novo)**: 11 provedores sem chave, cada um em API
  pública oficial ou feed oficial (Bing RSS, Bing News, Marginalia,
  Wikipédia, Stack Exchange, HN Algolia, PubMed, Open Library, Banco
  Mundial, BCB, Commons). Códigos de erro honestos (`rede`, `bloqueado`,
  `http`, `formato`, `tipo`, `tamanho`, `vazio`, `indisponivel`), teto de
  768 KB, UA identificável, `diagnosticar()` para auditoria.
- **`search_orchestrator.py` (novo)**: classificação determinística do
  assunto (9 classes + produto/comparação/temporal), variantes de consulta
  que **nunca alteram números/orçamento/marcas** (produto não recebe
  expansão), dedupe por URL canônica, ranking por correspondência real,
  detecção de lacunas e recuperação limitada a uma rodada
  (`recuperacao_adiada` quando o tempo acaba). Estados honestos:
  `ok/parcial/sem_resultados/sem_correspondencia/bloqueado/rede/indisponivel`.
- **`web_extract.py` (novo)**: leitura determinística de páginas (mini-DOM
  estilo readability), metadados (OG/JSON-LD), links, tabelas e **trecho
  literal** usado como proveniência. `trafilatura`/`extruct` entram como
  **opcionais** (soft-import), sem dependência obrigatória.
- **`research.py`**: `_buscar_orquestrado` (orçamento rápido: 2 consultas /
  3 provedores / 10 s), diagnóstico por provedor (`status_provedor`) e
  textos de estado da pesquisa.
- **`pc_agent.py`**: liga a busca web por `JULIA_WEB_SEARCH` (padrão `1`).

### 2. Shopping verificado (commit `549a34f`)

- **`source_check.py` (novo)**: verificação de links e imagens com veredito
  honesto (`verificado/parcial/reprovado/nao_verificado`) e motivo
  explícito; SSRF revalidado a cada redirect; sinais determinísticos de
  **produto × listagem** (JSON-LD Product/Offer, og:type, preço em meta,
  verbos de compra vs. URL/texto de busca/categoria, nº de preços);
  formatos reais de imagem por assinatura binária + dimensões (sem PIL).
- **`shopping.py`**: cadeia `mlb → ddg → ddg-lite → web` (a etapa V5.5 roda
  por último e não altera a ordem legada); página de listagem só gera card
  quando o item traz **URL própria** no JSON-LD — e marcado
  `item_de_listagem` com link `nao_verificado`; **alternativas** até +25%
  do teto com **diferenças explícitas** (preço % acima, RAM, armazenamento,
  condição); imagem reprovada é limpa do card; `verificacao` no resultado
  conta vereditos de links **e** imagens.

### 3. Agentes e evidências (commit `c050d4d`)

- **`research_agents.py`**: `ProvedorOrquestrado` ("web") entra por
  **último** na cadeia dos agentes (`provedores_reais(orquestrado=True)` em
  produção); busca vazia com estado `bloqueado/rede/indisponivel` vira erro
  registrado (nunca resultado inventado); `buscar_com_fallback` devolve o
  diagnóstico real (`detalhe`); lacunas de busca viram **novas frentes**
  (busca + leitura + análise, uma única rodada extra); consultas de
  recuperação do orquestrador entram no replanejamento.
- **`evidence_graph.py`**: divergência **converte unidades** (65 W ==
  0,065 kW nunca é divergência falsa; W × kW com valores distintos →
  `valor_divergente` "Mesma dimensão..."); `fonte_desatualizada` (só acusa
  com data conhecida; > 2 anos) aparece como informação na auditoria, sem
  mudar o `ok`.

### 4. Apresentação no JDUI (commit `75f5168`)

- Card de produto ganhou **selo honesto do link**: ✓ Link verificado ·
  Verificação parcial · Link reprovado · Link não verificado · Link de
  listagem (item não aberto) — com o motivo no tooltip.
- CTA vira **"Abrir link ↗"** quando o link foi reprovado ("oferta" seria
  mentira).
- Campos novos na whitelist do `jdui.py` **em paridade** com o validador do
  `public/jdui.js` (teste com node harness real); links longos não estouram
  mais o card (overflow corrigido no `styles.css`).

### 5. Testes congelados + endurecimentos (commit `79517e1`)

- **`tests/test_search_core_v55.py` (22 testes, sem rede)**: parsers dos
  provedores com fixtures congelados, variantes preservando o pedido,
  dedupe canônico, lacunas reais, estados honestos, recuperação (roda uma
  vez / adiada / nunca sem lacuna), `_buscar_orquestrado` e extração de
  página.
- Endurecimentos que os testes revelaram (correções reais, não cosméticas):
  - URL sem `http(s)`/host não é canônica → **não entra** como fonte
    (descarte `url inválida`);
  - `quanto custa …` agora classifica como **pedido de produto/preço**;
  - `até R$ 3000` é **teto de preço, não pedido de data** (não gera mais
    lacuna falsa de "datas").

## Prova executada

- **Suíte completa: `601 passed, 4 skipped`** (~2 min 52 s) com
  `.venv\Scripts\python.exe -m pytest -q tests` — eram 528/4 antes do V5.5;
  **+73 testes novos, nenhum removido**: search core 22, source_check 17,
  shopping 15, research 11, jdui 5, evidence_graph +3.
- `node --check` ok em `public/jdui.js` e `public/app.js`; node harness
  validando o selo/render do card sem "FAIL".
- **Probes ao vivo** (sem bypass, sem mock):
  - "fone bluetooth até R$ 500" → 4 produtos, **todos `verificado`**,
    3 imagens reais verificadas (formato/dimensões), fase "verificando"
    visível no painel.
  - "notebook 16gb ram até R$ 3000" → 7,3 s, 1 alternativa próxima com
    **link verificado** e diferenças explícitas.
- **Auditoria de provedores ao vivo (17/10/2026)**: respondem — Bing HTML +
  RSS, Marginalia, Wikipédia opensearch, Stack Exchange, HN Algolia, PubMed,
  Open Library, Banco Mundial, BCB, Commons. Bloqueados no ambiente — DDG
  (CAPTCHA), Mercado Livre API (403), Mojeek/Brave/Startpage/Yahoo/searx.be,
  Magalu/Casas Bahia/Pichau/Terabyte (403), Amazon BR (503), Semantic
  Scholar (429). Kabum responde e o Bing descobre páginas de produto dela.
  Nenhum bloqueio foi contornado — todos viram estado/veredito honesto.

## Limitações (honestas)

- DDG continua bloqueado (CAPTCHA) no ambiente; a cadeia legada o registra
  como bloqueado e o V5.5 **não depende dele** (Bing/Marginalia carregam a
  busca geral).
- APIs de loja (Mercado Livre) alternam 403/503; quando bloqueiam, o
  resultado vem de outras fontes do orquestrador ou vem vazio com motivo —
  nunca preenchido com suposição.
- `JULIA_SEARXNG_URL` não configurado: `ProvedorSearXNG` responde
  "indisponível" honesto (integração só com instância própria autorizada).
- Sem renderização JavaScript: página que só monta conteúdo via JS é
  marcada `parcial`/`ilegivel`.
- **Crawl4AI não adotado** (exigiria navegador/deps pesadas não
  autorizadas); a extração determinística cobre o caso. `trafilatura`/
  `extruct` são opcionais e não exigidos pelo CI.
- Verificação semântica de afirmações segue **BLOQUEADA** (dependeria de
  LLM); verificação numérica/léxica com unidades é a autoridade.
- Smoke online dos provedores é opcional/separado (rede não é pré-requisito
  do CI). `render.yaml` intocado; nenhum commit foi empurrado.

## Configuração

| Variável                  | Padrão | Efeito |
|---------------------------|--------|--------|
| `JULIA_WEB_SEARCH`        | `1`    | Liga a busca web orquestrada no agente |
| `JULIA_SEARXNG_URL`       | —      | Instância SearXNG própria autorizada |
| `JULIA_ACADEMIC_RESEARCH` | —      | `1` adiciona provedor acadêmico opcional |
| `JULIA_RESEARCH_MAILTO`   | —      | Contato cortês para APIs acadêmicas |

## Documentos

- `docs/JULIA_RESEARCH_INTELLIGENCE_3.md` — arquitetura, contratos,
  orçamentos, env vars, decisões OSS, limitações.
- `docs/JULIA_ADAPTIVE_SEARCH.md` — classificação, variantes, provedores,
  lacunas, recuperação e estados honestos.
- `docs/JULIA_SOURCE_VALIDATION.md` — vereditos de link/imagem, sinais
  produto × listagem, apresentação no JDUI.
- `docs/V5_5_PROGRESS.md` — progresso por fase/commit.
- `docs/JULIA_MOBILE_ROADMAP.md` — seção V5.5 atualizada (3D de
  otimização/integração passa a V5.6+, futuro).

## Próximos passos sugeridos

1. Configurar uma instância SearXNG autorizada (opcional) para diversificar
   a busca geral.
2. Rodar o smoke online separado (marcado `e2e_real`) num momento de rede
   estável, para revalidar os provedores bloqueados no período.
3. Futuro: seguir de V5.6 (otimização/integração 3D) ou aprofundar
   verificação factual quando houver LLM confiável disponível.
