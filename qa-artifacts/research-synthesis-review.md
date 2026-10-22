# Revisão textual — avaliação técnica de síntese

Escopo: rodada inicial com 20 perguntas, quatro resumos manuais de documentação oficial e inferência real. Inspeção pelo próprio agente de implementação, sem avaliação cega independente. Não mede recuperação web ou outras áreas de pesquisa.

| Pergunta | Primeira rodada | Observação |
|---|---|---|
| Q01 — sort versus sorted | Fallback | Diagnóstico posterior reproduziu parágrafo longo. |
| Q02 — preservar lista original | Assistida | Responde diretamente com sorted e cita fonte. |
| Q03 — sorted sobre tupla | Fallback | Candidata posterior válida, sem prova de que a primeira falhou pelo mesmo motivo. |
| Q04 — retorno de sort | Assistida | None e mutação corretos; acrescenta interpretação de design ausente do resumo fornecido. |
| Q05 — estabilidade | Fallback | Diagnóstico juntou frases não adjacentes em uma citação; continua rejeitado. |
| Q06 — reverse e empates | Assistida | Explicita preservação da estabilidade. |
| Q07 — chamadas de key | Assistida | Responde uma vez por registro. |
| Q08 — comparação sem caixa | Assistida | Identifica casefold; descrição de caixa baixa é simplificada e não substitui documentação detalhada de Unicode. |
| Q09 — ordenação por várias chaves | Assistida | Secundária antes de principal, com estabilidade. |
| Q10 — lista em tupla | Assistida | Resposta direta, preserva diferença entre contêiner e conteúdo. |
| Q11 — cópia superficial | Fallback | Diagnóstico posterior forneceu uma candidata válida. |
| Q12 — duplicatas | Assistida | Identifica conjuntos; não compara todos os tipos de dados. |
| Q13 — conjunto vazio | Fallback | Diagnóstico posterior forneceu uma candidata válida. |
| Q14 — lista versus deque | Assistida | Recomenda deque; comparação de eficiência vai além do trecho literal citado. |
| Q15 — lista como chave | Assistida | Responde que não pode ser chave. |
| Q16 — concorrência WAL | Assistida | Distingue leitores concorrentes e somente um escritor. |
| Q17 — pasta de rede | Assistida | Explicita que WAL não funciona nesse cenário. |
| Q18 — checkpoint | Fallback | Candidata posterior válida; detalhes adicionais exigem revisão semântica. |
| Q19 — foreign_keys por conexão | Assistida | Responde por conexão; acrescenta estado padrão não presente no resumo, embora documentado na página oficial. |
| Q20 — transação e restrição diferida | Fallback | Diagnóstico posterior válido; a conclusão sobre falha do COMMIT fica no trecho citado, com redação que pode ser mais direta. |

Os casos Q04, Q14 e Q19 mostram por que referência existente e trecho literal não bastam para garantir que cada detalhe da redação esteja sustentado pelo conteúdo enviado ao modelo. A entrega mantém avisos explícitos e não usa a aceitação como selo de verdade. Uma verificação semântica independente e uma avaliação cega diversificada são pendências.

O diagnóstico direcionado usou outras sete inferências, portanto não é um segundo conjunto independente. Seu replay local aceitou seis candidatas, conservando a recusa do quote não contíguo em Q05. Nenhum gabarito foi alterado para chamar o resultado de precisão universal.
