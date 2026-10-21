# Vexx AI / Júlia Mobile — UX/UI polish

Data: 15/10/2026. Escopo: correções incrementais; sem reescrever o projeto, push ou deploy.

## Estado inicial e concorrência

Baseline iniciado em `2f22e7b`: havia alterações em `tests/test_ai.py`,
`tests/test_research_e2e.py` e novos auxiliares de processos E2E. Foram preservadas.
O checkout recebeu outros commits e edições enquanto este trabalho estava em andamento
(incluindo `34f3c74` e `4524b2f`). Esta sessão não executou commits. Alterações de
quality lab, documentos, benchmarks, unidades e exclusão de scripts auxiliares pertencem
ao trabalho concorrente e não foram revertidas nem atribuídas a esta intervenção.

Baseline: **297 passaram, 1 falhou, 2 ignorados**, em 198,47 s.
A falha foi a ausência de `research_completed` quando o teste já observava estado final.

## Correções realizadas

| Problema observado no código/teste | Correção |
|---|---|
| Replay de resposta já concluída saía como `ai_error` | Agente retorna `ai_done` com o mesmo ID e conteúdo persistido |
| Consultar uma resposta pronta podia ser bloqueado pela cota de nova geração | Idempotência é resolvida antes da cota, mantendo autenticação e bloqueio de conta |
| Mesmo ID podia ser associado à conversa/papel incorretos | Verificação da identidade da mensagem antes do replay/piggyback |
| Threads podiam preparar a mesma mensagem simultaneamente | Preparação serializada no agente e estado `queued` tratado como ocupado |
| Exceção inesperada deixava pedido permanentemente ocupado | Estado de falha persistido, erro explícito no stream e retry disponível |
| Reinício deixava estados `queued/processing` presos | Recuperação no início do processo, preservando o conteúdo parcial |
| EOF depois de alguns deltas deixava resposta em “gerando” | Parcial salvo e estado de falha recuperável, sem sucesso falso |
| `done` vazio era aceito | Validação de conteúdo e ID final antes de marcar resposta sincronizada |
| Deltas repetidos eram concatenados duas vezes | Deduplicação por sequência; lacunas são tratadas como interrupção |
| Trecho final anexado pelo agente reutilizava sequência | Sequência final incrementada a partir do último delta emitido |
| Parser não tolerava CRLF fragmentado | Separação de eventos aceita LF/CRLF e dados em várias linhas |
| Heartbeats eram ignorados pelo watchdog | Recebimento mantém a conexão viva; servidor mede inatividade |
| Parcial só existia na tela | Checkpoints limitados a uma gravação por segundo no IndexedDB e SQLite (`ai_requests`) |
| Cancelamento podia iniciar nova tentativa automaticamente | Resposta interrompida fica disponível para retry manual; fallback recebe AbortSignal |
| Polling reconstruía a resposta durante streaming | Atualização em segundo plano evita substituir a conversa em geração |
| Texto/estado desaparecia ao remontar JDUI | Prosa e componentes ficam em hosts separados; componentes só remontam quando mudam |
| Transação JDUI aguardava outra transação e podia expirar | Leitura e escrita usam o mesmo object store/transação |
| Aparelho sem estado local não buscava estado remoto | GET de estados JDUI ocorre mesmo quando não há nada para publicar |
| Recuperação de placeholders podia perder o dono | Recuperação limitada às mensagens da conta, mantendo os campos originais |
| Troca de chat durante envio podia renomear outro chat | Atualização usa o ID capturado na mensagem; rascunho novo não é apagado |
| Indicadores de geração redundantes | Um status textual no composer; placeholder discreto e métricas técnicas apenas no log |
| Célula vazia de tabela deslocava colunas | Preservação de células vazias e barras escapadas |
| Ênfase e links modificavam código inline | Trechos inline protegidos antes da formatação |
| Referências criavam URLs com sintaxe Markdown | Referências usam o formatador; `[S1]` só vira link se houver URL correspondente |
| Imagem quebrada virava fotografia aleatória | Removido fallback para Picsum; nenhuma imagem substituta inventada |
| HTML do modelo executava JavaScript | Prévia HTML com sandbox sem scripts e CSP; JDUI declarativo continua interativo |
| Zoom do EvidenceGraph só alterava fonte | Zoom ajusta viewBox; filtros em português e nós acessíveis por teclado |
| Progresso inventava denominador 1 ou mostrava `0/0` | Estado sem dados explícito em JDUI e travessão nas métricas ainda vazias |
| Estado final da pesquisa precedia o evento final | Publicação do evento antes do estado final observado por polling |
| Thread de teste de isolamento esperava quantidade fixa de RPCs | Encerramento pela última operação e assert de término, mantendo as verificações de segurança |

O caminho rápido continua enviando texto e ID junto ao pedido de IA, sem aguardar
sincronização completa. O fallback `sem_mensagem` continua sincronizando somente a
mensagem necessária e verificando seu ACK antes da tentativa de compatibilidade.
Isso não promete uma latência específica do provedor.

## Arquivos desta intervenção

