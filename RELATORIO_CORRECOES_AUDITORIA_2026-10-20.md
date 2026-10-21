# Vexx AI — correções da auditoria de 20/10/2026

## Escopo e preservação

Correções incrementais autorizadas pelo usuário após a auditoria. Base Git local: `607ff1f`.
Sem push, deploy, alteração de credenciais ou exclusão de dados reais. Testes de escrita,
exclusão e replay de sessão usaram bancos temporários e a conta descartável `preview`.
Rebrand, identidade Lucas, pesquisa, memória, contas, JDUI e permissões de controle remoto preservados.

Já havia alterações em `research_agents.py`, o módulo não rastreado `media_evidence.py`
e artefatos de publicação/QA. Foram preservados. Este relatório atribui a esta rodada
somente os ajustes descritos abaixo; não declara toda a evolução de mídia pronta para publicar.
O catálogo 3D do commit `9519df6` já constava em `origin/main` na inspeção inicial.

## Correções por achado

| Achado | Correção implementada | Verificação e limites |
|---|---|---|
| A01 — SVG pode inserir HTML/redirecionar | SVG passa a ser imagem `data:image/svg+xml`, fora do DOM inline. CSS mantém tamanho responsivo. | Chrome renderizou SVG válido; payload com `meta refresh` e script ficou isolado, sem navegação, execução ou requisição externa. |
| A02 — revogação desativada após falhas | Falha na consulta retorna 503 e mantém futuras verificações. Cache vencido com agente offline também recusa acesso protegido. | Duas falhas seguidas e terceira consulta revogada: 503, 503, 401. Cache ainda tem TTL de 60 s para revogações feitas fora deste relay. |
| A03 — somente 500 revogações | Consulta retorna todas as sessões revogadas ainda não expiradas. | 502 registros recuperados, incluindo o mais antigo e SID legado. |
| A04 — histórico global limitado a 200 | Filtro por conversa antes do LIMIT; cursor `(created_at,id)` e download paginado. Frontend grava cada página, sem acumular todas as mensagens numa lista. | 450 mensagens sem lacunas/duplicações, conversa antiga isolada, conta distinta e cursores inválidos. A interface ainda usa `getAll()` em outros caminhos. |
| A05 — conversa apagada volta na sincronização | Tombstone consultado em ingestão, preparação da IA e persistência da resposta/pedido; gravações usam transação de escrita. Exclusão explícita passa pelo mesmo armazenamento de organização. | Mensagem antiga, metadado com data futura e resposta tardia não recriam chat excluído; outra conta preservada. Sem stress prolongado de múltiplos dispositivos físicos. |
| A06 — JSON cortado torna pesquisa ilegível | Serializador limitado rejeita excesso antes de escrever, preservando o registro válido. Orquestrador registra falha usando último checkpoint válido. | Roundtrip, rejeição de 61 mil caracteres e encerramento recuperável do job testados. Registros antigos já corrompidos não foram alterados automaticamente. |
| A07 — conteúdo/localização na URL SSE | Frontend envia POST JSON com CSRF; rota POST reutiliza o streaming. Valor `memory=0` permanece desativado. | Composer real no Chrome e testes de CSRF/transporte. GET legado mantido por compatibilidade; clientes antigos ainda devem ser atualizados. Logs antigos não foram apagados. |
| A08 — JDUI antigo sobrescreve novo | Timestamp normalizado e comparação determinística `(updated_at,state)` no SQLite, mantendo isolamento por dono. | Estado mais antigo recusado; empate converge; outra conta não sobrescreve chave. |
| A09 — apenas últimos 300 estados enviados/500 listados | Upload em lotes de 100 e download com cursor de 200 itens, com detecção de cursor repetido. | 505 estados recuperados em páginas sem perda. |
| A10 — ACK de ID com conteúdo diferente | ACK somente para inserção ou repetição idêntica; preparação da IA rejeita texto conflitante antes de replay/geração. | Reenvio idêntico aceito; texto, conversa e papel conflitantes recusados. |
| A11 — limpar cache deixa dados | Limpeza inclui mensagens, sessões, salvos, UI e meta; reinicia caches em memória e invalida sincronizações antigas por geração/conta. | Cinco stores vazios no Chrome após limpeza descartável. |
| A12 — modelo 3D de variante incorreta | Xbox diferente de Series S usa console explicitamente genérico; motor elétrico não cai no V8. | Regressões de resolução de catálogo. Não foram adicionados modelos detalhados novos. |
| A13 — mídia da pesquisa não reaparece | `midia` incluída na gravação e recuperação dos jobs. | Roundtrip SQLite; preservado o trabalho de mídia que já existia no checkout. |
| A14 — rótulos antigos | Exportação/compartilhamento identifica Lucas; opção de aprendizado usa “Aprender automaticamente”. | Smoke e inspeção da captura de ajustes em 390 px. |
| A15 — logout de SID legado não revoga | Revogação faz upsert durável do SID desconhecido. Logout só remove cookie após confirmação do PC; falha é apresentada ao usuário. | Reabertura do SQLite e Chrome: logout 200, replay do cookie descartável retorna 401. Logout offline fica pendente de reconexão. |

