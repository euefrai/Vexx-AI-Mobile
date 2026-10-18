# Júlia — Precisão da pesquisa (V5.7)

Objetivo da V5.7: elevar a precisão **real** das pesquisas (o que é buscado,
o que é aceito como resposta e o que é descartado), reutilizando o Search
Orchestrator V5.5 — sem recriar arquitetura, sem contornar bloqueios e sem
inventar resultados.

Regra central: **nunca declarar sucesso com resultado irrelevante** e
**nunca apagar** um resultado — ele pode ser rebaixado ou descartado com
motivo registrado (`descartes`), base para o Evidence Graph.

## 1. Fluxo (ordem preservada)

```
intenção → cadeia de provedores (ordem V5.5, sem reordenação)
        → coleta (bing RSS, wikipedia, marginalia, …)
        → dedupe canônico + republicações
        → correspondência com o pedido
        → ranqueamento (relevância + reputação + recência)
        → leitura das fontes (SSRF-safe, cache, teto 2 MB/10 s)
        → relatório + lacunas
        → recuperação (1 rodada, consulta enxuta)
```

A ordem dos provedores em `_escolher_provedores` é contrato congelado da
V5.5 e **não** foi alterada (mesmo com preferências possíveis, ex.:
wikipedia antes de marginalia para PT).

## 2. Reformulação conservadora de pergunta

`consulta_conteudo(consulta)` (novo) remove **apenas** a moldura de pergunta
e artigos iniciais; devolve `""` quando não sobra termo distintivo — nunca
inventa consulta:

| Entrada | Saída |
|---|---|
| `como funciona o freio ABS` | `freio ABS` |
| `o que é fotossíntese` | `fotossíntese` |
| `quanto custa a placa a?` | `placa` |
| `freio ABS` | `""` (nada a reformular) |
| `qual o melhor preço?` | `""` |

Uso: quando um provedor devolve resultados sem correspondência (ou vazio),
`pesquisar()` tenta **a mesma fonte uma vez** com a consulta reformulada,
antes de trocar de provedor. A etapa é registrada no relatório:
`bing (consulta reformulada 'freio ABS'): 6 resultados`.

Contratos preservados: a consulta original é sempre a primeira tentativa;
`variantes` não mudou; nada é silenciado.

## 3. Correspondência honesta

- `_ESTOPO` ganhou verbos/funcionais de pergunta (`funciona`, `faz`,
  `serve`, `significa`, `existe`, `foi`, `era`…) — não provam
  correspondência temática e não contam como termo do pedido.
- `_termos_correspondencia` extrai só termos com ≥ 3 caracteres, fora do
  estoque: `como funciona o freio ABS` → `['freio', 'abs']`.
- Limiares: `correspondencia < 0.5` → o resultado é declarado **enxuto**
  (`enxuta`) e dispara a rodada de recuperação em
  `pesquisar_com_recuperacao` (antes só `≤ 0.15`).
- Junk lexical (dicionários de "funciona") é demovido pelo ranqueamento,
  nunca removido (os contratos congelados V5.5 exigem que ele permaneça em
  `achados` — apenas no fim).

## 4. Duplicatas e republicações

`deduplicar()`:

1. **URL canônica** (comportamento V5.5): tracking removido, `www` equiparado;
   mantém a versão com mais trecho.
2. **Republicação (novo)**: título praticamente idêntico entre URLs
   distintas — Jaccard ≥ 0.9 com ≥ 4 termos — a versão posterior vira
   descarte com motivo `republicação de <url>` e a mantida ganha
   `republicacoes: [urls]`. Títulos curtos (< 4 termos) nunca entram na
   regra (evita juntar páginas distintas de tema comum).

## 5. Recuperação

`pesquisar_com_recuperacao(consulta)`: se a correspondência ficou fraca,
faz **uma** rodada adicional com a consulta enxuta, soma os achados e
recalcula correspondência; devolve `recuperou` e as `etapas` completas.
Não declara `ok` por quantidade — estado depende de correspondência real.
O ganho da rodada é **medido e declarado** (§6): `ganho_informacao` com
`dominios_novos`/`temas_novos`/`ganho_real` e etapa
`recuperação com/sem ganho novo` — nunca fingir melhora só porque a rodada
rodou. O recorte temporal (seção 7) é preservado no re-rank da recuperação.

