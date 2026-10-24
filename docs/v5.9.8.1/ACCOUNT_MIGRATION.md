# Migração de contas V5981

## Dry-run operacional — antes da aplicação

SQLite autoritativo: identificado no ambiente do novo PC Agent de produção, fora do Git. Cinco contas existentes: três admin e duas user. As duas user estão ativas, aprovadas, têm credencial local e evento usuario_criado pelo fluxo oficial aberto. Não há marcador de serviço/fixture nessas contas. Dono legado permanece admin.

Critérios: snapshot congelado, status ativo, aprovado=1, credencial presente, origem de criação oficial auditada, sem marcador de teste/serviço; desconhecidas são excluídas. Novos usuários após a aplicação não entram, mesmo em reexecução. Os nomes e os manifestos por UID ficam no diretório operacional privado.

Plano: testar migração e reversão em SQLite temporário; confirmar vínculo da conta local com a configuração do processo; backup consistente e quick_check; BEGIN IMMEDIATE; alterar somente role; inserir auditoria transacional por UID e recibo em app_config. Confirmar hashes, status, aprovação, remote_ok, IDs, ownership e sessões preservados. Sem migração em startup e sem alteração do padrão de cadastro user.

Estado: dry-run validado; duas promoções previstas, três admins preservados. Resultado da aplicação será registrado após execução.
