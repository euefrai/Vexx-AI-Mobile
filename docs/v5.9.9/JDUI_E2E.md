# Chat real e QA visual

Ambiente: Chrome, relay FastAPI local, PC Agent real, WebSocket e SQLite temporários; login de conta QA e modelo configurado explicitamente gratuito. Sem sessão ou dados pessoais de produção. Os scripts de QA não são o motor do produto.

As dez perguntas A–J do pedido foram executadas pela UI. Cada resultado foi seguido por reload e conferência de persistência. A primeira rodada revelou falhas que o harness de componentes anterior não mostrava: mídia em consulta não visual, documentação sem busca, aviso de job em vez de galeria e texto de ferramenta não executada. Logs intermediários foram preservados.

A rodada posterior mostrou cinco cards reais Commons na pergunta da Ponte Estaiada, três imagens carregadas na observação inicial e persistência após reload. Isso comprova o caminho do resultado ao chat; não é análise visual nem prova de que toda miniatura carregará em qualquer rede. Vídeos não recuperados e ofertas bloqueadas continuam limitações reais.

Uma captura de corpo SSE no Playwright ficou aguardando encerramento embora a UI já tivesse respondido. O teste passou a observar término visível e persistência. Não se declara captura do protocolo completo do app: a sonda SSE upstream do modelo é separada e limitada a prefixo de 64 KB. Nenhum raciocínio privado foi gravado; somente contagens de campos/eventos e resposta pública.

Geometria, modal, teclado, zoom CSS 200%, redução de movimento, estados vazios e screenshots finais devem ser lidos nos artefatos/relatório. Ausência de erro JS não é usada sozinha como aprovação visual. Viewports simulados não equivalem a aparelho físico nem a perfil de CPU/RAM mobile.

Resultado final visual: root=viewport em1280/390/320, cards245/350/288px; modal/setas/Escape/foco/reload e estado de metadados passaram, cinco imagens carregadas e zero erros JS. A suíte final de entrega registrou1493passed/4skip/2warnings. O estado terminal de requisições também ganhou regressão SQLite após observar um checkpoint tardio reabrindo processing; não confundir conclusão visual com esse marcador do backend.
