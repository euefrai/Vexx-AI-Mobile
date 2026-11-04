# Redução de bloqueios e recuperação de leitura

Data: 04/11/2026. Escopo desta rodada: publicar as correções de leitura já
validadas, pesquisar documentação e preparar os próximos passos. As mudanças
de arquitetura abaixo descrevem o plano original. Os incrementos 1 e 2 foram
implementados depois, localmente, em `RELATORIO_ACESSO_PESQUISA.md`, com resultados
reais e limitações explícitas. O incremento 3 foi implementado depois, com
cache limitado em memória e revalidação, em `RELATORIO_CACHE_E_CARDS.md`.
Recuperação externa e aprovação completa da síntese continuam pendentes.

## Conclusão

O Vexx precisa diminuir a dependência de uma única página HTML e distinguir
falhas de acesso, extração e geração. Não há evidência de um mecanismo que
garanta acesso a todo site. A prioridade será aumentar a proporção de perguntas
respondidas com conteúdo efetivamente lido, preservando precisão e origem.

## Verificações atuais

Três requisições públicas, anônimas e somente de leitura, sem gerar respostas
com modelo nem usar a sessão de produção. Registro:
`qa-artifacts/research-access-channel-probe.json`.

| Canal | Resultado nesta máquina | Interpretação |
| --- | --- | --- |
| Ubatã Notícias, REST pública do WordPress | Um post com conteúdo e URL original; sem desafio detectado; 1,09 s | Canal promissor para leitura, além do feed já existente. Não comprova relevância regional, atualidade de todas as notícias nem funcionamento no Render. |
| KaBuM, página exata de uma RTX 3050 6 GB | HTML recuperado e 2.717 caracteres extraídos; sem desafio detectado; 1,36 s | A página específica pode ser lida neste ambiente; não demonstra acesso irrestrito à loja nem aprovação de preço/estoque. |
| API oficial do Mercado Livre, sem token | HTTP 403; 0,65 s | Acesso negado. Não houve evidência suficiente para atribuir a causa a CAPTCHA ou afirmar que um token sozinho resolverá. |

São observações pontuais. Rede/IP do servidor pode ter resultado diferente.
Não foi medida uma taxa global de bloqueio, nem testadas todas as lojas.

## O que o código já tem e onde perde informação

- `search_providers.py:_buscar_impl`: pausa por provedor após bloqueios.
  `research_agents.py:agente_analista`: cache negativo por URL dentro do job,
  com expiração. Falta coordenação de leitura por origem entre pesquisas.
- `research.py:baixar`: preserva HTTP no erro, mas agrupa 401, 403 e 429 sob
  `bloqueado`; não conserva `Retry-After` para a política geral de leitura.
  `academic_research.py:_retry_after` já oferece um precedente interno.
- `research.py:document_cache_context`: cache de leitura vinculado a
  proprietário, conversa, objetivo e job. Esse isolamento é necessário para
  evidências; sozinho não evita baixar novamente o mesmo documento público
  em outra pesquisa. Não se deve compartilhar trechos selecionados para outra
  pergunta sem revalidar entidade, versão e requisitos.
- `public_store_reader.py:render`: chama Firecrawl sem `Authorization`, captura
  erros e retorna `None`. A opção vem desligada por padrão. O contrato oficial
  exige Bearer token; esse modo anônimo não é base confiável de produção.
- Já existem catálogo público KaBuM, feeds de publicadores, APIs acadêmicas,
  inventário Python, Brave opcional e Mercado Livre com token opcional.
  A estratégia deve aproveitar esses adaptadores, sem duplicá-los.
- Os últimos testes de síntese também tiveram autenticação/cota inválida e
  resultado parcial no Mistral. Isso é separado do acesso aos sites e continua
  pendente em `RELATORIO_LEITURA_COMPLEMENTAR.md`.

## Plano de implementação em ordem

1. **Diagnóstico e controle por origem.** Preservar status HTTP, `Retry-After`,
   método de leitura e motivo específico. Separar autenticação, acesso negado,
   desafio observado, limite de tráfego, timeout, HTML vazio, extração sem trecho
   e falha do modelo. Limitar concorrência, juntar downloads simultâneos da mesma
   URL e pausar a origem com prazo limitado. Não presumir que todo 403 é CAPTCHA;
   não repetir a chamada quando o prazo exceder o orçamento da pesquisa.
