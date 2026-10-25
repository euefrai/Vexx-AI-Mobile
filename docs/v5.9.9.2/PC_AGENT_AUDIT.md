# Auditoria operacional somente leitura

Snapshot atual em `qa-artifacts/v5992/runtime-observation.json`: somente um processo local correspondente foi observado, PID10744, pai6708, iniciado pelo controle do Studio, checkout de produção, SQLite padrão em `%USERPROFILE%/.julia-mobile/memory.sqlite3`, relay Render e TCP ESTABLISHED em443. Os dois PIDs históricos da versão anterior não foram tratados como atuais. Revisão efetivamente importada não foi atestada por esse processo legado.

Isso não prova ausência global de outro agente em outro host, nem competição real por consumidor. Sem canal de controle do legado ou trace autorizado de request/job IDs do relay, jobs internos, autenticação da conexão e competição permanecem desconhecidos. Nenhum conteúdo do SQLite real foi lido ou alterado; nenhum stop/restart/kill foi enviado a produção. O Studio permaneceu intacto. Os processos QA usam SQLite temporário e relay localhost próprios.

Recomendação posterior: obter identificação da revisão/instância e operações pelo canal suportado; correlacionar consumidor e request IDs no relay; padronizar a entrada pelo wrapper com singleton e inicialização idempotente; testar concorrência e parada graciosa em QA; somente então consolidar produção com autorização operacional específica. A proteção do wrapper não impede automaticamente um launcher legado que o contorne.
