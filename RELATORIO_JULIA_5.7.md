# Relatório Júlia V5.7 — Research Accuracy & Intelligent Results

Data: 17/10/2026 • Commits locais `aa9f3c2`, `382be6d`, `8223f75`, `1f508c2`
e o commit desta documentação (topo do log) • **Sem push/deploy**

## Pedido

Elevar a qualidade **real** das pesquisas da Júlia em 10 fases (problemas
auditados de verdade, não hipotéticos): precisão e cobertura da busca,
recuperação quando a primeira rodada falha, validação de links/imagens/fontes,
leitura e interpretação de conteúdo, resultados visuais (JDUI), fluxo SSE
honesto, benchmark independente e documentação — reutilizando a arquitetura
existente. Sem mudar identidade/modelo/credenciais do Lucas, sem tocar na
extensão da Júlia ou no Fajulto Studio, sem contornar CAPTCHA/bot-wall, sem
recriar arquitetura, sem inventar fontes/preços/imagens/testes.

## Entregas por fase

### Fase 1 — Auditoria real (concluída)

Auditoria com subagente de exploração + 10 sondas de rede reais
(`%TEMP%\opencode\v57_probe*.py`) contra os módulos, com orçamento curto.
Problemas reproduzidos com evidência (tabela completa em
[V5_7_PROGRESS.md](docs/V5_7_PROGRESS.md)):

- **P1** consulta em forma de pergunta → 6/6 páginas de dicionário de
  "funciona", `correspondencia 0.333`, `estado ok` (Wikipedia escolhida mas
  nunca consultada);
- **P2** shopping misturava marcas (Asus/Dell no pedido Lenovo) e devolvia
  páginas de categoria; `specs` não capturava "8gb 512gb";
- **P3** "mojibake" — **descartado**: artefato do console do Windows, bytes
  íntegros (`\xe7\xe3`, nenhum `U+FFFD`);
- **P4** bloqueios de loja confirmados (MLB 403, Magalu 403 bot-wall, KaBuM
  listagem `sem_sinais_produto`) — regra: sem bypass, veredito honesto;
- **P5** sinônimos pt-PT×pt-BR derrubavam veredito de página (parcial);
- **P6** erro interno mascarado como `provedor_indisponivel` (corrigido —
  incremento 4: exceção sem `codigo` vira `erro_interno` com causa real).

Baseline da área: 266 passed / 4 skipped; suíte completa V5.6: 670/4.

### Fase 2 — Precisão da busca (FUNCIONAL; lista declarada concluída)

- Reformulação conservadora: `consulta_conteudo()` remove só moldura de
  pergunta/artigos; `""` se nada distintivo. Retry na mesma fonte (1x),
  registrado nas etapas; consulta original continua a primeira tentativa.
- Correspondência: `_ESTOPO` com verbos de pergunta; `correspondencia < 0.5`
  declara `enxuta` e dispara recuperação; junk é demovido, nunca apagado.
- Republicações: título quase idêntico (Jaccard ≥ 0.9, ≥ 4 termos) em URLs
  distintas vira descarte `republicação de <url>`; a mantida ganha
  `republicacoes`.
- **Prova real**: `como funciona o freio ABS` → 0.333/dicionários **antes** →
  1.0 com artigos reais **depois**, etapa `consult. reformulada` no relatório.
- Conteúdo desatualizado (incremento 3): em consulta com recorte temporal,
  item com ano conhecido ganha `ano` + `desatualizado` (regra única do
  `evidence_graph`: ano ≤ alvo−2; **sem data não acusa**); rebaixado, nunca
  apagado. Resultado expõe `temporal` e `desatualizados: [urls]`.
- Parada por ganho real (incremento 5): consulta que repetiu domínio/tema
  não dispara a próxima (`parada por ganho zero`); ganho da recuperação é
  medido e declarado (`ganho_informacao` + etapa com/sem ganho novo).
