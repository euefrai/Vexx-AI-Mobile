# Vexx PC

Aplicativo público independente para Windows 10/11. Não instala Studio, túneis, serviços de desenvolvimento nem o agente central de inferência.

## Instalar

1. No site Vexx AI, abra **Meu PC → Preparar computador → Baixar Vexx PC para Windows**.
2. Abra **Vexx-PC-Setup-1.6.0.exe** e instale. O pacote inclui Python e todas as dependências do aplicativo. Não exige Python do sistema, WinGet ou extração manual. Em computadores sem WebView2, o instalador baixa esse componente oficial da Microsoft; nesse caso precisa de internet.
3. No site, entre na sua conta e abra **Meu PC → Seu nick e PIN**. Crie um nick exclusivo (3–30 caracteres) e um PIN (6–12 números). Abra o aplicativo e informe apenas os mesmos nick e PIN para conectar. O endereço oficial já está preenchido; outro servidor HTTPS fica nas opções avançadas. Cada conta mantém um PC vinculado; novo vínculo substitui o anterior.
4. Autorize visualização ou controle no **painel local**, apenas quando precisar. Escolha permissão por uma hora ou **Permitir mouse e teclado permanentemente**. A opção permanente é explícita, fica vinculada à credencial desse PC e retorna ao reabrir o aplicativo. **Revogar acesso permanente**, trocar o vínculo ou revogar no site cancela essa opção. Sem essa escolha, o acesso começa pausado ao abrir. No celular, entre na mesma conta e abra **Meu PC**.

O aplicativo abre em janela própria e cria atalhos no menu Iniciar e, opcionalmente, na Área de Trabalho. Instala para seu usuário em Windows 10/11 x64, sem administrador. Fechar a janela encerra o aplicativo e o acesso remoto. A desinstalação em Aplicativos do Windows remove o código e preserva a configuração e o índice. O EXE ainda não possui assinatura Authenticode.

## O que inclui

- Visão geral: CPU, RAM, unidades locais, bateria, tempo desde a inicialização do Windows, consumo do aplicativo e sugestões locais de processos com alto uso de RAM, aplicativos grandes e arquivos grandes. Encerrar um processo pede confirmação e protege o Windows; apps abrem o gerenciador nativo e arquivos vão para a revisão da aba Limpeza.
- Arquivos: navegação por pastas, seleção de até 100 arquivos, filtros por tipo, tamanho e data, ordenação pelos maiores e índice SQLite FTS5 de nomes/caminhos/tamanhos. Pesquisa com 3 caracteres ou mais, paginação de 60 itens, tempo de consulta limitado a 150 ms. O conteúdo não é indexado nem enviado ao site. Caminhos e pastas enviados ao Copiloto são analisados localmente com limites de tempo, quantidade e tamanho; textos, PDF, Word, Excel, PowerPoint e metadados de imagens podem ser resumidos. Só são enviados ao provedor de IA escolhido após confirmação. Tamanhos de pastas representam apenas arquivos indexados, sem caches/protegidos.
- Auditoria do sistema: reúne métricas, discos, processos, índice local, Lixeiras Vexx/Windows, apps grandes, inicialização e plano de energia. Sugestões de arquivos vão para a Lixeira restaurável e processos só são encerrados após seleção e confirmação. Pastas locais conhecidas do OneDrive, Google Drive, Dropbox e iCloud podem ser listadas; contas e conteúdo remoto da nuvem não são acessados. A auditoria é local; uma segunda opinião do provedor externo é opcional e pede consentimento.
- Rede: interfaces ativas, IPs locais, velocidade reportada e tráfego observado. SSID Wi-Fi quando disponível. Não executa speed test nem identifica uma interface ativa como prova de internet.
- Logs: até 300 eventos da sessão, filtro e exportação. Não grava tokens ou conteúdo de arquivos.
- Copiloto: aceita anexos pequenos de texto e caminhos de arquivos/pastas. O desligamento em linguagem natural apresenta o comando e pede confirmação. Para outro comando Windows, envie `!cmd comando`; o texto exato aparece para revisão, e só é iniciado após confirmar. A revisão expira em cinco minutos.

- Limpeza: instaladores/APKs, imagens, vídeos, áudios, compactados e temporários. O aplicativo mostra candidatos; não decide sozinho o que é inútil. Aplicativos instalados aparecem por tamanho estimado, com remoção pelo gerenciador nativo do Windows.
- Projetos: análise antes de executar, plano com comandos/dependências/portas, logs e opção para parar o grupo de processos iniciado pelo Vexx. O Copiloto usa uma área de scroll independente e vira painel lateral recolhível em janelas pequenas.

## Limpeza e Lixeira Vexx

**Revisar remoção** mostra nomes, caminhos e tamanho antes de alterar arquivos. A remoção move arquivos comuns para uma lixeira própria no mesmo volume, sem copiar arquivos grandes nem recorrer à exclusão permanente. Ela continua ocupando espaço até **Revisar exclusão definitiva**, que exige digitar `EXCLUIR`. Restaurar nunca sobrescreve um arquivo existente. Não há esvaziamento automático nem exclusão recursiva de pastas. Arquivos do sistema, programas instalados, ambientes, links, junctions e dados do Vexx são protegidos.

