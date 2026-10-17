# Dados atuais no chat

Implementação de 17/10/2026. Pedidos de clima, notícias e relógio são resolvidos antes do LLM, nos fluxos completo e SSE. A resposta usa as mesmas regras de persistência, replay e ownership das outras mensagens.

## Como usar

- `Qual o clima agora?` — usa a localização autorizada nas configurações; sem ela, pergunta a cidade. Responder `Salvador, Bahia` continua a consulta original, inclusive se ela pedia previsão.
- `Qual o clima agora em Salvador, Bahia?`
- `Vai chover amanhã em Recife, Pernambuco?`
- `Previsão do tempo para os próximos 7 dias em Lisboa, Portugal.`
- `Que horas são?`, `Qual a data de hoje?`, `Qual é a data?` — relógio e fuso enviados pelo aparelho; calendário continua usando o mecanismo existente.
- `Que horas são em Tóquio, Japão?` — geocodificação e conversão por fuso IANA, sem inferência do modelo.
- `Quais as notícias de hoje?`, `Últimas notícias sobre tecnologia.`

Não deduz cidade pelo IP ou pelo fuso. Cidade escrita no pedido tem prioridade sobre a configuração. Homônimos podem exigir estado/país. Não solicita GPS automaticamente nem salva nova memória de localização. O cache meteorológico usa coordenadas arredondadas; não contém IDs de contas.

## Fontes, custo e limites

**Open-Meteo:** geocodificação e condições meteorológicas/previsão. Dispensa chave e cadastro na API gratuita, destinada a uso **não comercial**, com limite anunciado de 10.000 chamadas/dia e sem garantia de disponibilidade. Uso comercial exige revisar a licença/contratação ou hospedar uma alternativa. Dados requerem atribuição, incluída na resposta. Referências: [documentação](https://open-meteo.com/en/docs), [geocoding](https://open-meteo.com/en/docs/geocoding-api), [preços e termos de uso](https://open-meteo.com/en/pricing).

O clima informa temperatura, sensação, umidade, vento, horário de validade, consulta e fonte. Condições são estimadas por modelos meteorológicos, não uma observação instantânea garantida no endereço do usuário. Previsão inclui mínima/máxima e probabilidade de chuva; não há dados históricos nesta integração.

**Notícias:** consulta Bing News RSS existente; se não houver resultados recentes utilizáveis, tenta feeds públicos do [G1](https://g1.globo.com/rss/g1/), [BBC Brasil](https://feeds.bbci.co.uk/portuguese/rss.xml) e [Agência Brasil](https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml). Exibe até cinco manchetes com links, veículo e data, sem republicar artigos nem fingir que os leu integralmente. “Hoje” respeita o fuso recebido; pedidos genéricos usam até 48 horas. Notícias sem data, antigas, futuras ou publicidade identificada pela URL são descartadas.

**Relógio:** não necessita de API de hora. Usa o instante do aparelho e `zoneinfo`; para outra cidade, resolve seu fuso. Sem instante local recebido, uma consulta explícita a outra cidade usa o relógio UTC do agente convertido e identificado. Sem cidade nem relógio local, pede a informação em vez de inventar localização.

Cache em memória limitado a 128 entradas: geocoding 1 hora, clima 5 minutos, notícias 3 minutos. Não serve leitura vencida como “agora”; rejeita condições com mais de 2 horas ou muito à frente do relógio do agente. Consultas HTTP têm timeout e limite de bytes. Notícias têm orçamento aproximado de 14 segundos entre provedores; DNS/redirects podem acrescentar tempo. Uma chamada em andamento termina no timeout; cancelamento SSE impede persistir/enviar a resposta final depois de cancelada.

## Segurança e falhas

Hosts das APIs/feeds são fixos; parâmetros são codificados. O cliente HTTP existente valida SSRF, redirects e tipo de conteúdo. Acrescentado suporte a gzip com limite tanto comprimido quanto descomprimido (necessário para o feed real do G1). Nenhum script de modelo é executado. Conteúdo externo é formatado como dados, não reinjetado como instrução no LLM.

Rede/429/403/dados inválidos geram uma explicação breve. Não há bypass de bloqueios ou troca silenciosa por números inventados. A consulta continua dependendo do PC Agent e da internet; o cache não transforma o serviço em clima offline.

## Verificação

`tests/test_live_data.py` cobre roteamento, datas, cache, valores faltantes, ambiguidades, prioridade de localização explícita, filtros de notícias, erros de rede, gzip limitado, persistência, replay, isolamento de contas/conversas e cancelamento SSE.

`tools/qa-live-data.cjs` executa Chrome contra `tests/preview_workspace.py`, com SQLite temporário e APIs externas reais. Evidências em `qa-artifacts/live-data/`. Nunca apontar o preview para dados reais. A política de modelos, credenciais, autenticação e permissões não foi alterada.