- Índice geral (incremento 6, fecha a lista): página de índice/listagem é
  sinalizada (`pagina_de_indice`) e demovida (−2, nunca apagada; resultado
  expõe `indice_geral`); rodada só de índices gera etapa honesta, lacuna e
  recuperação dirigida — fontes primárias por classe seguem primeiro pela
  cadeia congelada. **Lista declarada da FASE 2 concluída** (incrementos
  1–6). Detalhes:
  [JULIA_RESEARCH_ACCURACY.md](docs/JULIA_RESEARCH_ACCURACY.md).

### Fase 3 — Provedores e diagnóstico (FUNCIONAL herdado + registro)

Cadeia multi-provedor V5.5 preservada (ordem não alterada). Bloqueios
externos registrados sem contorno: DDG CAPTCHA, Mercado Livre API 403,
Magalu 403, Amazon BR 503, Mojeek/Brave/Startpage/Yahoo/searx.be
indisponíveis, Semantic Scholar 429 — cada um vira estado honesto
(`bloqueado`/`indisponivel`). P6 corrigido no incremento 4 (erro interno
ganhou código próprio, sem mascarar causa).

### Fase 4 — Links, produtos e imagens (FUNCIONAL incremental)

- Marca pedida é critério obrigatório: outra marca → alternativa explícita
  ("outra marca: asus (pedido: lenovo)"); sem marca confirmável →
  `marca_nao_confirmada`. Nunca aparece como se fosse o pedido.
- Specs pareadas: "8gb 512gb" → RAM 8 + armazenamento 512 (notebook/celular/
  tablet); `_armazenamento_aparente` não confunde 16GB de RAM com
  armazenamento.
- Link exato: `url_item > url_final > url`; listagem marcada como listagem.
- Imagem: `verificar_imagens` (até 3) — `reprovado` remove a foto e o card
  mostra "Sem foto confirmada" + motivo; `parcial`/`nao_verificado` mantêm
  aviso. Vereditos/códigos em
  [JULIA_SOURCE_AND_IMAGE_VALIDATION.md](docs/JULIA_SOURCE_AND_IMAGE_VALIDATION.md).
- **Prova real**: pedido Lenovo → produtos Lenovo (`verificado`, `url_item`)
  + Asus/Dell como alternativas explícitas; specs RAM 8/512 capturadas.

### Fase 5 — Leitura e trechos (FUNCIONAL)

`melhor_trecho` não escolhe mais trecho de referências/bibliografia
("Consultado em", "Cópia arquivada", ISBN, doi, `«»`, `↑` descontam pontos).
**Prova real**: Wikipédia Freio ABS → trecho das referências **antes** →
trecho do corpo ("as rodas estarão travadas… o ABS irá reduzir…") **depois**.
Parsers de PDF/DOCX/CSV/JSON seguem os da V5.5 (sem OCR/visão sem tool).

### Fase 6 — Evidências e hipóteses (FUNCIONAL herdado, verificado)

`evidence_graph.py`, `hypothesis_engine.py`, `research_agents.py`,
`continuous_research.py` — sem mudanças nesta versão; cobertura por testes
verificada nesta data: 60 passed / 1 skipped
(`test_evidence_graph`, `test_hypothesis_engine`, `test_research_agents`,
`test_continuous_research`, `test_evidence_benchmarks`). Estados
proposto→evidência→teste→resultado são do vocabulário existente; sem
evidência não há "confirmado".

### Fase 7 — JDUI (FUNCIONAL)

- Cartões de fonte clicáveis (`Abrir fonte ↗`, estado
  Encontrada/Aberta/Utilizada, domínio/data/trecho).
- Selo de imagem novo no card de produto (parcial/não verificada/reprovada —
  nunca foto não verificada como confirmada).
- Autolink com rótulo curto `host + caminho` (href completo, `title` com a
  URL inteira) — fim das URLs gigantes quebrando o layout.
