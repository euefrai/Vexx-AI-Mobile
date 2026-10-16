# Identidade do assistente

A fonte central é `assistant_identity.py`: nome oficial **Luccas Trawman** e
nome de conversa **Lucas**. O nome completo só deve aparecer quando solicitado.
As regras evitam apresentações e assinaturas repetidas, orientam uma correção
breve e educada quando outro nome for usado e pedem linguagem natural e amigável.
A correção não se aplica a nomes de terceiros, personagens ou marcas mencionados.

`pc_agent.ai_config()` incorpora a identidade após as instruções personalizadas
de `JULIA_SYSTEM_PROMPT`, sem sujeitá-la ao limite de 2.000 caracteres dessas
instruções. Uma variável vazia usa o prompt padrão. A montagem do chat e a
continuação também aplicam a mesma função idempotente, cobrindo configurações
legadas, respostas comuns e streaming, em conversas novas ou existentes.
O usuário não precisa repetir estas regras nos prompts. Histórico e dados
salvos não são reescritos; Vexx AI permanece como marca do produto.

Um processo do agente já aberto precisa ser reiniciado para carregar o código.
Não foi realizado deploy nem reinício de serviços de produção.

Validação: `python -m pytest -q tests/test_assistant_identity.py
tests/test_chatpro.py tests/test_avaliacao.py tests/test_ui_polish.py`:
**22 testes passaram**. Inclui configuração vazia/personalizada longa, reabertura
do SQLite, conversas novas/antigas e captura do prompt de continuação.
Os testes verificam a propagação real das instruções; a geração na continuação
é simulada. O comportamento verbal de um LLM real não foi avaliado nesta rodada.