## Robustez adicional

- **R01:** conexão de pesquisa usa diretamente os endereços públicos resolvidos/validados,
  preservando o hostname original no TLS/SNI. Redirects continuam validados. Proxies de
  ambiente não são usados nesse transporte, para não contornar a validação de destino.
  Testes controlados de DNS alternando público/loopback e HTTPS com verificação de hostname.
  Não houve ataque contra um host privado real. Instalações dependentes de proxy precisam
  de configuração segura específica antes de adotar esse transporte.
- **R02:** limite de oito streams no relay/agente e 256 eventos por fila. Saturação gera erro
  explícito/cancelamento ou preserva resultado terminal; desconexão consegue notificar fila cheia.
  Testes de limite, fila cheia na desconexão, cancelamento e limpeza. Não é benchmark de carga.
- Guardas de conta/geração impedem que respostas de sincronização antiga sejam aplicadas
  depois de trocar de conta ou limpar o cache. Service worker recebeu nova versão.

## Arquivos

Backend: `server.py`, `pc_agent.py`, `julia_auth.py`, `workspace_store.py`, `json_store.py` (novo),
`research.py`, `research_agents.py`, `model3d_catalog.py`.

Frontend: `public/app.js`, `public/workspace.js`, `public/index.html`, `public/interface.css`, `public/sw.js`.

Regressões: `tests/test_audit_fixes.py` (novo), `tests/test_frontend_smoke.py`, `tests/test_jdui.py`,
`tests/test_research_agents.py`, `tests/test_research_recovery.py`.
Os testes locais de HTTP agora autorizam somente o socket do próprio servidor temporário,
pois a proteção de DNS passou a existir também no momento da conexão. Nenhum teste foi removido.

## Validação

- Baseline da auditoria: **929 passaram, 4 pulados**.
- Primeira suíte desta rodada: **937 passaram, 3 falharam, 4 pulados**. Falhas corrigidas:
  expectativa do novo cursor JDUI e duas fixtures loopback que precisavam explicitar o transporte local.
- Após esses ajustes e o caso de limite JSON: **15 testes focados passaram**.
- Suíte final: **941 passaram, 4 pulados, 2 avisos, em 214,70 s**, sem falhas.
  Os quatro pulados dependem de Hermes/verificação semântica ou busca comercial externa
  indisponível/bloqueada. Avisos: depreciação de `mss.mss` e `timeout` no TestClient.
  Log: `qa-artifacts/correcoes-20261020/final-suite.txt`.
- `node --check` em app/workspace, `pip check` e `git diff --check`: aprovados.
- Chrome local: login, clique real no drawer em 320/390/1280 px, documentos/estudos/ajustes
  sem overflow; isolamento SVG; POST SSE para horário, persistência de usuário/resposta;
  cache limpo e replay de sessão revogada. Evidência em `browser-check.json` e capturas PNG.
- O ambiente de preview usa Hermes indisponível deliberadamente; a resposta de horário é
  determinística. Isso **não mede latência nem qualidade de um LLM real**.

## Pendências e próximo passo

R03–R08 não estão declarados resolvidos: documentos ainda podem ocupar o loop RPC;
listas grandes precisam de benchmark/índices; dependências ainda precisam de política de lock;
integrações externas dependem de disponibilidade; restauração completa/disco cheio precisam
de ensaio; mídia remota ainda demanda decisão de privacidade. R04/R05 tiveram apenas a
melhoria incremental de paginação e atualização do service worker.

Próximo passo técnico: medir um resumo de documento em paralelo com `/api/sync` em ambiente
descartável; a partir do bloqueio medido, mover somente as operações pesadas de documentos
para fila limitada com conexão SQLite própria, testando cancelamento, isolamento e ACK.
Depois medir histórico com 10 mil mensagens e testar Android/iOS reais. Deploy futuro deve
atualizar frontend, relay e agente em conjunto; esta rodada não foi publicada.
