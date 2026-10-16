# JÚLIA Research Metrics (V4.9)

## Recuperação (por consulta, K configurável)

P@K (divide por K mesmo com menos resultados), R@K, MRR, NDCG com ganhos
2^g-1, taxa de duplicação (conta 1× na relevância, reportada à parte).
Medidos separadamente em: busca web (E2E DDG, sem mock), FTS5+memória,
documentos (FTS+chunks), Evidence Graph (ranker lexical documentado como
baseline) — cada componente com sua fraqueza declarada, nunca uma média
que esconda perdas.

## Factual e citações

Matriz de confusão por rótulo (accuracy + precision/recall/support);
citações em 4 estágios independentes (existe → recuperada → trecho →
sustenta); contradições (TP/TN/FP/FN); checkpoints (cobertura por categoria
+ ids de operação duplicados).

## Onde se perde informação (medido)

- Títulos de seção fora do texto dos chunks → corrigido (título no 1º chunk).
- Unidades ausentes da tabela (ex.: volume) → adicionadas após benchmark.
- Números sem unidade/datas sem contexto → ressalva registrada, não suporte.

## Performance real (PC local, SQLite WAL)

- Verificador: 64 → 17 commits (batch em lote), ~2× mais rápido (0,18 s →
  0,09 s em 12 evidências).
- Busca documental: <2 ms/consulta; salvamento <33 ms (HTML maior: ~130 ms,
  custo único de parse).
- Pesquisa agêntica típica (6 evidências): ~1 s fim a fim local.
