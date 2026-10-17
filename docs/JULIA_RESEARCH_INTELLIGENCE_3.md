# Júlia — Research Intelligence 3.0 (V5.5)

Data: 17/10/2026 · Commits locais `b97493e` → `79517e1` (sem push/deploy)

Este documento descreve a evolução **V5.4.3 → V5.5** da camada de pesquisa da
Júlia: a busca deixa de depender de um único provedor frágil (DDG com
bot-wall) e passa a **orquestrar provedores reais de API/feed oficial**, com
estados honestos, verificação de links/imagens e apresentação profissional no
JDUI. Nada foi recriado do zero: os módulos existentes (`research.py`,
`research_agents.py`, `shopping.py`, `evidence_graph.py`, `intent.py`,
`jdui.py`) foram evoluídos com contratos legados preservados.

## Princípios (não negociáveis)

1. **Nunca fingir**: vazio ≠ bloqueado ≠ falha de rede ≠ sem resultados ≠ sem
   correspondência. Cada situação tem código e texto próprios.
2. **Sem bypass**: bot-wall/CAPTCHA/403 nunca é contornado. O provedor é
   marcado `bloqueado` e a busca segue para outro.
3. **Sem invenção**: o que não está no HTML/página recuperada não existe no
   resultado. Preço não confirmado não vira "oferta"; imagem não verificada
   não é promovida a "verificada".
4. **Pedido intacto**: números, orçamento, marcas, modelos e condições do
   pedido jamais mudam em consultas derivadas — só se acrescentam termos.
5. **Orçamento real**: a arquitetura funciona no Render Free (memória/CPU
   limitados) + agente no PC: timeouts curtos, tetos de bytes, cache SQLite
   por dono, recuperação limitada a uma rodada e adiada quando o tempo acaba.

## Arquitetura

```
                    ┌──────────────────────────‑┐
 consulta ────────► │ search_orchestrator.py    │
                    │ classificar → variantes → │
                    │ escolher provedores →     │
                    │ buscar (orçamento) →      │
                    │ dedupe → ranking →        │
                    │ lacunas → recuperação     │
                    └───────┬───────────────────┘
                            │ sp.buscar(nome, ...)
                    ┌───────▼───────────────────┐
                    │ search_providers.py       │
                    │ 11 provedores API/feed    │
                    │ oficial, sem chave        │
                    └───────┬───────────────────┘
                            │ research.baixar (SSRF, teto 768 KB, 3 redirects)
              ┌─────────────▼─────────────┐
              │ research.py                │
              │ _buscar_orquestrado        │
              │ ORCAMENTO_RAPIDA / status  │
              └───────┬───────────┬────────┘
                      │           │
        ┌─────────────▼───┐   ┌───▼────────────────────────┐
        │ web_extract.py   │   │ research_agents.py         │
        │ artigo/meta/     │   │ ProvedorOrquestrado "web"  │
        │ links/tabelas    │   │ lacunas → replanejamento   │
        └─────────────────┘   └────────────────────────────┘
                      │
        ┌─────────────▼────────────┐   ┌────────────────────┐
        │ shopping.py              │   │ evidence_graph.py   │
        │ mlb→ddg→ddg-lite→web     │   │ divergência unificada│
        │ + source_check (link/imagem) │ │ fontes desatualizadas │
        └─────────────┬────────────┘   └────────────────────┘
                      │ cards reais
              ┌───────▼────────────┐
              │ jdui.py + jdui.js  │
              │ selo honesto do    │
              │ link no card       │
              └────────────────────┘
```

## Camadas e contratos

### 1. `search_providers.py` — provedores reais (sem chave)

11 provedores, cada um via **API pública oficial ou feed oficial** (RSS/JSON).
Nenhum scraping agressivo; nenhuma chave; nenhum navegador.

| Provedor     | Fonte oficial                    | Classe(s)                 | Tipo achado    | Peso |
|--------------|----------------------------------|---------------------------|----------------|------|
| bing         | feed RSS `/search?format=rss`    | geral, notícias           | pagina         | 8.0  |
| marginalia   | old-search.marginalia.nu (texto) | geral                     | pagina         | 5.0  |
| wikipedia    | opensearch oficial               | enciclopédia, geral       | enciclopedia   | 7.0  |
| bing-news    | feed RSS `/news/search`          | notícias                  | noticia        | 7.0  |
| stackexchange| API oficial 2.3 (5 sites)        | técnico                   | tecnico        | 8.0  |
| hn           | Algolia (Hacker News)            | técnico, notícias         | tecnico        | 5.5  |
| pubmed       | E-utilities oficial              | saúde, acadêmico          | saude          | 8.0  |
| openlibrary  | API oficial                      | livros                    | livro          | 6.0  |
| worldbank    | API oficial                      | dados                     | dados          | 7.5  |
| bcb          | API SGS (séries oficiais)        | dados                     | dados          | 8.0  |
| commons      | Wikimedia API oficial            | imagens                   | imagem         | 6.0  |

