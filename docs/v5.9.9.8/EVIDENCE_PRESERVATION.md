# Preservação e deduplicação

Grafo usava os primeiros oito vínculos brutos, dominados por sintaxe, enquanto a seleção final já tinha retorno. Agora usa as passagens selecionadas e todos os requirement_ids associados. A aresta permanece REQUIRES_VERIFICATION, nunca prova factual.

Truncamento público de 32 vínculos agora faz distribuição por requisito. Teste de 35 vínculos de sintaxe mais um retorno garante que o retorno sobreviva. IDs, offsets literais, referências e limites são mantidos.

Investigação obrigatória do antigo 3→2: reexecuções da mesma captura variam entre dois e três documentos devido à fronteira/agendamento e dados ausentes no pool. URLs observadas: MDN pt-BR Object, pt-BR Object/assign e de Object/assign. Variante alemã não foi provada cópia sem informação adicional. Portanto NÃO foi classificada como deduplicação legítima apenas pela contagem.

Replay final mantém os três documentos, melhora comportamento, mantém retorno parcial; nenhuma faceta anteriormente suportada desaparece nesse replay. Não resolve causalmente toda a variação histórica. Hashes de fonte/excerto, IDs de documentos/passagens e requisitos retidos estão em replay-summary.json. Não alegar preservação universal de evidência sem conjunto anotado maior.
