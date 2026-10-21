# Chaves de provedores e seleção de modelos — 21/10/2026

## Publicação anterior

As correções de histórico, itens salvos, cópia e identidade foram publicadas em `origin/main`, commit `c0308e4f633d27e3de5402b925d7ccaf3f3788a3`. O snapshot publicado passou em 949 testes, com 4 ignorados e 2 avisos. As alterações locais de V5.8 não foram incluídas nesse push.

## Diagnóstico e correções desta rodada

1. **Catálogo cortado antes dos provedores externos.** Agente e relay limitavam o resultado total aos primeiros 500 IDs. Um catálogo grande do proxy podia ocupar toda essa lista; salvar uma chave não fazia os modelos daquele provedor aparecerem. Agora o transporte aceita até 2.000 modelos, com limites de 500 para o proxy e 200 por provedor externo. O agente também passa os metadados `items`, que o relay já esperava, mas não recebia.
2. **Atualizações lentas.** A descoberta consultava os provedores sequencialmente, podendo exceder os 30 segundos de espera do relay. As consultas independentes agora compartilham um pool limitado ao número de provedores, mantendo os timeouts de cada consulta.
3. **Campo apagado por atualização da interface.** A abertura e a atualização da lista recriavam os campos, descartando texto digitado enquanto o catálogo carregava. Rascunhos são preservados apenas no DOM durante essas atualizações; respostas antigas do catálogo são descartadas.
4. **Enter sem salvar.** Cada chave agora tem um formulário com submit tratado. Enter e o botão Salvar executam o mesmo fluxo, sem navegar nem recarregar a página. Durante a gravação, os controles ficam desabilitados para evitar envios duplicados.
5. **Confirmação ambígua.** A confirmação só aparece após o PC confirmar a gravação. O campo fica vazio por segurança, com uma explicação persistente. “Chave salva” não é apresentada como prova de acesso ao provedor. Recusa de autenticação, falha de gravação e falha de atualização de modelos têm mensagens distintas. Uma falha de gravação preserva o texto para nova tentativa.
6. **Seletor amontoado.** Lista mais larga e espaçada, com grupos nesta ordem: Grátis → Suas API keys → Outros, subdivididos por provedor. “Grátis” depende do identificador `:free` anunciado pelo catálogo; não se presume que todo provedor ou proxy seja gratuito. Modelos que exigem chave continuam desabilitados sem configuração. Busca sem resultados não altera silenciosamente o modelo usado nas mensagens. O modelo selecionado aparece por extenso abaixo da lista.
7. **Atalho após salvar.** “Escolher modelo deste provedor” abre a seleção já filtrada. Salvar uma chave não troca automaticamente para um modelo pago.

Não foi reproduzida perda da chave no arquivo `.env`: o teste confirmou gravação, recarga em processo novo e uso da chave no adaptador de streaming. Os defeitos confirmados estavam no catálogo e no fluxo de interface. Nenhuma chave real do usuário foi utilizada ou alterada.

## Arquivos

- `providers.py`: descoberta paralela, limites por provedor e prioridade dos IDs gratuitos.
- `pc_agent.py`, `server.py`: transporte do catálogo completo e metadados sem segredos; compatibilidade com agentes que não enviam o campo opcional `free`.
- `public/app.js`, `public/index.html`, `public/interface.css`, `public/sw.js`: formulários, mensagens, seleção, responsividade e atualização do cache.
- `tests/test_provider_catalog_regressions.py`: persistência em processo novo, streaming com a chave salva, concorrência e catálogo acima de 500 modelos.
- `tests/provider_fixture_agent.py`, `tests/preview_workspace.py`: ambiente descartável com provedor determinístico opcional.
- `qa-artifacts/provider-fixes-20261021/`: script de navegador, resultados, capturas e logs da suíte.

## Validação

- 43 testes focados de provedores aprovados.
- 20 verificações em Chrome aprovadas, sem erros JavaScript: salvar com Enter, recarregar, selecionar, responder via streaming, preservar rascunho durante atualização, falha de gravação, recusa de chave, substituição e remoção.
- Layout conferido em 320, 390 e 1280 px, com capturas inspecionadas.
- Relay, agente, SQLite e gravação no `.env` descartável são reais no teste de navegador. Somente o serviço externo de modelos/inferência é simulado.
- A primeira suíte completa identificou uma incompatibilidade com agentes antigos: o novo campo opcional `free` aparecia como `null`. A resposta foi corrigida para omitir o campo quando ausente, sem alterar ou remover o teste existente. Quatro testes focados desse caminho passaram após o ajuste.
- Resultado final da suíte completa: **965 aprovados, 4 ignorados, 2 avisos**, em 97,05 segundos; log em `qa-artifacts/provider-fixes-20261021/full-suite.txt`. Avisos existentes: descontinuação de `mss.mss()` e de `timeout` no TestClient. As 20 verificações de navegador passaram novamente com o código final.

## Limites e entrega

Não foram feitas chamadas de inferência pagas nem validação com chaves reais. Tarifas, quotas, permissões e disponibilidade continuam dependentes de cada provedor. O teste usa Chrome desktop com viewports móveis, não um celular físico. Esta rodada publica as correções de provedores separadamente das alterações locais de V5.8; o commit citado no início contém a rodada anterior. A atualização real requer publicar também o frontend/relay e reiniciar o agente com o código corrigido.

## Validação da publicação isolada

O snapshot destinado a `origin/main`, sem as mudanças locais de V5.8, passou em **952 testes, com 4 ignorados e 2 avisos**, além das **20 verificações de navegador**. Evidências: `release-suite.txt` e `release-browser-check.json` na pasta de QA desta rodada. O total difere da suíte local porque V5.8 não faz parte desta publicação.
