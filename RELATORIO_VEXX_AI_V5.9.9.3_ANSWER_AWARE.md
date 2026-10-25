# VEXX AI V5.9.9.3 — Answer-Aware

**Não aprovada para publicação.** A base de requisitos/passagens foi implementada e a estabilidade local passou, mas a meta de pesquisa universal com respostas completas não foi demonstrada. O classificador ainda perde informações úteis e o provedor frequentemente devolve páginas alheias. O resultado independente não justifica chamar esta versão de Research Ultra.

## Estado e commits

Base `869b04b`, branch `codex/v598-autonomous-research`, worktree `vexx-v598-dev`. Vinte casos congelados em `1f5ff18` antes das mudanças. Experimento de busca congelado em `af400f1`; ajuste visual `5127977`; HEAD final de código `86462e9`, proteção de identidade da interface motivada pelo QA. Commits posteriores de documentação/evidência não alteram o motor. **Sem push/deploy, reinício de produção ou alteração de dados reais, Studio, VERY, extensão, identidade Lucas, 3D ou grants.**

| Commit | Resultado local |
|---|---|
| `1f5ff18` | Congelamento de vinte perguntas/critérios, baseline antes dos algoritmos |
| `4561f84` | Requisitos explícitos, passagens literais, navegação limitada, cobertura/gaps, síntese e tabela JDUI |
| `68b9094` | Preserva escopo da pergunta, separa assunto de atributo, limita intervenção ao chat e prioriza nova pesquisa |
| `27a4319` | Fixture de intervenção declara o chat correto; asserções e teste negativo preservados |
| `438a065`, `af400f1` | Galeria descoberta continua no workspace; resposta textual só recebe mídia quando solicitada |
| `6149d83` | Garante texto extrativo/checkpoint quando dependências/orçamento pulam finais do plano |
| `5127977` | Tabela legível em zoom CSS200%, com scroll interno no tamanho estreito |
| `86462e9` | Não mistura uma operação qualificada com outra interface de mesmo nome |

## Auditoria e implementação

`answer-aware-before.json` reproduz a pergunta WEG inteira confundida com entidade e o falso positivo de WebAssembly capturado anteriormente. A investigação focou o caminho pergunta → fonte → leitura → passagem → requisito → síntese → chat.

| Causa localizada | Correção |
|---|---|
| Correspondência temática usada como suficiência | Requisitos de atributos explícitos no Query Intelligence; relação/entidade dentro do trecho lido, sem transformar snippet em leitura |
| Entidade e instruções/atributos misturados | Separação de padrões explícitos, IDs estáveis e pergunta original preservada; reformulação com restrições mantém o original |
| Trecho útil se perde no começo da página | Segmentação literal e janela de extração pertinente; números/tokens inteiros, offsets relativos à extração, seção/página somente reais |
| Links extraídos do HTML desaparecem antes do leitor | Links reais priorizados e seguidos dentro dos seis reads rápidos/orçamento profundo existentes; SSRF/redirects e DNS público preservados |
| Uma leitura encerra lacunas de várias informações | Gaps por requisito, estados/IDs/custos/etapas observáveis, sem repetir consulta genérica como se fosse ganho factual |
| Síntese bloqueada ou etapa final pulada deixa apenas início | Fallback extrativo persistido e entrega parcial terminal com ID estável; retomada atualiza sem duplicar; cancelamento não publica final |
| “Somente” numa nova pergunta altera pesquisa antiga | Nova pesquisa tem precedência; intervenções limitadas ao chat. Entrada alinhada aos 500 caracteres já aceitos pelo job |
| Cobertura editável e mídia sem intenção poluem a resposta | Tabela somente leitura, CSV/teclado reais, fonte ligada a aspectos; mídia descoberta continua separada do suporte factual |
| API JavaScript e instrução Wasm confundidas | Guard de identificador qualificado em título/seção/passagem, preservando aliases `prototype` sem aceitar mera coincidência de palavras |

