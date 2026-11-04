# Cache público e cards de pesquisa profunda

04/11/2026. Continuação do controle de acesso publicado no main em `5ecf05d`.
Este incremento reduz downloads de documentos públicos e conserva fontes no
resultado profundo. Não ativa serviços pagos, não troca o modelo do usuário,
não resolve CAPTCHA e não reinicia o PC Agent de produção.

## Implementação

- `public_document_cache.py`: corpos públicos em memória, isolados pelo dono,
  separados de trechos/evidências. Até 8 documentos por dono, 32 no processo e
  512 KiB por documento, sem persistência de corpos no disco. Conteúdo maior
  continua sendo lido normalmente, apenas não entra nesse cache.
- Respeita no-store/private, cookies, Vary e validade declarada. Sem autorização
  para armazenar ou validar, mantém o caminho de rede. Não guarda consultas com
  parâmetros privados; exceção estrita para leitura por slug da API pública
  conhecida do Ubatã. Âncoras de um mesmo documento compartilham o corpo; cada
  pergunta conserva seu link e refaz a seleção/validação das passagens.
- Revalidação por ETag/Last-Modified e HTTP 304. Coleta e última confirmação
  ficam separadas. Preços exigem nova confirmação; consultas temporais têm teto
  de 30 segundos e outras de 300, sempre limitados pelo servidor. Não usa corpo
  vencido se a rede falhar. SSRF e cancelamento também são verificados nos hits.
- Rejeita 304 sem cópia/validador correspondente e cabeçalhos inseguros. Uma
  resposta atrasada não sobrescreve outra atualização concorrente; conflito
  exige revalidação. Não aplica esse cache a transportes personalizados ou
  opções de requisição desconhecidas.
- Integrado à leitura comum/profunda e à REST do publicador. Os caches existentes
  de evidências continuam separados por conta/job. `JULIA_PUBLIC_DOCUMENT_CACHE=0`
  desliga o novo cache; o padrão é ligado. O estado é local a cada processo.

## Cards

O chat descartava grupos inteiros de fontes ao ultrapassar 10 mil caracteres.
`research_view.chat_blocks` reduz a quantidade de cards e detalhes opcionais,
mantendo texto factual, URLs exatas e estados de leitura. Se houver fontes lidas,
as prévias não lidas ficam na investigação, sem ocupar os cards finais. O último
recurso continua sendo texto válido, sem JSON cortado ou resposta vazia por
causa de um card grande. A visão completa do workspace não é modificada.

## Provas reais

`qa-artifacts/public-cache-live.json` preserva dois cenários:

- Referência de tipos Python, 814.438 caracteres: três leituras de rede; o corpo
  excedeu o limite de 512 KiB e não foi armazenado. Não contado como cache hit.
- Tutorial de estruturas Python, 110.941 caracteres: três contatos HTTP, um corpo
  baixado e duas revalidações 304. Âncoras diferentes conservaram URLs próprias,
  data original da coleta e novas confirmações. É redução de bytes nesse caso,
  não prova de menos requisições ou de eliminação de bloqueios em outros sites.

Interface local completa, conta e SQLite privados, rede/provedores reais:
pesquisa profunda semanal de Ubatã/região. Após a correção, seis cards de fontes
lidas, mesmos texto/mensagens/cards após reload, sem erros capturados depois
do login e sem overflow horizontal em 390 px. Captura inspecionada. Clique real
abriu a notícia exata dos feriados de Ubatã, sem ir para a home. As demais ações
dos cards não foram acionadas nesta rodada. Não é validação de celular físico.

Registros: `cache-cards-deep-ui-final.json`, `cache-cards-source-click.log` e
captura `output/playwright/cache-cards-deep-390.png`. A primeira tentativa com
sete cards também foi preservada; continha uma prévia não lida, posteriormente
removida da lista final, sem apagar o histórico de descoberta.

## Geração e limites

A síntese profunda continua sem aprovação: DeepSeek bloqueou por cota, preservando
o fallback extrativo e as evidências. Testes pequenos adicionais com credenciais
já configuradas encontraram modelos Gemini antigos indisponíveis e falha do
serviço no modelo atual; Mistral retornou rate_limit. Catálogo disponível não
foi tratado como prova de geração operacional. Não houve troca automática entre
provedores nem alteração de configuração do usuário. Detalhes sem credenciais:
`qa-artifacts/research-provider-operational-probe.json`.

O canal principal de pesquisa ainda precisa ser repetido com modelo operacional
para aprovar síntese correta/citada. Cache não remove políticas de acesso dos
sites, não cobre PDF nesta etapa e não é compartilhado entre processos.

## Verificação e arquivos

Regressões focadas passaram: isolamento, no-store/cookies/Vary, Age, tamanho,
ETag/Last-Modified, 304 incompatível, concorrência, frescor de preço, SSRF,
cancelamento, âncoras, nova seleção por entidade, limite do envelope e preservação
da resposta. Regressão focada final: 150 aprovados, um aviso, com conjuntos
sobrepostos aos testes anteriores. Suíte completa da árvore isolada, incluindo
somente os hunks desta entrega: **2.720 aprovados, 4 pulados, 2 avisos; exit 0
em 411,97 s**. Log: `qa-artifacts/public-cache-release-full.log`. Avisos existentes
de mss e timeout no TestClient. Código/testes conferidos com a árvore validada;
somente documentos receberam resultados depois. Diff-check passou. As 11
alterações preexistentes foram preservadas, descontados os hunks desta entrega.
Laboratório encerrado com identidade/operações verificadas, navegador fechado
e dados privados de QA preservados. Nenhum reinício do agente de produção.

Novos: `public_document_cache.py`, `tests/test_public_document_cache.py` e este
relatório. Integração: `research.py`, `research_agents.py`, `research_view.py`,
`public_store_reader.py`, `publisher_reader.py`; somente a chamada de empacotamento
em `pc_agent.py` e uma linha de isolamento em `tests/conftest.py`. Preservar os
outros hunks pendentes desses dois arquivos. Sem dependências novas.

Contratos consultados: [HTTP caching, RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html)
e [HTTP 304, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-304-not-modified).
Entrega autorizada para main; confirmação do envio e implantação são verificações
separadas. Não declarar deploy ou atualização do agente sem verificá-los.
