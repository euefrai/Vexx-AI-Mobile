# VEXX AI V5.9.9.9 — Deep Document Navigation & Retrieval Recovery

**Decisão: NO_GO para Research Ultra/pesquisa profunda completa.** A recuperação tardia foi comprovada com saída menor; descoberta continua pouco abrangente e a síntese autenticada sofreu falha do provedor.

## Resultado principal

| Verificação | Resultado observado |
|---|---|
| A — Leitura conhecida | Nikon: informações além de 11.000/12.000 recuperadas em 767 caracteres, offsets literais verificados, peso/bateria mantidos como suporte parcial |
| B — Descoberta sem URL | Novo holdout: 2/12 perguntas com passagens úteis, ambas APIs; uma página oficial apenas contextual; demais sem informação útil retida |
| C — Síntese | Escrita+revisão reais aprovadas em execução isolada; captura revalidada com guardas atuais; tentativa autenticada retornou vazia, com resultado parcial persistido |

As três verificações não ficaram aprovadas em cenários completos independentes. Não há justificativa para publicar a versão como pesquisa universal.

## Base e commits locais

HEAD inicial `8ccbbe0`, branch `codex/v598-autonomous-research`, árvore rastreada limpa no início.

- `bc3bc27`: novo holdout e corpus congelados antes da implementação.
- `51b8291`: seleção de seções tardias, parser interrogativo, proveniência, contexto no card, trace e testes.
- `2b1e457`: equivalência decimal inequívoca, unidades/moedas/identificadores e captura privada de síntese.
- `3c269ac`: regressões em outros domínios e QA por fonte conhecida.
- Documentação e evidências compactas: commit local de entrega, consultável em `git log` após este relatório.

Nenhum push/deploy. Nenhum PC Agent real encerrado; apenas harness QA temporário criado e encerrado. Nenhum SQLite de produção escrito.

## Mudanças e ponto de perda

O download já havia recuperado os bytes Nikon. `extrair_pagina` escolhia uma única janela de 8.000 caracteres antes da segmentação; `secoes` também cortava nas primeiras 12 seções. A informação tardia estava no texto transiente, mas não chegava ao gerador de passagens.

`web_extract._document_windows` agora percorre os elementos alinhados e os gaps do texto efetivamente disponível do extrator escolhido, ranqueia candidatos por faceta e retém até oito janelas não sobrepostas dentro de 8.000 caracteres. Não há nova chamada de rede, novo motor/agente, embeddings, dependência ou ampliação de contexto do modelo. Linhas de tabela preservam rótulo, valor, unidade e qualificadores.

`text_span` referencia a saída compacta; `source_span` referencia a extração normalizada com SHA. IDs, tipo de elemento, seção quando alinhada, contexto e requisitos seguem até cache/grafo/evidência. Cache mantém isolamento e muda a versão para 5.9.9.9. Contexto de seção real aparece no card existente, com estado parcial explícito.

A consulta “qual o peso da…” agora identifica a entidade sem exigir “é”. A mudança foi feita em desenvolvimento antes de abrir o holdout.

Mapa de limites de bytes/HTML/texto/análise/passagens/grafo/LLM/cards: [TEXT_LIMIT_ANALYSIS.md](docs/v5.9.9.9/TEXT_LIMIT_ANALYSIS.md).

## Evidência controlada e recursos

Sete HTMLs públicos idênticos antes/depois: documentos com passagem elegível **2→3**. Nikon: 7.998→767 caracteres, quatro janelas selecionadas pelo extrator, duas elegíveis como suporte parcial. Bateria e peso aparecem além do corte anterior. Quatro offsets comparados literalmente ao texto de referência, sem offsets de HTML inventados.

MDN assign/hypot preservaram suas facetas. Tramontina/NASA/SQLite/Yellowstone não ganharam evidência; saída menor sem resposta não é ganho de qualidade. Não se aumentou o trecho de até 1.800 caracteres por fonte do redator.

Amostra instrumentada Nikon: extração 0,231→0,248 s; pico de alocação Python 2.742.161→2.494.604 bytes. Outros casos tiveram custos maiores: SQLite 0,102→0,158 s; Yellowstone alocação 920.776→1.265.298 bytes. Não se afirma economia global de RAM, pico RSS ou significância estatística. [Replay](docs/v5.9.9.9/CONTROLLED_REPLAY.md).

## Descoberta externa

Novo conjunto de doze perguntas, congelado em `bc3bc27`. Execução live em 27/10/2026. Sem URLs semeadas em Track B e sem ajustes de retrieval após abrir os casos.

reduceRight e allSettled produziram passagens úteis. Registros com URL repetida e espelhos MDN não foram contados como corroboradores independentes. A biblioteca oficial foi aberta, mas não trouxe a contagem diária solicitada: apenas contexto. Complete refere-se às facetas parseadas, não à pergunta natural inteira.

Não existe gold humano independente para precisão/recall. As perguntas/rede diferem da V5998: 0→2 não comprova ganho causal global. Queries, candidatos, documentos, retenção, motivos de rejeição e tempos estão em `external-summary.json`. [Diagnóstico](docs/v5.9.9.9/SOURCE_DISCOVERY.md), [holdout](docs/v5.9.9.9/EXTERNAL_HOLDOUT.md).

## Validação numérica e síntese

Falso positivo controlado corrigido: `1,5 kg` e `1.5 kg` são equivalentes. Separadores com interpretação ambígua continuam não confirmados. Guardas rejeitam trocas de gramas/quilos, moedas explícitas e sufixos de bateria. Testes incluem formatos locais, milhares com centavos, percentuais, intervalos, datas, versões, identificadores e negativos. A revisão contextual continua obrigatória para atributo, entidade, aproximação e data; números iguais isoladamente não comprovam suporte.

