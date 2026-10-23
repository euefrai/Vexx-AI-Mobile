# V5.9.5 — matriz de provedores

Registro executável: `search_providers.capacidades()`. Snapshot: `qa-artifacts/v595/provider-capabilities.json`. Campos declarados descrevem o adaptador, não constituem aprovação externa. Os adaptadores públicos desse registro não recebem chave; isso não garante disponibilidade irrestrita do serviço.

| Adaptador existente | Entrega efetiva do adaptador | Autenticação/limites e prova nesta rodada |
| --- | --- | --- |
| Crossref | Metadados, DOI, autores, ano, abstract e links quando presentes | Público; metadados não equivalem a texto completo. Utilizado na investigação acadêmica; cobertura depende do depósito. |
| DDG | Descoberta web | Bloqueio observado; circuito aberto, sem contorno nem repetição após bloqueio. |
| Bing / Marginalia | Descoberta web | Timeout e limites existentes; resultados externos podem ser genéricos ou irrelevantes. Não fornecem inventário. |
| Google News RSS / Bing News | Título, URL e data declarada; Google também publicador | Feed tratado como metadado. Notícias locais retornaram feeds, sem artigo original lido. |
| Wikipédia | Descoberta enciclopédica | Fonte secundária; sem aprovação universal nesta rodada. |
| Stack Exchange / HN | Discussões técnicas e links | API pública; respeitar backoff. Não substituem documentação oficial nem artigos primários. |
| PubMed | Descoberta biomédica | Metadados não garantem OA. Não aprovado como leitor de texto completo nesta rodada. |
| Open Library | Catálogo bibliográfico | Não é oferta de compra nem estoque. Sem aprovação externa específica nesta rodada. |
| Banco Mundial / BCB | Indicadores/séries públicas | Frequência da série limita atualidade. Resposta de câmbio diário real, sem alegação de cotação de negociação em tempo real. |
| Commons | Descoberta de imagens/URLs | O adaptador não entrega licença completa; não declarar uso comercial autorizado. Pedido real de imagem não foi atendido. |
| Leitor oficial de documentação | HTML da página oficial selecionada | TaskGroup passou de zero para uma fonte oficial lida. Síntese por modelo não aprovada. |
| Shopping web existente | JSON-LD/Microdata/OG, páginas individuais, referências | 13 consultas reais; zero oferta exata confirmada. MLB não repetido após 403 anterior; rota web identificada nos artefatos. |
| OpenAlex / leitor OA existentes | Localização OA, texto HTML/PDF limitado com identidade | Dois PDFs efetivamente abertos. Novo caminho HTML provado por fixture, sem aprovação externa HTML. |
| Visual Crossing existente | Clima municipal agregado | Uma consulta real com configuração já existente; módulo e chave não alterados. |
| Modelo `poolside/laguna-s-2.1:free` | Descoberta de catálogo e tentativa de SSE | Presente entre 425 modelos; tentativa vazia, zero chunks. BLOCKED; sem novo retry ou fallback pago. |

## Direitos, custo e limites

O snapshot mantém `commercial_use=not_assessed`, direitos específicos da fonte, atualidade não garantida e `e2e_verified_fields=[]`. Não há avaliação jurídica de licença ou promessa de gratuidade permanente. Conteúdo OA não implica autorização comercial: um dos PDFs declara CC BY-NC-SA. Não foram criadas contas nem habilitados serviços pagos.

Consulta documental oficial: [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api), [metadados Crossref](https://www.crossref.org/documentation/retrieve-metadata/), [autenticação OpenAlex](https://help.openalex.org/api/authentication/). Não presumir OpenAlex irrestrito sem chave apenas porque uma consulta anterior funcionou. [Europe PMC REST](https://europepmc.org/RestfulWebService) e [OA](https://dev.europepmc.org/downloads/openaccess) foram avaliados documentalmente; nenhum adaptador Europe PMC foi adicionado.

Rede preserva downloader seguro, bloqueio de destinos privados, limites de bytes/tempo, checagem de identidade e circuito existente. Descoberta de mídia não baixa conteúdo nem executa código do modelo. Inventário de viagens/compras nunca é verificado por mero HTML de busca.
