# Confiabilidade da pesquisa — 29/10/2026

## Escopo e causas verificadas

As imagens mostram falhas em consultas comerciais de GPUs. A investigação separou descoberta de links, leitura da página, correspondência do produto e disponibilidade do provedor. HTTP 403 não prova, por si só, a presença de reCAPTCHA.

- **Cache negativo longo:** consultas antigas vazias ou sem preço útil podiam ser reutilizadas durante o TTL de seis horas. Agora o histórico dessas falhas permanece armazenado, mas não impede uma nova tentativa. Ofertas úteis preservam a data e a expiração originais; preço não confirmado não se torna confirmado.
- **Descoberta encerrada cedo:** obter links do catálogo de uma loja encerrava a descoberta, mesmo quando todas as páginas falhavam na leitura. A recuperação agora procura candidatos independentes e elimina URLs já conhecidas antes de decidir se o provedor trouxe resultados suficientes. Mantém duas ondas e o teto de páginas por onda, sem repetição infinita ou contorno de desafios.
- **Loja solicitada:** a recuperação respeita uma loja explicitamente pedida; mencionar uma marca como Amazon Echo não exige comprar naquela loja.
- **Produto incorreto:** a execução real da consulta ampla por GPUs de 6 GB trouxe um tablet Samsung de 6 GB RAM. O problema era a classificação incompleta das famílias comerciais, não a extração do preço. O filtro precisa distinguir categoria, acessórios e a variante VRAM.
- **Classificação de bloqueio:** exemplos técnicos legítimos e scripts inativos não devem virar bloqueios. Intersticiais reais continuam rejeitados, inclusive desafios JavaScript sem instrução legível. A implementação anterior já ignorava a mera palavra CAPTCHA e widgets comuns; esse comportamento foi preservado.

## Verificação real inicial

Execução do pipeline comercial com rede pública, sem modelo, fixtures ou dados pessoais, usando SQLite descartável:

| Pedido das imagens | Tempo inicial | Produtos retornados | Observação |
|---|---:|---:|---|
| RTX 3050 6 GB, preço e link direto | 6,58 s | 6 | Links de produtos da KaBuM lidos |
| GPUs 6 GB, preços e links | 5,88 s | 6 | Incluiu indevidamente um tablet; motivou correção de categoria |

A API oficial do Mercado Livre retornou HTTP 403 nas duas consultas. A descoberta pública e a leitura de páginas da KaBuM funcionaram. Isso confirma disponibilidade naquele momento e ambiente, sem garantir disponibilidade futura de todas as lojas.

Evidência inicial: `output/search-reliability/baseline.json`. O resultado inicial não é utilizado como aprovação da precisão da segunda consulta.

## Validação final

Concluída na etapa anterior: **2.234 testes aprovados, quatro pulados, dois avisos existentes, exit 0 em 201,60 s**, em cópia isolada do commit base `2802702` acrescida somente da correção. Log: `qa-artifacts/search-reliability-full-suite.log`.

A interface completa local retornou seis e quatro cards de GPUs para os dois pedidos, com dez links diretos de produtos. Uma oferta foi aberta pelo botão do card: o título RTX 3050 6 GB e o preço de R$ 1.499,99 corresponderam à página da loja. Reload preservou as quatro mensagens e dez cards. Não houve erro JavaScript durante o fluxo autenticado ou overflow em 320/390/1280 px. Conta, SQLite e processos de QA eram descartáveis. Evidência: `output/search-reliability/ui-result.json` e screenshots no mesmo diretório.

Os tempos do pipeline sem modelo na rodada final foram 5,047 s e 3,547 s; a resposta completa pela UI levou 26,382 s e 23,188 s. O cache da pesquisa geral e o intervalo temporal da aprofundada também foram corrigidos, preservando cache de mídia pertinente e estados de metadados/não analisada. As fixtures positivas de cache foram ajustadas para usar texto pertinente e chave comercial real, mantendo as verificações de isolamento. A execução inicial com duas falhas foi preservada em `qa-artifacts/search-reliability-full-suite-initial.log`.

As alterações desta etapa anterior permanecem locais. A continuação de descoberta e cobertura está documentada separadamente em `RELATORIO_PESQUISA_AVANCADA.md`.

## Arquivos da correção

`shopping.py`, `research.py`, `source_priority.py`; testes dedicados a cache, desafios de acesso, recuperação de leitura e categoria; `tools/probe_search_reliability.py` e `tools/live_search_reliability.cjs` para repetir verificações reais.

As alterações de documentos, servidor e interface produzidas em outro trabalho simultâneo foram preservadas e não fazem parte desta correção.

## Como ChatGPT e Gemini pesquisam

A documentação pública descreve rastreadores e controles dos proprietários de sites para o ChatGPT, e integração com Google Search e metadados de citações para o Gemini. Não documenta um mecanismo universal para atravessar reCAPTCHA. Essas arquiteturas reduzem a dependência de abrir cada página diretamente no momento da pergunta.

- [Rastreadores da OpenAI](https://developers.openai.com/api/docs/bots?app=1).
- [Grounding do Gemini com Google Search](https://ai.google.dev/gemini-api/docs/generate-content/google-search).
- [Requisitos técnicos da Busca Google](https://developers.google.com/search/docs/essentials/technical).

## Limites preservados

Não há promessa de acesso a qualquer site ou pesquisa sem falhas. Não foram adicionados solucionadores de CAPTCHA, evasão de controles, serviços pagos, chaves novas nem execução de código produzido pelo modelo. Uma fonte bloqueada continua bloqueada; o sistema busca evidências permitidas em outras fontes. Preço, variante e destino do link continuam sujeitos à validação. Cobertura comercial e acesso público variam entre lojas.