- "Fontes:" anexado por estrutura (cabeçalho + link), não por substring —
  menção solta à palavra não esconde mais fontes reais.
- Suíte JDUI 34/34; smoke de frontend 14/14. Detalhes:
  [JULIA_RESEARCH_RESULTS_JDUI.md](docs/JULIA_RESEARCH_RESULTS_JDUI.md).

### Fase 8 — SSE e recuperação (FUNCIONAL herdado, verificado)

Infra de streaming/jobs existente (pc_agent + server) coberta pelos E2E
verdes desta data (`test_e2e_processes` no conjunto acima). Sem mudança de
contrato nesta versão; P6 (honestidade de erro) resolvido no incremento 4.

### Fase 9 — Benchmark independente (concluída)

`benchmarks/pesquisa_v57_v1.json` (fixtures congeladas) +
`tools/bench_pesquisa_v57.py` (determinístico, provedores injetados, sem
rede) + `tests/test_bench_pesquisa_v57.py`. **34/34, taxa global 1.0**;
sondas reais no artefato
`qa-artifacts/v57/bench-pesquisa-v57-2026-10-18.json` (freio ABS:
correspondência 1.0, top3 real, etapa reformulada).

### Fase 10 — Documentação (concluída)

`docs/JULIA_RESEARCH_ACCURACY.md`,
`docs/JULIA_SOURCE_AND_IMAGE_VALIDATION.md`,
`docs/JULIA_RESEARCH_RESULTS_JDUI.md`, `docs/V5_7_PROGRESS.md`
(log por incremento) e este relatório; roadmap atualizado com a seção V5.7.

### Fase 3 — Provedores e confiabilidade de recuperação (frente nova, em andamento)

Continuação da V5.7 sobre a FASE 2 concluída, após auditoria de 2026-10-18:
11 provedores oficiais/keyless + DDG HTML/Lite, SearXNG opcional
(`JULIA_SEARXNG_URL`; sem instância autorizada aqui → indisponível
declarado), OpenAlex + Crossref no caminho acadêmico, circuito de 5 min por
provedor, retry 429 com backoff no acadêmico, cache com TTL, dedupe
canônico/republicações e registro de status por provedor — tudo **já
existente e preservado** (nada recriado). Incrementos concluídos:

1. **Métricas por provedor** (`search_providers.metricas()`): chamadas, ok,
   vazio, resultados, erros por código e latência média, alimentadas no
   dispatcher `buscar`; classificação de rede ampliada
   (`OSError`/timeout/reset → `rede`); testes de HTTP 202/403/429/5xx,
   timeout e página vazia.
2. **Imagens referenciadas** na extração (`web_extract.extrair_imagens`:
   JSON-LD → og/twitter → `<img src>`, absolutas, dedup, `data:` fora),
   expostas em `extrair_pagina()["imagens"]`.
3. **Origem declarada** pela página: `rel=canonical` para outro domínio vira
   `origem_declarada` na fonte, marca no grounding do Lucas e sinal no
   veredito de página — declarado, nunca verificado; o link não é trocado.

Suíte completa com os incrementos: **727 passed / 4 skipped** (722 dos
incrementos 1–2 + 5 do incremento 3); benchmark congelado re-verificado
offline **34/34**.

Sonda E2E real dos provedores (2026-10-18) em `qa-artifacts/v57/`
`fase3-provedores-2026-10-18.json`: bing/stackexchange/worldbank/wikipedia/
openlibrary/commons ok, OpenAlex/Crossref ok; pubmed/bing-news/hn/marginalia/
bcb responderam `vazio`; ddg/ddg-lite `rede` neste host — nada contornado.

Pendências honestas desta frente: exibição da origem declarada na JDUI;
medição de latência por provedor em uso contínuo; avaliação de
trafilatura/extruct/crawl4ai (licenças livres — Apache-2.0/MIT —, mas
dependências não se justificam por ora: o extrator atual já cobre título,
texto, seções, metadados, JSON-LD, canônica, links, tabelas e agora imagens;
os gates opcionais permanecem no código para quem instalar).

