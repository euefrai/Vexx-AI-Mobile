# Júlia Mobile — Roadmap 4.x

Princípios: conversa primeiro; sem IDE; sem Supabase/Firebase; sem pagos
obrigatórios; offline-first; nada simulado; cada versão com testes.

## V4.0 — FUNDAÇÃO (em execução)
- [ ] Fundação multiusuário: `owner_id`, ownership no backend, testes de isolamento.
- [ ] Chat profissional: arquivar, fixar, exportar (.md/.json), regenerar,
      continuar resposta truncada, busca no histórico. Sem botões decorativos.
- [ ] Contexto com orçamento + grounding (origens rotuladas, anti-invenção).
- [ ] Suíte de avaliação conversacional (8 testes do spec).
- [ ] Relatório V4.0 honesto (FUNCIONAL/PARCIAL/AUSENTE/BLOQUEADO).

## V4.1 — MEMÓRIA INTELIGENTE
- Tipos: trabalho/episódica/semântica/temporal/assunto (+social com autorização).
- Pipeline: identificar → classificar → pedir autorização quando sensível →
  normalizar → deduzir → persistir com proveniência/versão → recuperar → corrigir.
- Comandos: ver, corrigir, exportar, desativar, apagar. Temporais sem ano
  inventado. Testes de contradição e de "não inventar memória".

## V4.2 — EDUCAÇÃO
- Planos de estudo (assunto/objetivo/data/tempo/nível), checklist com progresso,
  flashcards + revisão espaçada, simulados, correção determinística do objetivo,
  histórico de desempenho. JDUI: plano, prova, flashcard, painel.

## V4.3 — JDUI AVANÇADO
- Atualizar interface sem perder estado; `chart` SVG a partir de dados reais
  (nunca série inventada); dashboards; `since` incremental no ui-state.

## V4.4 — PESQUISA E CONFIABILIDADE ✅ (2026-10-16)

- Inference reliability: códigos 402/422, `tentar_modelos` (preferencial +
  fallbacks explícitos, backoff, para em auth, erro original com 1 modelo),
  `chat_stream_fb` (troca só antes do 1º delta), circuit breaker por base,
  `JULIA_AI_FALLBACKS`. E2E determinístico. Hermes real: inferência bloqueada
  no provedor (ver JULIA_INFERENCE_RELIABILITY.md); quota zero em testes.

- Research Engine (`research.py`): buscar DDG (html+lite, parsers 2026) →
  recuperar páginas → extrair → divergências → runs persistidos; SSRF
  bloqueado em cada redirect; teto 2 MB/10 s/só-texto; cache SQLite por dono;
  citações [S1] validadas; grounding com wrapper anti-instrução; memória só
  como termos de tópico; transforms determinísticos (gráfico/tabela/dashboard/
  cards) sobre runs; reuso "com essas fontes". Sem frontend novo (links
  markdown). Status "pesquisando…" ao vivo: AUSENTE (stream é canônico).
  Docs + RELATORIO_JULIA_4.4.md. Suíte: ver relatório.

## V4.5 — DEEP RESEARCH AGENTS & LIVE RESEARCH ✅ (2026-10-16)
- `research_agents.py`: orchestrator, planner, 7 papéis, evidence store,
  verificação determinística, síntese extrativa + auditoria.
- Jobs em background (1/dono, teto 2), 5 rotas relay, painel live Minimal
  Premium com polling, comandos de memória sem LLM, fence de evidências.
- Quality Lab com métricas + casos; LLM-real = skip BLOQUEADO.
- Relatório em RELATORIO_JULIA_4.5.md.



## V4.6 — EVIDENCE INTELLIGENCE ✅ (2026-10-16)
- Grafo de evidências (SQLite, IDs estáveis), claims v2 com condições, verificação 2.0 com método registrado.
- Independência de fontes, contradições por dimensão, auditor 2.0, 16 benchmarks congelados.
- Componente evidencegraph + memória do grafo (5 perguntas sem LLM). Verificação semântica: BLOQUEADA.
- Relatório em RELATORIO_JULIA_4.6.md.

