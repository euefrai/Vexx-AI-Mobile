# Vexx PC público — implementação e validação

Validado localmente em 3 de novembro de 2026. Mudanças aplicadas ao checkout `julia-mobile-v0.2`; alterações anteriores de pesquisa, autenticação e outros trabalhos foram preservadas. O painel de desenvolvimento Fajulto não foi modificado.

## Histórico da entrega inicial

- `pc_companion/`: aplicativo independente com Visão geral, PC, Rede, Logs e Copiloto local. Sem Studio, Mente, serviços de desenvolvimento ou criação de túneis. Instalador Windows, ambiente virtual, dependências, atalho e encerramento pelo painel.
- `system.py`: CPU/RAM, armazenamento local, uptime do sistema, bateria, interfaces/IPs, tráfego, SSID quando disponível e RAM do aplicativo. Atualização a cada 3 s; consulta do Wi-Fi em processo oculto, com timeout, no máximo a cada 30 s.
- `indexer.py`: índice SQLite FTS5 em disco, leitura de metadados em lotes, pausa/retomada, atualização periódica/manual, paginação e limite de tempo por busca. Tamanhos de pastas calculados uma vez por varredura, considerando somente arquivos indexados. Consultas não percorrem o disco.
- `companion_api.py`: download por lista explícita de arquivos, código temporário de uso único e relay de dispositivos por conta. Rotas públicas de dispositivos nunca encaminham captura/entrada ao computador central.
- `companion_registry.py` + pequeno ponto de integração em `pc_agent.py`: persistência de vínculo/revogação no banco de contas existente. Credencial individual armazenada como hash no registro, validada por assinatura/expiração e situação da conta. Novo vínculo substitui o anterior.
- Frontend do site: download direto, guia e geração/revogação de vínculo; controle remoto passa a usar `/api/companion/*`. Indicador de PC online usa o dispositivo da conta. Mantidos gestos, lote de entrada, JPEG, Unicode e clipboard; retorno de texto do clipboard validado no novo relay.

## Verificações executadas

1. **105 testes passaram**: `tests/test_auth.py`, `test_security_hardening_v58.py`, `test_remote_access.py`, `test_remote_stream.py`, `test_remote_latency.py`, `test_pc_companion.py`. Abrangem conta/CSRF/origem, uso único/expiração do código, isolamento, credenciais substituídas, revogação persistente, bloqueio sem consentimento, payloads inválidos, pacote e busca real de metadados.
2. **Instalação real isolada**: extraído o ZIP gerado pelo endpoint; executado o PowerShell do pacote em pasta temporária, sem atalho nem lançamento automático. Ambiente criado do zero, dependências baixadas/instaladas, imports verificados. Aplicativo executado a partir da própria instalação, com banco de QA e raiz de arquivos limitada ao pacote. Reinstalação também passou. O caminho de instalação automática do Python pelo WinGet não foi executado: já havia Python compatível nesta máquina.
3. **HTTPS/WSS reais em loopback**: `tools/verify_pc_companion_tls.py`, certificado de QA verificado por CA temporária, API HTTP e socket reais. Vínculo → conexão de saída → pedido remoto → confirmação local → transporte JPEG → entrada/clipboard → pausa → revogação no site e remoção local. Autenticação/registro de conta foram fixtures sobre SQLite real; imagem e entrada nativa foram fixtures. Nenhum clique/tecla foi enviado ao Windows.
4. **Navegador real** via Playwright: painel instalado, leitura de métricas reais, navegação, busca, Copiloto, foco por teclado e encerramento. Layout conferido em desktop 1440 px e em 390/320 px, sem overflow horizontal do documento. Capturas em `output/playwright/`. A instalação final corrigiu o único erro inicial de console (favicon ausente).
5. **Índice de 100 mil entradas sintéticas**: 25 consultas da primeira página de 60 nomes contendo `.txt`, mediana **4,0 ms**, máximo **7,1 ms** nesta máquina. Isso mede consulta ao índice pronto, não a primeira indexação, todo tipo de busca, contenção de disco ou desempenho de outras máquinas. Busca no navegador com o pacote de QA retornou um arquivo em aproximadamente 6 ms.
6. Sintaxe JavaScript, parser PowerShell e compilação Python conferidos. `git diff --check` passou nos arquivos da entrega, exceto pelo diff global de `public/app.js`, que contém avisos de whitespace em alterações preexistentes; esse trabalho anterior não foi reformatado. Após os ajustes finais de clipboard/indicador de conexão, os 33 testes focados de dispositivo/transporte passaram novamente, assim como o teste HTTPS/WSS.