## 6. Critérios de parada (estado honesto)

Orçamento explícito: `max_consultas`, `max_provedores`, `min_resultados`,
`timeout_total`, `max_por_provedor`, mais 1 retry reformulado por provedor.
**Ganho real de informação** implementado (incremento 5), em dois pontos:

1. **Cadeia de consultas**: com resultado útil já obtido, se a consulta
   anterior não trouxe domínio nem tema novo, a próxima consulta não roda
   (etapa `parada por ganho zero: …`) — evita gastar orçamento repetindo o
   mesmo quadro.
2. **Recuperação**: o ganho da rodada extra é medido
   (`ganho_informacao.ganho_real`) e declarado nas etapas; ganho zero não
   vira discurso de melhora.

Medida = domínio novo (novos hosts) e tema novo (termos não-genéricos do
pedido cobertos a mais) — quantidade de resultados não conta como ganho.

## 7. Conteúdo desatualizado e erros honestos (V5.7)

- **Desatualizado**: quando a consulta tem recorte temporal (ano explícito
  ou classe temporal), cada item com **ano conhecido** (pubDate/`data`
  primeiro; senão ano no título) ganha `ano` + `desatualizado`, usando a
  regra única do `evidence_graph` — ano ≤ alvo−2, e **sem data conhecida
  NÃO acusa**. O item velho é apenas rebaixado (penalidade ≤ 4.5), nunca
  apagado; o relatório da busca expõe `temporal` e `desatualizados: [urls]`.
  Consulta sem recorte temporal não muda nada.
- **Erro interno ≠ provedor**: `pesquisa_rapida` não rotula mais qualquer
  exceção como `provedor_indisponivel`. Exceção de provedor/rede (com
  `codigo`) continua `provedor_indisponivel`; bug interno (sem `codigo`)
  vira `erro_interno` com a causa real na etapa
  (`erro interno na busca (TypeError)`). P6 da auditoria: corrigido.

## 8. Medição (V5.7)

- Benchmark independente offline com fixtures congeladas:
  `benchmarks/pesquisa_v57_v1.json` + `python tools/bench_pesquisa_v57.py`
  → **31/31, taxa global 1.0** (reformulação 8, correspondência 4, fluxo
  junk→retry 1, republicações 2, produtos 5, specs 2, links 5,
  desatualizado 2, ganho 2).
- Sonda real (2026-10-17), `como funciona o freio ABS`:
  - antes: 6/6 dicionários de "funciona", `correspondencia 0.333`, `estado ok`;
  - depois: `correspondencia 1.0`, topo com artigos reais de freio ABS,
    etapa `bing (consulta reformulada 'freio ABS')` registrada.
- Artefato: `qa-artifacts/v57/bench-pesquisa-v57-2026-10-18.json` (o de
  2026-10-17 fica como histórico, 27 casos).
- Regressão completa: 710 passed / 4 skipped (`pytest -q tests`).

## 9. Limites e bloqueios (sem bypass)

- Bloqueios externos observados: DDG (CAPTCHA), Mercado Livre API (403),
  Magalu (403 bot-wall), KaBuM listagem (reprovado/sem sinais de produto),
  Amazon BR (503), Mojeek/Brave/Startpage/Yahoo/searx.be (indisponíveis),
  Semantic Scholar (429). Nada foi contornado; cada bloqueio vira estado
  honesto (`bloqueado`/`reprovado`/`parcial`).
- Resultados de busca variam entre execuções: o benchmark determinístico
  injeta provedores; as sondas reais são **registro**, não assert.
- Pendência declarada: fontes primárias/reclassificação por assunto quando
  a primeira rodada traz só índice geral. Desatualizado temporal (§7), P6 e
  parada por ganho de informação (§6) **corrigidos** nos incrementos 3–5.

Ver também: [V5_7_PROGRESS.md](V5_7_PROGRESS.md),
[JULIA_SOURCE_AND_IMAGE_VALIDATION.md](JULIA_SOURCE_AND_IMAGE_VALIDATION.md),
[JULIA_RESEARCH_RESULTS_JDUI.md](JULIA_RESEARCH_RESULTS_JDUI.md) e
[../RELATORIO_JULIA_5.7.md](../RELATORIO_JULIA_5.7.md).
