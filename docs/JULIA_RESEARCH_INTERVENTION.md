# JÚLIA Research Intervention (V4.7)

Comandos de chat mapeados para operações estruturadas (sem LLM):

- "pesquise apenas X" / "só X" / "somente X" → `escopo_add`
- "priorize X" → `priorizar_dominio` (se domínio) ou `escopo_add`
- "ignore X" → `escopo_remove`
- "investigue melhor essa divergência" → `investigar_divergencia` (índice 0)
- "não precisa mais pesquisar X" / "pare de pesquisar X" → `parar_topico`
- "adicione X à comparação" → `adicionar_metrica`

Fluxo: valida job ativo do dono → valida op/parâmetros → nova versão →
resposta informa adicionadas/removidas/invalidadas. Resultados válidos nunca
reexecutados; incompatíveis preservados e sinalizados (não apagados).
Pausa (`pause`/`resume`) congela o worker com segurança; cancelar interrompe
futuras etapas. Estados de corrida cobertos por testes (pausa durante
execução, cancelamento duplo, intervenção em estado final).
