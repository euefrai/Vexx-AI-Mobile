# Auditoria operacional do Vexx AI — 05/11/2026

## Conclusão

O sistema tem componentes funcionais, mas a pesquisa profunda ainda não entrega respostas completas de forma consistente. A mesma revisão passou em 2.755 testes existentes e falhou em usos reais importantes. Os maiores problemas observados foram descoberta sem resultados em uma pergunta técnica independente, síntese rejeitada após leitura correta, comparação que perde o contexto, catálogo de modelos sem filtro de capacidade e regras globais que contaminam respostas de documentos.

Não atribuir todas as falhas a CAPTCHA: no caso SQLite nenhuma página chegou a ser lida; no caso Python a leitura funcionou e a síntese foi rejeitada; no caso comercial houve seis ofertas. Cada falha exige tratamento na etapa correta.

Esta entrega inclui auditoria por risco, testes reais no laboratório, inspeção do aplicativo Windows, novos contratos de aceitação e plano de refatoração. Na primeira rodada, o controle visual do Brave foi interrompido por falta de confirmação segura da URL. **Na retomada, os testes autenticados dos principais fluxos foram executados na aba do Vexx ao lado do chat**, após login realizado pelo usuário, a partir das 16:08 BRT. O controle do Brave não foi contornado. A retomada confirmou falhas da pesquisa na versão publicada; não é aprovação de todas as funcionalidades ou pentest completo.

## Revisões, dados e reinício

- Revisão publicada e usada como baseline: `57487fbfc89dea12ee74b909fa192e7c289d5388`.
- Checkout principal permaneceu em `624068e4953cf3c948d5952fade259e66d4af480`, com 35 arquivos rastreados previamente modificados. Seus hashes foram comparados no início e no fim: **nenhum mudou nesta auditoria**.
- O baseline foi exportado para uma cópia isolada, sem `.env` ou banco real. As conclusões de código referem-se à revisão publicada, não à mistura de alterações pendentes do checkout principal.
- O Agent anterior, PID 9552, executava checkout antigo `e91fc2e`, com alteração local. Foi encerrado por IPC autenticado, sem parada forçada.
- O Agent novo, PID **23260**, usa o worktree limpo da revisão publicada `57487fb`. Foi verificado como `production`, `RUNNING`, sem operações ativas e conectado ao relay. Uma nova consulta ao IPC no encerramento confirmou que continuava rodando.
- Backup privado antes da troca; integridade SQLite `ok`; 335 mensagens imediatamente antes e depois do reinício. Isso não significa congelar a contagem durante o uso posterior.
- O laboratório usou conta sintética, banco separado, endereço apenas em loopback e `JULIA_REMOTE=0`. Os processos de desenvolvimento foram encerrados ao final; seus dados foram preservados.
- Não houve push, deploy, mudança de credenciais reais, ampliação de permissões, exclusão de dados ou alteração da extensão Júlia/Fajulto Studio. A configuração de inicialização automática do Agent não foi alterada.

## Validação executada

| Verificação | Resultado e limite |
|---|---|
| Suíte completa do baseline publicado | **2.755 passaram, 4 pulados, 2 avisos**, em 587,01 s; Python 3.14 no Windows |
| Novos contratos de aceitação | Primeira rodada: 3 passaram e 7 falharam; retomada: **3 passaram e 9 falharam**, sem `xfail` ou skips; duas perdas adicionais reproduzidas |
| Sintaxe JavaScript | 13 arquivos próprios de `public/` e `pc_companion/web/`, sem erros; módulos 3D conferidos como ES modules |
| Harness remoto mobile | Passou: frames, descarte de blobs, batches, composição, Unicode, gestos, cancelamento e ordenação; simulação, não celular físico |
| Harness remoto desktop | Passou: somente preparação, sem abrir conexão nem solicitar frames |
| Produção sem autenticação | `/api/health` e `/api/diag` responderam 200; `/api/session` e `/api/account`, 401; cabeçalhos CSP, no-store e anti-frame presentes |
| Console do laboratório | Nenhum warning/error capturado nas consultas realizadas; não equivale a cobrir toda interação possível |
| Preservação de WIP | 35/35 arquivos anteriores com o mesmo SHA-256 |

