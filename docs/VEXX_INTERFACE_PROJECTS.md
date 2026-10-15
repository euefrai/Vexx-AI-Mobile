# Interface Vexx: projetos e navegação responsiva

## Organização das conversas

- `+` em Projetos cria um projeto; `···` ao lado do projeto permite renomeá-lo.
- `···` ao lado de uma conversa permite renomear, mover, fixar ou arquivar.
- Um projeto pode conter várias conversas. `Sem projeto` remove o vínculo sem apagar mensagens.
- `public/workspace.js` mantém os metadados no IndexedDB, separados por conta, e sincroniza com `/api/workspace/sync`.
- O agente persiste esses metadados no SQLite por meio de `workspace_store.py`. A implantação dos recursos de projetos requer os arquivos atualizados do frontend, servidor e agente.

## Correção do menu mobile — 15/10/2026

O escurecimento do fundo (`#drawerScrim`) era irmão externo de `#app`.
Como o app possui `isolation:isolate`, o `z-index:50` do menu não podia
ultrapassar o `z-index:40` desse elemento externo. O toque nos controles
atingia o fundo e fechava o menu sem executar a ação selecionada.

O fundo e o menu agora são irmãos dentro de `#app`, compartilhando o mesmo
contexto de empilhamento. O fundo permanece acima do conteúdo e abaixo do menu.
O bloqueio de interação com o conteúdo por `inert` continua restrito à coluna
principal quando o menu está aberto em telas pequenas.

Outros ajustes: botões de exportação quebram em linhas, nome e identificação
da conta ficam em linhas separadas, textos de ajustes usam linguagem direta,
e a cor do aplicativo instalado acompanha a interface. A versão do cache
do service worker passou para `VEXX-shell-v0.8-mobile-drawer`.

## Validação

Ambiente descartável: `tests/preview_workspace.py`, com servidor e agente
reais e SQLite temporário. Nenhuma conta ou conversa real foi alterada.

- Antes da correção, `elementFromPoint` no centro do botão de ajustes retornava `#drawerScrim`.
- Depois da correção, o mesmo ponto alcançou o botão de ajustes.
- Em 320 × 640: abertura dos ajustes; criação e renomeação de projeto; movimentação e abertura de conversa verificadas pela interface.
- Em 390 × 844: rolagem da lista e fechamento ao tocar fora do menu; sem transbordamento horizontal.
- Em 1280 × 720: menu permanece acessível, fundo oculto e navegação para ajustes funcionando.
- `python -m pytest tests/test_workspace.py tests/test_frontend_smoke.py -q`: **18 testes passaram**.
- `git diff --check`: sem erros de whitespace.

A validação usa tamanhos mobile em navegador desktop; não substitui um teste
em aparelho físico ou no teclado virtual de Android/iOS. O ambiente de interface
não possui provedor de IA conectado e não mede o tempo real de geração.

Para receber a atualização no aplicativo instalado, publique os arquivos desta
versão e reabra o aplicativo com conexão. Não é necessário apagar o armazenamento
local: ele pode conter mensagens ainda não sincronizadas.
