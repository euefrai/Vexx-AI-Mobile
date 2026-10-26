# Avaliação externa

Onze perguntas novas em `benchmarks/retrieval_v5997_external.json`, congeladas antes da otimização e registradas no commit de implementação. Elaboradas pelo mesmo agente, não rotuladas por humanos; não são gold de recall/precisão. Nenhum ajuste semântico ou de ranking foi feito para melhorar o resultado após abrir esse conjunto. Correções posteriores foram de precisão/completude do trace.

Executado com `tools/probe_context_v5996.py --dataset benchmarks/retrieval_v5997_external.json --case eff-NN --output <arquivo-novo.json>`, rede real e SQLite temporário, sem modelo ou UI. `external-summary.json` preserva perguntas, consultas efetivas, orçamento, motivos, revisão e hashes do código.

| Caso | Domínio | Buscas | Slots | Evidências lidas persistidas |
|---|---|---:|---:|---:|
| 01 | pathlib.relative_to | 2 | 12 | 0 |
| 02 | Tramontina | 3 | 12 | 1 |
| 03 | Cabanagem | 2 | 12 | 0 |
| 04 | Saúde em Irecê, sete dias | 3 | 5 | 0 |
| 05 | Regras da Chapada Diamantina | 2 | 12 | 0 |
| 06 | Nikon Z50II | 5 | 7 | 0 |
| 07 | FLIP 2026 | 5 | 6 | 0 |
| 08 | USB4 / Thunderbolt 4 | 3 | 6 | 0 |
| 09 | Mercury automóveis | 3 | 6 | 0 |
| 10 | StreamReader.readline | 2 | 12 | 0 |
| 11 | Visitantes em Jequié ontem | 4 | 6 | 0 |

Todos os jobs chegaram ao estado técnico concluída, mas o resultado foi **partial**, não pesquisa completa. Uma linha de evidência não equivale a fonte gold validada independentemente. Rejeições observadas incluem ENTITY_MISMATCH 95, TOPIC_MISMATCH 44, NO_ANSWER_PASSAGE 14; há também códigos compostos, bloqueios, tamanho, tipo e rede. São eventos, não fontes únicas nem rótulos humanos corretos por definição.

Sem comparação pareada de rede; não afirmar ganho causal, recall ou melhoria de latência externa. **Gate externo insuficiente; NO_GO.** A revisão declarada era ff486ed com código modificado; hashes de quatro módulos acompanham a execução. O corpo de recuperação foi depois commitado em c98d4be; 203d4d5 acrescenta precisão do trace, não um novo algoritmo de ranking.
