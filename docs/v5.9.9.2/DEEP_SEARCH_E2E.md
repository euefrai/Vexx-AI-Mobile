# Pesquisa profunda no navegador real

QA autenticado em Chrome, relay FastAPI e PC Agent reais, SQLite temporário, usuário de teste Alice QA. `tools/serve_admin_qa_v5981.py --research-live --evidence-dir qa-artifacts/v5992` permite somente modelo configurado explicitamente gratuito, com fallbacks desativados. Nenhum cookie, senha ou banco de produção foi usado. Driver: `tools/qa_discovery_v5992.cjs`, executado via Playwright CLI `run-code --filename`.

## Resultado observado

| Caso | Evidência / entrega | Limite |
|---|---|---|
| Museu do Amanhã, pedido composto | Job profundo termina, mensagem final persiste após reload | Zero leituras pertinentes; resultado parcial, não pesquisa concluída semanticamente (`e2e-accepted-museum.log`) |
| História da WEG | Um trecho lido da Wikipédia, com fundação de 1961 e fundadores no card, duas mensagens do assistente e IDs/textos preservados | Fonte secundária; não satisfaz plenamente pedido por fonte primária (`e2e-delivery-company.log`) |
| asyncio.TaskGroup, exemplos e limitações | Uma leitura da documentação oficial, link e card no chat; reload durante investigação e persistência final | Execução final usou fallback extrativo. Outra rodada real produziu redação pelo modelo gratuito; ambas parciais (`e2e-delivery-technical.log`, `e2e-accepted-technical.log`) |
| Ponte Estaiada, imagens | Cinco mídias Commons reais, origem/crédito/direitos, galeria e persistência | Metadados não são análise visual ou evidência textual (`e2e-delivery-images.log`) |
| Cancelamento | Job cancelado, sem `chat_result_id`, uma confirmação e nenhuma resposta final posterior | Somente interrupção cooperativa em QA (`e2e-delivery-cancel.log`) |
| TaskGroup, pedido simplificado | Modelo gratuito produziu parágrafo público com citação E1 e fonte oficial | Resultado parcial; saída continha U+202E e código malformado apesar de aprovação automática. Não aprovada por revisão manual (`e2e-delivery-focused-technical.log`) |

As requisições de chat retornaram HTTP 200 e `text/event-stream`. Os jobs prosseguiram pelo fluxo existente, com entrega final separada da confirmação inicial, sem duplicações de IDs observadas. Cada driver compara IDs e texto persistido antes/depois do reload; texto transitório do painel não é confundido com mensagem persistida. Resultado mecânico `status=concluida` significa fim do job; `research_outcome=partial` continua explícito.

## Correção descoberta pelo QA

`1ce380a` rejeita controles Unicode de direção ocultos nas chaves/valores JSON **já decodificados** da síntese/revisão, inclusive escapes Unicode. Letras naturais de idiomas RTL continuam válidas. A resposta insegura cai no fallback com evidências preservadas; código do modelo nunca é executado. Dois testes cobrem o limite e a preservação. Isso é proteção de saída, não otimização usando o holdout aberto. O código malformado pelo modelo permanece uma limitação de qualidade; a verificação automática por parágrafo não constitui revisão factual humana.

O pós-correção usa uma instância QA nova (`e2e-safety-technical.log`): HTTP 200/SSE, uma fonte lida reportada no status, mas timeout de redação/revisão, job `interrompida`, outcome `blocked`, sem mensagem final. `e2e-safety-evidence.log` capturou o painel antes de seus dados carregarem; não confirmou renderização/persistência das evidências após esse timeout e não conta como passe. A proteção Unicode passou nos testes determinísticos, mas esta última execução não validou uma síntese pública real pós-correção. Não se repete a tentativa para escolher um resultado favorável.

## Instrumentação e falhas preservadas

Falhas iniciais do harness por passagem de código via argv e comparação antes de completar o reload estão preservadas, mas não contam como passes. O driver passou a usar arquivo e esperar o último ID persistido. O teste remoto que falhou durante a suíte foi corrigido no agente simulado para responder ao handshake de revogação real; as permissões do produto não foram alteradas.

Nenhuma investigação profunda universal completa teve aprovação manual de inferência nesta versão. Os testes determinísticos e o fluxo real são evidências distintas. Os logs não comprovam execução em produção, reconexão sob falha real de rede, desempenho de celular físico ou precisão universal.