A antiga rejeição V5998 não pode ser adjudicada: a saída rejeitada não havia sido capturada. Isso não foi inventado retroativamente como erro do modelo ou do validador.

Modelo real gratuito `poolside/laguna-s-2.1:free`: execução isolada aprovada em redação e revisão, sem ampliar prazos. Tentativa autenticada recebeu HTTP 200 com resposta vazia em 15,043 s; estado blocked/provider=vazia, evidência/resultado parcial preservados. Sem retries para obter verde, sem fallback pago. TTFT não medido nesse caminho não streaming. [Números](docs/v5.9.9.9/NUMERIC_GROUNDING.md), [LLM](docs/v5.9.9.9/LLM_SYNTHESIS.md).

## QA e segurança

Chrome autenticado local validou fonte conhecida Nikon, fonte/link real, estados parciais, SSE, persistência, cancelamento, galeria, exportações MD/CSV, IndexedDB e reconexão injetada. Casos autônomos C/D/F não demonstraram evidência suficiente: não aprovados como cadeia profunda completa.

Cards/tabela dentro de 1280/390/320 px; screenshots de 320/1280 e galeria inspecionados. Zoom CSS 200%, teclado, readonly e reduced motion observados. Não foi teste físico. Retorno de foco da galeria falhou uma vez e passou na repetição instrumentada; causa intermitente pendente, sem correção especulativa.

Houve falha de configuração do harness durante navegação inicial e uma pesquisa padrão extra excluída dos critérios. Screenshot histórica sobrescrita pelo harness foi preservada localmente na pasta atual e original restaurada do Git, que estava limpo. Nenhuma falha foi contada como passe.

Auth, RBAC, CSRF, owner isolation, grants, SSRF/DNS/redirects, sanitização, WAL e cancelamento não foram relaxados. Sem mudanças em identidade Lucas, Studio, VERY ou extensão. Capturas integrais/respostas privadas/runtime ficam fora do Git. [E2E](docs/v5.9.9.9/AUTHENTICATED_E2E.md), [JDUI](docs/v5.9.9.9/JDUI_QA.md).

## Testes

Suítes preservadas: 1.707 passed na etapa de leitura; 1.731 passed após números. Com os três últimos casos adicionados, uma suíte terminou 1.733 passed/1 failed/4 skipped: backend Windows não reconectou na espera de 15 segundos. O teste isolado passou em 14,71 s, sem alteração de prazo/código. **Suíte final, após encerrar QA/navegador: 1.734 passed, 4 skipped, 2 warnings, 550,47 s.** A falha anterior permanece em `validation-summary.json`; a repetição verde não identifica sua causa nem prova ausência de intermitência.

Benchmarks: pesquisa 34/34, shopping 59/59, experiência 16/16. `node --check` nos dois scripts QA alterados, `py_compile` nas ferramentas/módulos e `git diff --check` executados. Nenhum teste removido ou mascarado. Logs completos ficam locais, com hashes no manifesto.

## Arquivos alterados

- Extração/seleção: `web_extract.py`, `query_intelligence.py`.
- Evidência/cache/trace/entrega: `evidence_graph.py`, `research.py`, `research_agents.py`, `retrieval_trace.py`, `research_view.py`.
- Síntese: `research_synthesis.py`.
- Regressões: `tests/test_deep_document_v5999.py`, `tests/test_numeric_grounding_v5999.py`.
- Ferramentas: `tools/replay_document_v5999.py`, `tools/probe_source_quality_v5998.py`, `tools/probe_synthesis_v5998.py`, `tools/qa_direct_delivery_v5994.py`, `tools/qa_discovery_v5992.cjs`, `tools/qa_evidence_visual_v5994.cjs`.
- Congelamento: `benchmarks/deep_document_v5999_holdout.json`, `benchmarks/deep_document_v5999_corpus.json`.
- Proteção de artefatos: `.gitignore`; relatórios em `docs/v5.9.9.9/`, resumos/scripts/capturas selecionados em `qa-artifacts/v5999/`.

HEAD final de código/testes: `3c269ac`; entrega documental em commit separado. O hash da entrega é informado no retorno e verificável com `git log -1`.

## Gates e pendências

| Gate | Avaliação |
|---|---|
| A alcance documental | Aprovado no texto disponível dos casos testados; fora do melhor bloco/PDF continua limitado |
| B estrutura | Passagens/linhas/títulos reais alinhados; não é compreensão universal de HTML |
| C rendimento | Ganho localizado mensurado; precisão global não medida |
| D requisitos | Facetas preservadas, Nikon parcial; parser ainda incompleto |
| E proveniência | Offsets/IDs/SHA verificados no replay; grafo não promove similaridade a verdade |
| F descoberta | Insuficiente, duas perguntas técnicas úteis de doze |
| G números | Regressões controladas corrigidas; contexto permanece com revisor, falha antiga indeterminada |
| H síntese | Isolada aprovada; autenticada bloqueada pelo provedor |
| I JDUI | Persistência/links/cards funcionam no escopo parcial; foco intermitente pendente |
| J segurança | Nenhuma flexibilização; falha de reconexão de teste registrada e reavaliada |

Próximos passos: melhorar seleção de candidatos/consultas dos provedores existentes; examinar perdas fora do melhor bloco e facetas não parseadas; investigar foco intermitente e estabilidade de inicialização/revisão. Congelar avaliação nova antes de otimizar novamente. Sem recomendar publicação enquanto descoberta e síntese autenticada continuarem insuficientes.
