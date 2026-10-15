# Relatório Júlia Mobile 4.8 — Deep Research Pro

## 1. Resultado

V4.8 foi implementada sobre o Orchestrator existente, sem criar papéis de
agente. As funcionalidades determinísticas e documentais foram integradas;
inferência semântica real continua explicitamente bloqueada enquanto o
provedor Hermes não estiver disponível.

## 2. Funcionalidades entregues

- **Documentos:** extração delimitada para formatos existentes e JSON,
  proveniência/localização, indexação FTS5 com fallback lexical,
  comparação que diferencia ausência comprovada de não localização e
  exclusão/indexação limitadas ao proprietário.
- **Pesquisa acadêmica:** consultas opcionais a OpenAlex e Crossref no
  Orchestrator já existente; resultados são metadados/resumos, não leitura
  alegada de artigos completos.
- **Análise determinística:** CSV, TSV, JSON tabular e operações estatísticas
  limitadas, com unidades e proveniência preservadas.
- **Fluxo conversacional e JDUI:** comandos explícitos para gráfico/comparação
  verificam proprietário, conversa, arquivo original e hash do conteúdo
  extraído. Só resultados reais aprovados pela análise e pelo adaptador de
  visualização são persistidos e emitidos como JDUI; dados ou séries não são
  sintetizados.
- **Pesquisa contínua:** hipóteses, checkpoints, replanejamento limitado,
  eventos/SSE, resultados e relatórios owner/job-scoped com citações validadas.
- **Documentação:** guias de documentos, recuperação, pesquisa acadêmica,
  análise de dados, hipóteses, checkpoints, relatórios e arquitetura V4.8.

## 3. Limitações mantidas explícitas

- Inferência Hermes, síntese semântica e avaliação semântica dependem de um
  provedor de inferência real; não foram substituídas por respostas simuladas.
- PDFs escaneados sem texto extraível não têm OCR. Relatórios são Markdown;
  exportação PDF não foi implementada.
- FTS5/recuperação lexical não é busca semântica. Busca sem resultado não prova
  ausência.
- Resultados acadêmicos podem conter apenas metadados ou resumos e não são
  tratados como artigos lidos ou como verificação de verdade.
- O benchmark sintético de 10.000 linhas agrupadas em 10 categorias mediu
  576,20 ms e 4,24 MiB de pico de alocação Python rastreada no ambiente local
  Windows/Python 3.14. Inclui construção da entrada e não é garantia de
  desempenho em hardware de produção.

## 4. Validação

- Baseline anterior às mudanças: **241 passed, 2 skipped, 3 warnings**.
- Testes focados V4.8 (documentos, isolamento, JDUI, Orchestrator, pesquisa
  acadêmica, análise, visualizações, hipóteses, continuidade e relatórios):
  **96 passed, 2 warnings**.
- E2Es reais executados separadamente: `test_e2e_ai_completo_com_processos_reais`
  **1 passed**; `test_e2e_pesquisa_com_eventos_reais` **1 passed**.
- Duas execuções completas registraram, respectivamente, **296 passed,
  2 skipped, 1 failed** e **295 passed, 2 skipped, 2 failed**. As falhas
  ocorreram no teardown Windows de `TemporaryDirectory`, quando arquivos
  `relay.log`/`agent.log` ainda estavam bloqueados (`PermissionError`), depois
  do fluxo E2E; cada E2E passou isoladamente. Portanto, a suíte global não é
  declarada totalmente verde.
- `git diff --check`: sem erros de whitespace no fechamento da validação.

## 5. Estado de entrega

Implementação local e documentação concluídas. Nenhum commit, push ou deploy
foi realizado. A falha intermitente de limpeza dos E2Es no Windows permanece
registrada, sem ser mascarada como sucesso funcional.
