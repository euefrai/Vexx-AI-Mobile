# Vexx AI — síntese fundamentada de pesquisa

Entrega local, 22/10/2026. Base: `c8a1845`. Sem push, deploy ou reinício do agente de produção.

## Alterado

- O worker de pesquisas agora solicita uma redação final ao modelo já configurado no PC. Coleta, busca, verificação, identidade Lucas e permissões existentes são preservadas. Não há ferramentas, execução de código do modelo ou inclusão do histórico/memória no prompt de redação.
- A chamada ocorre somente depois das rodadas adaptativas. Uma tentativa por job, sem troca automática de modelo; limite de 1.800 tokens e timeout passado ao cliente de até 25 s, limitado pelo tempo restante da pesquisa. Sem evidência lida ou tempo suficiente, mantém a extração. `VEXX_RESEARCH_SYNTHESIS=0` desliga a redação assistida.
- Saída estruturada: até cinco parágrafos com referências a evidências e trechos literais. IDs desconhecidos, trechos inventados/não contíguos, números/unidades ausentes dos trechos, saída vazia, HTML, URLs adicionadas pelo modelo e tamanho excessivo rejeitam a candidata inteira. Trechos separados da mesma fonte precisam de registros separados. Não se corta uma conclusão pela metade para caber no limite.
- A resposta aceita mostra links das fontes, limitações de abstracts e divergências conhecidas. O fallback também respeita um orçamento de apresentação sem cortar links longos; os links completos continuam nos cards de fontes. Proveniência guarda o ID real, trecho e parágrafo no checkpoint existente. Relatório, JDUI e exportações Markdown/CSV/JSON conservam a síntese.
- Corrigida a numeração das referências extrativas: ordenar por relevância podia renumerar fontes e perder a relação com seus IDs. Agora os rótulos permanecem estáveis e levam ao link da fonte. A auditoria confere referências contra evidências lidas.
- Falha, cancelamento, erro de formato ou recusa de validação preservam o fallback extrativo. Exceções arbitrárias do provedor não entram nos eventos nem na resposta; diagnóstico usa categorias fechadas. O fallback deixa de afirmar que nenhuma inferência foi solicitada quando uma tentativa ocorreu.

## Validação

- Baseline: **41 passed**, um aviso preexistente (`research_agents`, `evidence_graph`, `research_reports`).
- Primeiro conjunto ampliado: um teste de relatório falhou porque comparava texto simples com Markdown escapado; a asserção foi ajustada para conferir o conteúdo preservado. Depois: **71 passed**, incluindo as regressões anteriores.
- Integração final: **51 passed**, cobrindo fonte não lida, IDs, trechos separados, números/unidades, limites, erros, cancelamento concorrente, identidade, worker habilitado/desabilitado, retomada sem nova chamada, isolamento por dono, checkpoint, relatório, exports e JDUI.
- Suíte completa final: **1.187 passed, 4 skipped, 2 warnings em 114,15 s**. Logs anteriores aprovados: 1.181 e 1.185 testes; quatro skips e dois avisos preexistentes (mss/httpx). Nenhum teste removido. A revisão textual e suas ressalvas estão em `qa-artifacts/research-synthesis-review.md`.
- `git diff --check` aprovado. Arquivos de QA revisados quanto à presença das credenciais locais antes da entrega.

## Modelo real e comparação

Foram feitas duas chamadas de smoke e uma rodada de **20 perguntas técnicas reais**, com `poolside/laguna-s-2.1:free`, o modelo já configurado. O primeiro smoke foi rejeitado e o segundo produziu síntese aceita. A rodada usou resumos manuais em português conferidos nas documentações oficiais de [estruturas Python](https://docs.python.org/3/tutorial/datastructures.html), [ordenação Python](https://docs.python.org/3/howto/sorting.html), [SQLite WAL](https://www.sqlite.org/wal.html) e [chaves estrangeiras SQLite](https://www.sqlite.org/foreignkeys.html).

O corpus e o escopo estão em `benchmarks/research_synthesis_v1.json`; a execução opt-in está em `tools/evaluate_research_synthesis.py --live`. Banco descartável; nenhuma conversa real utilizada. A avaliação isola **redação/citações**, não mede o buscador nem leitura automática das páginas.

- Rodada inicial: **13 candidatas aceitas e sete fallbacks**. Isso é aceitação de formato/rastreabilidade, não uma taxa de verdade ou aprovação semântica.
- Tempo mediano: extração **0,93 ms**; tentativa de redação **5.107,33 ms**, sem tempo de coleta. A resposta assistida custa uma chamada e acrescenta latência; consultas simples de clima/horário/conversa não entram neste worker.
- Sete chamadas adicionais de diagnóstico, sem retries automáticos no produto. Duas rejeições foram reproduzidas por comprimento de parágrafo. O limite solicitado continua 500 caracteres; o teto validado passou a 650, preservando teto global de 3.000 caracteres antes dos avisos, compatível com a apresentação existente.
- Replay das sete candidatas salvas, sem nova inferência: **seis aceitas**, uma ainda recusada porque juntava frases não adjacentes como se fossem um único trecho. O replay não é outra rodada independente e não substitui os resultados originais. Todas as tentativas anteriores foram preservadas.
- Inspeção textual das saídas aceitas confirmou respostas mais diretas em vários casos. Há extrapolações de redação que os controles não resolvem: por exemplo, uma resposta acrescentou interpretação sobre o design de `list.sort`. Não se afirma suporte semântico completo nem equivalência ao Perplexity.

Evidências: `qa-artifacts/research-synthesis-{baseline,focused,integration,full-suite-delivery}.log`, `research-synthesis-evaluation.json`, `research-synthesis-diagnostic.json`, `research-synthesis-diagnostic-replay.json` e `research-synthesis-model-smoke*.json`.

## Arquivos e limites

Produção: `research_synthesis.py`, `research_agents.py`, `pc_agent.py`, `research_exports.py`, `.env.example`. Testes: `tests/test_research_synthesis.py`. Corpus, ferramenta, evidências e este relatório completam a entrega. Sem dependências novas ou migrações de banco.

Os controles garantem referências válidas, trechos presentes e verificações numéricas limitadas. Não provam que uma paráfrase decorre do trecho, não verificam causalidade e não detectam todas as trocas de entidades/condições ou números escritos por extenso. O próximo avanço é avaliar e ampliar esse suporte semântico com um conjunto independente e diversificado.

Cancelamento é conferido antes/depois da chamada e o resultado tardio é descartado; não aborta imediatamente uma requisição HTTP já em curso. O timeout depende também do comportamento do cliente/provedor. Se houver crash após registrar a tentativa, a retomada não repete a inferência automaticamente. Nenhum plano ou provedor foi ativado; custos seguem a configuração existente.

Não houve teste visual em navegador/aparelho físico nem smoke pela interface de produção nesta entrega. Integrações reais comprovadas aqui são as inferências isoladas; coleta web, SSE e armazenamento continuam cobertos pelos testes existentes e pelos novos testes de integração controlada.
