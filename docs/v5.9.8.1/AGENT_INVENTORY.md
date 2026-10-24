# Inventário de agentes — 24/10/2026

Foram encontradas duas cópias de `pc_agent.py`, mas somente um consumidor de produção ativo no inventário inicial. A segunda cópia é o worktree de desenvolvimento, não um segundo processo de produção. Os agentes temporários usados no QA têm relay loopback e SQLite próprios.

| Etapa | Processo | Origem e resultado |
|---|---|---|
| Inventário inicial | PID 25924, pai 18196 | Python 3.12/pythonw, iniciado pelo controle do Fajulto Studio; backend publicado 0814864 |
| Primeira transição | PID 28520 | Wrapper privado com lock e IPC autenticado; mesmo backend publicado |
| Atualização final do wrapper | PID 13712 | Substitui 28520 após STOPPED via IPC; revisão 5517c26 com código equivalente a 0814864 |

O checkout de produção avançou externamente para 5517c26 durante o trabalho. A primeira tentativa de atualizar o wrapper parou na pré-condição de SHA, antes de enviar parada. A comparação posterior confirmou que o descendente contém somente documentação/QA. O operador agora exige ancestralidade, ausência de alterações rastreadas e diff restrito a documentação/QA antes de aceitar essa equivalência. Não houve reset nem publicação da V598.

O supervisor existente usa terminate/kill e não tinha shutdown cooperativo. A primeira parada usou seu endpoint oficial, com zero trabalhos, reserva de escrita SQLite, backup consistente e rollback preparado. Foi último recurso autorizado, não parada graciosa do legado. A segunda foi cooperativa, autenticada, sem terminate/kill.

Hermes, YUI, Studio, túnel e integração vexx_remote são processos separados e foram preservados. A inspeção dirigida de tarefas, serviços e inicialização não identificou outro lançador ativo de PC Agent; não constitui varredura de todos os arquivos da máquina. Nenhum projeto externo foi editado.

O SQLite autoritativo foi identificado pelo ambiente do processo. Recibos completos, inventário, backups e logs operacionais ficam em diretório privado sob o perfil do usuário, fora do Git. O relatório público não contém ambiente, credenciais nem manifestos de contas.

Limitação: o supervisor legado foi marcado como intencionalmente parado e não supervisiona o novo wrapper. Seu lançador antigo ainda pode ignorar o bootstrap/lock até adoção futura do código. Não foi alterado para aparentar integração concluída.
