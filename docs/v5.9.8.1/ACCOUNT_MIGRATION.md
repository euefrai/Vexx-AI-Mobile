# Migração de contas V5981

## Dry-run operacional — antes da aplicação

SQLite autoritativo: identificado no ambiente do novo PC Agent de produção, fora do Git. Cinco contas existentes: três admin e duas user. As duas user estão ativas, aprovadas, têm credencial local e evento usuario_criado pelo fluxo oficial aberto. Não há marcador de serviço/fixture nessas contas. Dono legado permanece admin.

Critérios: snapshot congelado, status ativo, aprovado=1, credencial presente, origem de criação oficial auditada, sem marcador de teste/serviço; desconhecidas são excluídas. Novos usuários após a aplicação não entram, mesmo em reexecução. Os nomes e os manifestos por UID ficam no diretório operacional privado.

Plano: testar migração e reversão em SQLite temporário; confirmar vínculo da conta local com a configuração do processo; backup consistente e quick_check; BEGIN IMMEDIATE; alterar somente role; inserir auditoria transacional por UID e recibo em app_config. Confirmar hashes, status, aprovação, remote_ok, IDs, ownership e sessões preservados. Sem migração em startup e sem alteração do padrão de cadastro user.

## Resultado aplicado

Executada explicitamente no SQLite real após backup consistente e quick_check: duas promoções; admins passaram de três para cinco. Nenhuma conta foi criada/removida, nenhum password foi alterado. A comparação antes/depois confirmou IDs, hashes, nomes, status, aprovação, remote_ok, limites e sessões existentes inalterados. Reaplicação promoveu zero contas.

UID canônico do proprietário: local. Seu alias de login legado difere do username no SQLite, sem colisão com outro UID; o vínculo foi validado sem forçar renomeação. A classificação das duas contas usa proveniência de cadastro aberto oficial e ausência de marcadores de serviço/teste, não uma comprovação externa de identidade humana.

O plano congelado é revalidado sob BEGIN IMMEDIATE. Mudança concorrente aborta; a atualização somente de role, eventos de auditoria e marcador único em app_config são atômicos. Contas posteriores permanecem user, inclusive em nova execução. Não há migração em startup.

Reversão foi testada em banco temporário: atua apenas nas promoções pertencentes ao recibo, ignora alterações posteriores de papel, preserva o último admin e mantém o marcador contra reaplicação. Nenhuma reversão foi executada no banco real. Manifesto por UID, backup e recibo completos permanecem privados fora do Git.