Arquivos de produto: `query_intelligence.py`, `web_extract.py`, `evidence_graph.py`, `research.py`, `research_agents.py`, `research_gaps.py`, `research_synthesis.py`, `research_view.py`, `pc_agent.py`, `jdui.py`, `public/jdui.js`, `public/interface.css`. Infra de QA: `.gitignore`, dois datasets **novos**, dois drivers existentes estendidos e ferramentas offline de avaliação/replay. Testes: `tests/test_answer_aware_v5993.py` e um fixture de chat em `tests/test_research_agents.py`. Os datasets antigos congelados não foram alterados; não houve reescrita do projeto ou novo motor/agente/provedor pago.

## Comparação independente

Vinte casos, mesma pergunta/orçamento e relógio do baseline. Rede e índices vivos. Dados em `qa-artifacts/v5993/comparison.json`; [avaliação e limites](docs/v5.9.9.3/HOLDOUT_EVALUATION.md).

| Contador | V5.9.9.2 antes | Experimento `af400f1` |
|---|---:|---:|
| Leituras elegíveis / casos marcados pelo motor | 2 / 2 | 1 / 1 |
| Leituras devolvidas | 59 | 57 |
| Chamadas de provedor | 116 | 116 |
| Fetches observados | 218 | 209 |
| Mediana s | 5,827 | 5,656 |

Esses flags não medem precisão factual ou resposta completa. O motor ainda aceita um calendário no pedido de criação da Embrapa. O parser reconheceu onze aspectos em seis perguntas, mas errou entidades e deixou muitos requisitos sem representação; não se calcula “acurácia” a partir desse número.

A revisão dos trechos pelo agente encontrou um novo caso parcialmente útil devolvido (Tramontina: ano/produtos, sem fundadores), rejeitado pelo classificador, e mais um trecho parcial lido mas não devolvido (Array em inglês descrevendo `toSorted` e imutabilidade). O antes aceitava Array genérico sem a operação no trecho. **Recuperar essas informações e depois perdê-las ainda falha no critério de entrega ao chat.** Não são duas respostas concluídas. Não houve avaliação humana independente nem oráculo para recall absoluto, precisão global, grounding/completude/citação de respostas finais nestes probes sem LLM.

Replay de leituras antigas, sem nova busca: históricos vinte, flags12→11 em56 leituras; antigos quinze, 2→0 em41. Foram recusados o falso positivo de WebAssembly **e a passagem parcialmente útil de Chibata**, além de uma leitura de reciclagem no conjunto histórico. A regra ficou mais restritiva e ainda não separa todos os falsos positivos dos falsos negativos. Não se apresenta isso como ganho global de precisão.

O guard `86462e9` foi motivado pela confusão de interfaces no QA, depois de aberto o conjunto, e não por otimização dos vinte resultados. A comparação permanece atribuída a `af400f1`. **Não existe novo holdout independente que aprove o último guard/final desta versão**; os testes focados e o E2E específico não substituem isso.

## Execução autenticada e visual

[E2E detalhado](docs/v5.9.9.3/DEEP_SEARCH_E2E.md), [JDUI/visuais](docs/v5.9.9.3/JDUI_RESULTS.md). Chrome com FastAPI/agente reais, contas e SQLite descartáveis. Onze tentativas iniciais e onze fluxos reais de busca; depois quatro repetições focadas após correções. Fonte oficial/primária permanece pendente de verificação automática, em vez de aprovação por reputação do domínio.

O modelo gratuito retornou **rate_limit** na primeira rodada; o parcial preservou uma leitura e chegou ao chat. A síntese de pesquisa foi desativada nas rodadas seguintes. Um erro do harness achatou a configuração de caso único e enviou “e” ao chat comum, acionando uma chamada de chat não planejada; não conta como pesquisa e está preservado. O driver agora valida a configuração antes do envio. Não houve nova tentativa de redação/revisão de pesquisa após o rate limit. **Nenhuma inferência pública completa de pesquisa foi aprovada.**

