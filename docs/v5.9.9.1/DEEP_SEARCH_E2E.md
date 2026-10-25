# Deep Search autenticado

Harness existente com relay loopback, PC Agent real em development, SQLite temporário, contas fixture, controle remoto0 e modelo configurado explicitamente free. Nenhuma conta/credencial real usada. Os dois processos de produção não participaram.

Doze cenários exercitados: pesquisa curta, pedido longo, notícias municipal/nacional/internacional, documentação, produto, imagens, PDF público, multietapas, divergências e escassez. Logs iniciais mostram falhas reais e do harness: cookie de QA reaproveitado entre bancos temporários gerou403 e foi resolvido com sessão de teste nova, sem reduzir CSRF; espera assíncrona do primeiro harness avançou antes do término de jobs; exportação apontava para painel errado. Casos afetados foram repetidos com polling explícito e links do hub real, sem chamar essas rodadas iniciais de aprovação.

## Correções comprovadas

Comando profundo de notícias chegava antes à rota rápida. Agora cria job; a fundo conserva profundidade. Resultado do compositor existente é persistido com ID estável por job, tanto no worker quanto na leitura de status para recuperação idempotente. UI busca a mensagem pelo fluxo normal de sincronização. Não usa ai_requests de outra mensagem, não duplica no polling, não ressuscita chat excluído e não entrega resultado novo de job cancelado.

Fronteiras de investigação mantêm identificadores técnicos do pedido original. Caso de retomada inicialmente devolveu direitos autorais para TaskGroup; repetição final7011908 devolveu código da documentação oficial Python. Aliases de exemplos/limitações permitem documentos ingleses pertinentes, sem aceitar a página de assunto errado.

## Resultado e escopo

Jobs multietapas/divergências/escassez chegaram a estado terminal e entregaram mensagem final única após o aviso de início. Cancelamento resultou cancelada, sem mensagem final extra. Reload após início retomou a consulta e preservou resultado. Os outcomes foram **parciais**; término operacional não significa investigação completa ou síntese LLM aprovada.

Último SQLite: 5 mensagens/5 IDs, 2 requests completed, 1job concluida, 1resultado persistido, fonte oficial e0 operações ativas no runtime QA antes da parada graciosa. IndexedDB continha5 mensagens, 2assistentes estruturados e1resultado de pesquisa. Reload, MD/CSV e recuperação de imagem com falha injetada foram executados. Todos os harnesses QA foram encerrados e seus bancos temporários removidos.

SSE normal/stream/replay e isolamento estão na suíte. O navegador observou HTTP200, conteúdo final e persistência; não capturou todos os bytes SSE do app. A sonda upstream é separada. Não anunciar Deep Research universal completo: conteúdo/fatos/preços não recuperados continuam explícitos e não há julgamento factual independente de todas as respostas.
