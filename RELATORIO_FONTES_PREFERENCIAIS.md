# Fontes preferenciais e recuperação de leitura

Base: `0f64e7c`. Envio para `main` autorizado pelo usuário. O deploy do Render e a versão executada pelo PC Agent devem ser confirmados separadamente; o agente local não é reiniciado por um push.

## Comportamento

O catálogo central `source_priority.py` reúne 28 áreas e 10 lojas. Uma fonte nomeada pelo usuário tem prioridade sobre a escolha automática. A primeira consulta recebe escopo de domínio; a busca geral continua quando a etapa preferencial retorna vazia, falha ou não oferece candidatos suficientes. Preferência altera descoberta e desempate, mantendo os filtros de assunto, entidade, data, variante e preço.

Compras priorizam KaBuM, Shopee, Mercado Livre, Americanas e outras lojas do catálogo. A API oficial do Mercado Livre conserva seu lugar na cadeia. Tipos de página e correspondência do produto continuam precedendo a preferência pela loja. Página de categoria não ganha o selo de produto confirmado.

Para notícias de Ubatã, o feed público `https://ubatanoticias.com.br/feed/` vem antes dos buscadores. Título e data no RSS apenas descobrem a matéria; o artigo precisa ser aberto para fornecer evidência. O feed recebe uma tentativa do orçamento compartilhado e preserva espaço para busca geral se falhar. Notícias do mundo priorizam G1, com BBC, Reuters, AP e Agência Brasil como referências adicionais.

“Ubatã e região” admite também Ubaitaba, Aurelino Leal, Gongogi, Ibirapitanga, Ipiaú e Ibirataia. “Ubatã” sozinho conserva o filtro da cidade. Datas usam America/Bahia; “esta/nesta/desta semana” começa na segunda-feira. “Da semana” mantém a janela móvel já adotada pelo projeto. O catálogo jornalístico local não é aplicado automaticamente a clima ou distância entre cidades.

## Correções relacionadas ao acesso

- Mensagens de erro em scripts, estilos, comentários e templates não bastam para declarar uma página bloqueada. Instruções e estruturas de desafio continuam sendo recusadas.
- HTTP 401, 403 e 429 recebem diagnósticos diferentes: autenticação, acesso negado e limitação de requisições. Um 403 isolado não prova CAPTCHA.
- Uma página de desafio com JSON-LD residual não gera uma oferta.
- Compras distribuem candidatos equivalentes entre domínios antes de limitar a leitura. Após recusa, a pesquisa profunda prefere uma fonte independente dentro do mesmo orçamento.
- Na revisão de publicação, um teste reproduziu a KaBuM bloqueada ocupando as duas tentativas, apesar de existir outra loja acessível. A diversidade e os bloqueios agora precedem a ordem de lojas dentro do mesmo tipo/identidade. Regressão corrigida e revalidada com 57 testes focados.
- Consultas longas mantêm o domínio completo e a expressão de lojas bem formada.
- `public_store_reader.py` oferece renderização externa experimental, anônima, para páginas públicas específicas das três primeiras lojas. Fica **desativada por padrão** (`JULIA_PUBLIC_STORE_RENDER=0`). Não encaminha cookies, sessão, chave ou ações do modelo; recusa URLs com query/fragmento, páginas de conta, redirecionamentos de loja, desafios e respostas excessivas. Respeita o tempo restante, duas operações simultâneas e pausa após quota/autenticação do provedor.

## Verificações executadas

- Publicação: suíte completa em cópia isolada com **2020 aprovados, 4 ignorados, 2 avisos existentes**, 350,47 s. Após a correção final da ordem de lojas, o conjunto de compras e novas integrações foi reexecutado no snapshot final isolado: **273 aprovados, 2 ignorados**, 72,57 s. O código de produção não mudou após essa verificação; somente relatório/evidência de publicação.
- A configuração dos testes desliga as novas integrações externas por padrão também no CI. Os casos de integração ativam seus respectivos adaptadores simulados explicitamente; nenhuma dependência de resposta real das lojas foi introduzida na suíte.

