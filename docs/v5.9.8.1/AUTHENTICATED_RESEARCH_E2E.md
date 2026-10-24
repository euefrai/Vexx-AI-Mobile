# Pesquisa autenticada real após restart

Sessão de teste fornecida pelo usuário na aba Render; sem extrair cookies ou credenciais. Nova conversa de QA, seis cenários e um pedido adicional de resultado: sete mensagens do usuário e sete respostas não vazias, 14 IDs únicos. SQLite e reload confirmaram persistência; o navegador voltou a mostrar PC conectado. Modelo registrado: `poolside/laguna-s-2.1:free`. Nenhuma API paga foi ativada.

| Cenário | Resultado observado | Limite |
|---|---|---|
| Saudação | Resposta normal | Teste de funcionamento, não de pesquisa |
| Documentação oficial TaskGroup | Explicação substantiva, código e link oficial | Leitura integral/verificação de cada afirmação não comprovada |
| Baterias de estado sólido | Job concluído com outcome partial, zero fontes lidas; follow-up confirmou zero evidências | Não há síntese científica validada; concluida é estado terminal, não qualidade |
| Notícias de Ubatã, últimos sete dias | Retornou notícias de outras cidades | Falha geográfica real na V597 publicada |
| Imagens | URLs Wikimedia, sem galeria JDUI | Resoluções não verificadas independentemente; experiência parcial |
| Lenovo 16 GB até R$ 3.000 | Nenhuma oferta verificada; bloqueio 403/CAPTCHA reconhecido | Links genéricos não contam como preço/produto confirmado |

O painel publicado de pesquisa ainda alternou estado antigo de pesquisa/cancelamento após conclusão. A recuperação textual permitiu consultar o resultado; o fix de estado da V598 permanece local. O código publicado não foi substituído para esconder a falha.

Em relação à observação anterior, a pergunta sobre TaskGroup agora recebeu uma resposta substantiva. Os problemas de ciência, precisão municipal, galeria e ofertas verificadas continuam abertos. As 14 mensagens persistidas não provam streaming SSE correto em todos os casos: não houve captura do protocolo de rede em produção. As durações no artefato são totais do backend, não TTFT.

Evidência sanitizada: `qa-artifacts/v5981/research-e2e-persistence.json`. Identificadores de proprietário/conversa ficam somente no recibo operacional privado. Não foram consultadas conversas pessoais para compor estes resultados.
