# Integração de dados atuais — 17/10/2026

Base: `bac3cc1`, working tree inicialmente limpa. Implementação local, sem push/deploy, alteração de credenciais/modelos/identidade, extensão Júlia ou Fajulto. Ambiente de QA descartável, sem bases reais.

## Resultado

- Clima e previsão reais via Open-Meteo, sem chave. Temperatura, sensação, umidade, vento, validade da leitura, fonte e previsão de até sete dias.
- Data/hora continuam usando relógio e fuso do aparelho. Horário em outra cidade usa geocodificação e conversão IANA, sem LLM.
- Notícias recentes via Bing News RSS e fallback para G1/BBC/Agência Brasil. Links e datas reais; não afirma leitura integral dos artigos. Filtra manchetes antigas, sem data, futuras e publicidade identificada por URL.
- Pedidos tratados diretamente antes do modelo, tanto em SSE quanto no endpoint completo. Mantém persistência, IDs, replay e isolamento por proprietário/conversa.
- Sem cidade/coordenadas autorizadas, pergunta a cidade. A resposta curta continua o pedido anterior, incluindo previsão de amanhã. Cidade explícita tem prioridade sobre configurações; homônimos podem pedir esclarecimento.
- Cache limitado e timeouts; ausência de dados gera erro honesto. Não usa IP nem pede GPS automaticamente.

## Causas corrigidas

O app já enviava contexto temporal/local, mas não havia uma ferramenta meteorológica determinística no fluxo de resposta. O modelo recebia a pergunta sem uma leitura meteorológica e respondia com sua limitação. Agora a consulta externa precede a geração e não depende de o modelo decidir pesquisar.

Durante a validação real, o RSS do G1 devolveu gzip mesmo quando solicitado conteúdo sem compressão. O leitor anterior decodificava bytes comprimidos como texto. O cliente HTTP agora descompacta gzip, limitando tamanho antes e depois e rejeitando conteúdo inválido. Preservadas as proteções SSRF/redirects/tipos.

Também foram tratados: formato RSS `-0000` (UTC), nomes de cidades versus aeroportos, prioridade da cidade explícita, notícias com acentos no pedido, preservação da intenção de previsão ao perguntar cidade e cancelamento SSE durante a consulta.

## Testes e evidências

- Baseline focado antes das alterações: **60 passed** (`test_memoria41`, `test_intent`, `test_search_core_v55`).
- Integração focada: **76 passed** (`test_live_data`, memória, research, search core, UI/streaming).
- Suíte completa: **626 passed, 4 skipped**, 2 warnings, 185,36 segundos.
- Após os últimos ajustes de continuidade/validação: **59 passed**, incluindo o novo caso de consulta proibida/histórica e roteamento de data atual.
- Skips: dois casos de inferência LLM sem provedor e dois de shopping/rede/HTTP 403. Warnings existentes: mss e timeout TestClient. Nenhum teste removido.
- `git diff --check` sem erros.

Chrome real, sem mock das APIs, contra relay e PC Agent reais em SQLite temporário: login → “qual o clima agora?” → cidade → leitura meteorológica → previsão → horário em Tóquio → data local → notícias → reload. Seis respostas persistidas sem duplicação. Tabela Markdown de previsão, links externos, zero erros JS de página e captura mobile sem overflow horizontal. Captura mobile aberta e inspecionada.

Tempos observados nessa execução, sem promessa de SLA:

| Pedido | Tempo total no navegador |
|---|---:|
| Clima sem cidade, primeira interação | 2,62 s |
| Cidade informada / leitura real | 3,76 s |
| Previsão seguinte, com cache | 0,16 s |
| Horário em Tóquio | 1,31 s |
| Data local | 0,15 s |
| Notícias de hoje | 1,60 s |

Evidências: `qa-artifacts/live-data/results.json`, `weather-mobile.png`, `news-desktop.png`. Script reproduzível: `tools/qa-live-data.cjs`, contra `tests/preview_workspace.py`. O QA exige internet e pode falhar honestamente quando as fontes externas estiverem indisponíveis.

## Arquivos

`live_data.py`, `pc_agent.py`, `research.py`, `public/app.js`, `public/sw.js`, `tests/test_live_data.py`, `tools/qa-live-data.cjs`, documentação `docs/DADOS_ATUAIS.md` e evidências. Nenhuma dependência nova.

## Limites

- Open-Meteo gratuito é para uso **não comercial**; exige atribuição e tem limites de chamadas. Antes de uso comercial, revisar os termos: https://open-meteo.com/en/pricing. Não foi contratada API paga.
- Condições meteorológicas são estimativas de modelos, com horário de validade; não equivalem a um sensor instantâneo na rua do usuário. Sem histórico meteorológico nesta implementação.
- Notícias são manchetes dos feeds disponíveis, sem garantia de cobertura completa. “Hoje” pode ter poucos resultados na madrugada. Não houve bypass de bloqueios.
- Cache: clima 5 min, notícias 3 min, geocodificação 1 h; até 128 entradas na memória. Não há atualizações em segundo plano nem persistência nova de localização.
- Depende do PC Agent online e da internet. Uma consulta HTTP em andamento termina no timeout; o cancelamento evita publicar sua resposta depois.
- Testado em Chrome desktop com viewport mobile; Android/iOS físicos e ambiente de produção não foram testados/deployados nesta sessão.

Uso e contratos: `docs/DADOS_ATUAIS.md`.
