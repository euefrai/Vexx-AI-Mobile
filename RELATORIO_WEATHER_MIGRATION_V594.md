# Weather migration V5.9.4 — Visual Crossing

## Implementação

- Alterados: `live_data.py`, `conversation_followups.py`, `.env.example`, `.gitignore`, `public/sw.js`; testes e harness Chrome específicos. Não foram alterados identidade, 3D, extensão, Fajulto, grants ou contas.
- Endpoint: `https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days`, unidades métricas, seções current/days, português e campos restritos. Sem novo endpoint público de redistribuição meteorológica.
- Mantidos os contratos internos de clima/previsão, cards JDUI validados, contexto por proprietário/conversa, SSE e persistência. Não há chamadas aos endpoints hospedados do Open-Meteo. Mensagens antigas dessa fonte continuam interpretáveis como histórico, sem chamar o serviço.
- Brasil: cadastro IBGE, correspondência exata normalizada, UF/país/código e centroides municipais oficiais com rótulo explícito (não fingem sede urbana ou endereço). Geocodificação internacional opcional Photon/OSM, por consulta explícita, cache 24 h e serialização de até uma chamada/s; sem autocomplete. Serviço público sem SLA, desligável por `VEXX_PHOTON_ENABLED=0`.
- Timestamp epoch, timezone IANA, coordenadas retornadas, unidades, intervalos, números finitos e datas são validados. Temperatura atual vem exclusivamente de currentConditions; médias diárias nunca a substituem. O campo source distingue observação agregada, estimativa de modelo e origem não confirmada. Campos opcionais ausentes aparecem como não informados, sem zero fictício.
- `VISUAL_CROSSING_API_KEY` é lida apenas do ambiente do PC. A chave autorizada foi salva no `.env` local ignorado, sem frontend, Render ou fallback hardcoded. Downloader mantém SSRF, timeout e limite de bytes; requisições com credenciais rejeitam redirecionamento para outro host/esquema. Traces de QA ocultam key/token.

## Quota e cache

SQLite privado `weather-usage.sqlite3` junto ao banco do PC (ou `VISUAL_CROSSING_USAGE_PATH`) guarda apenas cache normalizado, fingerprint não reversível da chave, consumo e leases. Não altera as tabelas dos chats.

Cache de 5 min por chave/coordenadas/período fixo, compartilhado entre processos; descarte de entradas antigas após 30 min. Lease persistente de uma requisição simultânea, com recuperação após 120 s em caso de crash. Consumo local em janela móvel de 24 h, teto máximo de 1000 registros configurável para menos, reserva conservadora de 32 antes da rede e ajuste pelo queryCost retornado. Consumo de chamadas falhadas permanece conservador. O contador não conhece chamadas feitas fora deste PC/chave nem substitui a quota do fornecedor.

401/403, 429, timeout, indisponibilidade, dados antigos/invalidos e limite local geram respostas distintas, sem valores inventados ou chave. Circuit breaker/backoff de 60 s (300 s para chave recusada), sem retry automático que multiplique consumo. A chave ausente produz aviso de configuração, sem fallback Open-Meteo.

## Licença / atribuição

As [condições do plano](https://www.visualcrossing.com/weather-data-pricing/) incluem uso comercial gratuito, 1000 registros/dia e concorrência 1. O acesso de previsão oferecido pelo plano é maior; o app conserva seu horizonte de 7 dias. Não foi ativada assinatura, cobrança automática ou plano medido.

Os [termos](https://www.visualcrossing.com/weather-service-terms/) exigem atribuição e avisos apropriados, e vedam redistribuição como serviço de dados. Cards e texto mostram “Dados meteorológicos: Visual Crossing” com link; incluem aviso legível sobre erros, atrasos, estimativas, incerteza, ausência de garantia e alertas oficiais/decisões críticas. A [regra de cache](https://www.visualcrossing.com/resources/documentation/can-i-cache-and-store-visual-crossing-weather-data/) limita a validade operacional; o TTL de 5 min fica abaixo das janelas indicadas para condições e previsão.

Payloads meteorológicos reais, trace detalhado e transcript estruturado ficam **locais, ignorados pelo Git**, evitando publicar um conjunto bruto de dados. Evidências públicas usam resumo derivado, contagens, testes e screenshots da interface.

Photon: [política do serviço demonstrativo](https://github.com/komoot/photon#demo-server), uso moderado sem garantia; [dados OSM/ODbL e atribuição](https://www.openstreetmap.org/copyright). Não foi instalado geocodificador, nem usado o endpoint público Nominatim. O IBGE permanece a fonte oficial brasileira.

## Testes / smoke

- Regressões originais de clima foram adaptadas ao payload da Timeline sem retirar assertions de cache, idade, unidades, ausência de dados, ambiguidade ou isolamento. Credenciais e SQLite de quota são isolados de produção em todos os testes.
- 107 testes focados passaram, incluindo 25 casos específicos do adaptador: ausência/chave inválida, quota, timeout, cooldown, cache entre processos, concorrência, troca de chave, dados vazios/antigos/futuros, coordenadas, fuso, unidades, campos opcionais, fonte, atribuição e redirecionamento com credencial.
- Primeiro integral: 1153 passed, 4 skipped, 2 warnings. Integral final posterior à proteção de redirecionamento: EM_EXECUCAO.
- Smoke **externo real** bem-sucedido com chave autorizada: Ubatã/BA, IBGE 2932309, coordenadas oficiais municipais e America/Bahia. Não foi necessário LLM. O retorno classificou o dado atual como estimativa por modelo, sem fingir observação.
- Chrome real, relay e PC reais em SQLite descartável: 6 turnos de chat, clima externo real e amanhã por cache; cumprimento zero geocodificações; relógio e novo chat isolado; telas 1280/390/320. Deep Research usa fonte fictícia identificada, com reload/SSE, 43 eventos, cards, zoom e exportação 200. Câmbio externo real também preservado. Nenhuma exceção JS na execução aprovada.
- Benchmarks preservados: pesquisa 34/34, compras 59/59, experiência 16/16. Sem afirmação de precisão universal, telefone físico ou inferência real de modelo.
- Consumo: uma requisição meteorológica por execução Chrome aprovada, com reutilização no follow-up; smoke separado limitado. QueryCost do smoke registrado no contador local. Uso externo da conta e plano atualmente contratado não são consultáveis apenas com este fluxo e não foram modificados.

## Publicação

HEAD inicial `daa403c`; Git remoto verificado sem divergência, main local à frente. Produção inicial `cccd8b5996de`, PC online. Chave configurada no arquivo de ambiente do PC correto; ambiente de teste isolado. Sessão do usuário autenticada no navegador para smoke final, sem ler/exportar senha ou cookies.

STATUS_PUBLICACAO: aguardando integral final; nenhuma alteração de produção feita antes dos gates. Sequência autorizada: commit/push fast-forward → CI → confirmar Render → verificar ociosidade do PC → reiniciar somente seu agente com mesmo banco → smoke autenticado. Resultado final e hashes serão atualizados aqui.

Limitações: serviço público Photon sem SLA; limite local não é quota global da conta; períodos históricos continuam indisponíveis, sem mascará-los como atuais; centroides representam o município, não endereço preciso. Nenhuma fonte paga foi ativada e nenhuma API bruta de clima foi adicionada.
