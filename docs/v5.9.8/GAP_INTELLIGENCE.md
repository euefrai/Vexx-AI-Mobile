# Lacunas e controle V5.9.8

`research_gaps.py` identifica até seis dimensões sobre até 80 evidências. IDs são estáveis por pesquisa/dimensão. Cada lacuna contém descrição, subpergunta, dados esperados, IDs das evidências, URLs descobertas, tentativas anteriores, prioridade, consulta e orçamento restante. Não há rede ou execução de instruções do modelo nesse módulo.

Comparação científica exige duas publicações distintas com DOI ou tipo científico declarado. Enciclopédia e metadados descobertos não contam como estudo original lido. Métodos, resultados quantificados, condições e limitações vêm de seções efetivamente extraídas. Ausência no trecho não significa ausência no estudo inteiro. Dado extraído não equivale a conclusão cientificamente validada.

O controlador escolhe REPLAN, STOP_PARTIAL ou SYNTHESIZE dentro do orçamento existente. DOI descoberto e título real ancoram consultas; não são fabricados URLs de texto integral. Pesquisas repetidas são evitadas. Cancelamento, pausa, bloqueio e limites prevalecem. Decisões ficam no estado do job, limitadas às 16 últimas.

O plano inicial científico usa duas consultas curtas sobre o assunto e mantém a classificação científica, reservando páginas para lacunas observadas. Seções e proveniência sobrevivem ao leitor e à persistência. Unidades de energia por massa e volume são distintas, assim como capacidade específica e pressão.

Quando a repetição de trechos em fontes de afirmações ultrapassa 60.000 caracteres, apenas o resumo duplicado é compactado. Afirmações, estados, IDs, relações e evidências originais permanecem; o estado registra claim_sources_compacted. JSON não é cortado nem o limite desabilitado. Payloads excessivos por outras causas continuam sendo rejeitados com checkpoint anterior preservado.
