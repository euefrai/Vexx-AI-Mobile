# Refatoração da pesquisa — 05/11/2026

## Resultado desta etapa

Implementadas as prioridades imediatas do plano aprovado e os contratos de estabilização, em worktree isolada baseada na revisão publicada `57487fb`. As alterações ainda são locais. Esta entrega não conclui as fases de contrato único, descoberta autônoma, calibração geral de síntese e apresentação unificada.

## Problemas e correções

| Problema confirmado | Correção |
| --- | --- |
| Modelos de embedding/áudio e IDs removidos oferecidos ao chat | Metadados de capacidades preservados no catálogo; filtro conservador quando ausentes; validação local antes do trabalho pesado; erro acionável no seletor. |
| Default implícito removido, apesar de catálogo recente válido | Reutilização de opção gratuita do catálogo atual. Escolha explícita continua explícita e é rejeitada com orientação quando indisponível. |
| Protocolo `<longcat_tool_call>` visível ao usuário | Sanitização batch/stream com marcadores incrementais, exemplos literais preservados e descarte seguro do corpo excessivo. Nenhum código do modelo é executado. |
| URL explícita com pergunta longa desviada para descoberta | Reconhecimento do comando de leitura, preservando rejeição de links incidentais/negados e controles existentes de download. |
| Passagem de `SQLITE_BUSY` perdida em diferentes etapas | Preservação do identificador na consulta; seleção do bloco/janela e projeção da fonte ancoradas no símbolo. A janela de evidência usa o teto existente de 3.600 caracteres por fonte. Não promove suporte semântico. |
| Leitura explícita descartava escopo, seções e passagens da extração | Metadados necessários repassados para a fonte; resumo não vira texto completo. |
| Comparar disparava nova busca e podia apagar as opções mostradas | Comparação do conjunto da resposta anterior com data original; falha de atualização não substitui contexto por resultado vazio. |
| Repetir comparação contava produtos presentes somente nas referências | Contexto visível extraído dos itens JDUI validados, com correspondência por URL; JSON de referências não é tratado como produto exibido. Prosa antiga mantém fallback. |
| Card SQLite ainda mostrava o sumário numerado | Excerpt ancorado cabe no teto visual; pontuação de sumários não vence a explicação do identificador. Corrigido após reprodução real no navegador. |
| Pergunta sobre prazo de documento virava proposta de memória | Perguntas não são tratadas como afirmações pessoais. |
| “Dados reais” acionava aviso comercial | Correspondência comercial com limites de palavra e sem esse gatilho genérico. |
| Relógio de Brasília dependia de chave meteorológica | Associação exata de município/fuso IANA para Brasília, São Paulo, Salvador e Recife. |
| Busca por pasta/caminho não encontrava arquivos | FTS5 indexa nome e caminho; migração transacional em segundo plano, cancelamento e rollback. |
| Qualquer erro SQLite era mostrado como timeout; contador zerava durante falha | Códigos distintos; contador confirmado por lotes e reconciliado ao finalizar. |

## Arquivos alterados

- `providers.py`, `hermes_bridge.py`, `inference_status.py`: capacidades, catálogo temporário e defaults.
- `pc_agent.py`, `public/app.js`: validação de seleção, orientação do seletor e candidatos de memória.
- `tool_protocol.py`: sanitização incremental.
- `research.py`, `web_extract.py`: rota de leitura e preservação de evidência literal.
- `conversation_followups.py`: comparação e continuidade.
- `intent.py`, `live_data.py`: contexto comercial e relógio.
- `pc_companion/indexer.py`: índice, migração e diagnóstico.
- `tests/conftest.py`, `tests/test_ui_polish.py`, `tests/test_research_audit_contracts.py`, `tests/test_research_refactor.py`: regressões e isolamento do catálogo entre testes.
- Este relatório, `docs/RESEARCH_REFACTOR_PROGRESS.md` e recibos em `qa-artifacts/research-refactor-20261105/`.

## Testes e evidências

### Contratos e regressões

Os 12 contratos da auditoria passaram por correções de implementação. Os contratos foram integrados à suíte regular. Testes adicionais cobrem protocolo em chunks e excesso de buffer, capacidades declaradas, catálogo expirado ou de outra credencial, rejeição antes de pesquisa/memória, default implícito versus explícito, migração de índice legado, rollback/retry, contagem, comparação sem refresh e leitura completa pelo pipeline.

A primeira suíte da implementação encontrou duas incompatibilidades de frontend/harness. A renderização de erro passou a ser não bloqueante e o harness passou a carregar o novo helper real, preservando o teste de envio rápido e adicionando rejeição sem fetch. Rodada posterior: **2.785 passaram, 4 pulados e 2 avisos**. Após os últimos ajustes de leitura/capacidade, os **56 testes focados passaram**. A rodada completa final terminou sem falhas: **2.786 passaram, 4 pulados e 2 avisos**, em **340,56 s**, usando `pytest -q -rs --durations=8`.

As verificações externas puladas na rodada anterior envolveram síntese real sem provedor operacional e descoberta comercial recusada/sem resultados. Não equivalem a aprovação de integração. Avisos existentes: API de captura `mss` e timeout do `TestClient` Starlette.

Syntax check dos 13 arquivos JS próprios passou, respeitando módulos ES. Os harnesses de stream remoto em modo padrão e desktop passaram. Não são testes em celular físico.

### Fluxos reais no laboratório

Relay, Agent e SQLite separados, conta descartável e controle remoto desativado. Pesquisa e geração reais, sem respostas de modelo nem páginas de loja simuladas:

1. Relógio Brasília executado pela UI sem chave meteorológica: retornou data/hora pelo fuso IANA.
2. Pesquisa de RTX 3050 6 GB enviada pela UI: seis produtos retornados e salvos. As seis URLs são páginas `/produto/...` da KaBuM. Isso não prova acesso universal a lojas nem valida preço para consultas futuras.
3. Comparação executada pela API real do mesmo chat: quatro das seis opções (limite informado na resposta), `productcompare`, aviso de data original, persistência em SQLite, replay idêntico e somente uma resposta por ID. Na retomada, o botão Comparar foi clicado em Chromium com janela; o comparativo persistiu após reload. A repetição encontrou e corrigiu a contagem de referências como produtos visíveis; a resposta passou a informar quatro das quatro opções efetivamente exibidas.
4. Leitura explícita da documentação pública SQLite por API/SSE real: **14,59 s**, **3.322 caracteres**, resposta em português, citação `[S1]`, componente JDUI `sources`, símbolo literal e persistência. Revisão do conteúdo confirmou os três casos: bloqueio exclusivo, limpeza da última conexão e recuperação após crash. Nenhum protocolo cru foi exposto.

O modelo ainda acrescentou um aviso desnecessário sobre não ter feito outra leitura independente. A resposta factual estava correta e a fonte havia sido recuperada pelo sistema; a redação/estado apresentado continua pendente na fase de síntese. Não esconder essa limitação com remoção de validação.

### Retomada visual antes do push

Sessão Playwright CLI isolada, banco copiado somente do laboratório anterior, nenhum mock de rede ou modelo. Foram executados login descartável, clique em Comparar, repetição da comparação, reload, envio de pergunta pelo composer, leitura das respostas e fontes, menu mobile e abertura de oferta em nova aba. O navegador abriu `kabum.com.br/produto/998334/...`, título **GPU PCYES RTX 3050 6GB GDDR6 | KaBuM!**; não foi homepage da loja.

A fonte SQLite e a resposta com os três casos corretos persistiram após reload. O card passou a exibir uma passagem sobre o erro em vez do sumário. Viewports 1365, 390 e 320 px foram inspecionados; largura do documento igual à viewport nos dois menores. O menu mobile abriu, permitiu selecionar chat e fechou (`aria-hidden=true`). O seletor observou 450 opções e nenhuma de embedding/rerank.

Console após reload final: zero erros e zero avisos. Antes houve 401 de sessão não autenticada e um 503 do status do companion durante reinício deliberado do Agent de desenvolvimento. Não foram tratados como prova de bug de produção. Uma resposta com longa transcrição repetida terminou no meio da citação; uma pergunta concisa em novo chat completou. Esse comportamento de término/citação permanece na investigação de síntese, sem alegação de completude universal.

Recibo da retomada: `qa-artifacts/research-refactor-20261105/browser-validation.json`. Screenshots locais em `output/playwright/research-refactor/` (ignoradas pelo Git). Não foi realizado teste em celular físico.

Recibo sanitizado: `qa-artifacts/research-refactor-20261105/real-stack-result.json`. Credenciais, bancos, prompts pessoais e logs operacionais completos não foram adicionados ao repositório.

## Riscos e pendências

- Os cliques/reload previstos foram concluídos nos cenários descritos. Isso não aprova todas as telas e integrações do sistema. A revisão de término/truncamento de citações longas continua pendente.
- A leitura conhecida e a resposta correta de SQLite aprovam este cenário com URL fornecida; descoberta sem URL e generalização da síntese continuam pendentes.
- Fases seguintes: `ResearchRequest` imutável por adaptadores, diagnóstico por provedor, recuperação dirigida por lacunas e gabaritos de síntese. Próximos passos detalhados no arquivo de progresso.
- O reconhecimento de identificadores prioriza símbolos com underscore. Não é um parser universal de nomes técnicos nem substitui decomposição correta dos requisitos.
- Migração FTS é derivada e transacional, mas exige CPU, disco temporário e escrita proporcional ao índice. Não foi aplicada ao índice real instalado, de cerca de 1,2 GB. O teste de inserção de 100 mil itens variou entre 8 e 30 s nas rodadas; não é evidência de ganho de indexação. A consulta continua coberta pelo limite do teste de latência.
- Relógio sem clima está resolvido para os quatro municípios mapeados e fusos IANA explícitos; outras cidades ainda usam o fallback existente.
- Condição de pagamento junto ao preço, IDs estáveis de comparação, citações literais no renderer, histórico atrás do login expirado e linguagem dos status do PC permanecem itens da auditoria.
- Sem bypass de CAPTCHA, mudança de permissões remotas, alteração da extensão Júlia ou do Fajulto Studio.

## Preservação operacional

A conferência inicial preservou os hashes dos 35 arquivos previamente modificados no checkout principal. Na conferência da retomada, 32 permaneceram iguais e três arquivos de `pc_companion/web/` haviam sido modificados fora desta worktree (app.js, index.html e style.css, entre 21:03 e 21:07 BRT). Não foram sobrescritos nem incluídos no conjunto a publicar. O Agent de produção permaneceu `RUNNING`, PID 23260, sem reinício nesta implementação. Os dois laboratórios foram encerrados após verificar processo, banco e papel `development`, com dados preservados; o último encerrou Agent 21924 e relay local 29740. O push para main foi autorizado após as validações. A revisão do Agent em execução não muda automaticamente com o push.