Na verificação final `86462e9`, a pergunta qualificada terminou em 11,412 s: **uma** referência MDN da API JavaScript, resultado extrativo com citação/card, tabela, SSE e texto/ID preservados após reload. A instrução Wasm com falha diferente deixou de ser usada. O outcome continua parcial, sem fingir oficialidade verificada ou síntese humana. WEG teve uma fonte secundária com fundadores/data detectados e produtos ainda pendentes; não foi uma investigação completa.

Inspecionadas galeria e tabela em 1280/390/320px, modal, erro de imagem e CSS200%. Sem overflow de página medido; tabela estreita usa scroll interno e as capturas esquerda/direita foram abertas. Teclado, Escape, restauração do foco, reduced motion, reload, erro de imagem/recuperação, CSV da tabela e MD/CSV do job funcionaram. Na instância dos quatro casos: IndexedDB com 10 mensagens/3 estruturadas/2 resultados. Não houve teste de aparelho físico, zoom nativo, FPS ou auditoria integral de acessibilidade. A síntese extrativa e os metadados ainda são verbosos, e a ordem de código inline pode se perder no extrator.

## Testes, recursos e segurança

- Baseline anterior verificável: 1556 passed/4 skipped/2 warnings, seguido de recorte atual 92 passed. A primeira suíte encontrou cinco regressões; leituras/assunto “Bateria ZX”, consulta inicial e intervenção entre chats foram corrigidas, sem afrouxar benchmarks.
- Suítes completas verdes antes do último guard: 1574 passed/4 skipped/2 warnings. Após o guard: **1575 passed, 4 skipped, 2 warnings em 247,87 s**, `full-suite-qualified-final.log`. Dezenove testes novos de contrato cobrem relações, negativos, spans, conflitos, navegação, owner/chat, parcial/cancelamento, quote entre passagens e interface qualificada.
- Benchmarks antigos: **Search 34/34, Shopping 59/59, Experience 16/16**; datasets preservados. Não representam ganho externo. Avisos: depreciações `mss.mss` e timeout no Starlette TestClient.
- Sem aumento geral de fontes, concorrência, tokens ou bytes. A diferença de mediana de rede não tem atribuição causal garantida. Amostra ociosa QA: RSS relay 34.623.488 bytes/agente 3.842.048 bytes, CPU 0% em amostras 0,2 s; não são picos ou comparação de desempenho de produção. Tempos de busca/leitura/síntese e tamanho de contexto estão nos jobs/logs quando executados, sem inventar tempos de fases puladas.
- Auth, reauth, RBAC, CSRF, owner isolation, grants, SSRF/redirect, rate limit, circuito, WAL, cache/checkpoints e cancelamento continuam cobertos pela suíte existente. Nenhuma permissão foi ampliada e nenhum código do modelo/site foi executado. Os processos QA usam relay/banco próprios; recibos de limpeza e varredura de segredos estão na pasta QA. Arquivos privados de runtime, cookies e SQLite não integram a entrega.

## Pendências objetivas

Os requisitos ainda são padrões explícitos, não compreensão universal. Faltam relações comuns, correferência, semântica de atributos/listas, autoridade da fonte e seleção de passagem que preserve todas as partes úteis. A navegação é limitada e não garante referência específica. O planner ainda usa o controlador/replanejamento existente, sem uma política semântica geral para todas as ações sugeridas. Não foram demonstrados PDF pertinente, vídeo individual, comparação multifonte completa ou investigação complexa completa em perguntas novas.

Próximo passo: construir corpus anotado de passagens/entidades/relações, medir fidelidade das consultas/respostas de provedor e corrigir perdas sem aceitar assunto como prova. Usar os vinte abertos apenas como diagnóstico; congelar outro conjunto antes de otimizar, e exigir resposta pública completa com citações/cards/persistência. Não acrescentar complexidade ou publicar por aumento de testes.

Complementos: [requisitos](docs/v5.9.9.3/ANSWER_REQUIREMENTS.md), [passagens](docs/v5.9.9.3/PASSAGE_RETRIEVAL.md), [navegação](docs/v5.9.9.3/SOURCE_NAVIGATION.md), [validação](docs/v5.9.9.3/EVIDENCE_VALIDATION.md), [índice de evidências](qa-artifacts/v5993/README.md).
