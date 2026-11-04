# Controle de acesso e leitura do publicador

04/11/2026. Implementados os dois primeiros incrementos do plano: coordenação
de leituras públicas e REST pública do Ubatã Notícias. Alterações desta rodada
locais, sem novo push. O PC Agent de produção não foi reiniciado. Não houve
ativação de serviço pago, resolução de CAPTCHA ou alteração de dados reais.
O laboratório usa conta/SQLite privados e agente de desenvolvimento.

## Correções

- O transporte mantém códigos legados e acrescenta motivo específico:
  autenticação, acesso negado, limite de tráfego, indisponibilidade, desafio
  observado, timeout e rede. Um 403 sozinho não comprova CAPTCHA.
- `read_access.py` junta apenas downloads anônimos simultâneos equivalentes,
  sem guardar o corpo após o término nem alterar o cache isolado de evidências.
  Limites: dois downloads por origem, até 16 no processo, 256 estados de espera.
- 429/503 adiam a origem, com Retry-After em segundos/data. 401/403/desafio
  adiam só a URL por 15 segundos, preservando páginas públicas vizinhas.
  Prazo defensivo máximo de Retry-After: um ano. Não há espera longa síncrona
  para retentar uma origem adiada.
- Redirects entram no coordenador do destino, com revalidação SSRF e tempo
  restante. Filas podem expirar ou ser canceladas sem cancelar outro consumidor.
  Uma chamada de rede iniciada ainda depende dos timeouts do socket; não há
  interrupção instantânea de uma leitura bloqueante.
- A revisão final corrigiu uma corrida adicional: cancelamento do consumidor
  que iniciou o download não descarta o resultado já recuperado para outro
  consumidor que continua esperando. Regressão com threads reais aprovada.
- A limpeza de rodapé foi limitada ao próprio parágrafo: não remove texto
  legítimo anterior que comece com “O post”. Regressão específica aprovada.
- A interface revelou “e mostre as fontes” absorvido pelo nome da cidade:
  a consulta exigia literalmente “Ubatã e região e mostre as fontes”. Corrigida
  a separação de instruções terminais de fontes/links, preservando região,
  datas e temas substantivos.
- A rede real revelou crédito “Ubatã Notícias” fazendo notícia nacional parecer
  local. Crédito de autoria/foto deixou de comprovar o local do acontecimento.
  Os resultados anteriores e as regressões negativas foram preservados.

## REST do publicador

`publisher_reader.py` usa exclusivamente a API pública conhecida do Ubatã.
Descoberta consulta até 20 posts e mantém os filtros de período/local/tema;
candidato não recebe marca de leitura. Recuperação resolve o slug e exige
permalink exato, ID positivo, status publicado, conteúdo público não protegido,
título e data GMT válidos. Não usa excerpt como corpo, não troca artigo por
home e não encaminha sessão, credenciais ou parâmetros privados.

O extrator comum recebe o conteúdo e conserva texto, data, URL original e
procedência da API. Integrado à pesquisa comum e ao analista da profunda.
HTML continua como alternativa no tempo restante; SSRF/cancelamento propagam.
A descoberta usa o orçamento existente e reserva tentativa genérica quando os
canais do publicador falham. `JULIA_PUBLISHER_REST=0` desliga a integração,
ligada por padrão. Testes de outras integrações usam opt-in explícito.

## Rede real e interface

`qa-artifacts/publisher-origin-live-before.json` conserva os falsos positivos.
A repetição corrigida em `publisher-origin-live.json` encontrou um candidato
regional hoje, três na semana e dois para educação em Ubatã. Em cada pergunta,
o primeiro candidato foi lido pela pesquisa comum e persistido pelo analista
profundo, sem simular publicador ou geração. Esses testes não certificam todos
os candidatos nem cobertura completa dos temas.

A API Mercado Livre sem token retornou 403 com `access_denied`. A repetição foi
adiada localmente: um FETCH_STARTED e um ACCESS_DEFERRED, uma chamada externa.
Registro: `origin-negative-cache-live.json`. Não comprova a causa do 403 nem
funcionamento autenticado.

