# VEXX AI V5.9.8 — Autonomous Deep Research

## Resultado e publicação

Implementado em worktree isolada `vexx-v598-dev`, branch `codex/v598-autonomous-research`, base `0814864e0e20bcb94f22a0b4fe861b205c15ed7c`. Commits funcionais locais: `c7f414c`, `fc46fc8`, `5ea716d`. **Sem push, deploy ou restart do Render.** O checkout de produção e seus relatórios pendentes foram preservados.

A atualização do PC Agent está **BLOCKED_NO_GRACEFUL_SHUTDOWN**. PID 25924 usa pythonw sem console e não oferece canal de parada graciosa. Não foi encerrado à força; continua rodando o código carregado antes da V597. SHA em disco/relay não comprova versão carregada. Banco real e backup SQLite passaram em quick_check. Relatório operacional separado em RELATORIO_PC_AGENT_V597_RUNTIME.md.

## Bugs reais e alterações

1. Plano científico gastava orçamento com frentes genéricas antes de ler os dados necessários. Usa duas consultas curtas sobre o assunto, conserva roteamento científico e reserva replanejamento para lacunas observadas.
2. Evidência descoberta podia contar como ganho de leitura e enciclopédia como cobertura de comparação científica. Agora há distinção entre descoberta, resumo, documento lido e publicação original identificada.
3. Seções realmente extraídas eram perdidas em leitores/call sites. Métodos, resultados, condições e limitações preservam proveniência; dois estudos independentes são exigidos quando há comparação.
4. Controlador antes genérico passa a usar lacunas estruturadas com IDs, consultas específicas, tentativas e orçamento. Não executa código do modelo, não inventa URLs nem dados. Mantém cancelamento, checkpoints e filtros de segurança.
5. Wh/kg e Wh/L, capacidade específica e pressão podiam ser confundidos na verificação quantitativa. Dimensões e unidades agora são distintas.
6. Notícias municipais retornaram manchetes nacionais no teste real. Filtro usa cidade, região e janela do pedido em provedor e RSS; sem correspondência, responde ausência de dados. Comparação temporal foi corrigida para meia-noite UTC/fuso local.
7. Pedidos explícitos de documentação e imagens podiam virar promessa do modelo ou links sem galeria; passam ao workflow de pesquisa já existente. Modo profundo explícito era descartado e agora é preservado. Isso não equivale a aprovação externa do conteúdo gerado.
8. Histórico restaurado reanexava job concluído e mostrava barra/cancelamento antigos. Consulta estado terminal, verifica usuário/época/conversa e limita cache; mensagens têm ação Ver pesquisa.
9. Inserção do bloco de lacunas deslocava chaves persistentes de componentes. Chaves por tipo, com fallback legado, preservam o estado JDUI.
10. Rodada externa revelou JSONLimitError com 66.681 caracteres no resumo: trechos eram duplicados por afirmação. Compactação sob pressão gravou 33.921 caracteres no replay das mesmas evidências, retendo 12 afirmações e todos os IDs; evidências originais não são removidas.

Durante desenvolvimento houve uma regressão de import sombreado e uma variável usada antes da atribuição; corrigidas, com logs de falha preservados. Nenhum teste foi eliminado ou relaxado para esconder falhas.

## Arquivos

Backend: research_gaps.py (novo), research_agents.py, research_synthesis.py, units.py, search_verticals.py, live_data.py, pc_agent.py, research_view.py.

Frontend: public/app.js e public/jdui.js. Harness e contratos: tools/preview_research_v598.py, tools/verify_research_ui_v598.cjs. Avaliação controlada: tools/bench_autonomous_v598.py, benchmarks/autonomous_research_v598.json. Regressões: tests/test_autonomous_research_v598.py.

Documentação complementar: docs/v5.9.8/GAP_INTELLIGENCE.md, RESEARCH_BENCHMARK.md, JDUI_RESULTS.md, PROGRESS.md. Artefatos: qa-artifacts/v598/operational e development. Arquivos de banco real, backup e credenciais ficam fora do Git.

## Verificação executada

- Baseline publicado isolado: **1385 passed, 4 skipped, 2 warnings**.
- Rodada completa antes do último ajuste de armazenamento: **1408 passed, 4 skipped, 2 warnings**.
- Suíte completa final: **1409 passed, 4 skipped, 2 warnings em 444,30 s**, log development/final-storage-pytest.log.
- Regressões V598 finais: **24 passed**. Replay do volume externo: 7 evidências, 12 afirmações, todos os IDs preservados.
- Avisos existentes observados: depreciação de mss.mss no teste remoto e timeout do TestClient/Starlette. Não foram silenciados; não alterei controle remoto para corrigir aviso fora do escopo.
- Congelados: Search **34/34**, Shopping **59/59**, Experience **16/16**. Contratos frontend V597 e V598: **4 + 4**, além de sintaxe JavaScript.
- Quality Lab v1: P@5 **0,266667**, recall/MRR/nDCG **1**, duplicatas **0**; métricas limitadas ao corpus.
- Antes/depois controlado: **2 → 4 fontes lidas**, **0 → 1 replanejamento útil**, **0 duplicatas**; **0,843 → 1,908 s**. Não é ganho de velocidade ou prova de precisão na internet.
- Chrome real no harness: 1280/390/320 px e zoom CSS 200% sem overflow; tabela rolável em 320; persistência/isolamento IndexedDB; download real CSV; cinco imagens carregadas; modal/Escape; console final sem erros/avisos. Harness usa replay/fixture identificado, não sessão autenticada V598 ou celular físico.
- Produção autenticada no runtime antigo: seis perguntas em conversa nova e reload com 12 mensagens persistidas. Saudação PASS; docs, ciência, imagens e produtos PARTIAL; notícias municipais FAIL. Sem alterar histórico anterior ou extrair credenciais.
- Um ensaio gratuito do modelo: HTTP 200/SSE, zero chunks públicos sob orçamento 160, finish length. **BUDGET_LIMITED**; sem aprovação de síntese e sem concluir indisponibilidade geral.
- Doze categorias externas em SQLite temporário; manifesto aponta à rodada disponível por caso. Bloqueios foram respeitados. Resultados vazios e falhas históricas permanecem registrados. A última rodada de ciência não confirmou fontes originais; síntese científica real segue sem validação.
- Verificação de segredos: 157 caminhos examinados inicialmente e 135 arquivos da entrega em segunda passagem, zero correspondências; valores não foram emitidos. Diff de código sem erro de whitespace. Servidor de QA e Chrome temporários encerrados.

## Limitações e próximo passo

**Não está demonstrado nível Perplexity nem pesquisa científica completa em produção.** Lacunas extraídas não são suporte científico aprovado. Rede, fontes originais e conteúdo público do modelo continuam sendo gargalos reais. Não relaxei filtros para produzir resultados aparentemente melhores.

Próximo passo operacional: encerrar graciosamente o mecanismo que iniciou o PC Agent antigo ou usar reinício normal autorizado do ambiente; atualizar para a versão publicada e repetir os seis casos autenticados. Só depois avaliar publicação da V598, ainda local, e executar ciência com textos originais e inferência pública suficiente. Não usar kill como atalho.
