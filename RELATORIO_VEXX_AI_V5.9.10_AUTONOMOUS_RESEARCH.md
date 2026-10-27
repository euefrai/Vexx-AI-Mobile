# VEXX AI V5.9.10 — Autonomous Research

**Decisão: NO_GO para Research Ultra.** Há correções locais comprovadas, mas a descoberta externa continua insuficiente e nenhuma pesquisa profunda do QA entregou síntese LLM completa e validada. Sem push, deploy, reinício de produção ou alteração de dados reais.

## Estado e implementação

Worktree `vexx-v598-dev`, branch `codex/v598-autonomous-research`, base `6d73e48`; árvore rastreada inicialmente limpa. Arquivos antigos não rastreados foram preservados.

| Commit local | Entrega |
|---|---|
| `e8d8e0c` | Novo holdout de 16 perguntas e manifestos de controle congelados antes das correções. |
| `f0977ea` | Requisitos naturais/consultas conservadoras; transporte de tabelas já extraídas; relações literais com suporte parcial e persistência. |
| `9ef70de` | Content parts corretos; metadados seguros de respostas vazias e classificação de truncamento/filtro no writer. |
| `a03d67d` | Foco após remount de galeria; fim dos tailers de jobs interrompidos/pausados; diagnóstico da reconexão Windows. |
| `7fd07e9` | Instrumentos de captura, contraste autenticado, UI e verificação de encerramento QA. |

Arquivos de produto: `query_intelligence.py`, `evidence_graph.py`, `research_agents.py`, `web_extract.py`, `hermes_bridge.py`, `pc_agent.py`, `public/jdui.js`. Regressões: `tests/test_autonomous_v5910.py`, `tests/test_synthesis_transport_v5910.py`, `tests/test_research_tailer_v5910.py`, diagnóstico adicional em `tests/test_agent_runtime_v5981.py`. Ferramentas/artefatos de QA separados do runtime de produto; capturas privadas ignoradas pelo Git.

## Resultado medido

- **Corpus controlado:** a mesma captura Bosch passou de zero fonte retida para uma, com fundador/ano/produtos **parcialmente** sustentados. Mesmo corpus/pool/orçamento; mede retenção após leitura, não descoberta ou ranking. O rerun externo Bosch continuou sem evidência útil.
- **Holdout novo:** 16 perguntas sem URL; três retiveram entradas, nenhuma reteve IDs de passagens vinculadas a requisitos. As três não tinham esquema aplicável suficiente. Não classificadas como respostas completas; não comparar causalmente com o antigo 2/12.
- **Leitura:** sete snapshots reexecutados; Nikon continua com 767 caracteres, duas passagens tardias/parciais e spans. Math.hypot mantém três facetas sustentadas. Limite de 8.000 e `_document_windows` preservados.
- **Modelo real:** mesmo gratuito `poolside/laguna-s-2.1:free`. B/agente recebeu HTTP 200 não vazio, mas citação incompatível; A/direto e C/endpoint autenticado atingiram 15s. Dados de entrada textuais equivalentes comprovados. Nenhum retry até verde. A causa do HTTP 200 vazio histórico permanece **não determinada**; parsing de content parts/perda de metadados foram corrigidos por reproduções controladas.
- **Chat real:** nove cenários via Chrome, FastAPI, PC Agent de desenvolvimento e SQLite temporário. WEG recuperou autonomamente fundador/ano, mas não produtos, e a redação foi rejeitada. Factual/notícias/comparação/deep novo não entregaram resposta fundamentada. Escassez não inventou números. Galeria/cancelamento funcionaram. Resultados observados persistiram após reload: SQLite e IndexedDB com 22 IDs únicos; MD/CSV baixados.
- **JDUI:** sem overflow em 1280/390/320 e CSS 200%; teclado/Escape/foco, link real, reduced motion, metadados e reload verificados em Chrome. Capturas inspecionadas; sem alegação de celular físico.
- **Lifecycle:** reprodução nova falhou nos estados `interrompida` e `pausada`; correção encerra tailers e libera drain. A intermitência antiga de reconexão não foi reproduzida nem declarada resolvida; timeout original mantido e diagnóstico melhorado.

