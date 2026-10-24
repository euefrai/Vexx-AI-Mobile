# PC Agent V5.9.7 — auditoria operacional

## Resultado

Atualização **BLOCKED_NO_GRACEFUL_SHUTDOWN**; gate de atualização **OPERATIONAL_NO_GO**. O processo anterior continua operacional. Não se trata de corrupção ou falha generalizada: não foi possível comprovar um mecanismo de parada graciosa permitido pelo pedido. Nenhum sinal, terminate/kill ou restart foi enviado.

PID identificado: **25924**, `Python312/pythonw.exe`, iniciado em 22/10/2026, antes das alterações V5.9.7. Script e cwd: `C:/Users/efrai/Documents/julia-mobile-v0.2-offline-sqlite/julia-mobile-v0.2/pc_agent.py`. Sem porta de entrada. Ambiente real do processo aponta ao relay `vexx-ai.onrender.com` e ao SQLite `C:/Users/efrai/.julia-mobile/memory.sqlite3`. Valores de credenciais não foram registrados.

Checkout e origin/main após fetch: `0814864e0e20bcb94f22a0b4fe861b205c15ed7c`, branch main. Isso comprova arquivos em disco, não o commit carregado no processo antigo. As alterações locais de relatório da rodada anterior foram preservadas.

`iniciar-agente.bat` existe, mas não corresponde ao processo ativo: usa `python` e defaults de relay/banco diferentes. O processo ativo usa Python 3.12 pythonw diretamente. Não foi usado esse launcher sem conferir a configuração.

## Proteção dos dados

Banco real identificado pelo ambiente do PID, não pelo ambiente herdado pelo Codex, cujo relay é diferente. `PRAGMA quick_check`: ok; journal_mode WAL. Pesquisa: duas concluídas, zero ativas. Pedidos IA: 105 completed, 15 failed, dois cancelled, zero pendentes. Não foram lidos textos de mensagens para esse diagnóstico.

Backup consistente pela API SQLite backup, com origem em conexão read-only, salvo em `.julia-mobile/backups/`, fora do Git. Backup também passou no quick_check. Caminho exato em `qa-artifacts/v598/operational/runtime-audit.json`. Sem migração, exclusão, reset de sessão ou cópia insegura do arquivo principal WAL.

## Parada e recuperação

O código publicado só trata KeyboardInterrupt no laço de conexão, sem endpoint/arquivo/pipe de shutdown. Um processo auxiliar se desanexou do próprio console e tentou localizar o console do PID: AttachConsole falhou com WinError 6 (sem console). Nenhum evento de controle foi enviado. Não há garantia de encerramento gracioso desse pythonw pelo mecanismo existente. O pedido proíbe força e determina registrar o bloqueio nessa situação.

Hermes e demais serviços foram apenas identificados, não reiniciados. PID novo: nenhum. Commit efetivamente carregado: não verificado. Recuperação não necessária porque o processo original foi preservado. Uma futura atualização deve ocorrer por encerramento gracioso do mecanismo que o iniciou ou por reinício normal autorizado do ambiente; não introduzir encerramento forçado disfarçado de atualização.

## Relay e navegador

`https://vexx-ai.space/api/diag` e domínio Render: commit `0814864e0e20`, PC online. Health não foi usado como prova de chat completo.

A sessão inicialmente expirou. Após a entrada do usuário com conta de teste, foram executados seis casos reais em uma conversa nova, sem extrair credenciais ou alterar conversas antigas. Saudação passou; documentação ficou só na promessa de verificar; pesquisa científica concluiu parcialmente; notícias municipais trouxeram manchetes nacionais incompatíveis; imagens trouxeram links sem galeria; produtos não confirmaram oferta compatível. Após recarga, as 12 mensagens permaneceram e o PC voltou conectado. Artefato: `qa-artifacts/v598/operational/authenticated-e2e.json`. Esses resultados pertencem ao processo antigo, não à V5.9.8.

O teste único do modelo gratuito configurado encontrou 426 modelos, HTTP 200 e 162 eventos SSE, mas zero chunks públicos: os 160 tokens disponíveis foram consumidos antes de conteúdo público, com finish_reason length. Diagnóstico **BUDGET_LIMITED**, sem aprovação de síntese científica e sem concluir indisponibilidade geral do provedor. Não houve retry, modelo pago ou registro de texto de raciocínio. O JSON bruto registra BLOCKED para esse ensaio limitado; esta interpretação distingue limite de orçamento de indisponibilidade.

## Separação operacional

V5.9.8 será desenvolvida em `C:/Users/efrai/Documents/julia-mobile-v0.2-offline-sqlite/vexx-v598-dev`, branch `codex/v598-autonomous-research`, base publicada V5.9.7. Não serão usados o banco real ou benchmarks extensos em produção. A criação de worktree pela ferramenta do app retornou "Not a git repository" para o contexto pai; foi usado git worktree add no repositório filho correto.
