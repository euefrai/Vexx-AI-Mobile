# Pesquisa, comparação e cards JDUI

Data: 28/10/2026, America/Bahia. Base da implementação: `33b9e2d`.

## Resultado

- Cards de fontes com domínio, estado de leitura, trecho e proveniência expansível.
- Filtros Todas / Com leitura / Sem leitura; uma leitura parcial permanece identificada como parcial. Contagens se referem à lista apresentada, não à pesquisa inteira.
- Ações Analisar fonte, Comparar fontes e Criar resumo reutilizam o chat e os links do filtro selecionado, com até seis fontes. Pedidos usam texto legível, sem JSON de interface no chat.
- Comparação por produto e tabela alternáveis, com preferência persistida; cada produto mantém sua oferta acessível.
- Estados de envio, falha, conexão indisponível, filtros vazios, teclado, redução de movimento e responsividade.

## Causas corrigidas

1. **Comparar fontes podia perder os links escolhidos.** O leitor anterior só aceitava uma URL em pedidos muito curtos. Os novos atalhos usam uma lista explícita de URLs; o backend reconhece esse formato, lê as páginas e injeta as evidências no contexto do modelo com IDs S1, S2 etc. Uma falha não elimina fontes lidas, nem dispara uma busca genérica substituta.
2. **Trecho relevante não aparecia no card.** A apresentação preferia a introdução da página mesmo quando existia uma passagem selecionada para responder. Agora apresenta essa passagem quando a fonte foi lida.
3. **Fontes utilizadas podiam ficar fora dos dez cards.** Fontes lidas ligadas aos achados têm prioridade, seguidas de fontes lidas de contexto; a ordem original é preservada em cada grupo.
4. **Metadados antigos podiam sugerir leitura parcial de página bloqueada.** Estado e escopo agora dependem da leitura efetiva, mantendo a prévia como prévia.
5. **Menor preço podia comparar moedas diferentes ou um único valor conhecido.** O destaque só ocorre na mesma moeda e com pelo menos dois preços informados. A moeda fica visível e condições da oferta permanecem explícitas.

## Limites e segurança

- Sem execução de código do modelo. Componentes continuam validados e links passam pelos validadores existentes.
- A leitura explícita usa o mesmo downloader: SSRF, redirects, MIME e tamanho continuam protegidos. Internet desativada e restrições do usuário continuam respeitadas.
- Máximo de seis URLs e três leitores simultâneos, com orçamento compartilhado de 12 segundos repassado aos downloads. Esse orçamento não substitui as limitações de DNS e transporte do sistema operacional.
- Ações não garantem acesso a páginas bloqueadas, precisão do modelo ou completude universal. Fontes inacessíveis continuam sendo apresentadas como limitações.
- Cards mantêm o limite de 300 caracteres por trecho e dez fontes. Registros completos continuam no mecanismo de pesquisa existente.
- Implementação e validação realizadas localmente; envio para `main` autorizado pelo usuário após a entrega. O deploy do Render e a atualização do PC Agent têm validação separada. Nenhum dado real foi alterado pelos testes desta etapa.

## Arquivos

- `research.py`: interpretação da lista explícita e leitura concorrente limitada.
- `pc_agent.py`: fontes selecionadas no contexto do modelo, IDs e falhas individuais.
- `research_view.py`: passagens selecionadas, prioridade e estados fiéis à leitura.
- `public/jdui.js`: cards, filtros, ações e comparação.
- `public/interface.css`: apresentação e responsividade dos componentes.
- `public/sw.js`: versão do cache atualizada.
- `tests/test_research_cards.py`: regressões de evidências, leitura, concorrência, contexto e segurança.
- `tools/preview_research_cards.py` e `tools/qa_research_cards.cjs`: cenário isolado e verificações reproduzíveis no Chrome.

## Verificação

- Testes focados finais: **71 aprovados**, incluindo internet desativada, restrição do usuário, bloqueio SSRF, falha parcial, concorrência e contexto do modelo.
- Suíte automática completa: **2048 aprovados, 4 ignorados, 2 avisos**, em 288,86 segundos. Os dois casos de permissão acrescentados após a coleta dessa suíte passaram na execução focada final. Avisos existentes: depreciações de `mss.mss` e do parâmetro `timeout` do TestClient.
- Chrome real, componentes e funções de persistência IndexedDB do aplicativo, com dados controlados: filtros, recarga, separação de contas, contexto dos atalhos, falha, indisponibilidade, envio pendente, moedas, estado vazio e conteúdo inseguro.
- Larguras 320, 390 e 1280 px, nas duas visualizações: sem overflow horizontal da página. Zoom de 200%, teclado e redução de movimento aprovados. Sem erros de console ou exceções da página no cenário.
- Leitura HTTP real de `https://www.python.org/about/` e `https://docs.python.org/3/tutorial/`: duas páginas abertas, 1200 caracteres de cada uma no contexto, IDs distintos e cards gerados; cerca de 0,85 segundo nesta execução. Nenhum modelo foi chamado nesse teste.
- Evidências incluídas: `output/playwright/research-cards-check.json`, `research-cards-live-read.json` e capturas nas três larguras. Logs automatizados locais em `qa-artifacts/research-cards-*.log`.

A validação autenticada em produção e a qualidade da síntese de um provedor real continuam fora desta verificação local. A leitura real e a montagem do contexto foram executadas; a inferência não foi chamada nem simulada como concluída.
