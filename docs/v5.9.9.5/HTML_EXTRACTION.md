# Fidelidade HTML e contexto

A ordem de texto/elementos inline da correção anterior foi preservada. Headings menores que 25 caracteres agora permanecem nas seções; antes sumiam títulos como Syntax/Limits e Gabarito. `passage_candidates` separa marcadores de explicação/correção de alternativas, mantém spans literais e adiciona papel observável. A camada de evidência reavalia o texto, sem confiar no papel recebido de um modelo.

Testes executados verificam: identificadores com spans, assinatura/parâmetros, listas, headings curtos, tabelas, blocos de código, links, negação, números/unidades, `<`, `&&`, `!=`, ausência de duplicação, exclusão de boilerplate/script e `texto[start:end] == passagem`. A explicação pode sobreviver mesmo quando alternativas anteriores são rejeitadas.

O parser não executa HTML/JS. Offsets referem-se ao texto extraído retornado, não bytes do HTML ou página/PDF inventada. Espaçamento continua normalizado: não foi implementada preservação universal da indentação de código. PDF complexo, tabelas mescladas, contexto além do teto e todos os layouts de exercícios não foram validados nesta rodada.

Evidência: `tests/test_ordered_extraction_v5994.py`, `tests/test_evidence_reliability_v5995.py` e logs focados/suíte final em `qa-artifacts/v5995/`.
