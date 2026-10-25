# Auditoria operacional sem mutações

Snapshot fresco identificou Python13712 via agent_runtime_v5981_final.py e31456 via pc_agent.py, este filho do controle do Studio. Ambos apontavam ao relay Render/diretório de produção e tinham TCP ESTABLISHED ao mesmo remoto443. Isso comprova conexões TCP; não prova duas sessões WebSocket autenticadas, competição por consumidor nem qual agente serve cada job.

Foi consultado **somente status** no canal IPC autenticado do wrapper, após verificar PID e instante de criação. Resposta: RUNNING, active_operations0 naquele instante. Entradas históricas de status sem processo vivo foram contabilizadas separadamente; não são dezenas de agentes ativos. Chave, nonce, prova, generation e endereço do canal não foram exportados.

O legado não oferece esse canal identificado. Jobs ativos/competição nele e commit efetivamente importado permanecem desconhecidos. HEAD no disco não atesta código carregado. Caminho SQLite é o configurado/default do backend; não foi lido conteúdo real para esta auditoria. Nenhum stop/restart/kill foi enviado a produção, nenhum dado real alterado e Studio não foi editado. Status de produção não é status dos agentes QA isolados.

O singleton protege launch pelo wrapper; não protege automaticamente inicialização direta que o contorne. Plano futuro: verificar tarefas por canal autorizado/relay, identificar supervisor e fonte carregada, padronizar uma entrada com lock e inicialização idempotente, exercitar concorrência/parada em QA e só então consolidar produção com autorização operacional específica. Não matar PID histórico. Impacto potencial na pesquisa existe, mas não foi atribuído a um erro concreto sem rastrear request/job IDs do relay.