O catálogo persistente fica em `trash.sqlite3`; os arquivos ficam em `.vexx-trash` na pasta de dados ou, em outro volume, ao lado da pasta original. Reinstalar, atualizar e desinstalar o código preservam os dados. Não apague essa pasta manualmente se quiser restaurar arquivos. A revisão expira em cinco minutos e confere novamente todos os arquivos antes da operação.

## Iniciar projetos

Na aba **Arquivos**, abra uma pasta ou selecione **▷ Iniciar…** ao lado da entrada. Também é possível colar o caminho em **Projetos**. A análise não executa código: apresenta o plano e pede uma ação explícita para iniciar. Execute apenas projetos confiáveis; preparar dependências executa os instaladores e scripts declarados por eles.

São reconhecidos Python (`main.py`, `app.py`, `server.py`, `manage.py` ou arquivo `.py` escolhido), FastAPI, Flask, Django, scripts `dev`/`start` do npm, JavaScript Node selecionado e HTML estático. Python usa `.vexx-venv` próprio e pode preparar `requirements.txt`/`pyproject.toml`; Node precisa estar instalado. HTML, CSS e JS locais são servidos por HTTP em loopback, com proteção de caminhos e arquivos ocultos. O Vexx reconhece backend/frontend em pastas comuns e destinos literais de proxy Vite, configurando a porta do backend e variáveis de URL. Não adivinha senhas, bancos, serviços externos ou todos os formatos de projeto.

Para dependências ou ordens específicas, crie `vexx-project.json` na raiz. Os serviços começam na ordem declarada e uma porta só é apresentada depois de confirmar que pertence ao grupo iniciado. Exemplo:

```json
{"services": [
  {"name": "Backend", "cwd": "backend", "command": ["python", "main.py"], "port": 8000},
  {"name": "Interface", "cwd": "frontend", "command": ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"], "port": 5173}
]}
```

Os caminhos precisam permanecer dentro do projeto; comandos são listas de argumentos, sem shell genérico. Portas ocupadas geram erro: o app não adota nem encerra programas existentes. No Windows, grupos de processos pertencentes ao projeto são encerrados ao parar ou fechar o Vexx PC. Até três projetos podem ficar ativos por sessão. A preparação de cada comando tem limite de dez minutos e a confirmação de porta, um minuto. Aplicações que exigem múltiplos comandos, versões específicas do Python ou configuração externa podem precisar de ajustes manuais.

O primeiro índice precisa percorrer os arquivos e pode levar tempo em discos grandes. Ele trabalha em lotes, respeita permissões, evita junctions/symlinks e pode ser pausado. Resultados aparecem conforme o índice avança. Metadados atualizados a cada 30 minutos ou manualmente. Não há promessa de pesquisa instantânea antes da indexação.

## Nick e PIN persistentes

As credenciais ficam no SQLite de autenticação do agente central, com hash scrypt do PIN, sem expiração automática. O PIN não é recuperável na interface e não é salvo no aplicativo: após o vínculo, o app mantém apenas sua credencial individual e o nick. **Desvincular** mantém nick/PIN; **trocar** ou **apagar** no site revoga o dispositivo atual. Nick é exclusivo, sem distinção entre maiúsculas e minúsculas. Cinco falhas bloqueiam novas tentativas por 15 minutos no registro persistente, além do limite por IP no relay. A troca confere uma geração para impedir que uma conexão em andamento reative credenciais antigas.

## Configurar IA no aplicativo

Abra a aba **IA**. Escolha Ollama, OpenAI, Hermes/proxy ou outro endpoint compatível, informe endereço base, modelo e chave quando exigida. **Testar e listar modelos** consulta o serviço escolhido; salve o modelo para conversar no Copiloto. Ollama usa `/api/tags` e `/api/chat`; os outros modos usam `/models` e `/chat/completions` relativos ao endereço base. Hermes sugere `http://127.0.0.1:8645/v1`; altere para a porta real do seu proxy. O app não instala, inicia nem converte protocolos de outros serviços.

A chave é protegida com DPAPI para o usuário do Windows em `ai.json`; a API local só informa se existe chave. Trocar provedor/endereço exige informar novamente a chave, evitando enviá-la ao serviço errado. Em execução por código fora do Windows, o arquivo usa permissão 0600. Desmarcar IA preserva os comandos locais. Mensagens de conversa seguem diretamente ao provedor escolhido, com histórico curto em memória; arquivos, índice e chaves não são incluídos. A IA não recebe ferramentas para executar comandos ou controlar o PC. HTTP somente para loopback/rede privada; serviços externos exigem HTTPS. Não são seguidos redirecionamentos com a chave.