## V4.7 — LIVE RESEARCH 2.0 + AGENTES INTERATIVOS ✅ (2026-10-16)
- SSE push real + polling fallback; painel com fases, filtros, evidências expansíveis.
- Intervenção estruturada (6 ops), pausa/retomada, follow-ups adaptativos, checkpoints 2.0.
- Perfis futuros (professora/pesquisadora/…) entram aqui quando houver LLM (dependem de inferência).
- Relatório em RELATORIO_JULIA_4.7.md (esta entrega cobre V4.6.1 + V4.7).

## V4.8 — DEEP RESEARCH PRO (implementada; limitações registradas)
- Inteligência documental: extração delimitada, proveniência, chunks com localização,
  índice FTS5 com fallback lexical, comparação entre documentos e exclusão por dono.
- Pesquisa acadêmica opcional por OpenAlex/Crossref, com metadados atribuídos à fonte;
  não afirma leitura de texto integral quando só há resumo.
- Análise estruturada determinística, hipóteses/checkpoints owner-scoped e relatórios
  Markdown com citações verificadas; JDUI é gerada apenas de dados reais.
- Orchestrator, SSE, contexto/memória delimitados, relatórios persistidos e comando
  conversacional para análise tabular integrados. Hermes sem inferência real, OCR e
  exportação PDF permanecem BLOQUEADOS/AUSENTES; suíte global tem falha intermitente
  de limpeza de logs de E2E no Windows. Ver [RELATORIO_JULIA_4.8.md](../RELATORIO_JULIA_4.8.md).

## V4.9 — RESEARCH QUALITY LAB 3.0 (parcial; fundação reproduzível)
- Dataset local sintético versionado + recuperação real do pipeline documental;
  métricas P@K/Recall@K/MRR/NDCG, citações por etapa e checkpoints 10/25/50.
- Hardening dos E2Es Windows; três execuções passaram com 312 testes cada,
  excluindo um teste afetado por edição local não commitada de UI. Avaliação
  factual/citações semântica com revisão independente, dashboard administrativo,
  qualidade web/modos e medições de CPU/RAM/tokens continuam pendentes.
- Hermes real permanece BLOQUEADO; ver `RELATORIO_JULIA_4.9.md`.

## V4.9.1 - SHOPPING INTELLIGENCE (entregue; ver RELATORIO_JULIA_4.9.1.md)
- Pesquisa visual de produtos no chat: intencao, criterios (orcamento BRL,
  marcas, RAM fisica vs virtual), busca DDG dupla, extracao JSON-LD/OpenGraph,
  dedupe multi-loja, filtros com motivos, comparacao deterministica e
  persistencia por dono (preco guardado = historico com verificado_em).
- JDUI real: productcard/productgrid/productcompare/productdetails/
  productgallery (fotos lazy, ordenar, comparar, ofertas, fontes).
- Regras: nunca inventar produto/preco/imagem/avaliacao; sem dado -> "Preco
  nao confirmado"; sem "menor preco da internet". E2E ao vivo pendente de
  provedor sem bot-wall.

## V5.0 - ADVANCED MEMORY & LUCCAS TRAWMAN IDENTITY (entregue; ver RELATORIO_JULIA_5.0.md)
- Identidade Lucas deterministica (nome, nome completo, natureza IA,
  correcao educada) nos fluxos stream e completo, sem LLM.
- Memoria com confirmacao visivel no chat, higiene (no-op, historico,
  anti-exemplo), orcamento de 1500 chars, Project Memory e continuidade
  deterministica (projetos, onde paramos, nota de corte, restart).

## V5.1 - INTENT & UNDERSTANDING ENGINE (entregue; ver RELATORIO_JULIA_5.1.md)
- Intent Engine 2.0 (intent.py): estrutura validada, 2+ evidencias p/
  ferramenta externa, follow-ups com contexto, formato como modificador.
- Instruction following: proibicoes/obrigatorias/formato, skip de pesquisa,
  validador deterministico + recuperacao segura (usados).