- Desenvolvimento: suíte completa com **2017 aprovados, 4 ignorados, 2 avisos existentes**, 251,62 s; posteriormente, **96 testes focados aprovados**, 15,49 s. Registro em `qa-artifacts/preferred-sources-final-focused.log`.
- Teste público real de notícias: **3 matérias abertas e relevantes**, datas preservadas, cache SQLite isolado reutilizado; aproximadamente **4,28 s**. Incluiu uma matéria de Ibirapitanga. Sem síntese por modelo ou sessão autenticada de produção nesse teste.
- KaBuM: um link de produto realmente descoberto na página inicial abriu e produziu uma oferta com preço declarado e link verificado. Evidência em `qa-artifacts/store-render-public-probe.json`.
- Mercado Livre: página inicial acessível no teste; isso não comprova acesso a anúncios ou à API.
- Shopee: leitura direta sem texto; o serviço externo também devolveu uma rota de verificação em uma tentativa. Essa resposta foi recusada. **Acesso universal ou CAPTCHA resolvido não foram demonstrados.**
- Repetição do teste de notícias: `python tools/probe_preferred_sources.py --live-news`, usando `JULIA_ENV_FILE` de teste. O script cria e remove somente um SQLite temporário; não usa o banco pessoal.
- Testes offline usam `JULIA_PREFERRED_NEWS_FEEDS=0` e `JULIA_PUBLIC_STORE_RENDER=0`, com casos específicos habilitando/mocando cada integração.

## Arquivos deste escopo

`source_priority.py`, `query_intelligence.py`, `search_orchestrator.py`, `search_providers.py`, `search_verticals.py`, `research.py`, `research_agents.py`, `shopping.py`, `public_store_reader.py`, `.env.example`, testes de prioridade/feed/renderização/recuperação, `tools/probe_preferred_sources.py` e os artefatos citados.

Alterações paralelas de interface/servidor no checkout foram preservadas; não foram feitas como parte desta implementação. Nenhum dado real foi apagado e nenhuma conta foi criada em provedores.

## Limitações

Preferência não é certificação de disponibilidade ou exatidão de um veículo. Não houve teste público de todas as 28 áreas, de todas as lojas ou do chat autenticado. O catálogo RSS é limitado e não prova cobertura exaustiva da semana. Resultados de busca e resumos de feed continuam sem equivaler a artigo lido. A prioridade não substitui a recuperação posterior do agente quando páginas descobertas falham na leitura.

Firecrawl documenta extração de páginas dinâmicas em https://docs.firecrawl.dev/features/scrape; o fallback experimental não promete acesso a qualquer site. Para algumas lojas, APIs autorizadas ou participação do usuário em uma sessão de navegador ainda podem ser necessárias.

## Exemplos do catálogo

A tabela abaixo demonstra roteamento configurado; não comprova disponibilidade de cada domínio no momento da consulta.

| Área | Primeira referência configurada |
|---|---|
| Ubatã Notícias | ubatanoticias.com.br |
| Notícias da Bahia | g1.globo.com |
| Notícias gerais e do mundo | g1.globo.com |
| Notícias do Brasil | g1.globo.com |
| Jogos e games | ign.com.br |
| Tecnologia | tecmundo.com.br |
| Inteligência artificial | arxiv.org |
| Ciência | scielo.br |
| Comportamento humano e psicologia | scielo.br |
| Saúde | fiocruz.br |
| Filosofia | plato.stanford.edu |
| Matemática | mathworld.wolfram.com |
| História | britannica.com |
| Finanças e economia | bcb.gov.br |
| Direito | planalto.gov.br |
| Educação | mec.gov.br |
| Esportes | ge.globo.com |
| Cinema, séries e música | g1.globo.com |
| Livros e literatura | openlibrary.org |
| Culinária | tudogostoso.com.br |
| Viagem e turismo | visitbrasil.com |
| Carros e veículos | quatrorodas.abril.com.br |
| Meio ambiente | gov.br |
| Casa e reforma | casa.com.br |
| Pets | petmd.com |
| Agricultura e agro | embrapa.br |
| Religião | britannica.com |
| Compras e ofertas | kabum.com.br, shopee.com.br |
