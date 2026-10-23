# Pesquisa: substituição de fontes sem conteúdo útil

## Problema reproduzido

O analista selecionava uma fatia fixa das candidatas. Uma página bloqueada, inacessível, vazia, explicitamente não lida ou sem correspondência com o pedido consumia sua tentativa sem aproveitar a próxima candidata, mesmo com orçamento disponível. Baseline local: **7 falhas, 3 testes passando** antes da implementação.

## Alterações

- O analista tenta a próxima candidata na ordem do ranking existente quando uma leitura não traz conteúdo útil. Uma fonte válida não dispara tentativa extra.
- Não há nova busca nem chamada de modelo. A substituição usa somente as candidatas já encontradas.
- Limite por etapa: até **duas vezes o número de páginas inicialmente permitido**, sempre limitado pelo saldo global de páginas, quantidade de candidatas e prazo original. O paralelismo continua limitado a três workers. Tentativas que falham também consomem orçamento.
- URLs canônicas duplicadas e URLs inválidas são descartadas antes do download, sem consumir uma vaga de substituição. Essa deduplicação não substitui a validação de rede/SSRF do downloader existente.
- Cancelamento ou prazo vencido impedem novas substituições. Conteúdo concluído depois do prazo continua descartado.
- A mesma regra de relevância vale para decidir a substituição e para registrar a fonte. Fontes sem leitura permanecem identificadas como tal; não viram suporte confirmado nem são descritas no evento como páginas lidas.
- Resumos acadêmicos úteis mantêm seu escopo `abstract_only`; não são promovidos a texto completo e não provocam downloads extras apenas por serem resumos.
- Evento `source_replacement_started` registra a tentativa extra. Fontes e evidências continuam isoladas pelo usuário e persistidas no banco existente.

## Arquivos

- `research_agents.py`: seleção, deduplicação, recuperação limitada e descrição honesta da leitura.
- `tests/test_research_source_replacement.py`: 13 casos de regressão, incluindo falhas, orçamento, duplicatas, URL inválida, prazo, cancelamento e resumo acadêmico.
- `qa-artifacts/source-replacement-public-smoke.json`: resultado público do smoke, sem credenciais ou dados do usuário.

## Verificação

- **121 testes focados passaram**, incluindo coleta paralela, pesquisa adaptativa, segurança e escopo acadêmico.
- Rede real: primeira URL inexistente de `docs.python.org` falhou; a próxima página oficial (`asyncio-task.html`) foi aberta, extraída e persistida em banco temporário. **1,11 s**, duas tentativas debitadas, uma fonte lida, zero chamadas de modelo.
- Suíte completa: **1.289 passaram, 4 ignorados, 2 avisos em 313,65 s**. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. Log local: `qa-artifacts/source-replacement-full.log`.
- `git diff --check`: sem erros.

## Limites e publicação

As tentativas extras usam o mesmo orçamento global, podendo deixar menos páginas para etapas posteriores. A recuperação não contorna bloqueios nem garante fonte alternativa quando todas as candidatas falham. Threads com download iniciado continuam até o timeout existente, sem gravar conteúdo tardio. O smoke testa leitura e persistência, não acurácia geral nem interface autenticada. Este relatório registra a validação local; o resultado da publicação autorizada posteriormente será informado na entrega.