- Contrato de achado: `{titulo, url, trecho, origem, tipo, meta?}`; URL só
  entra se começa com `http`; títulos/trechos limpos e limitados.
- `buscar(nome, consulta, ...)` levanta `ErroProvedor(codigo)` com códigos
  honestos: `rede`, `bloqueado`, `http`, `formato`, `tipo`, `tamanho`,
  `vazio`, `indisponivel`.
- `diagnosticar()` sonda todos os provedores para auditoria/relatório.
- Download delegado a `research.baixar`: disciplina SSRF em cada redirect,
  teto de bytes (`MAX_BYTES = 768 KB`), UA identificável `JuliaResearch/1.0`.

### 2. `search_orchestrator.py` — orquestração

Ver detalhes de comportamento em [JULIA_ADAPTIVE_SEARCH.md](JULIA_ADAPTIVE_SEARCH.md).
Resumo do contrato público:

- `classificar(consulta)` → classes (`geral/tecnico/academico/noticias/
  enciclopedia/dados/imagens/livros/saude`) + `produto`, `comparacao`,
  `temporal`, `tecnica`, `idioma`.
- `variantes(consulta, classes, teto, produto)` → consultas derivadas
  determinísticas (sinônimos, sem acento, expansão de classe) que **nunca**
  alteram números/marcas/orçamento; produto não recebe expansão.
- `termos_para_provedor(consulta, classe)` → ajuste técnico determinístico
  (pt→inglês) para Stack Exchange/HN.
- `canonizar_url(url)` → URL canônica de dedupe sem rastreio; **""** quando
  não é `http(s)` com host (resultado sem URL utilizável não é fonte).
- `deduplicar(achados)` → `(únicos, descartes)`; funde a versão com trecho
  mais rico; motivo explícito nos descartes.
- `ranquear(achados, consulta, classes, info)` → pontuação por termos,
  peso do provedor, tipo e atualidade; páginas dos próprios provedores
  (bing.com, google.com, ...) valem menos.
- `detectar_lacunas(consulta, achados, classes, info)` e
  `_consultas_recuperacao(...)` → o que o pedido exige e as fontes não
  cobrem, com consultas complementares que preservam o pedido.
- `pesquisar(...)` → resultado com `achados`, `etapas`, `estado` +
  `estado_texto`, `provedores {usados, falhas, vazios, consultados}`,
  `classes`, `lacunas`, `consultas`, `recuperacao`, `descartes`,
  `correspondencia`, `segundos`.
- `pesquisar_com_recuperacao(...)` → +1 rodada de recuperação por lacuna,
  **uma única vez**; `limite_primeira` adia quando a 1ª rodada já gastou o
  tempo (`recuperou=false` + `recuperacao_adiada` declarado).

Estados do orquestrador (`CODIGO_TEXTO`): `ok`, `parcial`,
`sem_resultados`, `sem_correspondencia`, `bloqueado`, `rede`, `indisponivel`.

### 3. `web_extract.py` — leitura de páginas

Mini-DOM tolerante + pontuação de blocos por densidade de texto (estilo
readability), remoção de boilerplate (menu/rodapé/anúncio/comentários).
**Stdlib only**; nunca executa JavaScript; nunca segue instruções do conteúdo.

- `extrair_pagina(pagina, url, consulta)` →
  `{titulo, texto, paragrafos, secoes, metadados, links, tabelas,
  trecho_usado, extrator, ilegivel, tamanho_html}`.
- `extrair_metadados` → title/OG/Twitter/JSON-LD (`Article`, `Product`, ...):
  `publicado_em`, `atualizado_em`, `autor`, `site`, `idioma`, `canonica`.
- `extrair_links` (interno/externo, sem javascript/mailto), `extrair_tabelas`.
- `melhor_trecho(texto, consulta)` → trecho **literal** que melhor cobre a
  consulta (proveniência, sem gerar texto).
- `ilegivel(texto)` → heurística de binário/página vazia; nunca inventa.
- Opcionais soft-import: `trafilatura` como extrator principal (marcado em
  `extrator`) e `extruct` para Microdata/RDFa (`extruct` no resultado).
  Sem eles, a extração determinística continua completa.

### 4. `research.py` — entrada do Research Engine

- `_buscar_orquestrado(consulta, max_resultados, timeout, orcamento)` →
  `(achados, info)`; usa `ORCAMENTO_RAPIDA` (`max_consultas=2`,
  `max_provedores=3`, `timeout_total=10 s`, `min_resultados=3`) e
  `LIMITE_RECUPERACAO_S = 8.0` para a recuperação.
