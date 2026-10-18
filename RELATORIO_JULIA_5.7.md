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

### Fase 2 — Precisão da busca (FUNCIONAL; pendências declaradas)

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
- Pendências declaradas (não fingidas): fontes primárias/reclassificação e
  parada por ganho real de informação. Detalhes:
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
rede) + `tests/test_bench_pesquisa_v57.py`. **27/27, taxa global 1.0**;
sondas reais no artefato
`qa-artifacts/v57/bench-pesquisa-v57-2026-10-18.json` (freio ABS:
correspondência 1.0, top3 real, etapa reformulada).

### Fase 10 — Documentação (concluída)

`docs/JULIA_RESEARCH_ACCURACY.md`,
`docs/JULIA_SOURCE_AND_IMAGE_VALIDATION.md`,
`docs/JULIA_RESEARCH_RESULTS_JDUI.md`, `docs/V5_7_PROGRESS.md`
(log por incremento) e este relatório; roadmap atualizado com a seção V5.7.

## Métricas (antes → depois)

| Medida | Antes | Depois |
|---|---|---|
| `freio ABS`: correspondência / topo | 0.333, dicionários "funciona" | 1.0, artigos de freio ABS |
| Reformulação registrada | não existia | etapa `consulta reformulada 'freio ABS'` |
| Shopping Lenovo: marcas no resultado | Asus/Dell misturados | só Lenovo; Asus/Dell como alternativas explícitas |
| Specs capturadas ("8gb 512gb") | só `flag_novo` | RAM 8GB + armazenamento 512GB |
| Trecho Wikipédia ABS | referências ("Consultado em…") | corpo do artigo |
| Benchmark congelado | não existia | 29/29 (taxa 1.0) |
| Suíte completa | 670 passed / 4 skipped (V5.6) | **706 passed / 4 skipped** (V5.7) |

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
  físico e leitor de tela reais (pendência herdada da V5.6), ganho real de
  informação como critério de parada.- P6 **corrigido** (incremento 4): erro interno tem código próprio
  (`erro_interno`) e causa na etapa; provedor indisponível de verdade
  continua `provedor_indisponivel`.

## Próximos passos sugeridos

1. Parada por ganho de informação (novos domínios/temas) em vez de só
   quantidade.
2. Fontes primárias e reclassificação por assunto quando a rodada traz só
   índice geral.
3. Estender o benchmark com casos de E2E real opcional e histórico de taxas
   por versão.
