# Vexx AI V5.9.4 — Context Intelligence & Verified Retrieval

## Resultado e estado do Git

HEAD inicial: `24ba58b`. HEAD final do código validado: `f8c2508` (um commit posterior arquiva somente documentação e QA). Commits locais: `43b524c` (contexto/geografia/dados ao vivo), `786d1d1` (isolamento adicional, regressões e mobile), `f8c2508` (consulta por código IBGE e proteção da rota 3D).

Correções aplicadas diretamente, sem reescrever o sistema, sem push/deploy/reinício de produção. Identidade Lucas, extensão Júlia, Fajulto Studio, 3D, credenciais, grants, RBAC e permissões remotas preservados.

## O que foi corrigido

- Cumprimentos são resolvidos antes de preencher cidades. Perguntas explícitas sobre a cidade Oi continuam válidas.
- O resolvedor existente conserva intenção meteorológica, cidade, período, unidade e parâmetros pendentes dentro do chat. Funciona após pedidos de esclarecimento e erros; encerra o assunto em cumprimentos/novo tema. Histórico limitado a 32 mensagens e ao ponto anterior à requisição atual, isolado por proprietário/conversa.
- Cidade/UF/país separados antes da consulta; acentos, caixa, barra, UF por extenso/sigla e código municipal aceitos. Correspondência exata normalizada; filtro de país/UF/município; homônimos permanecem ambíguos. Nenhum dicionário de cidades favoritas e nenhuma preferência silenciosa por capital.
- Cadastro IBGE com cache de um dia para UF/código. Quando o geocodificador falha e há município confirmado, fallback limitado a metadados oficiais, explicitamente rotulado **centroide municipal**, sem fingir endereço preciso ou sede urbana. Se não houver confirmação, não se nega a existência do lugar.
- Clima valida coordenadas, timestamp, janela atual, unidades, limites numéricos e intervalos de previsão. Cache meteorológico de cinco minutos, datado; dados antigos não viram condições atuais. O texto identifica estimativa por modelo/previsão e cita a fonte. Não usa médias ou outra cidade.
- Relógio real do servidor convertido por ZoneInfo no fuso legítimo do aparelho/local explícito. Horário antigo fornecido pelo cliente não determina a hora atual. Sem fuso confirmado, pede esclarecimento. Fuso IANA explícito também é aceito.
- Respostas por ferramenta precedem inferência nos fluxos síncrono e SSE. HTTP 429 das APIs JSON ativa cooldown de 60 s, sem loops. Fallback de modelos existente continua limitado a cinco candidatos configurados, com backoff; não foi adicionado provedor/modelo pago.
- Documentos implícitos são filtrados por proprietário e conversa **antes do LIMIT**. Removido fallback para último documento global; exigido pedido pertinente, limites de palavras e respeito à negação. “todo dia” não seleciona TODO.md. APIs explícitas de leitura conservam sua autorização existente.
- Revisão final fechou dois conflitos reproduzidos: o filtro de programação bloqueava “código IBGE”, e pedidos 3D com “cidade de…” podiam ser capturados como localização. Consulta oficial por código foi confirmada também na API real, sem inferência; pedidos 3D continuam no motor existente.
- Cards meteorológico/geográfico/horário/erro reutilizam o schema `cards` validado existente, sem HTML/JS executável do modelo. Forecast card mostra intervalo do dia solicitado, sem apresentar temperatura atual como previsão. Data da primeira coluna da tabela não quebra no celular; overflow fica no contêiner da tabela.
- A classificação existente expõe `route` com GREETING, GENERAL_CHAT, CURRENT_TIME, WEATHER_CURRENT/FORECAST, LOCATION_LOOKUP, CURRENCY, SHOPPING, TRANSPORT, NEWS, EVENTS, GENERAL_SEARCH, DEEP_RESEARCH, DOCUMENT_QUERY e PROJECT_FILE_QUERY; preserva `intencao` e contratos dos benchmarks anteriores. Combina Intent Engine, Query Intelligence e adaptadores existentes, sem novo motor paralelo.

## Evidências e testes

Detalhamento causal: [INCIDENTS](docs/v5.9.4/INCIDENTS.md). Fluxo real: [E2E_RESULTS](docs/v5.9.4/E2E_RESULTS.md). Progresso: [PROGRESS](docs/v5.9.4/PROGRESS.md).