- Sincroniza o diagnóstico por provedor (`registrar_status`/`status_provedor`
  com `resultados`, `bloqueado`, `vazio`, `erro`, `em`).
- `ESTADO_TEXTO` da pesquisa: `ok`, `parcial`, `paginas_ilegiveis`,
  `sem_resultados`, `sem_correspondencia`, `bloqueado`, `rede`,
  `indisponivel` — usados nos eventos e na resposta.
- `pesquisa_rapida(...)` continua aceitando `buscar_fn`/`recuperar_fn`
  injetáveis (testes/agentes); sem injeção, usa o orquestrador.
- Cache SQLite por dono (`TTL_RAPIDA = 6 h`, `TTL_PROFUNDA = 24 h`);
  `MAX_REDIRECTS = 3`; download só-texto com teto.

### 5. `research_agents.py` — agentes de pesquisa

- `ProvedorOrquestrado` (`nome="web"`): busca web multi-provedor para os
  agentes; guarda `.info` (estado honesto, lacunas, recuperação). Vazio com
  estado `bloqueado/rede/indisponivel` vira `ResearchErro` com o mesmo
  código — o orquestrador de agentes registra e alterna.
- `provedores_reais(orquestrado=False)`: ordem legada preservada
  (ddg → searxng → wikipedia [→ academic]); `orquestrado=True` (produção,
  `JULIA_WEB_SEARCH=1`) acrescenta `web` como **último**.
- `buscar_com_fallback`: vazio silencioso também alterna; devolve `detalhe`
  com o `info` real do provedor que atendeu.
- `agente_busca`: grava `usados["recuperacao_busca"]` e
  `usados["lacunas_busca"]` (cap 4) e expõe `estado` nos eventos.
- `replanejar`: lacuna que ainda não é frente do plano cria o triplo
  **busca + ler + analisar** (uma única rodada extra, orçamento original);
  `_lacunas` incorpora as consultas de recuperação do orquestrador.
- Modos (`MODOS`) com orçamento real: `rapida` 2 buscas/3 páginas/30 s,
  `pro` 4/6/60 s, `profunda` 8/12/120 s, `investigativa` 12/20/300 s.

### 6. `shopping.py` + `source_check.py` — produtos verificados

Detalhes em [JULIA_SOURCE_VALIDATION.md](JULIA_SOURCE_VALIDATION.md).

- Cadeia de provedores: `mlb → ddg → ddg-lite → web` (a etapa web V5.5 roda
  por **último** e não altera a ordem legada dos diagnósticos).
- `_recuperar_ofertas` avalia a página com `source_check.avaliar_pagina`
  (sem novo download): produto sem sinais não vira card; item extraído de
  listagem/categoria só entra com URL própria no JSON-LD e fica marcado
  (`item_de_listagem`, link `nao_verificado`).
- `separar_alternativas`: até +25% do teto, cada alternativa com
  `diferencas` explícitas (preço % acima, RAM física/virtual, armazenamento,
  condição usado/novo) e `distancia`; o resto vira descarte com motivo.
- `verificar_imagens`: valida até 3 imagens reais (formato, dimensões,
  tamanho); `reprovado` limpa a imagem (card mostra "sem foto");
  `nao_verificado` mantém com registro.
- `verificacao` no resultado: contagens honestas de vereditos de **links e
  imagens** (`_resumo_verificacao`).

### 7. `evidence_graph.py` — divergências e auditoria

- `_mesma_medida`/`investigar_divergencia`: conversão de unidades via
  `units.py` (65 W == 0,065 kW nunca é "divergência"); W × kW com valores
  distintos → `valor_divergente` ("Mesma dimensão..."); dimensões diferentes
  → `unidade_ou_metrica`; sem dimensão → `inconclusivo`. Nunca fabrica
  reconciliação.
- `fonte_desatualizada(ev, ano_ref=None, idade_max_anos=2)`: só acusa com
  data conhecida e antiga; sem data, não acusa.
- `auditar_resposta` inclui `fontes_desatualizadas` como **informação**
  (não altera `ok`).

### 8. Apresentação no JDUI

- `jdui.py`: `VEREDITOS_LINK`; whitelist do card ganhou `link_veredito`,
  `link_motivo`, `item_de_listagem`, `imagem_veredito` (inválidos → `""`).
- `public/jdui.js`: validador espelho + selo honesto
  (`✓ Link verificado`, `Verificação parcial`, `Link reprovado`,
  `Link não verificado`, `Link de listagem (item não aberto)`) com `title`
  = motivo; CTA vira **"Abrir link ↗"** quando o link foi reprovado.
- `public/styles.css`: quebra de linha longa nos campos de produto
  (`overflow-wrap:anywhere`) — nada estoura o card no mobile.