Referências: [API Ollama](https://docs.ollama.com/api/chat), [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Atualizar pelo aplicativo

O ícone **↻** no topo verifica novas versões no site HTTPS ao qual este PC foi vinculado. A verificação também ocorre ao iniciar e a cada 30 minutos. Quando houver uma versão mais recente, o botão mostra **Atualizar**; clique para baixar, conferir o SHA-256 e instalar. Sem nova versão, o botão apenas informa a versão atual.

A instalação é preparada em uma pasta separada, com seu próprio ambiente virtual e dependências. O aplicativo pausa o acesso remoto e encerra de forma controlada. A nova versão só vira a versão ativa depois de iniciar e responder ao teste de saúde com a identidade correta. Se dependências ou inicialização falharem, a versão anterior é reaberta. A conta, a credencial e o índice continuam na pasta de dados. O acesso remoto volta pausado, exceto se você escolheu controle permanente para a mesma credencial. A Lixeira Vexx e as configurações também são preservadas.

O atalho usa `app/launch.py` e `app/current.json`; as versões ficam em `app/releases/`. O atualizador não sobrescreve nem apaga versões anteriores. Instalações manuais pelo código não se atualizam sozinhas: use o instalador Windows para habilitar essa função. O pacote e o manifesto vêm do mesmo site confiável por HTTPS, sem redirecionamentos; SHA-256 confere integridade, não constitui uma assinatura independente do publicador.

O instalador inicial é um EXE; o ZIP continua sendo apenas o formato interno de atualização, baixado e aplicado pelo próprio app.

Para publicar uma nova atualização, aumente `__version__` em `pc_companion/__init__.py`, valide e implante o repositório. O endpoint público `/api/companion/release` informa versão, tamanho, arquivos e hash do ZIP gerado. Não inclua configurações ou bancos pessoais no pacote.

## Dados e segurança

Dados: `%LOCALAPPDATA%\VexxPC\config.json` (credencial individual) e `files.sqlite3` (índice). Código/dependências: versões isoladas na subpasta `app/releases`. Reinstalar não apaga configuração nem índice. Não compartilhe config.json. Sem credencial administrativa do servidor, banco de contas ou código de outros projetos no download.

O painel usa uma porta loopback livre escolhida pelo sistema. Não abre portas na rede nem encerra processos existentes. Operações locais exigem token por sessão e validação de origem. O aplicativo inicia a conexão TLS de saída. Acesso remoto exige autorização local; fechamento ou pausa bloqueia novos comandos. A tela inteira e eventos de entrada atravessam o relay do seu site em TLS; não há criptografia ponta a ponta adicional, áudio, acesso à tela bloqueada ou UAC.

**Desvincular** no painel revoga a credencial no servidor antes de removê-la localmente; se estiver offline, pause o acesso e use **Desvincular** no site. Credenciais expiram em 90 dias: gere novo vínculo quando necessário. O servidor confere revogações e situação da conta periodicamente e em novas conexões. Reiniciar o relay desconecta os PCs e invalida códigos pendentes, sem perder vínculos persistidos no SQLite central.

## Executar pelo código

Na raiz do repositório, com Python 3.12+:

```powershell
python -m venv .venv-pc
.venv-pc\Scripts\python -m pip install -r pc_companion/requirements.txt
.venv-pc\Scripts\python -m pc_companion
```

Para diagnóstico/QA isolada: `python -m pc_companion --no-browser --port 0 --data-dir C:\temp\vexx-qa --root C:\pasta-de-teste`. A porta efetiva aparece no terminal; não adote outro serviço pela porta. No Windows, a execução normal abre uma janela WebView2. `--no-browser` executa apenas o serviço local para diagnóstico. Para encerrar a versão de código, use Ctrl+C no terminal. A versão instalada oferece **Encerrar aplicativo** no painel.

## Publicar no site

Implante juntos `companion_api.py`, `companion_registry.py`, a pasta `pc_companion`, `remoto.py`, a integração em `server.py` e o frontend. Atualize também o agente central (`pc_agent.py`) para persistir os vínculos no banco de autenticação existente. O download público `/downloads/vexx-pc-agent-setup.exe` aponta ao EXE da versão no GitHub Releases. Gere com `python tools/build_pc_installer.py` no Windows (Pillow necessário), confira a instalação e publique o EXE e `SHA256SUMS` na release `vexx-pc-v<versão>` **antes** de implantar a nova versão no site. A compilação inclui Python independente, wheels para instalação offline e bootstrapper WebView2 com assinatura Microsoft verificada. As fontes e hashes dos fornecedores estão em `installer/sources.json`. O workflow Windows também permite compilar artefatos para revisão. O servidor mantém o ZIP interno em `/downloads/vexx-pc-agent-windows.zip`, gerado por lista explícita de arquivos. A conta e a IA continuam usando o agente central; o PC público cuida apenas do dispositivo da pessoa. As rotas antigas de acesso remoto permanecem para compatibilidade, enquanto o site público usa `/api/companion/*`.

Referências: [SQLite FTS5 trigram](https://www.sqlite.org/fts5.html#the_trigram_tokenizer), [WebView2](https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution), [Python standalone](https://docs.astral.sh/python-build-standalone/).
