# Critérios de anotação

Unidade: uma passagem em relação a **um** requisito explícito. O gabarito é
definido pelo conteúdo da fixture, antes da execução do classificador.

| Label | Critério |
|---|---|
| DIRECT_SUPPORT | Entidade e predicado explícitos sustentam o atributo e suas condições obrigatórias. |
| PARTIAL_SUPPORT | Há um valor pertinente, mas falta uma condição pedida; deve permanecer parcial. |
| TOPIC_ONLY | Menciona o assunto, sem relação ou valor solicitado. |
| CONTRADICTORY | Nega explicitamente a relação positiva; não pode confirmar aquele valor. |
| WRONG_ENTITY | Predicado de outra entidade, variante ou interface. |
| WRONG_ATTRIBUTE | Entidade correta, atributo diferente. |
| INSUFFICIENT_CONTEXT | Pronome sem antecedente inequívoco no contexto disponível. |
| UNREAD | Snippet ou metadados sem leitura da página. |
| IRRELEVANT | Nem entidade nem informação pertinente. |

Não confundir a negação de uma relação de fundação com comportamento negativo
legítimo: “não modifica o original” responde sobre mutabilidade.
Uma negação não demonstra qual seria o valor positivo correto.
Revisão feita pelo mesmo agente autor: **não há gold humano independente**.
Nenhum label é obtido das decisões do mecanismo avaliado.

Precisão/recall binários medem retenção de DIRECT ou PARTIAL; a separação é
explícita. Também medimos precisão exclusivamente de DIRECT, retenção de PARTIAL
e parciais indevidamente promovidas. Demais labels não são classificados como
evidência suficiente. A matriz não implica que o motor saiba distinguir todos
os motivos de rejeição. Parser e busca externa são avaliados separadamente.
