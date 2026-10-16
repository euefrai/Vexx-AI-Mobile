# Relatório Júlia 5.1 — Intent & Understanding Engine

## Status: ENTREGUE

## Fase 1 — Auditoria e baseline

Tree limpo na V5.0 (`ebb6db1`); roteamento espalhado em 15+ detectores
(`intencao_*`, `cmd_*`, `shopping.detectar`, `sugerir`, `intencao_imagem`).
Baseline antes de modificar: **104 passed, 3 skipped** (interactive,
research, shopping, memoria50, identity, jdui).

## Fases 2–7 — Implementação

- **`intent.py`** (novo): `analisar` → estrutura validada (intenção,
  confiança, evidências, entidades, restrições, referências, correção,
  ambiguidades, ferramentas, `podem_pesquisar`); `validar` → violações
  determinísticas (vazia, proibida, formato, ação não executada,
  superlativo, card sem dados). Correções do smoke: classes de evidência,
  desempate local>externo, follow-ups com contexto, formato modificador.
- **Integração** (`pc_agent.py`): `extras["intent"]`, `ferramentas_usadas`,
  skip de Research/Shopping com "não pesquise", diretiva de formato,
  filtro de usados (recuperação), validador nos fluxos stream e completo.
- **Memória+intenção**: sem valores sensíveis em entidades; correção
  explícita sobrescreve memória antiga (fluxo V5.0 já garantia).

## Fase 8 — Benchmark: 124/124 (100%)

`benchmarks/intent_v1.json` (16 categorias). Acurácia global **1.000**,
mínimo por categoria **0.875** (multi). Roteamento: **novo 124 vs legado
89** nos mesmos casos (legado não cobre JDUI/código/pc_controle e erra
1-evidência). Limiares do teste: global ≥ 0.90, categoria ≥ 0.75.

## Bugs corrigidos

- Correção com falso-positivo (`e ` solto); shopping sem plural/preço;
  "duas linhas" por extenso; proibição com vírgula; follow-ups sem
  contexto; `IndentationError` (docstring colada); `fontes` sem espaço;
  1-evidência fraca roteando; categoria=marca ("tablet Samsung");
  empate jdui×tarefa; proibida por palavra (não frase).

## Arquivos

`intent.py`, `benchmarks/intent_v1.json`, `tests/test_intent.py`,
`tests/test_intent_benchmark.py`, `pc_agent.py` (integração),
`shopping.py` (categoria ignora marca), docs (2), roadmap.

## Testes, limitações, bloqueados

- `test_intent.py` 16 testes; benchmark parte da regressão.
- Regressão total `not e2e_real`: **410 passed** (394 + 16 novos),
  8 deselected (`e2e_real`), só 2 warnings pré-existentes.
- Limites: semântica literal (sinônimos raros escapam); typos graves
  ("notibook") ficam em `conversa` por honestidade; formato curto
  depende do LLM; código roteia p/ LLM (sem especialista técnico).
- Bloqueado: inferência real (Hermes) — nuances, sumarização e
  validação semântica seguem nele; E2E ao vivo de shopping pendente.