Os 4 testes pulados não são contabilizados como integração aprovada. A suíte completa não foi repetida depois de alterações apenas em documentação e no arquivo de contratos: nenhum código do baseline foi modificado.

Os contratos estão em `tools/audit_cases/contracts_20261105.py`, executados explicitamente com `PYTHONPATH` apontando para o baseline. O arquivo não usa o prefixo da coleta automática: é uma especificação de aceitação desta auditoria, ainda com falhas conhecidas. **CI verde não aprova esses nove critérios**. Após corrigi-los, transferir os casos aplicáveis para a suíte regular, sem enfraquecer as expectativas.

Comando de reprodução, a partir do diretório da revisão sob auditoria, sem carregar credenciais reais:

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:JULIA_ENV_FILE = Join-Path $env:TEMP 'vexx-audit-no-env'
python -m pytest <caminho-absoluto>/tools/audit_cases/contracts_20261105.py -q --tb=short
```

Evidências locais: `qa-artifacts/system-audit-20261105/validation-summary.json`, `research-trace.json`, `new-contracts.log`, `baseline-summary.txt` e `deep-research-running.jpg`. Não contêm chaves, senhas reais ou conversas pessoais; o recibo e o backup operacional continuam no diretório privado fora do Git.

## Uso real pela interface

Interações executadas por controles visíveis do navegador/aplicativo, com respostas de rede/modelo reais no laboratório, sem fixtures de busca ou de resposta:

| Cenário | Observação |
|---|---|
| Entrar com conta sintética | Login concluído; PC conectado |
| Criar projeto, criar chat dentro dele, renomear projeto | Funcionou; criou duas conversas no mesmo projeto |
| Mover e renomear conversa no mobile | Funcionou; conversa passou para Sem projeto e projeto voltou a conter uma conversa |
| Reload dos cards de compra | Seis cards e links continuaram disponíveis |
| Menu mobile | Abriu, permitiu organizar chat e fechou; layout emulado em 390 × 844, sem overflow horizontal medido |
| Hora e data em Brasília | Retornou erro de chave meteorológica no laboratório, em vez da hora |
| Python TaskGroup × gather | Descobriu e leu documentação oficial; síntese final rejeitada; entregou trechos em inglês com lacunas |
| RTX 3050 6 GB no Brasil | Seis cards de oferta com nomes, preço, imagem, estoque e URL de produto |
| Primeira oferta aberta fora do Vexx | Página KaBuM do SKU 998334, modelo correto, R$ 1.443,99 no Pix; não foi homepage/listagem |
| Botão Comparar do primeiro card | Voltou sem alternativa, apesar das seis ofertas anteriores; não apresentou comparação |
| Trocar compras por notícias de Ubatã | Não manteve o assunto GPU; trouxe três matérias de 05/11/2026 do Ubatã Notícias, com trecho recuperado e permalink |
| Pesquisa profunda SQLite WAL × rollback | Interrompida sem evidências: três buscas, três falhas de descoberta e zero páginas lidas |
| Upload de TXT e pergunta sobre seus dados | Acertou orçamento R$ 1.200,00, 12 sensores e prazo 20/11/2026; acrescentou sugestão de memória e aviso comercial indevidos |
| Provedores, memória, documentos e Meu PC | Inspeção de telas/estados; catálogo inclui modelos inadequados, memória vazia, Meu PC desktop exibe preparação e não controle |
| Vexx PC 1.4.0 instalado | Painel real mostrou erro no índice; busca por nome inexistente retornou mensagem de timeout |

Somente a primeira oferta foi conferida manualmente na página externa. As outras cinco tinham URLs de produto no DOM, mas não foram todas visitadas. O clique em nova aba exigiu abrir o destino observado pelo navegador de auditoria; não foi declarado defeito de abertura do Vexx a partir dessa limitação da ferramenta.

O laboratório não copiou a chave meteorológica da configuração real. Assim, o erro de chave é evidência do **acoplamento indevido do relógio à meteorologia**, não prova de falta da chave em produção. Não houve teste de clima real nesta rodada.

### Retomada: testes autenticados na versão publicada

Projeto criado pela interface: **Auditoria 05-11 — Produção**, com conversas identificadas. Conversas anteriores não foram editadas nem apagadas. A versão publicada continuou `57487fbfc89d`.

| Caso | Resultado em produção |
|---|---|
| Hora/data em Brasília | Funcionou: 05/11/2026, 16:08; expôs escapes literais como `\(` e `Sao\_Paulo` no texto |
| RTX 3050 6 GB | Seis ofertas, com as mesmas URLs de produto verificadas no laboratório |
| Comparar pelo card | Falhou novamente, retornando que não confirmou outra opção |
| Notícias de Ubatã após compras | Três matérias de 05/11, com conteúdo recuperado e permalinks; sem mistura com GPU |
| Reload autenticado | Sessão restaurada; **6 ofertas e 3 cards de fonte** preservados |
| SQLite profundo, sem URL | `rj-a32756273897`: três buscas, zero páginas; cada tentativa registrou cinco falhas de provedor |
| Python, modelo antigo | `rj-3269df5848de`: documentação lida; síntese bloqueada por `modelo-nao-encontrado` |
| Python, modelo disponível | `rj-15358d2319b7`: documentação lida; síntese bloqueada por `timeout` |
| URL explícita SQLite | Resposta exibiu `<longcat_tool_call>browser_navigate…`; chamada não executada; erro e sugestão de memória indevida persistiram após reload |

O modelo antigo efetivamente enviado era `poolside/laguna-s-2.1:free`, ausente do catálogo atual. O seletor tinha valor vazio, embora o pedido mantivesse esse ID via preferência local. Para testar um modelo presente, a seleção desta aba foi alterada pela UI para **`meituan/longcat-2.5:free`**, permanecendo assim. Essa é uma preferência local deste navegador; não corrige a configuração dos outros aparelhos. Não foram alteradas chaves, permissões ou configurações de produção no servidor.

Uma leitura real da URL conhecida `https://www.sqlite.org/wal.html` terminou em 1,64 s, sem CAPTCHA. Porém, o recorte exportado como texto lido não continha a informação sobre `SQLITE_BUSY`. Uma segunda seleção sobre o mesmo conteúdo mostrou que uma pergunta mais específica podia escolher um bloco de checkpoint e perder esse identificador. O contrato sintético reproduz a perda após normalização de fonte sem depender da rede.

Um diagnóstico limitado com a consulta curta `SQLite WAL SQLITE_BUSY` encontrou candidatos em StackExchange/HN, enquanto o pedido completo com “documentação oficial” prioriza Bing/DDG/Wikipedia. Foram inspecionados os títulos e destinos: há uma pergunta pertinente sobre BUSY, outros resultados parciais e também um irrelevante; **não são oito evidências válidas nem substitutos aprovados de documentação oficial**. Isso aponta recuperação por entidades e navegação até fontes primárias como investigação útil, sem afrouxar autoridade/relevância.

Evidências adicionais: `production-shopping.txt`, `production-python.txt`, `production-python-current-model.txt`, `production-known-source.txt`, `production-trace.json`, `production-after-reload.jpg`, `sqlite-known-source.json`, `sqlite-passage-probe.json`, `discovery-probe.json` e `retry-contracts.log`. São dados dos testes sintéticos e fontes públicas. Console: nenhum warning/error capturado na consulta final. Agent PID 23260 continuou `RUNNING`, sem operações ativas; 35 hashes anteriores continuaram intactos.

## Achados priorizados

### P1 — afetam a utilidade central

**A01. Descoberta profunda pode terminar sem uma única leitura.** A pergunta SQLite teve `buscas=3`, `paginas=0`, agregado de provedor `nenhum` com três falhas e resultado interrompido. Não existe evidência nesta execução de bloqueio CAPTCHA da documentação SQLite: o fluxo nem chegou nela. O resumo agregado perde a causa útil de cada provedor; a recuperação ainda usa formulações longas próximas do pedido original. Pontos de inspeção: `research.py:_buscar_orquestrado`, `search_orchestrator.py:pesquisar/pesquisar_com_recuperacao`, `research_agents.py:executar`. A disponibilidade universal da descoberta não está aprovada.

**A02. Leitura relevante não se transforma consistentemente em resposta.** No caso Python foram três buscas, uma página lida, sem falha de leitura. A evidência contém a diferença entre propagação de exceções e cancelamento de TaskGroup/gather. A tentativa de síntese terminou com `semantic_support_rejected`; a interface publicou síntese extrativa em inglês. O critério léxico marcou ambos os requisitos de cancelamento como parcialmente sustentados. Pontos: `research_agents.py:_synthesis_context/agente_sintetizador`, `research_synthesis.py:generate/check_support`, `evidence_graph.py:_passage_support`. É preciso comparar texto gerado, citações e revisão com um gabarito humano antes de afirmar que houve falso positivo do validador. Não remover validações para produzir texto mais completo.

**A03. Comparar é tratado como buscar outro produto e pode apagar o contexto útil.** `public/jdui.js:2313` envia somente uma frase com o nome do produto. `conversation_followups.py:product_reply` entra no fluxo de alternativas, pesquisa novamente e salva o resultado filtrado mesmo vazio. Isso torna a última consulta vazia e compromete referências posteriores. Reprodução por clique e contrato `test_failed_product_refresh_preserves_displayed_context`. Falha de atualização deve ser um resultado de tentativa separado, preservando o conjunto que o usuário viu e seus horários de verificação.

**A04. O seletor oferece modelos sem capacidade adequada ao chat.** A tela real listou embeddings, áudio/live/TTS e outros modelos especializados. `providers.py:182-239` transforma IDs retornados em opções sem um contrato de capacidades. A presença de chave ou de ID no catálogo não prova geração de texto/stream/JSON. Contrato `test_chat_model_catalog_does_not_offer_embeddings`. Evitar apenas uma blacklist de nomes: preservar metadados de capacidade do provedor e manter uma curadoria conservadora quando eles não existirem.

**A16. Uma seleção antiga continua sendo enviada mesmo ausente do catálogo.** Reproduzido em produção. `public/app.js:modeloAtivo` lê diretamente a preferência local; `fillModels/loadModels` sinalizam indisponibilidade na área de modelos, mas não impedem o envio. O usuário pode ver o seletor vazio e só receber uma pesquisa interrompida depois de descoberta e leitura. Validar o modelo antes do trabalho caro; oferecer seleção explícita de um modelo compatível e informar a causa no próprio chat. Não trocar silenciosamente uma escolha explícita por outro provedor. Modelo presente também não prova disponibilidade: a tentativa seguinte teve timeout.

**A17. Uma página acessível perde o trecho que responde à pergunta.** Na leitura SQLite, o texto extraído com consulta geral continha `SQLITE_BUSY`, mas a janela de 1.200 caracteres exposta por `_fonte_de/_janela_lida` não; a consulta específica também alterou a seleção de bloco e perdeu o identificador ainda na extração. Contrato `test_known_document_keeps_passage_answering_the_named_error`. Auditar separadamente escolha do bloco, janelas do documento e projeção da fonte. Não resolver só aumentando o texto enviado ao modelo: preservar passagem alvo, contexto de seção e offsets dentro do orçamento.

**A18. Dialeto de ferramenta do modelo escapa do filtro e chega ao chat.** Caso real com `<longcat_tool_call>` e argumentos de navegação persistidos como resposta. `tool_protocol.py` reconhece o marcador genérico `<tool_call>`, não esse dialeto. Não houve execução da chamada, mas houve quebra do protocolo de apresentação. Contrato `test_native_longcat_tool_call_is_filtered_without_execution`, incluindo fragmentação em chunks. Normalizar/rejeitar dialetos suportados e produzir erro seguro; preservar menções literais em documentação/código e limites de buffer. Não implementar execução automática dessas chamadas para tentar corrigir o vazamento.

### P2 — correção, privacidade local e UX

**A05. Relógio de cidade depende da API meteorológica.** `live_data.py:417-437`, especialmente 430: geocodificação sem timezone chama `_weather_data`. Consultar hora pode consumir quota meteorológica, acrescentar rede e falhar por chave/clima. O caminho IANA explícito funciona sem essa dependência. Contrato falhando para Brasília e dois controles passando para UTC/America/Bahia. Resolver fusos por fonte apropriada e declarar ambiguidade em cidades homônimas.

**A06. Valores financeiros de documento recebem aviso falso de compra.** Resposta correta do TXT foi seguida por “são do meu conhecimento geral” e instrução para confirmar na loja. `intent.py:423-490` usa termos como `reais` e números monetários sem distinguir a origem dos dados; o próprio texto “não contém dados reais” contribui para o falso contexto comercial. `pc_agent.py:3543-3567` acrescenta o aviso globalmente. Contrato `test_document_budget_does_not_get_a_shopping_disclaimer`. A origem documento/cálculo/oferta precisa acompanhar cada afirmação; aviso de compra só deve valer para afirmação comercial correspondente.

**A07. Uma pergunta é transformada em candidata a memória pessoal.** `pc_agent.py:1133-1175` aplica regex de evento/prazo a uma pergunta sobre o documento. Resultado real: “Posso guardar o Órbita? Use apenas o documento”. A confirmação protegeu contra gravação automática, mas a proposta é ruído e pode induzir confirmação sem sentido. Contrato `test_question_about_document_deadline_is_not_a_personal_memory`. Distinguir declaração pessoal explícita de pergunta, citação, hipótese e conteúdo de terceiros.

**A08. Busca local não cumpre a promessa de pesquisar parte do caminho.** UI oferece “Nome, extensão ou parte do caminho”, mas `pc_companion/indexer.py:31` mantém `path UNINDEXED` e `search` busca somente `names MATCH`. Arquivo dentro de pasta correspondente não é encontrado quando seu nome não contém a consulta. Contrato `test_file_search_finds_part_of_parent_path`. Definir separadamente nome, ancestral/caminho, extensão e filtros, com índices que respeitem esses contratos e sem varrer disco por consulta.

**A09. Erros SQLite são apresentados como timeout.** `pc_companion/indexer.py:190-195` captura qualquer `OperationalError` e retorna “limite de tempo”. Um teste com tabela FTS ausente reproduz a falsa mensagem. Distinguir `SQLITE_INTERRUPT` causado pelo orçamento de execução de tabela ausente, lock, disco cheio ou corrupção; registrar código de erro sem caminhos sensíveis no log público.

**A10. Índice instalado realmente está em falha e seu estado é pouco confiável.** O painel Windows mostrou `OperationalError` e 1.792 entradas, enquanto uma consulta somente leitura contou 1.001.230 registros; o banco tinha cerca de 1,2 GB. `scan()` zera o contador e só o reconcilia no caminho de sucesso. O erro original é descartado, impedindo concluir se a causa foi lock, armazenamento ou outra falha. Uma verificação ampla desse índice foi interrompida por custo; **não há diagnóstico de corrupção**. Usar contador confirmado separado do progresso da varredura, checkpoint por lote, telemetria de falha e orçamento de I/O. Não reconstruir/apagar o índice real sem revisão específica.

**A11. Histórico continua no DOM atrás do login expirado.** Observado no site publicado antes da autenticação. `public/app.js:1712-1724` apenas exibe o overlay na falha de sessão; outras rotas de 401 fazem o mesmo. Isso não prova vazamento via API: os dados já estavam no IndexedDB deste navegador e os endpoints anônimos testados retornaram 401. Há risco em computador compartilhado e para leitor de tela/foco. Limpar a representação visual sensível e tornar o restante da aplicação inerte enquanto não autenticado, preservando o histórico local conforme política do produto.

**A12. Trechos técnicos perdem a representação literal ao virar Markdown.** No corpo da síntese extrativa, `__aexit__()` apareceu como `aexit()`; no card de fonte o identificador continuou correto. Um trecho de origem não deve ser reinterpretado como formatação. Renderizar citações como texto seguro com proveniência/offset, separadamente de Markdown autoral; testar underscores, asteriscos, tabelas e URLs literais. Não liberar HTML arbitrário do modelo.

**A13. Preço não informa a condição de pagamento junto ao valor.** Primeiro card: R$ 1.443,99; página visitada: esse valor é à vista no Pix, com outro total parcelado. O aviso genérico “confira pagamento” não substitui a condição da oferta. `shopping.py:_jdui_produto`, `jdui.py:_v_oferta` e `public/jdui.js:productCard` precisam preservar a condição quando efetivamente extraída, mantendo “não informada” na ausência, sem dedução.

**A14. “PC conectado” e “Vexx PC offline” aparecem na mesma tela.** No laboratório o primeiro é o Agent central e o segundo é o companion da conta, portanto a infraestrutura não é necessariamente contraditória. A linguagem é ambígua para o usuário. Separar “IA disponível” de “Seu computador vinculado” e mostrar qual permissão/sessão falta. O desktop exibiu preparação corretamente; nenhuma permissão nova foi concedida.

**A15. Operação pode voltar para checkout antigo após nova inicialização.** Antes do reinício o processo estava em revisão antiga, órfão de supervisor ativo, enquanto Render e worktree publicado já estavam adiante. A troca desta rodada corrigiu o processo atual, mas inicialização automática/reboot não foram validados. Consolidar manifesto de versão, origem de configuração, processo único, parada graciosa e verificação de versão em cada início. Não anunciar consolidação de startup como concluída.

### P3 — manutenção e riscos de evolução

- `mss.mss()` emite depreciação no teste real de captura; migrar para a API suportada antes de ampliar dependências. Há também aviso do timeout do TestClient. Não são falhas de usuário comprovadas nesta rodada.
- Dependências têm faixas de versão, sem lock reproduzível observado no baseline; a suíte local usou Python 3.14, CI declara 3.12 e o Agent real usa 3.12. Validar essa matriz na publicação, incluindo runtime empacotado.
- `pc_agent.py:run` tem aproximadamente 802 linhas e o arquivo 6.156; `research_agents.py:agente_analista`, aproximadamente 677 linhas. São sinais de acoplamento e risco de mudança, não evidência isolada de bug.
- A UI mistura mensagens, modelos, IndexedDB, jobs e apresentação num grande controlador. Refatorar por contratos e efeitos, sem normalizar indiscriminadamente `public/app.js`, que já contém peculiaridades de encoding/EOL no trabalho anterior.
- A infraestrutura de relay/Agent central é um ponto comum de indisponibilidade. Cotas por usuário e limites existem, mas a experiência de pesquisa depende da saúde desse processo e dos provedores.

## O que se mostrou preservado

Revisão de rotas/código e suíte existente cobriram autenticação, CSRF, isolamento por owner, revogação, persistência, permissões remotas, limites e segurança de leitura. Os caminhos inspecionados usam cookie HttpOnly/SameSite Strict, CSP e controle explícito; chamadas de ferramenta geradas como texto não são autorização para execução (`tool_protocol.py`). O cache público continua tendo limites, escopo por usuário e revalidação; fontes bloqueadas não devem virar evidência de conteúdo lido.

Isso não é atestado de ausência de vulnerabilidades nem pentest completo. Não foram executados carga hostil em produção, exploração destrutiva, troca de credenciais, pareamento de dispositivo real ou concessão permanente de controle. As permissões existentes foram preservadas.

## Plano de refatoração, em etapas pequenas

### 0. Prioridade revista após a produção

1. Bloquear seleção obsoleta/incompatível antes de descoberta e leitura, com ação clara no chat. Distinguir ID removido de timeout, quota e falha de validação; não esconder tudo sob “provedor indisponível”.
2. Fechar o vazamento de dialetos de ferramentas em batch e streaming, sem executar payloads. Verificar a rota de leitura de URL explícita para que ela não dependa de um pedido de navegação gerado pelo modelo.
3. Corrigir a perda da passagem sobre identificador explícito na escolha de bloco e na janela da fonte, com limites e offsets preservados.
4. Corrigir comparação/contexto, antes de ampliar provedores ou adicionar funcionalidades.

Os testes reais de produção devem ser repetidos depois dessas correções. Catálogo carregado, página lida e job finalizado não são critérios suficientes de sucesso.

### 1. Estabilizar os contratos quebrados antes de ampliar busca

Corrigir A03–A09 e catálogo primeiro, com commits separados e os sete contratos vermelhos tornando-se verdes por correção de causa. Cobertura de controle deve continuar passando: IANA sem clima, nome acentuado/consulta com aspas, owner e cancelamento. Incluir condições de pagamento no esquema só quando recuperadas da fonte. Tratar o índice instalado como trilha operacional independente, sem bloquear a pesquisa web nem apagar dados reais.

**Aceitação:** 12/12 contratos, regressões correspondentes integradas à suíte regular, suíte completa sem novas falhas, reprodução dos mesmos cliques/perguntas pela UI.

### 2. Introduzir um contrato único do pedido e de cada etapa

Extrair do controlador um `ResearchRequest` imutável com pergunta original, intenção, entidades, atributos, local, janela temporal, idioma, owner, restrições e origem. Adaptadores devem recebê-lo sem reconstruir condições a partir de frases geradas. Criar resultados tipados de descoberta, leitura, seleção de passagens, síntese e publicação, preservando códigos como provider_unavailable, rate_limited, blocked, unreadable, no_match, budget_exhausted e validation_rejected.

Mover estado/persistência por interfaces, preservando o esquema existente por adaptadores; não reescrever banco, UI e motor ao mesmo tempo. Manter compatibilidade com jobs antigos e chaves de idempotência.

**Aceitação:** rastrear a mesma pergunta pelo job até o card, sem perda de entity/variant/owner; replay não duplica mensagem; erro de uma etapa não vira erro de outra. Logs sem credenciais, prompts completos ou conteúdo pessoal.

### 3. Recuperar descoberta e leitura com orçamento explícito

Reproduzir SQLite com rastreio por provedor: query enviada, resultado descartado e motivo, tempo/deadline, candidato selecionado e primeira leitura. Comparar pergunta literal com uma consulta técnica curta derivada das entidades/requisitos. Fontes preferenciais precisam ser tentativas limitadas, não barreiras que excluam a web restante.

Separar descoberta de documentos de sua leitura; reutilizar documentos válidos e escolher diferentes passagens sem reenviar todo o texto ao modelo. Acrescentar adaptadores oficiais apenas quando justificados por casos reais. Preservar SSRF, limites de bytes, MIME, redirect, cancelamento, cache e respeito a bloqueios. Não implementar bypass de CAPTCHA nem repetir a mesma fonte bloqueada em loop. Não adicionar SearXNG para tentar corrigir uma falha de extração.

**Aceitação:** encontrar fonte pertinente sem URL em perguntas novas de áreas diferentes; quando um site bloquear, recuperar uma alternativa legítima ou informar a causa precisa. Medir fontes úteis lidas, não volume de URLs ou número de testes.

### 4. Calibrar evidência e síntese com gabarito revisado

Guardar fixtures públicas versionadas de passagens e requisitos, com seção e offsets. Para cada requisito, distinguir dado recuperado de texto usado na resposta. Avaliar referência completa/abreviada de API, negação, quantificadores, números, variantes e contexto da seção. O caso Python é obrigatório: revisar a redação e o parecer reais para descobrir se houve erro do modelo, suporte insuficiente ou falso negativo da revisão.

Separar indisponibilidade do provedor, saída malformada, falta de citação e rejeição semântica. Permitir recuperação limitada e dirigida pela causa, mantendo os mesmos limites e sem transformar evidência parcial em afirmação completa. Escolher apenas modelos com capacidade de texto/JSON/stream necessária, sem fallback silencioso para um modelo incompatível.

**Aceitação independente:** A — localizar o trecho exato numa fonte conhecida; B — descobrir fonte sem receber URL; C — produzir resposta correta em português, com citações correspondentes, cards e persistência após reload. Aprovar cada eixo separadamente em casos que não sejam variantes do mesmo teste Python. Medir omissões e falsos suportes; nunca aumentar completude relaxando a verificação.

### 5. Publicar por um único apresentador e validar o ciclo completo

Centralizar a transformação de resultado em mensagem, JDUI e workspace, sem alterar a evidência. Definir tipos próprios para citação literal, parágrafo autoral, oferta, comparação, aviso e limitação. A comparação deve receber IDs do conjunto exibido e origem/data dos dados, não depender somente de uma frase longa com nome do produto. Revalidar preço quando solicitado e preservar o contexto anterior se a atualização falhar.

Simplificar a resposta inicial: conclusão sustentada, opções/fontes úteis e lacunas específicas; detalhes léxicos, métricas e diagnóstico ficam acessíveis em expansão. Preservar acessibilidade, foco, botões, dark theme, links externos seguros e limites do envelope JDUI.

**Aceitação:** mesmo resultado antes/depois de reload; ações do card operam sobre os itens certos; mobile 320/390 e desktop, zoom, teclado virtual e foco real; SSE com cancelamento/reconexão e respostas parciais sem duplicar. Só então considerar publicação.

## Pendências objetivas

1. Corrigir as causas e repetir a bateria autenticada já reproduzida em produção; não é mais necessário refazer a auditoria inicial ou solicitar acesso ao Brave para isso.
2. SQLite: A foi executado na retomada e revelou perda de passagem; B falhou no pedido oficial completo; C não foi aprovado. Exigir os três eixos após a correção.
3. Revisar draft e parecer semântico do caso Python contra gabarito; o resultado parcial por si só não prova erro do validador.
4. Reproduzir o erro original do índice instalado com diagnóstico seguro; não há justificativa para declarar corrupção ou reconstruir o banco agora.
5. Executar celular físico, teclado virtual, stream e gestos reais; o harness não substitui isso. WebRTC continua fora do escopo desta auditoria.
6. Validar reinício automático/reboot, Linux/CI, carga multiusuário, fluxos completos de estudo, cadastro e troca de chave em conta de teste. Não foram aprovados por inspeção de tela.

O próximo incremento recomendado é a etapa 0 revista, seguido dos demais contratos e do gabarito A/B/C. A auditoria não alterou o motor para esconder erros e não considera o sistema pronto apenas pelo total de testes verdes. Nenhum push foi realizado na retomada.
