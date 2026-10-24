# Runtime e parada cooperativa

`agent_runtime.py` oferece lock de processo do sistema operacional, identidade por relay/papel/instância, metadados atômicos e canal local Windows named pipe. Desenvolvimento exige relay local e banco separado. Diretórios customizados de QA têm canais distintos para impedir colisões entre suítes paralelas.

O canal usa desafio HMAC, nonce, geração, PID e instante de criação do processo. As mensagens são JSON limitado, transportado por bytes; não há pickle, eval, shell ou porta TCP administrativa. A chave fica em diretório com ACL do usuário atual. A segurança é contra outro contexto sem essa chave; processos do mesmo usuário Windows não são um limite de isolamento forte.

Estados: RUNNING → STOP_REQUESTED → STOP_ACCEPTED → STOPPING_NEW_JOBS → DRAINING → SQLITE_FLUSH → CONNECTION_CLOSE → STOPPED. Thread/future é contabilizado antes de iniciar, novas operações são recusadas e trabalhos aceitos podem terminar. Reconnect é interrompível. Timeout de drenagem mantém lock e processo vivos em BLOCKED_DRAIN_TIMEOUT; não autoriza kill nem consumidor concorrente. Uma nova tentativa de stop é possível.

O wrapper importa o backend publicado por caminho absoluto. Na atualização operacional final, 28520 terminou por IPC, o novo PID 13712 iniciou com fonte equivalente à V597, quick_check retornou ok e a contagem de mensagens foi preservada. Hash SHA256 do wrapper carregado: `cb239545cd3de7d8a27ce5b2713bd25ea93d1bbbe4411b42f18d134e53beb5c0`. Recibo completo e backup fora do Git.

Testes locais usam processos reais, pythonw, WebSocket loopback, crash, lock obsoleto, consumidor duplicado, mensagem inválida, autenticação, PID/geração, drenagem e SQLite. Não simulam uma falha real do provedor em produção. Alias diferentes de um mesmo relay e lançadores antigos que ignoram o bootstrap continuam limitações de adoção.

Os operadores `ops_restart_v597.py` e `ops_controlled_restart_v5981.py` são procedimentos direcionados à transição registrada, não um serviço genérico de restart. Não devem ser reexecutados cegamente: validam recibo/PID/criação/revisão e abortam se o cenário mudou. O segundo não força encerramento em timeout. Uma inicialização que permanece viva sem confirmar RUNNING requer inspeção manual; não é declarada recuperação automática comprovada.