- Baseline anterior às correções: `qa-artifacts/v594/baseline.json`.
- Checkpoints: 42, 57, 92 testes; após ajustar regressões, 88 testes; conjuntos focados finais: **80 passed** e **122 passed** (incluindo 3D). Matriz V594 inclui **40 casos parametrizados**, sem rede externa nos testes unitários.
- Suíte completa final: **1129 passed, 4 skipped, 2 warnings em 255,76 s**. Checkpoint integral anterior à última revisão de roteamento: **1126 passed, 4 skipped, 2 warnings em 241,32 s**. Primeira execução: 3 failed, 1121 passed, 4 skipped; causas e correções registradas abaixo, sem eliminar assertions de isolamento/erro.
- Benchmarks congelados preservados: pesquisa **34/34**, compras **59/59**, experiência **16/16**.
- QualityLab local: P@5 **0,275**, P@10 **0,1375**, recall@10 **0,916667**, MRR **1**, nDCG@10 **0,982614**. Holdout congelado mantido. Não são medições de precisão universal ou da internet.
- Matriz rotulada de intenção **16/16**, resolução simulada de seis variações de Ubatã e três outros municípios; testes de homônimos/clarificação, 429, stale data/histórico, usuários, projetos e concorrência. Métricas e escopos em `qa-artifacts/v594/metrics.json`.
- Chrome real + relay/PC reais: clima real Ubatã/BA e amanhã, cumprimento com **zero geocodificações**, relógio, chat novo isolado; Deep Research fixture com reload/interrupção SSE, **43 eventos**, cards/imagem/zoom/exportação **200 / 1983 bytes**; câmbio Frankfurter real e gráfico de 23 pontos datados. Viewports **1280, 390, 320**; conteúdo e screenshots inspecionados, sem exceções JS na execução aprovada.
- Na amostra real final, temperatura **27.4 °C**, estimativa válida em **22/10/2026 16:45 America/Bahia**; não é um valor atemporal. Fonte/campos brutos públicos em `live-trace.jsonl`. Primeiro turno **5504 ms**, amanhã **450 ms**, cumprimento **416 ms**. Uma consulta meteorológica alimentou duas respostas por cache, sem repetição da API no follow-up. Contagens da instrumentação JSON excluem IBGE/Frankfurter/discovery de modelos.

### Falhas encontradas durante a validação

Dois testes antigos usavam “Olá/oi” como entrada genérica para chegar ao LLM/comando de memória; passaram a exercitar a resposta determinística de cumprimento. Apenas essas entradas foram trocadas por pedido de história para manter as assertions de replay entre proprietários e liberação após exceção. O teste de horário foi fortalecido: congela o **servidor**, mantém data antiga do cliente e verifica que ela não prevalece, junto com o card.

A primeira matriz nova detectou fixture internacional ambígua e ausência de `type=ui` no card; corrigidos antes da aprovação. Tentativas Chrome anteriores registram capitalização visual da badge e esperas faltantes do harness ao criar chat; não foram apresentadas como aprovadas. Todos os logs anteriores foram mantidos. A tabela mobile com dia quebrado foi corrigida e conferida novamente.

## Licenças, disponibilidade e segurança

- Open-Meteo gratuito: [termos oficiais](https://open-meteo.com/en/terms) restringem a API gratuita a **uso não comercial**, com limites publicados de 10.000/dia, 5.000/hora e 600/minuto. Dados exigem atribuição conforme licença. Esta execução local não comercial é compatível; **operação comercial do Vexx AI não está validada/autorizada por esta entrega**. Se houver assinatura, publicidade ou finalidade comercial, não usar o endpoint gratuito nessa modalidade sem contrato apropriado. Nenhum serviço pago foi habilitado.
- [Geocoding API / GeoNames](https://open-meteo.com/en/docs/geocoding-api): filtro de país e atribuição preservados. Clima e geocodificação continuam em hosts fixos, com limites de tamanho/timeout e SSRF/redirects verificados pelo downloader existente.
- [IBGE Localidades](https://servicodados.ibge.gov.br/api/docs/localidades): fonte oficial de municípios/identificadores. [Registro 2932309](https://servicodados.ibge.gov.br/api/v1/localidades/municipios/2932309). Fallback geométrico consulta somente IDs numéricos oficiais e rotula sua precisão municipal.
- Respostas ao usuário não expõem exceções brutas, chaves ou comandos internos. Rede pública pode falhar; não há garantia de continuidade ou leitura de artigos comerciais/bloqueados. Não foram contornados bloqueios.

## Arquivos alterados e limitações

Produção: `conversation_followups.py`, `intent.py`, `live_data.py`, `pc_agent.py`, `docs_agent.py`, `public/interface.css`. QA: `tests/test_context_v594.py`, `tests/test_isolamento.py`, `tests/test_memoria41.py`, `tests/test_ui_polish.py`, `tests/live_fixture_agent_v594.py`, `tools/chrome_e2e_v594.py`; relatórios e `qa-artifacts/v594/`.

- Não foi reproduzido o histórico original publicado do TODO.md nem provocado HTTP 429 externo de Mistral. Comprovamos um fallback indevido local e corrigimos; não afirmamos vazamento entre usuários. O 429 meteorológico e a ausência de chamada ao LLM foram testados com fixtures/sentinelas identificadas.
- Não houve inferência real de modelo neste E2E. Pesquisa profunda exercita infraestrutura real com fonte fictícia; fontes externas de produtos, ciência, notícias/eventos não foram novamente avaliadas. Os contratos e resultados congelados V5.9.3 foram preservados, sem novas promessas de estoque, tarifa ou evento.
- Não testa telefone físico, todos os municípios/fusos/idiomas nem precisão universal. Celsius e horizonte de até sete dias são o contrato meteorológico atual; histórico não é apresentado como agora.
- Não foi criado isolamento de memória global por projeto nem motor novo. Documentos implícitos e slots ficam por conversa/proprietário; mover o mesmo chat preserva seu próprio histórico. Memória global autorizada, segurança e controles existentes continuam com seus contratos.
- Versão publicada não inspecionada nem atualizada. Para disponibilizar estas mudanças será necessária uma implantação separada, autorizada posteriormente.
