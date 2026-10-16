# JÚLIA Long-Context Evaluation (V4.9)

## Cenários 10/25/50

`checkpoint_scenarios` no dataset: N checkpoints sequenciais por job, depois
close→reopen→restore e comparação campo a campo (objetivo, restrições,
decisões, evidências, pendências) + detecção de ids de operação duplicados.

## Retomada real (§6)

`test_retomada_longa_preserva_estado_e_nao_duplica` interrompe um `executar`
de verdade no meio (modo investigativa) e retoma: mesmos ids de evidência
(sem duplicatas), achados preservados, sequência de eventos ordenada e sem
repetição.

## Limites honestos

- Sem LLM não há compactação semântica (`semantic_compaction:
  unavailable_without_llm`); continuidade = registros estruturados, não resumo.
- Resumo (`_resumo`) é auxiliar de exibição, nunca fonte de retomada.
- Retomada perfeita não prometida: medida por retenção (achados + eventos).
