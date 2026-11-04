# Vexx PC

Aplicativo público independente para Windows 10/11. Não instala Studio, túneis, serviços de desenvolvimento nem o agente central de inferência.

## Instalar

1. No site Vexx AI, abra **Meu PC → Preparar computador → Baixar Vexx PC para Windows**.
2. Abra **Vexx-PC-Setup-1.2.0.exe** e instale. O pacote inclui Python e todas as dependências do aplicativo. Não exige Python do sistema, WinGet ou extração manual. Em computadores sem WebView2, o instalador baixa esse componente oficial da Microsoft; nesse caso precisa de internet.
3. Abra **Vexx PC** pelo atalho. No site, entre na sua conta e gere um código temporário. No aplicativo, informe o endereço HTTPS do site e o código. Cada conta mantém um PC vinculado; novo vínculo substitui o anterior.
4. Autorize visualização ou controle no **painel local**, apenas quando precisar. A permissão dura até uma hora, é revogável e começa pausada ao abrir o aplicativo. No celular, entre na mesma conta e abra **Meu PC**.

O aplicativo abre em janela própria e cria atalhos no menu Iniciar e, opcionalmente, na Área de Trabalho. Instala para seu usuário em Windows 10/11 x64, sem administrador. Fechar a janela encerra o aplicativo e o acesso remoto. A desinstalação em Aplicativos do Windows remove o código e preserva a configuração e o índice. O EXE ainda não possui assinatura Authenticode.

## O que inclui

- Visão geral: CPU, RAM, unidades locais, bateria, tempo desde a inicialização do Windows e consumo do aplicativo.
- PC: índice SQLite FTS5 de nomes/caminhos/tamanhos. Pesquisa com 3 caracteres ou mais, paginação de 60 itens, tempo de consulta limitado a 150 ms. Nenhum conteúdo de arquivo é lido ou enviado para o site. Tamanhos de pastas representam apenas arquivos indexados, sem caches/protegidos.
- Rede: interfaces ativas, IPs locais, velocidade reportada e tráfego observado. SSID Wi-Fi quando disponível. Não executa speed test nem identifica uma interface ativa como prova de internet.
- Logs: até 300 eventos da sessão, filtro e exportação. Não grava tokens ou conteúdo de arquivos.
- Copiloto: comandos locais em português, sem chave de IA: `status do computador`, `buscar relatorio.pdf`, `diagnosticar conexao`, `abrir logs`, `pausar acesso`, `pausar indice`, `atualizar indice`. Não executa comandos de terminal arbitrários.

O primeiro índice precisa percorrer os arquivos e pode levar tempo em discos grandes. Ele trabalha em lotes, respeita permissões, evita junctions/symlinks e pode ser pausado. Resultados aparecem conforme o índice avança. Metadados atualizados a cada 30 minutos ou manualmente. Não há promessa de pesquisa instantânea antes da indexação.

## Atualizar pelo aplicativo

O ícone **↻** no topo verifica novas versões no site HTTPS ao qual este PC foi vinculado. A verificação também ocorre ao iniciar e a cada 30 minutos. Quando houver uma versão mais recente, o botão mostra **Atualizar**; clique para baixar, conferir o SHA-256 e instalar. Sem nova versão, o botão apenas informa a versão atual.

A instalação é preparada em uma pasta separada, com seu próprio ambiente virtual e dependências. O aplicativo pausa o acesso remoto e encerra de forma controlada. A nova versão só vira a versão ativa depois de iniciar e responder ao teste de saúde com a identidade correta. Se dependências ou inicialização falharem, a versão anterior é reaberta. A conta, a credencial e o índice continuam na pasta de dados. O acesso remoto volta pausado.

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
