# JÚLIA Research Quality Lab 3.0 (V4.9)

Motor de avaliação reproduzível: datasets congelados e versionados
(`benchmarks/research_quality_v1.json`, `v2.json`), documentos de referência
verificados (`truth_basis: synthetic_local_fixture`), respostas esperadas
rotuladas e métricas determinísticas.

## Suites

- `run_document_retrieval_benchmark`: indexa os documentos de verdade
  (extração real por formato) e mede P@K/R@K/MRR/NDCG/duplicatas por consulta,
  com tempos por estágio (extração ms + busca ms).
- `run_memory_retrieval_benchmark` (v2): fatos semeados + `memorias_relevantes`.
- `run_graph_retrieval_benchmark` (v2): evidências semeadas + ranker lexical.
- `run_factual_verification_benchmark` (v2): pares rotulados → matriz de
  confusão por rótulo (semântica real depende de LLM; o determinístico é
  medido como ele é).
- `run_format_benchmark` (v2): gera PDF/DOCX/XLSX/HTML/JSON/CSV/MD/TXT e
  verifica extração + busca por marca d'água.
- `run_checkpoint_benchmark`: cenários 10/25/50 com save→close→reopen→restore.

## Regras

Nenhuma métrica inventada: tudo sai de execuções locais. LLM-real só em
testes `e2e_real` com skip declarado. Relatórios persistem em `quality_runs`
(`run_research_quality_lab.py --store-db`, `/api/admin/quality/*`).
