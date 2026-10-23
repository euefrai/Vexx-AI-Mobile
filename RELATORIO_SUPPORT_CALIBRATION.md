# Vexx AI — calibração de contradições

Entrega local sobre `34c5924`, sem push/deploy/reinício de produção. Modelo, credenciais, permissões e dados reais preservados.

## Alterado

- `CONTRADICTED` agora exige `counterevidence`: ID de fonte citada pelo próprio parágrafo, citação literal dessa fonte e trecho literal da conclusão refutado. Quote limitado a 12–450 caracteres e afirmação a 12–250.
- Prova ausente, inventada, de fonte não citada, com afirmação diferente, extra não permitido ou trecho não contíguo faz o estado passar a `INCONCLUSIVE`, nunca a `SUPPORTED`. Dados inválidos da prova não são persistidos. `proposed_state` e `counterevidence_status` registram a decisão original e a validação.
- Uma citação idêntica à afirmação não é aceita como refutação. Expressões reconhecidas de ausência de informação/avaliação, como “não informou”, “não avaliou”, “não disponibilizou” ou “não contém avaliações”, também não são apresentadas como contradição. A regra é conservadora, limitada a padrões explícitos; não é um analisador semântico completo.
- A negação de uma propriedade do produto, como “não contém mercúrio”, continua elegível como oposição literal. Apenas exigir uma palavra negativa seria incorreto.
- Citação rastreável continua sendo uma condição necessária, não prova de que a interpretação do revisor está certa. A revisão mantém os quatro estados, remoção de parágrafos sem suporte completo, fallback e os limites existentes: duas chamadas no máximo, sem retries, no mesmo orçamento compartilhado.
- Avaliador ganhou seleção de corpus, métricas separadas de falso bloqueio versus erro da revisão e captura limitada de resposta/código de erro para diagnóstico. Nenhum histórico ou memória real é usado nos experimentos.

## Testes e evidências

- Baseline: **66 passed**. Durante os novos testes, uma flexão verbal (“avaliou”) não foi reconhecida; a regra e suas regressões foram corrigidas. Também foram cobertos “informou”, “disponibilizou” e “recuperou”. O primeiro log com falha foi preservado.
- Focados finais: **110 passed**. Cobrem provas ausentes/inventadas, IDs e fonte não citada, limites de tamanho, claim diferente, quote não contíguo, ausência de dados, negação factual válida e falsa refutação por texto idêntico. Testes anteriores de geração, revisão, checkpoint, relatórios e exports foram mantidos.
- Suíte completa: **1.242 passed, 4 skipped, 2 warnings em 375,71 s**. A execução completa foi iniciada antes das últimas correções de flexão e da rejeição de prova idêntica; esses ajustes foram cobertos depois pelos 110 testes focados da versão final. Verificações de sintaxe, `git diff --check` e busca de credenciais nos arquivos de entrega feitas na conclusão.
- Artefatos: `qa-artifacts/support-calibration-*`; ferramenta `tools/evaluate_semantic_support.py`; corpus novo `benchmarks/support_calibration_v2.json`. O corpus antigo permaneceu inalterado.

## Avaliação real, sem prometer ganho não demonstrado

Modelo preservado: `poolside/laguna-s-2.1:free`. Foram 36 avaliações individuais com modelo real e uma sonda mínima de disponibilidade, sem retries automáticos ou ativação de plano/provedor. Os casos são **sintéticos**, não representam pesquisas reais na web. A concordância avalia o estado, não a categoria de motivo.

| Conjunto | Concordância | Revisões válidas | Sem suporte classificado como sustentado | Controles corretos bloqueados |
|---|---:|---:|---:|---:|
| 12 casos novos, antes | 5/12 | 7/12 | 0 | 2/4, ambos por erro da revisão |
| Mesmos casos novos, depois | 5/12 | 5/12 | 0 | 1/4, por erro da revisão |
| 12 casos antigos, regressão depois | 8/12 | 10/12 | 0 | 0/3 |

Nos casos novos, a única falsa classificação de contradição da rodada anterior não reapareceu, mas houve menos revisões válidas depois. Apenas H03, H04 e H06 tiveram respostas válidas em ambas as rodadas; esses três já estavam corretos antes e continuaram corretos. Portanto, **não foi demonstrado aumento geral de precisão nem redução de falso bloqueio por classificação**. A diferença de bloqueios dos controles decorreu da disponibilidade, não de uma melhora comprovada do julgamento.

A primeira comparação terminou antes de ajustes adicionais de flexão verbal e da rejeição de prova idêntica, feitos por testes determinísticos. Esses ajustes não mudam os resultados válidos registrados dessa rodada. A regressão real também precede os últimos ajustes de flexão; as regressões determinísticas finais cobrem a regra final. Nenhum gabarito ou resultado foi reclassificado para aumentar a pontuação.

O código exige provas mais rastreáveis e preserva o bloqueio conservador, mas os rótulos ainda podem errar e as falhas intermitentes impedem uma conclusão forte sobre qualidade. Os logs genéricos de disponibilidade das primeiras rodadas não permitem atribuir uma causa específica a todas as falhas. A sonda mínima respondeu; isso não prova disponibilidade contínua.

## Limites e arquivos

Produção: `research_synthesis.py`. QA: `tests/test_semantic_support.py`, novo `tests/test_support_calibration.py`, avaliador, corpus, evidências e este relatório. Sem dependências ou migrações novas. Sem teste visual, aparelho físico ou interface de produção nesta etapa.

Os padrões de ausência podem deixar casos de fora e, conservadoramente, também rebaixar uma contradição verdadeira sobre o que um documento informou. IDs/trechos válidos não garantem relevância, oposição lógica, contexto completo ou verdade. Novas pesquisas continuam sujeitas à disponibilidade do modelo e aos limites da etapa anterior.
