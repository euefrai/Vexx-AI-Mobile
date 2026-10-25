# Calibração exploratória da camada de relações existente

Sem classificador paralelo. `evidence_graph.requirement_coverage` continua avaliando passagens lidas e relações explícitas; o requisito fornecido pelo avaliador isola essa camada, sem fingir que descoberta/parsing também passaram.

| Divisão | Baseline 31b063c | Candidato | Limite |
|---|---|---|---|
| Desenvolvimento, n=11 | TP3 FP0 FN1 TN7; retenção recall 0,75, F1 0,8571 | TP4 FP0 FN0 TN7; recall/F1 1 | Um DIRECT anotado foi retido somente como PARTIAL; cobertura direta permanece 0,75. |
| Validação, n=6 | TP0 FP0 FN2 TN4 | Mesmo resultado | Um positivo ambíguo UNVERIFIED; data de nascimento continua fora das relações suportadas. |
| Holdout, n=3 | TP0 FP0 FN1 TN2 | Mesmo resultado | Parcial industrial ainda perdido; não calibrar sobre ele agora. |

Precisão sem denominador é null, não 100%. Estes números são exploratórios sobre anotações MODEL_PROPOSED, não precisão global, verdade semântica ou certificação independente. Métricas binárias de retenção não confirmam que todos os rótulos de rejeição são distinguidos pelo motor.

Correções: contexto causal de heading pode preservar parcial; alias de operação sob título qualificado preserva parcial sem completar requisito; sintaxe reconhece `Object.assign` sem absorver a linguagem; exercícios sem alternativa correta comprovada são rejeitados e explicações literais podem ser lidas separadamente. Restrições obrigatórias e direção causal continuam exigidas.

Riscos restantes: papéis de exercícios são heurísticas conservadoras; marcadores parecidos em prosa podem gerar FN. Heading não prova que todas as frases pertencem à entidade. Métodos/idiomas/predicados não cobertos continuam perdendo passagens úteis. Não ampliar regex com exemplos selados para elevar contagem.