## Métricas (antes → depois)

| Medida | Antes | Depois |
|---|---|---|
| `freio ABS`: correspondência / topo | 0.333, dicionários "funciona" | 1.0, artigos de freio ABS |
| Reformulação registrada | não existia | etapa `consulta reformulada 'freio ABS'` |
| Shopping Lenovo: marcas no resultado | Asus/Dell misturados | só Lenovo; Asus/Dell como alternativas explícitas |
| Specs capturadas ("8gb 512gb") | só `flag_novo` | RAM 8GB + armazenamento 512GB |
| Trecho Wikipédia ABS | referências ("Consultado em…") | corpo do artigo |
| Benchmark congelado | não existia | 34/34 (taxa 1.0) |
| Parada por ganho zero | não existia (só quantidade) | consulta redundante não roda; `ganho_informacao` declarado na recuperação |
| Rodada só de índices | aceita como `ok` | índices sinalizados/demovidos; lacuna + recuperação dirigida |
| Suíte completa | 670 passed / 4 skipped (V5.6) | **712 passed / 4 skipped** (V5.7) |
| Métricas por provedor (FASE 3) | só último status + contagem da rodada | `metricas()`: chamadas/ok/vazio/erros/ms por provedor |
| Imagens referenciadas (FASE 3) | não extraídas | `extrair_pagina["imagens"]` (JSON-LD/og/`<img>`, dedup) |
| Origem declarada (FASE 3) | não sinalizada | `origem_declarada` + marca no grounding |
| Suíte completa (FASE 3, inc. 1–3) | 712 passed / 4 skipped | **727 passed / 4 skipped** |

## Contratos preservados

Ordem/encadeamento de provedores; vocabulário de estados V5.5; junk mantido
em `achados` (apenas demovido); `variantes` inalterado; SSRF/redirect
seguro/multiusuário/auth/cache/tetos de download; JDUI em paridade de schema
(`public/jdui.py` × `jdui.js`, 34/34); motor 3D intocado; extensão da Júlia
e Fajulto Studio intocados; nenhum push.

## Limitações honestas e o que não foi medido

- Bloqueios de fontes externas continuam (tabela na doc de validação) — sem
  bypass por decisão de projeto.
- Resultados de busca variam entre execuções; por isso o benchmark usa
  provedores injetados e as sondas reais são registro, não assert.
- Selo de imagem cobre até 3 produtos por busca; os demais ficam sem selo
  (estado neutro, nunca "confirmado").
- Não medido nesta versão: latência/custo de produção antes/depois, mobile
  físico e leitor de tela reais (pendência herdada da V5.6).
- FASE 3 (em andamento): ddg/ddg-lite responderam `rede` na sonda de
  2026-10-18 (antes, CAPTCHA) — registrado como está, sem bypass; a marca
  `origem_declarada` ainda não é exibida na JDUI (disponível para agentes);
  trafilatura/extruct não instalados (gates opcionais no código, sem
  justificativa de dependência por ora).- P6 **corrigido** (incremento 4): erro interno tem código próprio
  (`erro_interno`) e causa na etapa; provedor indisponível de verdade
  continua `provedor_indisponivel`.

## Próximos passos sugeridos

1. Estender o benchmark com casos de E2E real opcional e histórico de taxas
   por versão.
2. Candidatos (não prometidos): preferência de fontes primárias por classe
   além da cadeia congelada de provedores; mobile físico e leitor de tela
   reais (herdado da V5.6).
3. FASE 3 (continuação): exibir a origem declarada na JDUI; aproveitar as
   métricas por provedor para medição contínua de latência/taxa de falha;
   decidir sobre trafilatura/extruct apenas com ganho comprovado em E2E.