Na interface local completa, “Pesquise as notícias de hoje de Ubatã e região e
mostre as fontes” passou de zero fontes para uma notícia lida, um card e link
abrindo o artigo exato por clique real. Texto, mensagens e card iguais após
reload. Zero erros capturados após login e nenhum overflow horizontal em 390 px;
captura inspecionada. Houve 401 esperado na consulta de sessão antes do login.
A resposta foi extrativa, sem redação de LLM. Não é teste em celular físico,
auditoria de todas as telas ou prova de implantação no Render.

Na profunda pela interface: seis fontes lidas, nove evidências registradas e
quatro links na resposta final. Texto/mensagens iguais após reload, sem erro
capturado ou overflow em 390 px. Estado **blocked/interrompida**,
`provider_code=quota` no DeepSeek: redação/revisão assistida não concluída.
O fallback preservou evidências e limitações. Não exibiu cards `.jdui-srccard`;
não foi considerado aprovação de síntese nem de JDUI premium na profunda.

Registros em `qa-artifacts/`: `origin-news-ui-before.log`,
`origin-news-ui-final.json`, `origin-source-click.log`, `origin-deep-ui.json`,
`origin-deep-outcome.json`. Capturas em `output/playwright/origin-news-390.png`
e `output/playwright/origin-deep-390.png`. Laboratório encerrado com verificação
dos PIDs, diretório, banco privado, papel de desenvolvimento e operações zeradas;
dados de QA preservados e navegador fechado.

## Arquivos e testes

Novos: `read_access.py`, `publisher_reader.py`, `tests/test_read_access.py`,
`tests/test_publisher_reader.py` e este relatório. Integração em `research.py`,
`research_agents.py`, `retrieval_trace.py`, `public_store_reader.py`,
`search_orchestrator.py`, `search_verticals.py`, `query_intelligence.py` e uma
linha de isolamento em `tests/conftest.py`. Outras alterações preexistentes de
autenticação, servidor, watchdog e UI foram preservadas; não incluir num push
automaticamente. Em especial, o restante do diff de conftest preexistia.

Transporte/segurança: 81 aprovados. Integração de leitor, cancelamento e
persistência: 114 aprovados, um aviso. Após achados reais, consultas/feeds/fontes:
106 aprovados. Após a última corrida corrigida, 58 aprovados nos testes de
coordenação, publicador e leitura paralela. Conjuntos sobrepostos; não somar.
O workspace completo passou com 2.720 aprovados, 4 pulados e 2 avisos em 547,13 s
antes desse último ajuste (`origin-access-full-suite.log`). A suíte final isolada,
sem WIP de outras frentes, é registrada no fechamento abaixo.
Uma exportação isolada intermediária foi interrompida após acrescentar a última
regressão de preservação de parágrafos; não é contada como aprovação. A validação
final usa nova árvore com ambos os ajustes e o teste adicional.

Fechamento: **2.697 aprovados, 4 pulados, 2 avisos; exit 0 em 452,02 s** na
árvore isolada final, incluindo os dois ajustes de revisão. Log:
`qa-artifacts/origin-access-final-isolated-suite.log`. Os avisos são as
depreciações existentes de mss e timeout no TestClient. Os arquivos de código
e testes conferem com a exportação validada; somente a documentação recebeu
o resultado depois. Diff-check passou. As 11 alterações de outras frentes
continuam preservadas byte a byte, descontada a linha nova de conftest.
O índice principal permanece vazio; não houve commit/push nesta rodada.

## Pendências

Cache público com revalidação e frescor permanece para o próximo incremento.
Revisar a autenticação do leitor externo: Firecrawl anônimo não foi ativado.
Repetir síntese com provedor/cota operacional e corrigir cards do fallback
profundo antes de aprovar a experiência completa. Coordenação é por processo,
não distribuída. Não há promessa de acesso a qualquer site.

Contratos: [WordPress Posts REST](https://developer.wordpress.org/rest-api/reference/posts/)
e [RFC 9110, Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).
