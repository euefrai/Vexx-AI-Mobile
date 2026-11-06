# Refatoração da pesquisa — progresso em 05/11/2026

## Estado e isolamento

- Branch: `codex/research-contract-refactor`, base `57487fb`.
- Implementação local; sem push, deploy ou reinício de produção nesta etapa.
- Os 35 arquivos previamente alterados foram preservados na implementação inicial. Na retomada, três arquivos de `pc_companion/web/` mudaram fora desta worktree; foram preservados e não fazem parte deste conjunto de publicação.
- Rebrand, permissões de controle remoto e dados reais preservados.

## Implementado — prioridades 0 e contratos da etapa 1

- Catálogo com capacidades; exclusão de modelos incompatíveis com chat; seleção obsoleta rejeitada antes de memória/pesquisa. Catálogo temporário, limitado e separado por configuração, sem rede por mensagem. Seleção explícita nunca substituída silenciosamente.
- Remoção segura de protocolo Longcat em resposta normal e streaming, inclusive marcadores divididos e excesso de buffer. Exemplos em código preservados; payloads nunca executados.
- URL explicitamente solicitada reconhecida com pergunta longa. Identificadores literais preservados na limpeza da consulta, escolha do bloco, janelas documentais e fonte enviada ao modelo. Metadados da leitura explícita não são descartados.
- Comparação utiliza opções efetivamente mostradas; falha de atualização não apaga contexto anterior. Mantém datas originais e informa que não é nova cotação.
- Perguntas sobre documento não viram afirmações de memória; “dados reais” não dispara aviso comercial.
- Relógio independente de clima para quatro municípios com associação IANA exata. Outras cidades conservam o fallback anterior.
- Busca local por caminho, migração FTS transacional/cancelável, contador confirmado e distinção de erro SQLite/timeout. Índice real instalado não foi migrado.
- Contratos da auditoria integrados à suíte regular, sem xfail ou remoção de expectativas.

## Evidência e aceitação

- 12/12 contratos da auditoria passaram.
- Rodada completa final, após os últimos ajustes: **2.786 passaram, 4 pulados, 2 avisos**, em 340,56 s. Não houve falhas.
- Retomada visual concluída em Chromium com janela: comparação por clique, reload, abertura da oferta na página específica KaBuM, leitura pelo composer, fontes e persistência após reload. Viewports 1365, 390 e 320 px; sem overflow horizontal da página nos dois menores. Menu mobile abriu e permitiu selecionar o chat. Não é teste em celular físico nem aceite universal de toda a UI.
- O teste visual encontrou e corrigiu contagem de produtos mencionados apenas nas referências e card de fonte que mostrava o sumário em vez da passagem sobre o erro. Regressões adicionadas.
- API real do laboratório, sem mocks: seis produtos KaBuM com URLs de produto; comparação de quatro das seis opções (limite do componente informado na resposta), JDUI `productcompare`, persistência SQLite, replay idêntico e uma única resposta.
- API/SSE real: leitura de `sqlite.org/wal.html`, resposta em português com as três causas documentadas de `SQLITE_BUSY`, citação, JDUI de fontes e persistência; 14,59 s, sem protocolo cru.
- Recibo público: `qa-artifacts/research-refactor-20261105/real-stack-result.json`.
- Retomada visual: `qa-artifacts/research-refactor-20261105/browser-validation.json`; imagens locais em `output/playwright/research-refactor/`.
- Laboratório encerrado com segurança: Agent development 13940 e relay local 28272 parados, dados preservados; produção não foi reiniciada.

## Limites e próximo passo exato

As prioridades iniciais foram implementadas e os cliques/reload previstos foram repetidos. A publicação depende da suíte final com os dois ajustes encontrados na UI; o plano inteiro não está concluído.

1. Concluir a suíte final, registrar o resultado e publicar apenas este conjunto validado. Depois iniciar o contrato imutável da etapa 2. Uma resposta longa repetida terminou no meio da citação; o pedido conciso em novo chat completou. Manter a investigação de término/truncamento na fase de síntese.
2. Introduzir `ResearchRequest` imutável por adaptador no job existente, preservando owner, pergunta, entidades/variantes, restrições e origem até as evidências. Não reescrever persistência e UI juntos. Testar replay e cancelamento.
3. Rastrear descoberta por provedor e consulta sem URL; distinguir bloqueio, indisponibilidade, timeout, falta de correspondência e orçamento. A recuperação com URL fornecida não aprova descoberta autônoma.
4. Calibrar síntese com gabaritos públicos revisados (incluindo Python TaskGroup/gather). Corrigir o aviso desnecessário do modelo sobre releitura, mantendo limitações reais. Não relaxar suporte/citações.
5. Apresentador único de resultados; IDs estáveis para ações dos cards, condição de pagamento e citações literais seguras. Tratar também a representação sensível atrás de sessão expirada, identificada na auditoria.

Não publicar como pesquisa universal/perfeita. CAPTCHA, disponibilidade de provedores e acesso a fontes continuam sujeitos a limites externos. Não há bypass implementado.