2. **Canais públicos do próprio publicador.** Para Ubatã, validar a REST pública
   com filtros de período, conteúdo, identidade do artigo e URL original.
   Manter RSS resumido como descoberta. Em compras, aproveitar os adaptadores
   existentes: catálogo para encontrar o produto, página/API para confirmar
   variante, oferta e link. Uma API autenticada continua sujeita a permissões.
3. **Cache de documento separado de evidências.** Começar por dados públicos
   dentro do mesmo proprietário, sem cookies/sessão. Revalidar corpo e versão,
   usar ETag/Last-Modified quando o servidor permitir e respeitar Cache-Control,
   Vary e no-store. Selecionar passagens novamente para cada pedido. Conteúdo
   antigo não confirma preço ou notícia atual; guardar data de coleta e escopo.
4. **Recuperação limitada de conteúdo.** Tentar representações publicadas
   oficialmente, inclusive Markdown quando oferecido, e uma alternativa
   pertinente quando a fonte não for exigida pelo usuário. Um leitor externo
   autenticado pode ser avaliado com orçamento máximo e procedência explícita;
   não ativar serviço pago nem enviar URLs privadas automaticamente. Registrar
   falhas por URL mesmo quando o serviço responder HTTP 200. Não usar automação
   para resolver desafios nem tratar renderização JavaScript como garantia.
5. **Prova de ponta a ponta.** Repetir perguntas inéditas de compras, notícias,
   documentação e pesquisa acadêmica com modelo operacional. Conferir trecho,
   síntese, citações, produto exato, cards e reload. Executar casos também no
   caminho real do servidor antes de atribuir os resultados à produção.

As proteções SSRF, redirects, limites de bytes/tempo, isolamento de contas e
regras de fonte explícita continuam obrigatórias. Não encaminhar credenciais
entre origens ou provedores. Não converter snippet, resumo ou tela de bloqueio
em evidência de documento integral. Um site inacessível pode continuar
inacessível; a resposta deve identificar o que foi comprovado e o que faltou.

## Aceitação e medição

Comparar uma matriz fixa antes/depois, preservando erros e denominadores:
descoberta relevante; transporte bem-sucedido por origem/canal; trecho útil
recuperado; requisitos com suporte; resposta final correta e citada; persistência
dos cards; requisições por resposta, latência e custo. Repetir em mais de uma
janela de tempo. Melhorar esses indicadores sem trocar o assunto da pergunta,
inventar preços, afrouxar validadores ou apenas aumentar o total de testes.

Primeiro incremento recomendado: item 1, com testes focados de 401/403/429,
Retry-After em segundos/data, concorrência, expiração, cancelamento e SSRF.
Depois, o canal WordPress de Ubatã, comprovado aqui somente como acesso público.
SearXNG permanece fora deste incremento: ampliar descoberta não resolve sozinho
o acesso ao documento de origem.

## Documentação consultada

- [OpenAI: Web search](https://developers.openai.com/api/docs/guides/tools-web-search):
  documenta acesso ao vivo e conteúdo indexado/em cache. Não revela um método
  universal de contornar desafios nem permite inferir a infraestrutura interna
  do ChatGPT, Gemini ou Perplexity.
- [Cloudflare: políticas para bots](https://developers.cloudflare.com/waf/custom-rules/use-cases/challenge-bad-bots/):
  o operador pode permitir bots verificados e desafiar/bloquear outros.
  Trocar apenas User-Agent não concede essa identidade ou permissão.
- [Google: controle de frequência](https://developers.google.com/crawling/docs/crawlers-fetchers/reduce-crawl-rate):
  descreve redução de tráfego diante de 429/503 e o uso de Retry-After.
- [WordPress: posts REST](https://developer.wordpress.org/rest-api/reference/posts/):
  documenta consulta, período, conteúdo e recuperação de artigo por ID.
- [Firecrawl: contrato de scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape):
  autenticação Bearer obrigatória; a integração atual precisa de revisão antes
  de se apoiar nesse canal.
- [Tavily: Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract):
  mostra resultados por URL e `failed_results`, inclusive sob HTTP 200.
- [Cloudflare: Markdown for Agents](https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/):
  negociação `Accept: text/markdown` apenas nas zonas que habilitaram o recurso.
  Não remove controles de acesso; a representação convertida não conserva ETag
  e Last-Modified para revalidação condicional.

Não houve teste de serviço externo pago, configuração de novas chaves,
implementação deste plano ou reinício do PC Agent nesta rodada.
