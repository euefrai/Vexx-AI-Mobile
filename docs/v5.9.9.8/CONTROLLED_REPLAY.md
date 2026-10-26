# Replay controlado

Entrada API congelada: e32a6f3be16947a4f0647f15adfc9f4011cdb6e6f6bc9f505263299f7079f16d.

| Versão | Leituras | Evidências | Sintaxe / retorno / comportamento |
|---|---:|---:|---|
| ff486ed | 12 | 2 | suportado / descoberto / descoberto |
| cc60042 | 10 | 3 | suportado / parcial / descoberto |
| Correção final | 3 | 3 | suportado / parcial / suportado |

Replay de texto não executa novamente a extração HTML. Comparação A de snapshots verifica separadamente a extração; sete hashes iguais nos pares acessíveis. Replay HTML de desenvolvimento: API 6→0 leituras, 0→0 evidências; empresa 5→5, 0→0; história 7→7, 0→0.

Limites: pool compartilhado não mede qualidade das consultas; frozen_missing não representa falha de rede; diferenças de agendamento impedem atribuir toda redução de leituras exclusivamente ao código. Não usar RSS pontual como pico. Tempos, SQLite e tamanho de cache são amostras do harness, não latência de produção.

Excluir das conclusões A antigos arquivos sem sufixo verified: adaptador inicial devolvia uma fonte para URLs diferentes. Excluir replay-api-candidate.json intermediário: filtro de índice pai ainda incorreto. Artefatos mantidos localmente para rastreabilidade; resumos usam execuções verificadas.