- `public/app.js`: fluxo de chat/SSE, renderização, estados JDUI, Markdown e métricas.
- `public/jdui.js`: EvidenceGraph e progresso sem dados.
- `public/index.html`, `public/interface.css`, `public/sw.js`: apresentação, acessibilidade e cache `VEXX-shell-v0.9-stream-polish`.
- `pc_agent.py`, `server.py`, `research_agents.py`: idempotência, recuperação, parciais, timeout e evento final.
- `tests/test_ui_polish.py`: execução do JavaScript real com transporte controlado e testes SQLite.
- `tests/test_frontend_smoke.py`: regressões de Markdown, fontes e sandbox.
- `tests/test_isolamento.py`: encerramento determinístico do agente de teste.
- `tests/test_research_quality_lab.py`: preparação de autenticação determinística; verificações que usavam `out`/`db` movidas de volta ao teste que cria essas variáveis, sem remover assertions.
- `tests/preview_workspace.py`: fixtures explicitamente fictícias, habilitadas por `VEXX_UI_FIXTURES=1` em banco temporário.

## Verificação executada

- 19 testes focados após a primeira correção de streaming; o harness executa nove cenários com bytes fragmentados, sem substituir `runAIRequest` por mock.
- 35 testes focados de streaming, Markdown e JDUI na etapa seguinte.
- 23 testes focados de frontend, JDUI V4.3 e regressões de polish após os ajustes posteriores.
- Node: sintaxe de `app.js` e `jdui.js` verificada.
- Navegador real, servidor FastAPI e agente com SQLite temporário: login, leitura de mensagens, tabela com célula vazia, quiz, filtro e zoom do EvidenceGraph.
- Resposta do quiz e filtro preservados após reload e recebidos em outra origem (`localhost` versus `127.0.0.1`), por sincronização com o agente.
- Layout em 390 × 844 e desktop; largura do documento mobile = 390 px, sem transbordamento horizontal na conversa verificada.
- Nó do EvidenceGraph ativado com Enter. Console inspecionado sem erros nesses fluxos.
- Telas Estudos e Meu PC abertas para inspeção; nenhum comando remoto executado.

### Cobertura JDUI

Registro identificado: **19 componentes**: quiz, checklist, calculator, cards,
diagram, table, form, progress, exam, tabs, accordion, studyplan, flashcards,
studyprogress, lesson, chart, dashboard, compare e evidencegraph.

Foram usados os testes existentes de validação, limites, estado, renderização e
segurança, além das regressões novas. Checklist, tabela, formulário e calculadora
têm testes de interação/remontagem no harness; componentes educacionais e gráficos
têm testes específicos de schema/API. A verificação visual desta rodada foi
concentrada em quiz, tabela e EvidenceGraph; **não equivale a testar manualmente
todas as combinações dos 19 componentes em todos os navegadores**.

## Limitações e pendências

- O preview usa respostas e dados sintéticos identificados como teste. Não possui Hermes conectado; não mede latência de um modelo real.
- O navegador foi redimensionado; não houve teste em aparelho físico nem com teclado virtual Android/iOS.
- Login foi exercitado; não foi criada ou excluída conta real, nem modificada memória real. Revisão de memórias suspeitas exige evidência da origem e confirmação de conteúdo; não foram apagadas automaticamente.
- Não houve ampliação de permissões de controle remoto, mudança na extensão Júlia ou no Fajulto Studio.
- Falhas de rede não retomam o fluxo de tokens pelo último evento: preservam o parcial e permitem retry com o mesmo ID; respostas já concluídas são recuperadas por replay/sync.
- O lock de preparação cobre as threads de um processo de agente. Execução simultânea de múltiplos agentes sobre o mesmo SQLite não foi validada.
- A suíte roda sobre um checkout que também está recebendo alterações externas. Resultados devem ser associados à execução registrada, sem atribuir toda alteração pendente a esta sessão.

## Resultado final da suíte

Comando: `..\.venv\Scripts\python.exe -m pytest -q -rs`

**328 passaram, 2 ignorados, 2 avisos, nenhuma falha**, em **189,05 s**.

- Ignorados: verificação semântica LLM em `test_evidence_benchmarks.py` e inferência
  Hermes em `test_research_quality.py`, ambos sem provedor disponível.
- Avisos: depreciação de `mss.mss` e do parâmetro `timeout` em Starlette TestClient.
- `git diff --check` não encontrou erros de whitespace.

Antes desta execução, a suíte encontrou duas falhas em testes adicionados pelo
trabalho concorrente de quality lab: preparação de credenciais via `setdefault`
herdava outro usuário, e assertions de um teste tinham sido deslocadas para outro.
As causas foram corrigidas mantendo o conteúdo das verificações. O teste Node de
EvidenceGraph também passou com o DOM de teste atualizado para representar `dataset`.

Não houve push/deploy. O ambiente descartável de navegador/servidor/agente foi encerrado.
Arquivos e testes acrescentados por outro processo após a coleta desta suíte não
podem ser considerados cobertos por essa contagem.


## Complemento de 20/10/2026 — correções autorizadas da auditoria

Foram implementadas correções de sincronização, histórico paginado, exclusão durável,
conflitos de IDs, estados JDUI, JSON persistente, segurança SVG/sessões/DNS e limites SSE.
Relatório detalhado: [RELATORIO_CORRECOES_AUDITORIA_2026-10-20.md](RELATORIO_CORRECOES_AUDITORIA_2026-10-20.md).

Validação final: **941 passaram, 4 pulados e 2 avisos**. Chrome local verificou
composer POST, persistência, logout/replay, limpeza de cache, SVG e navegação em
320/390/1280 px. Não equivale a teste em aparelho físico ou latência de LLM real.
Sem push/deploy. Dados e credenciais reais preservados. Riscos operacionais restantes
e próximo passo estão documentados no relatório detalhado.
