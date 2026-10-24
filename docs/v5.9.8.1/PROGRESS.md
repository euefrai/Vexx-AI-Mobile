# V5981 — progresso

Pedido anexado 45d91fc6: estabilizar runtime, console admin seguro, migração limitada e pesquisa autenticada. Sem push/deploy/Render/Windows restart; não alterar Studio/VERY/extensão.

Base dev: 60d002b, branch codex/v598-autonomous-research. Produção: 0814864. Inventário atual: um pc_agent.py ativo, PID25924, pai18196 Fajulto controle.py. Duas cópias são checkout publicado e worktree dev inativa, não dois consumidores. Hermes/yui/Studio/vexx_remote são integrações separadas preservadas. Inventário privado em ~/.julia-mobile/ops-v5981.

Supervisor existente usa terminate/kill; nenhum shutdown gracioso no processo antigo. Nova autorização permite último recurso direcionado somente com quiescência, backup e rollback preparados. Ainda nenhum processo encerrado.

SQLite real tem cinco contas, três admin e duas user, todas ativas/aprovadas. Coluna criado_por não existe; não presumir classificação humana apenas por status. Confirmar proveniência no audit_log e excluir identidades incertas/QA/serviço. Não imprimir nomes/segredos. Papéis futuros continuam user.

Implementação pendente: singleton e IPC local autenticado, teste de shutdown pythonw; restart publicado com wrapper operacional separado; reautorização admin com cookie vinculado à sessão e role verificado sem cache; UI /admin; migração transacional explícita; testes focados e suíte final; relatórios.


## Atualização operacional

Produção reiniciada: PID antigo25924 saiu via endpoint de parada do supervisor, que internamente usa terminate (último recurso autorizado, não parada graciosa do legado), após zero jobs, reserva de escrita SQLite, backup e rollback. Novo PID28520 pythonw executa wrapper privado com backend publicado0814864, sem V598 experimental. Relay confirma online e SQLite quick_check ok. Wrapper tem singleton e named pipe HMAC local; sourcehash e recibo privados em ~/.julia-mobile/ops-v5981. Studio/VERY/Hermes não foram alterados nem encerrados. Supervisor marcou parada intencional; lançamento manual legado do Studio ainda pode ignorar o novo lock até adoção do bootstrap, limitação a documentar.

Migração real: duas contas de cadastro aberto, ativas/aprovadas, promovidas após testes/backup; admins3→5, hashes/status/remote_ok/limites/IDs/sessões inalterados. UID proprietário local confirmado, alias legado diferente sem colisão; não foi presumida igualdade de nomes. Recibo e snapshot privados. Migração idempotente, reversão testada em temporário.

Console local: admin_http/admin_console/admin_migration, public/admin.{html,css,js}, /admin interceptado antes de cache/LLM. Grant HttpOnly/SameSite vinculado à sessão e revisão de segurança,10min,CSRF/rate-limit, papel/status/aprovação/sid frescos no PC. Sessão do proprietário Argon2 registrada no user_sessions existente após reauth para permitir revogação. Sem novo banco/login, sem shell e sem acesso automático a conversas/controle remoto.

Chrome QA real com relay+PC Agent WSS+SQLite temporário: login,reauth,reload,limites,teclado,320/390/1280,zoomCSS200%,XSSescaped,/admin sem mensagens/AI_requests e bloqueio do console. Últimas pequenas correções precisam nova rodada final. Fixtures não são produção. Primeiro harness caiu por lambda de modelo com assinatura incompleta; corrigida sem rede/modelo. Venv pythonw usa launcher/filho: testes verificam PID real, não assumem Popen.pid.

Pesquisa autenticada após login de teste: saudação PASS; TaskGroup resposta substantiva com fonte oficial; ciência rj-80157b50e470 concluida com outcomepartial,0fonteslidas; recuperarresultado confirmou0evidências. Notícias municipais continuam incorretas naV597; imagens e shopping em andamento. Não aplicar fixV598 em produção.

Validação:91 focados passaram; rodada integral intermediária1440passed/2failed/4skip. Falhas: encoding de inserçãoJS(cp1252) e teste de isolamento precisava de outroadmin para permitir bloquear dono sem remover último. Corrigidos; nada removido/silenciado. NamedpipecustomQA recebeu identidade por diretório para não colidir em rodadas paralelas. Código final e suite final ainda pendentes; logs anteriores preservados.
