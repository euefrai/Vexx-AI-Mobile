# JULIA Intent Engine 2.0 (V5.1)

`intent.py` — interpretação determinística de mensagens (stdlib, sem LLM,
sem rede). Nunca levanta; sem evidência suficiente, a intenção é `conversa`.

## Estrutura produzida por `analisar(texto, contexto=None)`

- **intencao**: conversa, shopping, pesquisa, pesquisa_profunda,
  estudo_prova/aula/reforco, memoria, calculo, codigo, imagem, identidade,
  projeto, jdui, pc_controle.
- **confianca**: 0.95 (identidade/memória) · 0.85 (evidenciado) ·
  0.5/0.3 (hipótese/fraco).
- **evidencias/secundarias**: de onde veio a decisão (auditoria).
- **entidades**: shopping via `shopping.extrair_criterios`
  (categoria, marcas, orçamento, specs).
- **restricoes**: obrigatorias, proibidas, preferencias, formato
  (`max_linhas`, `detalhe`, `midia`, `tabela`).
- **referencias**: primeiros_n, ultimo/segunda/terceira, selecao,
  anafórico, ordenacao, variacao.
- **correcao**: o texto corrige o pedido anterior.
- **ambiguidades**: o que falta para decidir bem.
- **ferramentas**: llm, shopping, research(deep), learning, memory,
  deterministico, jdui, pc_controle.
- **podem_pesquisar**: False com "não pesquise/sem internet".

## Regras de decisão

- Ferramenta externa (pesquisa web, compra) exige **2+ classes de
  evidência** (verbo, substantivo, preço, spec, condição, mídia).
  1 evidência fraca → `conversa` honesta + hipótese em `secundarias`.
- Padrões fortes locais (identidade, memória, quiz, "em tabela")
  decidem com 1; formato explícito tem peso 2.
- Formato (jdui) é **modificador**: com tarefa real junto, a tarefa vira
  principal e o formato vai para `secundarias`/ferramentas.
- `contexto={"ultimos_resultados": ...}` resolve follow-ups
  ("compare os dois primeiros" → shopping após shopping).
- Correção + conteúdo de memória ("corrigindo: meu nome é…") → `memoria`;
  afirmação inicial ("isso mesmo…") sem alvo não vira `projeto`.
- Valores sensíveis nunca viram entidades.

## Benchmark

`benchmarks/intent_v1.json` (versionado): 124 casos PT-BR em 16 categorias
(simples, shopping, pesquisa, estudos, ferramentas, código, JDUI, memória,
negativas, correções, referências, projeto, multi, segurança, ambíguas,
informais com typos). `tests/test_intent_benchmark.py` mede acurácia
global/por categoria e compara roteamento novo vs legado (detectores
antigos) nos mesmos casos — sem notas inventadas, só contagem.