## Orçamento, cache e limites (Render Free + PC)

| Item                              | Valor                                        |
|-----------------------------------|----------------------------------------------|
| Download por requisição           | 768 KB (`search_providers.MAX_BYTES`)        |
| HTML de extração                  | 2 MB (`web_extract.MAX_HTML`)                |
| Texto extraído                    | 8.000 chars (`TETO_TEXTO`)                    |
| Página na verificação de fonte    | 1,5 MB (`source_check.MAX_BYTES_PAGINA`)     |
| Imagem na verificação             | 2,5 MB (`MAX_BYTES_IMAGEM`)                  |
| Redirects                         | 3 (`research.MAX_REDIRECTS`)                 |
| Busca rápida do orquestrador      | 2 consultas / 3 provedores / 10 s / mín. 3   |
| Recuperação por lacuna            | 1 rodada; adiada se 1ª rodada > 8 s          |
| Cache de pesquisa                 | SQLite por dono: 6 h rápida / 24 h profunda  |
| Cache de shopping                 | 6 h (`TTL_CONSULTA`), 20 consultas/conversa  |
| Imagens validadas por busca       | 3 (em paralelo, 3 workers)                   |

## Variáveis de ambiente

| Variável                  | Padrão | Efeito                                              |
|---------------------------|--------|-----------------------------------------------------|
| `JULIA_WEB_SEARCH`        | `1`    | Liga a busca web orquestrada no agente (pc_agent)   |
| `JULIA_SEARXNG_URL`       | —      | Instância SearXNG **autorizada** própria; sem URL, indisponível (nunca finge) |
| `JULIA_ACADEMIC_RESEARCH` | —      | `1` adiciona provedor acadêmico (OpenAlex/Crossref) |
| `JULIA_RESEARCH_MAILTO`   | —      | Contato do provedor acadêmico (cortesia de API)     |

`render.yaml` não mudou. Nada de chave obrigatória para a busca V5.5.

## Inspiração OSS e decisões (licenças compatíveis)

- **trafilatura** (Apache-2.0): adotado como extrator **opcional** soft-import
  (fallback determinístico mantido). **extruct** (MIT): opcional idem.
- **searxng** (AGPL-3.0): não embutido; integração **apenas** com instância
  própria autorizada via `JULIA_SEARXNG_URL`.
- Ideas de **gpt-researcher** / **open_deep_research** (MIT): ciclo
  lacuna → recuperação limitada → replanejamento — implementado de forma
  determinística e com teto (sem loops).
- **crawl4ai**: **não adotado** nesta entrega — exigiria navegador/deps
  pesadas não autorizadas; a extração determinística cobre o caso de uso.
- **ragas** (Apache-2.0): não adotado — métricas semânticas dependem de LLM
  (verificação semântica segue BLOQUEADA por design).

## Testes

Suíte completa: **601 passed, 4 skipped** (~2 min 52 s).
Novos testes V5.5 (73):

- `tests/test_search_core_v55.py` — 22 (fixtures congelados de provedores,
  orquestrador, recuperação, extração; sem rede).
- `tests/test_source_check.py` — 17 (vereditos de link/imagem, SSRF,
  listagem × produto, formatos de imagem).
- `tests/test_shopping_v55.py` — 15 (pipeline shopping V5.5, listagem,
  alternativas com diferenças, fence JDUI).
- `tests/test_research_v55.py` — 11 (provedor orquestrado nos agentes,
  replanejamento por lacuna, recuperação, status por provedor).
- `tests/test_jdui_v55.py` — 5 (whitelist + selo no node harness real).
- `tests/test_evidence_graph.py` — +3 (unidades na divergência, fonte
  desatualizada informativa).

Comando local:

```powershell
.venv\Scripts\python.exe -m pytest -q tests
```

## Limitações honestas

- **DDG segue bloqueado** no ambiente atual (CAPTCHA): a cadeia legada o
  registra como bloqueado e o V5.5 não depende dele — Bing/Marginalia
  carregam a busca geral. Sem bypass, por decisão.
- **APIs de loja** (Mercado Livre) respondem 403/503 em vários momentos;
  quando bloqueiam, o resultado vem de outras fontes ou do orquestrador.
- **SearXNG** não está configurado; `ProvedorSearXNG` retorna indisponível
  honesto até existir instância autorizada.
- Sem renderização JS: páginas que só montam conteúdo via JavaScript são
  marcadas `parcial`/`ilegivel`, nunca preenchidas com suposição.
- Verificação semântica de afirmações segue **BLOQUEADA** (dependeria de
  LLM); a verificação numérica/léxica é a autoridade.
- O smoke online dos provedores é opcional e separado dos testes de suíte
  (rede não é pré-requisito para CI local).
