# V5.9.4 — incidentes e causas comprovadas

Checkout inicial: `24ba58b`. A versão publicada não foi inspecionada. As capturas descritas no pedido não trazem o histórico/RPC original; não atribuímos automaticamente o incidente publicado a este checkout.

| Incidente | Evidência anterior | Causa localizada | Correção / prova |
|---|---|---|---|
| A: Ubatã não localizada | `baseline.json`: consulta real `name=ubata bahia` vazia; consulta por `Ubata` retorna Ubatã/BA | Cidade e UF enviadas juntas como nome; ausência de restrição administrativa | Separação cidade/UF/país, cadastro IBGE e correspondência normalizada exata. Chrome real confirma IBGE 2932309 / GeoNames 3445849. |
| B: contexto perdido | Resposta de erro não começava com o cabeçalho de clima usado pelo antigo resolvedor | Continuação dependia do texto da última resposta; pedidos de esclarecimento/erros não conservavam cidade | Reconstrução de slots usando até 32 mensagens da própria conversa, anteriores à requisição. Mantém cidade após falha, usa amanhã como previsão e pergunta atual como atual. |
| C: oi vira cidade | `greeting_after_weather` reproduziu `qual a temperatura em oi` | Captura permissiva de cidade pendente antes de classificar cumprimento | GREETING determinístico primeiro; Chrome mede zero geocodificações após oi. Cidade explicitamente chamada Oi continua consultável. |
| D: barra rejeitada | `slash_location_after_weather = null` | Validador de cidade curta excluía `/` | Slot aceita cidade/UF com barra; UF/país filtrados antes de selecionar resultado. |
| E: cidade/temperatura substituídas | Não reproduzido valor inventado do modelo original | O antigo atalho para uma única capital não exigia o estado solicitado; respostas de modelo não eram prova de clima | Removida preferência automática por capital; nome exato, UF, país, município, ambiguidade de coordenadas e limites/unidades/idade do dado verificados. Sem valor quando fonte falha. |
| F: modelo 429 | Nenhum 429 de Mistral real provocado nesta execução | Dependência desnecessária de inferência em intenções resolvíveis por ferramenta; fallback de modelos já tem fila limitada e backoff | Clima/horário/local/câmbio/cumprimento diretos nos dois caminhos sync/SSE. Sentinelas garantem ausência de LLM. 429 meteorológico simulado prova cooldown de 60 s e uma chamada em duas tentativas. Nenhum modelo pago ativado. |
| G: TODO.md | `unrelated_doc_fallback = true` em SQLite descartável com TODO de outro chat | `or docs` usava último documento de todo o proprietário; nome-base também era comparado globalmente | Escopo de conversa aplicado na consulta SQL antes do limite; pedido de documento explícito e limite de palavras. Não ler quando negado. Testes de outro chat, usuário, projeto e nome comum “todo”. |

O caminho G é comprovado localmente. **Não prova que o TODO.md da captura tenha sido recuperado por esse caminho**, nem que houve acesso entre usuários. A consulta anterior já filtrava proprietário. Nenhuma credencial, grant ou permissão remota foi alterada.

## Fluxo e limites

Frontend → relay → `ai_preparar`/idempotência → `cmd_dados_atuais` → Intent existente + slots de mensagens → geocodificador IBGE/GeoNames → Open-Meteo/relógio → persistência da resposta direta → SSE → schema JDUI existente.

Slots são reconstruídos, sem tabela de memória paralela: intenção meteorológica, cidade/UF/país (normalizados no resolvedor), período, unidade Celsius, pedido original, pendências e origem conversa/esclarecimento. Cumprimento ou novo assunto interrompe a tarefa. Histórico é limitado por proprietário/conversa e rowid da mensagem atual; uma mensagem posterior já inserida não pode fornecer sua cidade a uma requisição anterior.

Documentos implícitos ficam no chat onde foram anexados. Os chats de dois projetos distintos têm slots/documentos separados. Mover o mesmo chat para outro projeto preserva o histórico desse próprio chat; não foi criado um novo sistema de grants de projetos. APIs explícitas de documentos continuam usando sua autorização existente.

Ferramentas diretas dispensam montagem do prompt com documentos/memórias/pesquisa. Memória global autorizada e recursos de pesquisa existentes foram preservados. Não foi feita uma afirmação de isolamento universal de todos os mecanismos de memória.


## Revisão de conflitos adicionais

Após o primeiro integral verde, duas reproduções adicionais: `qual é o código IBGE de Ubatã BA?` retornava None no adaptador por conter “código”; `crie um modelo 3D da cidade de Salvador` retornava LOCATION_LOOKUP antes do motor 3D. O filtro agora distingue código IBGE de programação, a consulta extrai município/código oficial e a rota direta respeita primeiro a intenção model3d existente. Três regressões novas e o conjunto 3D passaram, sem alterar arquivos do motor 3D. Evidência de consulta oficial externa em `official-id-live.json`.
