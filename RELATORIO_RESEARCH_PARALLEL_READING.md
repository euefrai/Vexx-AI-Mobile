# Pesquisa: coleta paralela com prazo e evidências preservadas

## Problemas confirmados

- O analista abria até três páginas em paralelo, mas aguardava os futures na ordem da busca. Uma primeira página lenta bloqueava a coleta das demais.
- Ao esgotar o prazo, o código marcava toda a leitura como cancelada e descartava resultados já concluídos. Teste reproduzido: a segunda fonte termina, a primeira permanece travada, nenhuma evidência é salva.
- Chamadas com prazo já esgotado debitavam páginas sem realizar download.
- Havia dois processos de PC Agent conectados ao mesmo relay de produção e banco. Ambos estavam ociosos. O reinício revelou que o controlador local recria automaticamente o agente: a instância manual foi encerrada e a gerenciada foi preservada. Ambiente crítico equivalente, banco, credenciais e controle remoto desativado foram conferidos; reconexão confirmada por `/api/diag`. O controlador não foi alterado.

## Correções

- Coleta conforme os downloads terminam, com espera de até 100 ms entre verificações de cancelamento e prazo.
- Cada resultado recebe o instante de conclusão. Apenas resultados concluídos dentro do prazo podem virar evidência; resultados tardios não escrevem no banco.
- Prazo esgotado preserva as páginas concluídas. Cancelamento explícito continua interrompendo o registro de novas evidências.
- Prazo vencido antes da leitura não consome orçamento. Paralelismo máximo de três, limites de páginas, extração, relevância, proteção de rede e regras de evidência permanecem no fluxo existente.
- A ordem final segue a busca/relevância, sem depender da velocidade de cada site. Fontes persistidas continuam reutilizáveis sem outro download.

## Arquivos

- `research_agents.py`: coleta, prazo, cancelamento e evento de leitura parcial.
- `tests/test_research_parallel_reading.py`: seis testes de regressão com threads reais e leitores controlados.
- Este relatório e artefatos locais em `qa-artifacts/parallel-reading-*`.

## Verificação

- Baseline antes da alteração: **2 falharam, 3 passaram**. As falhas reproduziram a perda da fonte concluída e o débito com prazo vencido.
- Testes focados após a alteração: **108 passaram**.
- Smoke de rede real: duas páginas oficiais de `docs.python.org`, abertas e extraídas em **1,00 s** no total; duas evidências com `texto_lido=true`, escopo `page_text`, persistidas em banco temporário. **Zero chamadas de modelo**. Resultado em `qa-artifacts/parallel-reading-public-smoke.json`.
- Suíte completa: **1.276 passaram, 4 ignorados, 2 avisos em 283,11 s**. Avisos existentes de depreciação de `mss.mss` e timeout no TestClient. Log em `qa-artifacts/parallel-reading-full.log`.
- Após os testes, o agente gerenciado foi recarregado com a alteração local. Confirmados: uma instância de produção, novo processo iniciado após a edição, mesmo banco, variáveis críticas/credenciais equivalentes e controle remoto desativado. `/api/diag` confirmou `pc_online=true`; o relay permanece no commit publicado `6a967ce93b0b`. Registro operacional sem segredos em `qa-artifacts/research-agent-restart.json`.
- `git diff --check` passou.

## Limites

Threads Python não interrompem à força um download já iniciado. A coleta deixa de esperá-lo; a operação termina pelo timeout de rede existente, sem registrar resultados tardios. O smoke confirma abertura e persistência dessas duas fontes, não mede acurácia geral de respostas nem equivale a um teste autenticado da interface. Esta melhoria reduz perda de evidências e espera indevida; não altera a latência do provedor de IA. Este relatório registra a validação local; o resultado da publicação autorizada posteriormente será informado na entrega.
