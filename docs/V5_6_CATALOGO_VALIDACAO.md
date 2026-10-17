# Catálogo 3D local — validação para push

Data: 17/10/2026.

## Conteúdo

Catálogo local com 14 cenas educativas aproximadas, incluindo consoles, celular, controle, placa-mãe, gabinete, monitor, teclado, headset, mesa, suporte de celular, motor V8 e notebook. As cenas usam primitivas locais, sem downloads ou execução de código do modelo. Não são CAD nem reproduções oficiais; medidas e encaixes são ilustrativos.

Integração com pedidos 3D, exploração de peças e reconstrução a partir do pedido anterior, respeitando proprietário e conversa. Arquivos: `model3d_catalog.py`, `model3d.py`, `pc_agent.py` e `tests/test_model3d_v56.py`.

## Falha de teste corrigida

O teste novo esperava uma resposta textual para `Amplie` quando o usuário não tinha acesso à cena. O contrato existente, coberto por `test_model3d.py`, retorna `None` para que comandos curtos sem contexto 3D não capturem ações de outros recursos. A expectativa foi corrigida, sem alterar o comportamento de produção. O teste também passou a exigir isolamento entre conversas e zoom efetivo (redução da distância da câmera) na conversa do proprietário correto.

## Verificação

- 73 testes de 3D passaram.
- Após ampliar a paridade Python/JavaScript para todas as cenas do catálogo, os 16 testes V5.6 passaram novamente.
- IDs, relações entre peças, grupos, limite de 20 KB por cena, precisão declarada, continuação e isolamento são verificados automaticamente.
- `git diff --check` passou.
- A execução da suíte completa está registrada em `qa-artifacts/3d-catalog-tests.txt`.

Não foi executada nova inspeção visual no navegador nem teste em celular físico nesta rodada. A aprovação automatizada não implica fidelidade visual ou mecânica a produtos reais. A imagem de falha do teste anterior de clima não faz parte deste commit.