Artefatos locais: `output/pc-companion-release/Vexx-PC-Windows.zip`, `validation.json`, `output/pc-companion-install.log`, `output/pc-companion-tls-smoke.log` e `output-companion-regression.log`. Artefatos e bancos de QA não fazem parte do ZIP público.

## Limites e publicação

- Os testes locais não demonstram download/vínculo no site implantado. A publicação precisa incluir os arquivos do relay/frontend e a atualização do agente central junto. Não basta copiar somente a pasta do aplicativo; a versão publicada deve ser conferida pelo manifesto e download reais.
- Há um PC por conta. O agente central continua necessário para autenticação e IA. Estado de conexão/códigos é volátil no relay; registro de dispositivos é persistente no SQLite central. Use a topologia atual de uma instância do relay; múltiplos workers/instâncias exigem coordenação compartilhada de sockets e códigos.
- Na versão inicial 1.1, o download exigia extração manual. Essa limitação foi substituída pelo instalador EXE da versão 1.2 descrito abaixo. O EXE ainda não possui assinatura Authenticode.
- A primeira indexação demora conforme disco/quantidade de arquivos. Caches, diretórios protegidos, dependências, junctions e volumes remotos são ignorados. O índice pode ficar defasado até a próxima atualização; tamanhos de pastas podem ser parciais. Não foi feita uma varredura completa dos discos pessoais durante QA.
- A autorização remota dura até uma hora e começa pausada em cada execução. TLS de transporte; sem criptografia ponta a ponta adicional, áudio, UAC ou tela bloqueada. Captura/entrada nativas e conectividade entre duas máquinas/redes reais ainda precisam de aceitação após implantação.
- O Copiloto público executa comandos locais de diagnóstico, busca, navegação e pausa/atualização. As ações administrativas do painel de desenvolvimento foram excluídas. Não há execução arbitrária de terminal ou dependência de provedor de IA no aplicativo público.

## Referências técnicas

