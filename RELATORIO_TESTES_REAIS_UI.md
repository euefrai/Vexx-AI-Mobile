# UI/UX e pesquisas reais — 29/10/2026

## Escopo e ambientes

Trabalho incremental sobre `main`, base `c42792a`. Preservados o rebrand, as contas,
memória, pesquisa, JDUI e permissões de controle remoto. Sem reescrita do projeto.
Durante a rodada, outro trabalho adicionou o commit `aed713d` de APIs públicas;
a suíte completa final inclui esse estado do checkout. As correções descritas
aqui continuam sem commit e não foram agrupadas naquele commit.

- **Produção:** testes pelo navegador autenticado, em conversa criada para esta
  validação. O PC Agent antigo foi atualizado para a versão já publicada
  `c42792a`, após backup SQLite, checagem de ociosidade e encerramento por IPC.
  Nenhum encerramento forçado nem alteração no código do Fajulto ou da extensão.
- **Aplicação local completa:** relay e PC Agent reais, banco e conta descartáveis,
  login normal pela interface, consultas públicas reais e o modelo gratuito
  configurado `poolside/laguna-s-2.1:free`. Sem fixtures de pesquisa ou respostas
  simuladas. Não foram copiadas conversas pessoais para esse ambiente.
- **Regressões automatizadas:** fontes controladas e casos negativos, separadas
  da comprovação pela interface. Outros arquivos previamente modificados ou
  preparados no índice Git foram preservados.

**Estado no encerramento da primeira etapa:** as correções eram locais, sem
push/deploy, e o agente de produção tinha somente `c42792a`. O usuário autorizou
depois a continuação e a publicação conjunta; a etapa seguinte está descrita em
`RELATORIO_CONCLUSAO_PESQUISA.md`.
Ao terminar, o agente, relay e navegador exclusivos do laboratório foram
encerrados. Banco de QA e evidências preservados; agente de produção mantido.

## Problemas encontrados e correções

| Problema observado | Correção |
| --- | --- |
| Busca de GPU retornava páginas estrangeiras irrelevantes, embora a KaBuM exibisse ofertas acessíveis | Descoberta limitada pelo catálogo público real da KaBuM; cada produto continua passando pelo leitor e validador de página de produto. Sem contornar CAPTCHA. |
| Busca vazia terminava prometendo uma pesquisa futura que não continuava | Resposta determinística para ausência de ofertas, baseada no diagnóstico real. Não atribui qualquer falha a CAPTCHA/403 sem evidência. |
| “Diferenças que você conseguiu confirmar” acionava pendências de memória | Comandos de memória explícitos, sem capturar a palavra “confirmar” em uma pergunta comum. |
| “Duas primeiras opções” não acionava comparação | Reconhecimento das referências no feminino. |
| Ofertas do cache apareciam em outro chat, mas o próximo pedido não encontrava contexto | Associação do resultado ao chat atual, preservando a data de verificação e a expiração originais. Sem renovar artificialmente preços. |
| “Notícias desta semana de Ubatã” perdia a localização | Reconhecimento de “desta/nesta/esta semana”, mantendo cidade e região. |
| Documentação oficial Python não era descoberta adequadamente | Inventário Sphinx oficial, com download e descompressão limitados, sem avaliar JavaScript; identificação das APIs preservada durante deduplicação. |
| Documento correto em inglês era descartado para uma pergunta em português | Requisitos explícitos de cancelamento/exceções para APIs qualificadas e seleção de trechos com os termos nos dois idiomas. A autoridade da fonte continua sendo uma condição independente. |
| Vários trechos da mesma parte do documento ocupavam a seleção | Distribuição por API e preservação da assinatura real das definições e seus offsets. Contexto de seção produz suporte parcial, sem promover automaticamente uma afirmação a verdade. |
| Falha da redação escondia quase todas as passagens já recuperadas | Apresentação alternativa preserva trechos complementares separados e citados, com limite de tamanho. Fences JDUI de fontes externas não são ativadas por essa apresentação. |
| Cards eram acrescentados no fim, apesar de haver posições reservadas no Markdown | Montagem na posição declarada; chaves de estado equivalentes à montagem antiga, incluindo grupos de componentes. |
| Referências extensas, avatar decorativo duplicado e colunas apertadas | Referências recolhíveis com controles nativos, identificação mais discreta e cards de fonte com largura confortável. Links e proveniência preservados. |
| Datas ISO cruas e dia aparentemente incorreto no fuso local | Datas legíveis em pt-BR; instantes convertidos para o fuso do navegador, datas sem horário preservadas. |
| Texto do botão “Abrir oferta” tinha pouco contraste | Estilo específico dos links de ação, preservando o tratamento de botões secundários. |
| Ênfase Markdown com `_` falhava ou ameaçava modificar URLs | Ênfase com limites de palavra e proteção prévia dos autolinks, código e identificadores. |
| Tabela repetia “Cancelamento” sem identificar qual API, além de duplicar autoridade | Nome da entidade incluído no aspecto; condição de autoridade apresentada uma vez. |
| Estado “concluída” podia parecer resposta completa apesar de lacunas | Texto explícito de etapas finalizadas com resultado parcial; contagem léxica confusa retirada da apresentação alternativa. Dados de diagnóstico continuam disponíveis. |