- Benchmark versionado: 124 casos PT-BR, 100% acuracia, roteamento 124x89
  vs legado.

## V5.2 - ADVANCED VISUAL JDUI (entregue; ver RELATORIO_JULIA_5.2.md)
- 3 novos componentes (sources, video link-card, roadmap so-leitura),
  tabela com CSV/teclado/paginacao, Visual Response Engine deterministico
  (tabela->grafico, pesquisa->visual, fontes com status), QA visual real
  em Chrome headless. Sem 3D.

## V5.3 — 3D Engine Foundation
- JDUI model3d validado, quatro primitivas, combinações limitadas e GLB local CC0.
- Three.js sob demanda, controles reais, referências conversacionais isoladas,
  fallback 2D, um contexto ativo e descarte explícito. Render serve apenas assets.
- Medições e limites: [JULIA_3D_PERFORMANCE.md](JULIA_3D_PERFORMANCE.md).
- Entrega e QA: [RELATORIO_JULIA_5.3.md](../RELATORIO_JULIA_5.3.md).

## V5.4 — Interactive 3D Intelligence
- Partes selecionáveis, operações validadas, etapas educativas e três cenas procedurais.
- Estado local imediato nos comandos, snapshots isolados e reuso de canvas.
- Contrato: [JULIA_3D_INTERACTIONS.md](JULIA_3D_INTERACTIONS.md); cenas: [JULIA_3D_EDUCATION.md](JULIA_3D_EDUCATION.md).
- Evidências, testes e limites: [RELATORIO_JULIA_5.4.md](../RELATORIO_JULIA_5.4.md).

## V5.5 — RESEARCH INTELLIGENCE 3.0 (em entrega; commits locais)
- Busca orquestrada multi-provedor real (11 provedores API/feed oficial, sem
  chave e sem bypass): estados honestos (ok/parcial/sem_resultados/
  sem_correspondencia/bloqueado/rede/indisponivel), dedupe canônico,
  lacunas do pedido com recuperação limitada a uma rodada.
- Leitura de páginas determinística (`web_extract.py`) com trafilatura/
  extruct opcionais; ranqueamento por correspondência real.
- Shopping verificado: link/imagem com veredito honesto (`source_check.py`),
  etapa web por último na cadeia, alternativas próximas com diferenças
  explícitas, `url_item` e selo no card do JDUI.
- Agentes: provedor "web" por último, lacunas de busca viram novas frentes
  (busca+ler+analisar, uma rodada), divergência com conversão de unidades,
  fontes desatualizadas informativas.
- Docs: [JULIA_RESEARCH_INTELLIGENCE_3.md](JULIA_RESEARCH_INTELLIGENCE_3.md),
  [JULIA_ADAPTIVE_SEARCH.md](JULIA_ADAPTIVE_SEARCH.md),
  [JULIA_SOURCE_VALIDATION.md](JULIA_SOURCE_VALIDATION.md),
  [V5_5_PROGRESS.md](V5_5_PROGRESS.md) e
  [RELATORIO_JULIA_5.5.md](../RELATORIO_JULIA_5.5.md).

## Integração pontual — Dados atuais (17/10/2026)
- Clima/previsão Open-Meteo, relógio por fuso/cidade e notícias via feeds reais, antes do LLM.
- Localização autorizada, continuidade da pergunta de cidade, cache, fontes, datas e fallback honesto.
- QA Chrome real e regressão: [RELATORIO_DADOS_ATUAIS.md](../RELATORIO_DADOS_ATUAIS.md).
- Uso, custo e limites: [DADOS_ATUAIS.md](DADOS_ATUAIS.md).

## V5.6 — 3D Visual Polish + Smart Assembly Foundation + Model Generation (entregue; commits locais)
- Polimento visual: sombras suaves estáticas (PCF 512), contornos de aresta,
  tone mapping ACES e palco com gradiente; motor Three rebuildado
  (146.978 bytes gzip, teste < 150.000).