[SQLite FTS5 trigram](https://www.sqlite.org/fts5.html#the_trigram_tokenizer) e [WinGet install](https://learn.microsoft.com/windows/package-manager/winget/install). A busca pede pelo menos três caracteres, conforme a capacidade do índice trigram.

## Atualizador 1.1.0 e preparação da publicação

O código desta entrega foi isolado em `vexx-pc-agent-publish-dd6f5c4`, sobre o commit publicado `dd6f5c4`, na branch `codex/vexx-pc-public-updates`. Foram incluídos somente os arquivos da edição pública e seus pontos de integração. Alterações concorrentes de pesquisa/autenticação do outro checkout não foram copiadas.

- Versão pública: `1.1.0`; manifesto em `/api/companion/release`, ZIP por lista explícita, SHA-256 e metadados de arquivo fixos. Verificação ao iniciar e a cada 30 minutos, além do botão **↻** no topo. Atualização somente após clique do usuário e apenas em instalações reconhecidas.
- Pacotes: HTTPS sem redirecionamento, teto de tamanho, versão estrita, hash, lista de membros, caminhos, duplicatas, symlinks e nomes reservados do Windows validados antes de extrair.
- Instalação por versões em `app/releases`, com venv própria. A versão ativa não é sobrescrita; `current.json` só é promovido após dependências/imports e confirmação HTTP da identidade e saúde do novo processo. Conta/índice permanecem fora das pastas de versões.
- Encerramento do aplicativo antigo é cooperativo. O teste real identificou o processo filho do inicializador de venv do Windows; a checagem de saúde exige que o PID pertença à árvore do processo recém-criado, além do nonce de instância e versão. Não reutiliza uma porta ocupada nem adota outro serviço.
- `tools/verify_pc_companion_update.py`: instalação real do ZIP, atualização via HTTPS verificado de **1.1.0 para 1.1.1** e falha intencional nas dependências de **1.1.2**, com retorno automático à **1.1.1**. Confirmados encerramento normal, venv nova, saúde antes da promoção, configuração preservada, integridade do índice, acesso remoto pausado e preservação da versão anterior. As versões 1.1.1/1.1.2 são fixtures locais de QA, não releases públicas.
- `tests/test_pc_companion_update.py`: 33 testes focados de integridade, manifesto, isolamento da instalação, promoção após saúde e rollback. Suíte ampliada de segurança/dispositivo executada na cópia limpa; o resultado final também é acompanhado no CI após o push.
- UI real: botão de verificar versão e mensagem sem vínculo conferidos; ícone visível e documento sem overflow em 320 px. Código JavaScript/Python/PowerShell e `git diff --check` verificados.

Reproduzir QA de atualização no Windows: instalar `trustme` no Python de QA e executar `python tools/verify_pc_companion_update.py`. Não usa credenciais, contas ou bancos de produção e não envia entrada nativa ao Windows. Evidência local em `output/pc-update-*/summary.json`; teste não é distribuído no ZIP.


## Instalador e aplicativo Windows 1.2.0

O download principal passa a ser `/downloads/vexx-pc-agent-setup.exe`, com redirecionamento fixo ao artefato da mesma versão no GitHub Releases. O ZIP permanece exclusivamente como transporte interno do atualizador e para compatibilidade com instalações anteriores.

- Inno Setup por usuário, atalhos no menu Iniciar/Área de Trabalho e desinstalação pelo Windows. Python 3.13 independente e wheels das dependências acompanham o EXE; a instalação usa `pip --no-index`. Nenhuma instalação de Python do sistema é necessária. O bootstrapper WebView2 oficial é verificado por Authenticode na compilação; somente máquinas sem esse runtime precisam de internet para prepará-lo.
- Janela própria com pywebview/WebView2, sem ponte de execução Python. Fechar a janela drena o servidor local e encerra o acesso. Mutex impede abrir duas instâncias e bloqueia a reinstalação sobre o runtime em uso. Diagnóstico continua disponível com `--no-browser`.
- Atualizador inicia a nova janela oculta, confirma saúde/PID/nonce antes da promoção e solicita exibição por API local autenticada. Compatibilidade com a versão anterior baseada em navegador permanece.
- Fontes e hashes de Python/Inno: `installer/sources.json`; compilação: `tools/build_pc_installer.py` e workflow `pc-installer.yml`. O EXE e `SHA256SUMS` precisam estar publicados antes do deploy que altera o link. Nenhum executável grande é versionado no Git.
- 139 testes locais passaram, incluindo isolamento/autorização, integridade do pacote, modos nativo/diagnóstico, encerramento e redirecionamento do instalador. `tools/verify_pc_companion_update.py` usa versões derivadas da versão real; o teste HTTPS verificou 1.2.0 → 1.2.1 e rollback após falha de dependências da fixture 1.2.2, preservando os dados. `--native` habilita o mesmo fluxo com janelas reais do Windows.

A instalação inicial continua sujeita à confirmação do Windows para aplicativos sem assinatura do publicador. O caminho de preparação WebView2 ausente não foi exercitado nesta máquina, que já possui o runtime. O teste de acesso entre dois computadores/redes reais permanece separado dos testes locais.


## Nick/PIN e IA — 1.3.0

- Perfil persistente de nick exclusivo e PIN com hash scrypt no banco central. Rotação/exclusão revogam o dispositivo, invalidam códigos temporários pendentes e impedem reativação por uma conexão concorrente com geração antiga. Desvincular preserva o perfil; códigos temporários antigos ficam apenas por compatibilidade da API. Interface do site em Meu PC e no guia de instalação.
- Aplicativo usa nick/PIN, inicia a conexão WSS automaticamente e mantém consentimento local por até uma hora para captura/controle. O PIN não é persistido no PC. A conexão do visualizador também é permitida no navegador desktop, com as mesmas verificações de autorização.
- Aba IA: configuração local de Ollama nativo e endpoints OpenAI compatíveis (incluindo Hermes/proxy), modelo, chave, teste/listagem de modelos. DPAPI no Windows, chave omitida de respostas/logs, descarte da chave ao trocar destino, limites de resposta/tempo e nenhum redirecionamento. Copiloto mantém comandos locais; a IA conversa sem ferramentas de execução e sem envio automático de arquivos ou métricas.
- Testes focados de persistência/reabertura SQLite, limite de PIN, isolamento entre contas, geração antiga, revogação, API local protegida, DPAPI e protocolos de todos os provedores. `tools/verify_pc_companion_tls.py` verifica nick/PIN → HTTPS/WSS → autorização → JPEG/entrada fixture → pausa → rotação/exclusão e conversa com uma API HTTP real de QA. Nenhuma entrada nativa é enviada ao Windows; validação entre duas máquinas/redes reais continua separada.
- As chaves e modelos usados em QA são fixtures. Não foi consumida chave de API do operador nem carregado modelo local pesado. A compatibilidade de um serviço específico depende de ele implementar a API selecionada e publicar o modelo configurado.
