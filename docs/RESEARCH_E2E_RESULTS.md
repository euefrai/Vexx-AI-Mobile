# E2E reais — V5.7 FINAL (2026-10-18)

## Método

1. **Bateria determinística** (`tools/bench_experiencia_real.py`, 16
   checagens): pipeline verdadeiro com fixtures locais, sem rede, DNS
   mockado; artefatos antes/depois preservados.
2. **Smoke externo leve** (`tools/smoke_externo_v57f.py`): rede real, camadas
   determinísticas do pipeline (sem LLM), sem desabilitar provedores, sem
   contornar bloqueios. Artefato:
   `qa-artifacts/v57/smoke-externo-v57f-2026-10-18.json`.
3. **Suíte completa** e **benchmarks congelados** (gabaritos intocados).

Ambiente: Hermes na porta 8645 (`/v1/models` HTTP 200 — DeepSeek V4.1 Flash
listado). Provedores: bing saudável; DDG com bot-wall; MLB e Magalu 403 —
nada contornado, nada mascarado.

## Bateria antes/depois

| | Bateria (16) | Artefato |
|---|---|---|
| Antes (worktree de `b91ab31`) | **10/16** | `bench-experiencia-real-2026-10-18-antes.json` |
| Depois (código final) | **16/16** | `bench-experiencia-real-2026-10-18-depois.json` |

As 6 checagens corrigidas: grounding com conteúdo lido; página do usuário
lida entra no prompt; página bloqueada com aviso honesto; fallback de preço
JS; coerção de `item_de_listagem` JS; tipo de `specs` JS.

## Smoke externo — resultados reais

| Bloco | Resultado | Honestidade |
|---|---|---|
| Hermes | porta 8645 aberta, `/v1/models` 200 | inferência LLM não exercitada (custo não autorizado) |
| Pesquisa real (fotossíntese) | `estado=ok`, bing, **3 fontes abertas**, conteúdo lido ≤1.200 cada, grounding 4.388 chars, 4,2s | DDG bloqueado no dia não foi usado; nada contornado |
| Página do usuário: Wikipédia | **aberta**, conteúdo do artigo no `texto_lido`, 2,3s | extração determinística tem resíduos de sidebar/marcação |
| Página do usuário: Magalu | **bloqueado (403)** | erro classificado, aviso honesto, sem fonte/Conteúdo inventado |
| Shopping real | **2/2 ofertas confirmadas na página do item** (KaBuM), URL + preço exibido (R$ 25,74 / R$ 110,12), 41,5s | `preco_valor` numérico ausente nesses cards (limitação); categoria Amazon ignorada com log |
| Prompt com página | página lida presente no prompt (amostra do texto confere), sem pesquisa genérica extra, 5.114 chars | — |

## Suíte e benchmarks (código final)

- Suíte completa: **868 passed, 4 skipped, 2 warnings** (~3min).
- Benchmark pesquisa (congelado): **34/34**.
- Benchmark shopping (congelado): **59/59**.

## Cenários de aceitação (12) — local × publicado

| # | Cenário | Local (determinístico/real) | Publicado |
|---|---|---|---|
| 1 | Produto específico | PASS — 2/2 confirmadas com URL | NOT_TESTED |
| 2 | Orçamento | PARTIAL — produto dentro do orçamento; gate numérico limitado por `preco_valor` ausente | NOT_TESTED |
| 3 | Comparação | NOT_RUN — cards comparativos existem (JDUI validado) | NOT_TESTED |
| 4 | Factual | PASS — 3 fontes lidas reais + grounding com conteúdo | NOT_TESTED |
| 5 | Recente | NOT_RUN — sem caso real nesta rodada; grounding carrega data de acesso | NOT_TESTED |
| 6 | Técnica | PASS — reformulação/correspondência 34/34 na bateria congelada | NOT_TESTED |
| 7 | Site (URL específica) | PASS — Wikipédia lida; Magalu bloqueada com aviso honesto | NOT_TESTED |
| 8 | Documento | PASS — `contrato.txt` e `vendas.csv` no docs_agent (bateria) | NOT_TESTED |
| 9 | Verificação | PARTIAL — fence de evidências testada na suíte; não exercitada em smoke real | NOT_TESTED |
| 10 | Sem resultados | PASS — provedor vazio → `sem_resultados` + aviso honesto (bateria) | NOT_TESTED |
| 11 | Follow-up | NOT_RUN — reuso/replay cobertos pela suíte; sem caso real novo | NOT_TESTED |
| 12 | JDUI | PARTIAL — paridade Node 4/4 + frontend smoke na suíte; navegador real pendente | NOT_TESTED |

Legenda: PASS = evidência real/determinística nesta rodada; PARTIAL =
funciona com limitação declarada; NOT_RUN = não executado nesta rodada
(estado honesto, sem inferência); NOT_TESTED (publicado) = **deploy não
autorizado nesta rodada** — nenhum teste foi feito no serviço publicado.

## Limitações herdadas do smoke (registradas, não escondidas)

- Extração determinística da Wikipédia inclui resíduos de sidebar/marcação na
  janela lida (trafilatura não instalada no ambiente).
- `preco_valor` numérico ausente em cards reais (preço em texto) — limita o
  gate de orçamento e filtros que exigem número.
- DDG/Magalu/MLB bloqueados no dia; a busca seguiu com bing.
- LLM (Hermes) disponível, mas respostas geradas não foram avaliadas nesta
  rodada (sem autorização de custo).
