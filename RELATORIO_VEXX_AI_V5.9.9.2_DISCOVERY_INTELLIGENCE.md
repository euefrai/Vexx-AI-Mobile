# VEXX AI V5.9.9.2 — Discovery Intelligence

**Decisão: não aprovar publicação.** Houve correções reproduzíveis no planejamento, na seleção anterior aos cortes e no conteúdo entregue aos cards, mas o conjunto novo não demonstrou ganho consistente de recuperação. Não houve pesquisa profunda completa com inferência aprovada manualmente. A quantidade de testes não compensa esses limites.

## Código e escopo

Base confirmada `4d13807`; desenvolvimento em `vexx-v598-dev`, branch `codex/v598-autonomous-research`. Núcleo de busca congelado em `ad16f21` antes de abrir o novo holdout; HEAD final de código `1ce380a`. Commits posteriores de evidência/documentação não mudam o motor. Nenhum push, deploy, reinício de produção, alteração de dados reais, Studio, VERY, extensão, identidade Lucas, 3D ou permissões de controle remoto.

| Commit local | Alteração |
|---|---|
| `2c6a324` | Congela quinze consultas independentes; instrumenta baseline e captura limitada de respostas/leitura |
| `b9c8631` | Separa tema/instruções; planeja consultas; preserva oportunidades originais antes do corte |
| `ee3f486` | Retenta entidade após incompatibilidade real; não confunde comandos com nomes |
| `ad16f21` | Preserva janela histórica literal útil; aplica requisito de documento também no profundo |
| `c9104dc` | Corrige protocolo do agente simulado de teste e mantém QA real focado |
| `1ce380a` | Rejeita controles ocultos de direção na saída do modelo, preservando fallback/evidências |

## Problemas e correções

A [matriz causal dos doze casos](docs/v5.9.9.2/ROOT_CAUSE_ANALYSIS.md) distingue consulta, resposta externa, seleção, leitura e validação. O fornecedor por vezes devolve itens alheios apesar de receber a consulta correta; reduzir parâmetros RSS não resolveu consistentemente, portanto não foi aplicada uma falsa correção de encoding. Bloqueios externos não foram contornados.

- `query_intelligence.py`: perfil determinístico com assunto, entidades candidatas, informação requerida e preferências de apresentação separadas. Mantém pedido original e restrições; não é NER universal ou desambiguação factual completa.
- `search_orchestrator.py`: plano observável, recuperação do publicador antes de repetir manchete, retentativa pelo tema exato quando há incompatibilidade, ganho de descoberta sem contar domínios irrelevantes. Reutiliza tentativas e concorrência existentes. Uma coleção de palavras dispersas não vira correspondência suficiente.
- `research.py`: preserva oportunidades de leitura antes do corte de doze e versiona cache sem apagar dados; expõe diagnóstico de descoberta/plano.
- `research_agents.py` e `search_verticals.py`: pedido PDF exige conteúdo de documento realmente extraído no rápido e no profundo; histórico preserva janela contígua literal até 1500 caracteres, com nomes/datas do texto lido. Evita aviso de manutenção ocupando o card da WEG.
- `research_synthesis.py`: rejeita controles Unicode ocultos na saída JSON decodificada, inclusive escapes. Mantém letras RTL normais e não executa código do modelo.
- Testes: corrigido fixture de calendário UTC/Bahia e handshake de revogação do agente simulado, sem afrouxar produto. Falhas e regressões intermediárias permanecem nos logs.

Novos arquivos auxiliares: `tests/test_discovery_v5992.py`, `tools/bench_discovery_v5992.py`, `tools/summarize_discovery_v5992.py`, `tools/qa_discovery_v5992.cjs` e `benchmarks/discovery_v5992_holdout.json`. Também alterados `tests/test_source_recovery_v5991.py`, `tests/test_universal_search_v599.py`, `tests/test_remoto.py` e `.gitignore` para excluir metadados privados QA. Os benchmarks antigos congelados não foram alterados. Não houve mudança de UI/JS ou novo motor/provedor/agente.

## Antes/depois na rede real

Baseline `2c6a324`; depois `ad16f21`, mesmas perguntas e orçamentos. O relógio final do parser é ancorado no baseline porque a execução atravessou meia-noite; relógio do aplicativo permanece real. Índices, rede e carga podem variar. Fonte: `qa-artifacts/v5992/comparison.json`.

| Conjunto | Leituras elegíveis (motor) | Casos com alguma elegível | Fontes abertas devolvidas | Candidatos no pool | Chamadas de provedor | Fetches observados | Mediana s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Antigos 12, antes | 0 | 0/12 | 33 | 119 | 60 | 121 | 7,992 |
| Antigos 12, depois | 5 | 3/12 | 32 | 131 | 53 | 125 | 12,893 |
| Históricos 20, antes | 13 | 7/20 | 54 | 185 | 108 | 210 | 10,199 |
| Históricos 20, depois | 12 | 7/20 | 56 | 197 | 113 | 223 | 5,987 |
| Novos 15, antes | 2 | 2/15 | 42 | 128 | 75 | 148 | 9,140 |
| Novos 15, depois | 2 | 2/15 | 41 | 128 | 68 | 151 | 12,101 |

**Elegibilidade do motor não comprova relevância suficiente, precisão factual nem pesquisa concluída.** Nos doze casos antigos, os cinco flags pertencem a três pedidos: notícia do Acre (um artigo original recuperado), museu (três leituras de origens variadas) e WEG (uma leitura secundária). Não são cinco respostas completas. Os vinte históricos perderam uma leitura elegível, com o mesmo número de casos atendidos.

