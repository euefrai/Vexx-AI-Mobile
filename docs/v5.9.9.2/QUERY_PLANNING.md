# Planejamento dentro do motor existente

`search_orchestrator.query_plan` registra somente variantes necessárias: TOPIC_FOCUSED, ORIGINAL_QUERY e, quando há informação requerida separável, ENTITY_EXACT. O plano não significa que todas as consultas foram executadas. A lista de tentativas efetivas continua sendo a fonte de verdade. Notícias, ciência, rotas e lacunas reutilizam suas estratégias existentes; não foi adicionado motor, agente ou provedor.

Exemplo de diagnóstico: História do Museu do Amanhã fontes oficiais → Museu do Amanhã História fontes oficiais; se a resposta ainda trata de outros museus, a mesma fonte pode receber Museu do Amanhã. O pedido completo permanece na validação pós-leitura. Uma consulta sem correspondência não é encerrada como boa apenas porque a coleção inteira contém palavras dispersas do pedido.

Cada tentativa observada registra provedor/consulta, resultados descobertos, novas URLs e candidatos úteis segundo metadados. `evidence_obtained=0` nessa etapa é intencional: descoberta não é leitura. O ganho de domínios/temas agora considera candidatos correspondentes ao pedido; continua sendo ganho de descoberta, não julgamento factual independente.

Os limites existentes de tentativas, consultas, tempo, páginas, bytes e concorrência permanecem. Provedor bloqueado não recebe retries de bypass. No fluxo de notícias a recuperação declarada do publicador vem antes de uma nova busca de manchete que poderia repetir o agregador. Não há tradução livre ou expansões arbitrárias. Novidades ativa intenção noticiosa, mas não inventa automaticamente uma janela de sete dias quando o pedido não a definiu.

O benchmark final ancora somente o relógio do parser no `request.resolved_at` do respectivo baseline. Isso mantém os mesmos dias/horas após a meia-noite, sem modificar perguntas/gabaritos ou o relógio do aplicativo. `request_clock_reference`, SHA do conjunto e revisão constam em cada linha; a rede continua ao vivo e pode mudar.
