# APIs gratuitas de pesquisa (camada adicional)

Esta camada melhora a descoberta com APIs públicas documentadas. Ela é
**aditiva**: nenhum provedor antigo foi removido e qualquer falha nova vira
`ErroProvedor`/`ErroFonte`, registrada nas métricas, sem interromper o fallback.

## Princípios

- **Sem bypass**: nada de contornar CAPTCHA, bot-wall, 403 ou endpoint não
  documentado de loja. Quando a fonte recusa, o código é `bloqueado` e a busca
  continua em outro provedor.
- **Sem chave obrigatória**: os provedores keyless funcionam por padrão.
  Provedores com chave (Brave, GitHub e Mercado Livre) só entram quando a
  variável correspondente existe.
- **Sem invenção**: cada resultado mantém a URL e o trecho devolvidos pela
  fonte. Dados estruturados (CEP/CNPJ/cotação) são marcados como
  `content_scope=metadata_only`; não são apresentados como texto lido.
- **Falha isolada**: timeout, 429, JSON inválido ou payload acima do limite
  afetam somente aquele provedor.

## Provedores integrados

| Provedor | Endpoint público | Autenticação | Limite gratuito documentado | Uso no Vexx |
|---|---|---|---|---|
| OpenAlex | `api.openalex.org/works` | Nenhuma (chave gratuita opcional) | ~10 req/s keyless; chave eleva cota e habilita cursor paging | Metadados acadêmicos, DOI, resumo, acesso aberto |
| arXiv | `export.arxiv.org/api/query` | Nenhuma | ~1 requisição a cada 3 s recomendada | Preprints, autores, PDF e DOI quando publicado |
| GitHub | `api.github.com/search/repositories` | Nenhuma; `GITHUB_TOKEN` opcional | 10 buscas/min sem token; token eleva o limite | Repositórios, estrelas, linguagem e licença |
| BrasilAPI | `brasilapi.com.br/api/cep/v2/{cep}` e `/api/cnpj/v1/{cnpj}` | Nenhuma | Uma consulta por documento explícito | CEP, endereço, IBGE, coordenadas; CNPJ, razão social, CNAE e situação |
| CoinGecko | `api.coingecko.com/api/v3` | Nenhuma no endpoint demo | Cota pública do plano demo | Cotação BRL/USD, variação 24h e ranking de criptoativos |
| Brave Search | `api.search.brave.com/res/v1/web/search` | `BRAVE_SEARCH_API_KEY` | Crédito gratuito mensal; limites do plano contratado | Busca web independente quando a chave existe |
| Mercado Livre | `api.mercadolibre.com/sites/MLB/search` | `MERCADO_LIVRE_ACCESS_TOKEN` opcional | API pública pode responder 403 sem token | Ofertas oficiais quando o token está configurado; fallback de lojas sem ele |

### Onde cada um entra no roteamento

- **CEP/CNPJ explícito** → `brasilapi` primeiro, depois buscadores gerais.
- **Criptoativo nomeado** (bitcoin, ethereum, criptomoeda etc.) → `coingecko`
  primeiro, depois buscadores gerais.
- **Pedido acadêmico** → `crossref`, `openalex`, `arxiv`, depois PubMed/
  Wikipédia/Bing conforme o assunto.
- **Pedido técnico com intenção de código/repositório** → Stack Exchange, HN,
  GitHub e Bing.
- **Busca geral/notícias** → Brave (se configurado), Bing, DDG, Marginalia e
  Wikipédia.

## Configuração

```ini
# Liga/desliga toda a camada nova (padrão: 1). Provedores antigos continuam.
JULIA_FREE_APIS=1

# Opcional: eleva o limite da busca de repositórios do GitHub.
GITHUB_TOKEN=

# Opcional: busca web independente. Sem a chave, o Brave não é anunciado
# em disponiveis() nem consultado.
BRAVE_SEARCH_API_KEY=

# Opcional: ofertas oficiais do Mercado Livre. Sem token, a API pública pode
# responder 403 e a busca de lojas segue pelo fallback existente.
MERCADO_LIVRE_ACCESS_TOKEN=
```

Contato acadêmico opcional (já existente):

```ini
JULIA_RESEARCH_MAILTO=seu-email@exemplo.org
```

## Relação com o Mercado Livre

A API pública do Mercado Livre passou a responder `403` sem autenticação em
parte dos ambientes. O adaptador agora envia `Authorization: Bearer` **somente
no cabeçalho** quando `MERCADO_LIVRE_ACCESS_TOKEN` existe. O token nunca entra
na URL, no resultado ou em mensagem de erro. Sem token, o comportamento é o
mesmo de antes: falha registrada e fallback de lojas.

## O que foi deliberadamente não integrado

- **Google Custom Search JSON API**: fechada para novos clientes e com
  desativação anunciada para **1º de janeiro de 2027**. Não é uma base
  confiável para uma integração nova.
- **REST Countries v3.1**: descontinuada. Se for necessária, usar a v5, não a
  v3.1.
- **Endpoints internos/não documentados de lojas (ex.: VTEX)**: evitados para
  não aumentar fragilidade, risco de bloqueio e dependência de formato privado.
- **Scraping de resultado de loja como se fosse API**: a descoberta de produto
  continua separada da verificação de preço/estrutura.

## Confiabilidade e segurança

- Cliente JSON/Atom próprio: URL validada por `research.url_segura`, redirects
  revalidados um a um, teto de bytes, timeout e content-type verificado.
- Tokens/chaves só em cabeçalhos; mensagens de erro não incluem segredo.
- Circuit breaker existente continua valendo para cada provedor novo.
- `search_providers.capacidades()` declara os campos, a autenticação, o limite
  e o status de cada adaptador; `e2e_verified_fields` permanece vazio até
  verificação real.
- Testes novos usam HTTP mockado e não dependem de rede:
  `python -m pytest tests/test_free_sources.py -q`.

## Licenças e termos

Cada fonte mantém seus próprios termos. Antes de uso comercial em escala,
revise: OpenAlex (dados abertos), Crossref, arXiv, GitHub API, BrasilAPI,
CoinGecko (atribuição) e Brave Search API. O Vexx não relicencia conteúdo de
terceiros e não trata metadados como texto integral lido.