A [avaliação dos quinze novos](docs/v5.9.9.2/HOLDOUT_EVALUATION.md) leu os trechos e registrou critérios/URLs em `holdout-judgments.json`: zero → **um caso parcialmente útil** sobre a causa da Revolta da Chibata, sem suas consequências. O verbete geral de WebAssembly continuou aceito pelo motor sem conter a operação específica no trecho capturado. Seis metadados Commons no pedido de imagens permaneceram nas duas rodadas; isso não é leitura textual ou análise visual. O julgador foi o agente Codex após o congelamento, não um painel humano independente. Não há denominador para recall absoluto, precisão global ou todas as fontes relevantes descartadas.

O resultado revela limites ainda abertos: atributos de perguntas compostas misturados à entidade, fontes que respondem apenas a termos genéricos, documentação específica perdida em páginas iniciais e rotulagem lexical excessivamente permissiva. Nenhum algoritmo foi ajustado com os resultados do novo holdout já abertos. A proteção Unicode posterior veio de QA de síntese, não de ajuste da recuperação.

## Chat, JDUI e inferência reais

[E2E detalhado](docs/v5.9.9.2/DEEP_SEARCH_E2E.md) e [JDUI](docs/v5.9.9.2/JDUI_RESULTS.md). Chrome autenticado com contas/banco descartáveis, FastAPI, agente e modelo gratuito reais. Houve SSE, links oficiais, cards, IDs/textos preservados após reload, cancelamento sem final tardio e imagens reais com origem/direitos. WEG passou a apresentar fundação e fundadores no trecho literal, porém fonte secundária não satisfaz plenamente pedido por primária.

O modelo gratuito gerou texto público com citação em rodadas técnicas, sempre com cobertura parcial. Uma saída real continha caracteres U+202E e exemplo de código malformado apesar de aprovação automática; não foi aprovada manualmente. A nova proteção foi validada deterministicamente. A tentativa real após `1ce380a` terminou `interrompida/blocked`, timeout de redação/revisão, uma fonte lida reportada no status e **nenhuma resposta final no chat**. A captura do painel pós-timeout foi precoce e não confirmou sua renderização de evidências; não conta como teste aprovado dessa preservação. Não se declara inferência completa aprovada.

Inspecionadas capturas em 1280/390/320 px, modal, erro de imagem e CSS 200%; sem overflow horizontal nas medições. Teclado, Escape, foco, metadados e galeria após reload passaram. IndexedDB: treze mensagens, quatro estruturadas, três finais. SQLite QA: treze mensagens/quatro jobs. Downloads MD/CSV reais concluíram. Não foram validadas visualmente tabelas de uma resposta real, todos os estados vazios, celular físico ou acessibilidade integral. Nenhuma declaração de console global limpo: os drivers registraram zero `pageerror`, mas abortos de rede foram injetados deliberadamente.

## Testes, segurança e recursos

Baseline: **1535 passed, 1 failed, 4 skipped, 2 warnings**, falha de fixture de calendário. Última suíte completa anterior à proteção: **1554 passed, 4 skipped, 2 warnings** em 350,25 s. Proteção e síntese: **53 passed**. A suíte final pós-proteção passou: **1556 passed, 4 skipped, 2 warnings em 438,98 s**, registrada em `full-suite-final-safety.log`, código `1ce380a`.

Benchmarks determinísticos no código final: **Search 34/34, Shopping 59/59, Experience 16/16**. São verificações locais, não ganho independente de pesquisa externa. Avisos conhecidos: depreciações `mss.mss` e timeout do Starlette TestClient. Testes de autenticação, RBAC, CSRF, isolamento, SSRF/redirects, grants, persistência e cancelamento permanecem na suíte, sem remoção de casos.

Limites de rede, páginas, bytes, concorrência e orçamento não foram aumentados indiscriminadamente. O novo holdout ficou mais lento e fez três fetches observados a mais; não se promete redução de latência. Amostra ociosa QA: relay RSS 45.010.944 bytes, agente 3.751.936 bytes, CPU 0% no intervalo de 0,2 s por processo; não é pico, custo de inferência ou comparação causal. Microteste de contexto: 2000 verificações em 0,390106 s, sem baseline equivalente para alegar ganho. Contagem de fetches não inclui todos os redirects/pacotes/downloads binários.

[Auditoria operacional](docs/v5.9.9.2/PC_AGENT_AUDIT.md): um agente legado de produção observado, revisão/jobs/competição não atestados. Nenhum stop/restart foi enviado a ele. Instâncias QA foram encerradas pelo próprio harness e bancos temporários removidos; recibos `qa-cleanup-delivery.json`/`qa-cleanup-safety.json`. Metadados privados, cookies e SQLite não são versionados. A varredura de segredos lê configuração somente para comparação de valores; resultado e escopo em `secret-scan.json`, sem imprimir credenciais.

## Pendências e próximo passo exato

Não liberar como Research Ultra. Usar os quinze casos agora apenas para diagnóstico, congelar outro conjunto antes de otimizar novamente e corrigir a separação entidade/atributos e a detecção de respostas de provedor que ignoram o assunto. Priorizar navegação por links específicos legitimamente descobertos, validar o trecho pedido antes da elegibilidade e repetir comparação externa e inferência pública completa, mantendo negativas/tempo/região/modelo/PDF. Não afrouxar filtros nem contar metadados como leitura para elevar métricas.

Os documentos complementares são [entidades](docs/v5.9.9.2/ENTITY_RESOLUTION.md), [planejamento](docs/v5.9.9.2/QUERY_PLANNING.md) e [recuperação](docs/v5.9.9.2/SOURCE_RECOVERY.md). O [índice de evidências](qa-artifacts/v5992/README.md) identifica rodadas aceitas, falhas históricas e escopo de cada artefato. Arquivos antigos não relacionados de `.playwright-cli` permaneceram fora dos commits desta entrega.