## Verificação

Grupos focados: requisitos/query 92 aprovados; arquivo final de requisitos 10; transporte/síntese/números 84; frontend/runtime/transporte 26; lifecycle/runtime/research 39. Há sobreposição entre grupos: não somar como testes distintos.

Primeira suíte completa: **1.748 passed, 4 skipped, 2 warnings, 424,22s**. Depois surgiu a reprodução do tailer, justificando uma segunda suíte completa. **Suíte final: 1.754 passed, 4 skipped, 2 warnings, 539,86s; exit 0.** QA encerrado: ambos os bancos/runtimes temporários removidos, zero processos correspondentes. A sessão C precisou descartar seu próprio launcher após timeout de drain; a sessão live encerrou normalmente com zero operações ativas antes do stop. Não houve encerramento de PC Agent de produção.

Benchmarks executados: **Search 34/34; Shopping 59/59; Experience 16/16**. Não são prova de pesquisa externa nem de síntese real. Warnings: depreciações existentes de `mss.mss` e argumento `timeout` do TestClient. Nenhum teste removido ou validação afrouxada.

## Gates

| Gate | Estado | Motivo |
|---|---|---|
| A — Web normal | Parcial / não aprovado factual | Saudação rápida sem job; busca simples/notícias não recuperaram fontes. |
| B — Requisitos | Ganho localizado | Regressões corrigidas, mas comparação e entidade com instruções adicionais ainda falham. |
| C — Descoberta | **NO_GO** | Holdout sem passagens vinculadas; ganho do replay não se repetiu de forma universal. |
| D — Evidência | Parcial | Bosch no controle e WEG no QA; não cobre todos os requisitos. |
| E — Replanejamento | Regressão local aprovada | Lacuna pendente preservada sem repetir facetas resolvidas; não comprova conclusão externa. |
| F — Síntese real | **NO_GO / chamadas bloqueadas** | Quote mismatch/quantidade e timeouts; sem revisão válida de resposta completa. |
| G — Autônomo ponta a ponta | **NO_GO** | Nenhuma cadeia completa aprovada. |
| H — JDUI/persistência | Aprovado no escopo testado | Cards/resultados observados, reload, IndexedDB, exportações e galeria. |
| I — Estabilidade | Parcial | Foco e vazamento corrigidos; reconexão histórica sem causa reproduzida. |
| J — Segurança | Sem regressão identificada na suíte | Auth/RBAC/CSRF/SSRF, isolamento, permissões remotas e validações preservados; não equivale a auditoria externa integral. |

## Pendências e próximo passo

Prioridade seguinte: corrigir extração de entidades em comparações/pedidos com instruções, ampliar requisitos por relações demonstráveis em corpus de desenvolvimento e confrontar ranking/aliases com novos controles antes de outro holdout. Depois validar uma redação/revisão real com os mesmos trechos e orçamento, mantendo citações e números estritos. Não abrir mais buscas/modelos para esconder baixa precisão.

Ainda pendentes: causa histórica do vazio; reconexão intermitente; notícias/fontes atuais; cobertura das categorias sem esquema; título genérico `company` e data de criação do artigo no card; placeholder em 320px. As sínteses rejeitadas foram preservadas localmente para diagnóstico seguro, sem publicar payloads ou reasoning.

Detalhes e comandos/instrumentos: [rotas e causas](docs/v5.9.10/ROUTES_AND_DIAGNOSIS.md), [avaliação e limitações](docs/v5.9.10/EVALUATION.md), [progresso](docs/v5.9.10/PROGRESS.md). Sumários compactos em `qa-artifacts/v5910/*-summary.json`; corpos/páginas/configuração QA em `raw/`, fora do Git.