- Interação: grupos internos/externos, “mostre como isso se conecta”,
  “explique como funciona”, chips de fidelidade e fonte controlada nos detalhes.
- Geração honesta: catálogo local com 14 cenas aproximadas, templates
  paramétricos e pesquisa pública (rótulo `aproximado`/`conceitual`); sem
  template ou sem rede → limitação honesta, nunca geometria inventada.
- Fundações de montagem: `role`/`group`/`order` por peça, relações `related`,
  etapas com vista/separado e modo explodido.
- QA em Chrome real: `tools/3d/qa-v56.cjs` (+ regressão `qa-v54.cjs`),
  desempenho medido em `tools/3d/qa-perf.cjs`.
- Docs: [JULIA_3D_VISUAL_POLISH.md](JULIA_3D_VISUAL_POLISH.md),
  [JULIA_3D_MODEL_GENERATION.md](JULIA_3D_MODEL_GENERATION.md),
  [JULIA_3D_ASSEMBLY_FOUNDATION.md](JULIA_3D_ASSEMBLY_FOUNDATION.md),
  [V5_6_PROGRESS.md](V5_6_PROGRESS.md) e
  [RELATORIO_JULIA_5.6.md](../RELATORIO_JULIA_5.6.md).

## V5.7 — RESEARCH ACCURACY & INTELLIGENT RESULTS (em entrega; commits locais)
- Orquestrador: reformulação conservadora de pergunta (`consulta_conteudo`),
  retry na mesma fonte, correspondência honesta (`< 0.5` declara enxuta e
  dispara recuperação), republicações (Jaccard ≥ 0.9, ≥ 4 termos) com
  registro em descartes — nada é apagado.
- Leitura: trecho usado nunca vem de referências/bibliografia
  (`Consultado em`/`Cópia arquivada`/ISBN/doi/`«»`/`↑`).
- Shopping/validação: marca obrigatória (alternativas explícitas), specs
  pareadas (8GB 512GB → RAM 8 + armazenamento 512), `url_item` como link do
  item, selo de imagem honesto no card (parcial/não verificada/reprovada).
- JDUI: autolink com rótulo curto (`rotuloUrl`), bloco "Fontes:" anexado por
  estrutura (não por substring), cartões de fonte clicáveis.
- Benchmark independente: `benchmarks/pesquisa_v57_v1.json` +
  `tools/bench_pesquisa_v57.py` (27/27 offline; `--real` grava sonda),
  artefatos em `qa-artifacts/v57/`.
- Docs: [JULIA_RESEARCH_ACCURACY.md](JULIA_RESEARCH_ACCURACY.md),
  [JULIA_SOURCE_AND_IMAGE_VALIDATION.md](JULIA_SOURCE_AND_IMAGE_VALIDATION.md),
  [JULIA_RESEARCH_RESULTS_JDUI.md](JULIA_RESEARCH_RESULTS_JDUI.md),
  [V5_7_PROGRESS.md](V5_7_PROGRESS.md) e
  [RELATORIO_JULIA_5.7.md](../RELATORIO_JULIA_5.7.md).

## V5.7+ — 3D: evolução possível (sem data, sem trabalho iniciado)
- Tutorial de montagem guiado por etapas, com travas por peça e instruções.
- Ensaio em Android/iOS físicos e leitor de tela real (pendências de medição).
- Novos GLB originais autorizados e refinamentos visuais leves, se houver custo
  justificado (texturas/HDR/post ficam fora até reavaliação de desempenho).

## COMUNIDADE/MULTI-CONTA (adiada, sem versão definida)
- Cadastro, isolamento total, compartilhamento explícito (prompts, quizzes,
  interfaces), biblioteca e moderação. Continua adiada até autorização e
  conclusão dos requisitos de isolamento.

## Explicitamente FORA
- Fórmulas KaTeX (sem parser próprio confiável; reavaliar com lib leve).
- Edição in-place de mensagem e ramificação (custo alto, valor baixo p/ V4.0).
- Compartilhar respostas p/ link público (exige backend persistente — V4.6).