## Evidência real pela interface

Os resultados finais e capturas estão em `output/real-ui/`. A automação opera
controles reais do aplicativo; o script reproduzível é
`tools/live_ui_acceptance.cjs` e requer uma sessão local de QA já autenticada.

| Cenário | Evidência observada |
| --- | --- |
| Conversa comum | Resposta real do modelo explicando listas Python. |
| RTX 3050 de 6 GB no Brasil | Seis cards com URLs diretas `/produto/ID/slug`. Um card foi aberto na loja: título e variante corretos, preço de R$ 1.499,99 também presente na página. Essa verificação individual não certifica todas as outras ofertas ou lojas. |
| Comparação contextual | Falhas de memória, gênero e cache reproduzidas e corrigidas; execução final com dois cards de comparação, inclusive reutilizando o cache em outra conversa. |
| Notícias locais | Três fontes de Ubatã/região com conteúdo recuperado, links de matérias e datas legíveis. |
| Imagens da Ponte Estaiada | Cinco cards do Wikimedia Commons; carregamento real das cinco imagens conferido, mantendo links de origem. |
| Pesquisa profunda Python | Antes: nenhuma evidência. Depois: página oficial efetivamente lida, passagens de APIs distintas recuperadas e fonte persistida. A redação do modelo falhou em uma execução; o sistema apresentou extratos e manteve a classificação parcial. |
| Responsividade | Navegador em 320, 390 e 1280 px, sem overflow horizontal. Em 390 px, o menu aceitou clique real em Ajustes, abriu Configurações e retornou ao chat. Não equivale a um teste em Android/iPhone físico. |
| Persistência | Treze mensagens e quinze cards antes/depois de reload. Ordenação por nome também preservada após reload, sem apagar IndexedDB ou SQLite reais. |
| Referências e ações | Expansão real das referências mostrou oito links; contraste do botão corrigido e página do produto aberta pela ação do card. Nenhum erro inesperado de console nas execuções finais. |

## Validação automatizada

- Regressões focadas finais: **73 passaram, 2 puladas**.
- Extração, contexto de seção e recuperação de APIs: **52 passaram**.
- **Suíte completa final: 2.083 passaram, 4 puladas, 2 avisos, 218,53 s; exit 0.**
  Os avisos são de depreciação existentes (`mss.mss` e timeout do TestClient).
  As quatro verificações puladas não são contabilizadas como executadas.
- `git diff --check`: sem erros de whitespace; avisos de normalização CRLF nos
  arquivos que já seguem essa convenção do checkout.
- Resultados visuais, contagens e console finais: `output/real-ui/result-final.json`.
- Menu, configurações, referências e ordenação persistida:
  `output/real-ui/interactions-final.json`.
- Capturas: `chat-320.png`, `chat-390.png`, `chat-1280.png`, `chat-reloaded.png`,
  `settings-390.png`, `interaction-390.png` e `product-opened.png`, todas em
  `output/real-ui/`.
- Logs: `qa-artifacts/real-ui-focused-final.log`,
  `qa-artifacts/real-ui-api-read.log`, `qa-artifacts/real-ui-full-final.log`.

## Arquivos desta rodada

- Descoberta e compras: `store_discovery.py`, `python_docs_discovery.py`,
  `search_providers.py`, `search_orchestrator.py`, `shopping.py`.
- Roteamento, evidências e apresentação: `pc_agent.py`, `query_intelligence.py`,
  `web_extract.py`, `evidence_graph.py`, `research_agents.py`, `research_view.py`.
- Interface: `public/app.js`, `public/jdui.js`, `public/interface.css`, `public/sw.js`.
- Regressões: `tests/test_live_ui_recovery.py`, `tests/test_shopping.py`,
  `tests/test_synthesis_context_selection.py`, `tests/test_frontend_smoke.py`,
  `tests/test_jdui_fontes_v57.py`, `tests/test_shopping_generic_v57.py`,
  `tests/test_shopping_reliability_v57.py`, `tests/conftest.py`.
- Evidências e roteiro: este relatório, `docs/UI_POLISH_PROGRESS.md`,
  `tools/live_ui_acceptance.cjs`, `tools/live_ui_interactions.cjs`,
  capturas/resultados em `output/real-ui/`.

## Limitações e próximo passo registrados antes da continuação

**A — leitura:** passagens pertinentes comprovadas na documentação pública Python,
incluindo trechos posteriores ao corte inicial; a cobertura permanece parcial.
**B — descoberta:** comprovada sem fornecer a URL na
mensagem do chat. **C — síntese:** ainda não aprovada como redação completa; houve
saída vazia do modelo gratuito e o fallback preservou os extratos. Não foi
flexibilizada a validação para marcar a pesquisa como completa.

O próximo passo específico da pesquisa é medir a redação/revisão desse modelo
com os mesmos trechos e separar indisponibilidade, JSON vazio e rejeição de
suporte. A condição de autoridade oficial também permanece explícita, sem
considerar domínio ou título isoladamente como prova.

Não há garantia de acesso universal a marketplaces. A melhoria de descoberta
nativa desta rodada cobre KaBuM; bloqueios, mudanças no HTML, estoque e preços
podem mudar. Limites de leitura, timeouts, validação de URLs públicas, contas e
permissões de controle remoto foram mantidos.
