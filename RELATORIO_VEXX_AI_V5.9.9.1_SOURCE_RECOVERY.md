# VEXX AI V5.9.9.1 — Deep Search Recovery

24/10/2026. HEAD inicial **71e978e**, código final validado **7011908**, branch `codex/v598-autonomous-research`. Commits locais: 359e354,378ae2a, c9e6fbb, 13cb9f5,29e3b5c, 7011908. Commits posteriores de documentação/QA são conferíveis no Git local. Sem push, deploy, restart ou encerramento de produção; sem alterações em Studio, VERY, extensão, identidade Lucas, motor3D ou permissões remotas.

## Resultado

Há ganhos pontuais comprovados de leitura, precisão e entrega. **A cobertura universal continua insuficiente e não está aprovada para publicação como concluída.** Os vinte casos passaram de11para12 leituras elegíveis devolvidas, mas o holdout final teve0em12. Não se declara equivalência a Perplexity, precisão factual global ou ganho causal apenas por essa variação agregada.

## Bugs e correções

| Causa reproduzida | Correção |
|---|---|
| Original após seis resultados genéricos não recebia leitura | Seleção antes do corte, originais/diversidade e mesmo orçamento |
| Perdas de leitura eram confundidas com irrelevância | Diagnóstico por candidato com seleção, destino, extração e motivos distintos |
| Veículo diluía correspondência da manchete; homepage/duplicatas gastavam candidatos | Normalização de título e validação dos links de artigo |
| Redirect mudava base de canonical relativo | Extração usa URL efetivamente acessada |
| Atualização não era preservada separadamente no registro | publicado_em/atualizado_em separados, sem trocar evento por publicação |
| Notícias interceptavam pesquisa profunda | Rota explícita de job preservada; a fundo mantém modo profundo |
| Job terminava sem resposta no chat | Resultado JDUI persistido uma vez e sincronizado por histórico/status |
| Pedido de PDF virava galeria de manuais alheios | Tipo documento e pertinência temática obrigatórios |
| Frente limitações perdia a identidade asyncio.TaskGroup | Restrição do pedido original em cada frente; documento inglês pertinente aceito |
| Modal mostrava controles antes da foto sem feedback; botões quebravam palavras | Loading/erro reais, imagem carregada verificada e ações compactas |

Caso rastreável de leitura: artigo STF passou de não lido a2782 caracteres extraídos, mantendo rejeição por publicação insuficiente e sem certificar território. Caso técnico: trecho sobre direitos autorais foi substituído por código TaskGroup de docs.python.org; resultado parcial entregue e preservado no chat. Não executar código do modelo, inventar datas ou promover snippets a leitura.

## Medição externa

| Medida | Baseline fresco | Final |
|---|---:|---:|
| Casos de avaliação | 20 | 20 |
| Pool preservado, soma por caso | 193 | 194 |
| Abertas entre fontes devolvidas | 54 | 54 |
| Elegíveis lidas entre devolvidas | 11 | 12 |
| Chamadas de provedor / fetches | 114 / 214 | 111 / 212 |
| Mediana | 5,771 s | 6,064 s |

A seleção isolada manteve11 elegíveis. Rede/índice variam; não atribuímos causalmente o incremento final em empresa/Embraer ao patch. Dois candidatos com método explícito de recuperação no publicador foram lidos, nenhum elegível; essa contagem não abrange todos os artigos encontrados diretamente. Não há denominador de recall absoluto nem julgamento factual independente geral.

**Holdout final:**12 casos, 0 elegíveis, 33 aberturas devolvidas, 60 chamadas de provedor, 121 fetches, mediana5,847 s. Uma rodada anterior teve1elegível; ela não substitui o resultado final menos favorável. O conjunto não foi alterado para melhorar métricas.

## Validação

Baseline: 1507 passed, 4 skipped, 2 warnings. Final: **1536 passed, 4 skipped, 2 warnings em184,40 s**, `qa-artifacts/v5991/full-suite-final.log`, código7011908. Congelados: **Search34/34, Shopping59/59, Experience16/16**. Nenhum teste/gabarito existente removido ou enfraquecido.29 casos de regressão adicionados; focados e logs intermediários preservados.

Chrome autenticado executou doze cenários em iterações, com repetição dos afetados e casos adicionais de cancelamento/reload. Não equivale a doze respostas factualmente aprovadas. Jobs terminaram com outcomes parciais; entrega idempotente e isolamento foram testados. Último SQLite: 5 mensagens/5 IDs, 2 requests completed, 1resultado e0 operações QA ativas antes da parada. IndexedDB, downloads MD/CSV e galeria real foram verificados.

Visual: 1280/390/320, zoom CSS200%,5 imagens carregadas, modal com foto, setas/Escape/foco, metadados/reload e movimento reduzido. Screenshots inspecionados. Falha de imagem explicitamente injetada e recuperação passaram. Sem teste de aparelho físico, instalação PWA/FPS/contraste especializado ou captura integral dos bytes SSE do app.

REAL_MODEL separado: free poolside/laguna-s-2.1,130 chunks ordenados, HTTP200/SSE e fonte lida, mas literalidade/citação falhou. **PARTIAL; Deep Research não aprovado.** Sem raciocínio privado exportado. Snapshot relay+backend QA152,14 MB RSS; não é pico, delta ou medição de Chrome/produção.

## Segurança e operação

Auth, CSRF, RBAC, reauth, revogação, owner isolation, tool grants, SSRF/redirect, limites e sanitização continuam cobertos pela suíte. Sem promoção de contas, novos privilégios, endpoints administrativos ou infraestrutura paga. Arquivos privados de QA, chaves, cookies, bancos e backups não são versionados. Scan final está em secret-scan.json; é dirigido a valores secretos configurados e não auditoria de todo o histórico.

Dois processos de produção observados, com TCP ao mesmo remoto443. Status IPC autenticado do wrapper: RUNNING/0 operações naquele instante. Legado, consumo de jobs e commit importado não comprovados. Nenhuma operação de encerramento em produção. Todos os servidores/agentes/browser QA foram encerrados e bancos temporários removidos.

## Arquivos e documentação

Código: research.py, search_providers.py, search_orchestrator.py, research_agents.py, pc_agent.py, media_evidence.py, public/app.js, public/jdui.js, public/interface.css,.gitignore. Testes: test_source_recovery_v5991.py. Ferramentas: análise offline, probe reutilizado e drivers Chrome. Dataset de holdout independente, sem trocar gabaritos. Detalhes nos sete documentos em `docs/v5.9.9.1/`; artefatos em `qa-artifacts/v5991/`.

## Pendências

A maior limitação continua na descoberta de entidades/assuntos amplos e recuperação de publicadores dentro do orçamento. Cortes anteriores ao pool, geografia semântica/homônimos, restrições negativas gerais, originais sem publicação explícita, PDFs difíceis e comparação factual independente permanecem incompletos. Mensagens grandes podem omitir componentes do chat mantendo o job; precisam de cobertura adicional. Painel completo, instalação PWA offline e hardware físico exigem validação própria. Fases foram endereçadas com escopos parciais; não há certificação universal.

Próximo passo exato: investigar consultas genéricas que viram dicionários, resolver identidade central sem perder filtros e reservar melhor recuperação de original; medir contra outro holdout independente, sem afrouxar segurança ou validação para obter respostas. Consolidar PC Agents apenas em etapa operacional autorizada.
