# VEXX AI V5.9.8.1 — entrega local e validação operacional

Data: 24/10/2026. Worktree: `vexx-v598-dev`, branch `codex/v598-autonomous-research`. Sem push, deploy, restart do Render/Windows ou mudanças em Studio, VERY, extensão e motor 3D.

## Resultado

- Havia duas cópias de código, mas apenas um PC Agent de produção ativo no inventário inicial. Integrações legítimas foram preservadas.
- Backend publicado V597 reiniciado com backup e rollback preparados. A primeira transição precisou da parada legada do supervisor; a atualização final do wrapper foi por IPC autenticado e terminou em STOPPED sem terminate/kill. PID final observado: 13712; relay conectado, SQLite íntegro e contagem de mensagens preservada.
- Produção avançou externamente de 0814864 para 5517c26 durante a execução. Nenhum reset foi feito. A comparação confirmou somente documentação/QA, sem mudança no código executável. O wrapper final importa esse backend equivalente à V597, não o backend experimental V598.
- Console administrativo implementado e validado localmente: `/admin`, seis abas, reautenticação temporária, verificação de papel/status/aprovação/sessão no servidor e no PC, CSRF, throttling, cookies restritos, auditoria e confirmação de ações.
- Migração real explícita: duas contas elegíveis promovidas, admins de três para cinco; hashes, IDs, status, aprovação, permissões remotas, limites e sessões preservados. Novos cadastros continuam user. Backup e manifesto privado fora do Git.
- Seis cenários autenticados executados no chat real, mais recuperação de resultado. As 14 mensagens persistiram e reapareceram após reload. Isso confirmou funcionamento e também revelou limites importantes de pesquisa.

## Bugs e correções

| Problema | Correção e limite |
|---|---|
| Inicialização sem dono único e sem shutdown autenticado | Lock do SO, identidade, named pipe JSON/HMAC, metadados de PID/criação/geração e drenagem de operações; lançadores antigos ainda precisam adotar o bootstrap |
| Corrida entre parada e novas threads/futures | Registro antes do agendamento, recusa de novas operações e espera por trabalhos aceitos; timeout não força kill |
| Reconnect podia manter processo vivo durante parada | Interrupção cooperativa do fluxo de conexão/retry e encerramento ordenado do backend |
| Canal QA podia colidir em execuções paralelas | Identidade do pipe inclui diretório customizado; lock de produção mantém identidade canônica |
| Pacote inválido podia derrubar controle | JSON limitado, validação de tipo, autenticação e timeout de desafio |
| Papel/sessão administrativa sem confirmação recente | Grant de dez minutos vinculado à sessão e revisão, verificações atuais em cada chamada, revogação e bloqueio explícito |
| Sessão do proprietário legado não participava da revogação SQLite | Registro do sid existente após reauth válida, sem novo sistema de login |
| Remoção/rebaixamento/bloqueio concorrentes do último admin | Verificação e mutação serializadas em transação, contando admins ativos/aprovados |
| Fragmento de convite incluído em novos eventos de auditoria | Origem registrada como convite, sem fragmento; detalhes históricos não são expostos no console |
| Interface administrativa inexistente e métricas enganosas | Seis abas responsivas; ausência de amostra, disponibilidade e erros não medidos são explicitamente indisponíveis |
| `/admin` poderia virar conteúdo de conversa | Interceptação antes de IndexedDB/mensagem/IA; SQLite QA confirmou zero mensagens e zero ai_requests |

Não há execução de código do modelo, endpoint de shell ou acesso automático a chats privados. O papel admin não altera `remote_ok` nem ignora regras de ownership.

## Validação executada

| Verificação | Resultado | Escopo |
|---|---|---|
| Suíte completa final | **1443 passed, 4 skipped, 2 warnings**, 307,65 s | Código local final de aplicação e testes |
| Benchmark de pesquisa | **34/34** | Congelado/offline, não qualidade científica em produção |
| Benchmark de compras | **59/59** | Congelado/offline, não confirmação de ofertas atuais |
| Benchmark de experiência | **16/16** | Contratos existentes |
| Chrome real | 320/390/1280 px, zoom CSS 200%, teclado, reload, seis abas | FastAPI + PC Agent WebSocket + SQLite temporários, contas fixture |
| Segurança do console | Sessões, CSRF/origem, expiração/revogação, roles, throttling, isolamento, último admin, migração | HTTP/SQLite e processos locais reais; não pentest externo |
| Runtime Windows | pythonw, concorrência, crash/lock, HMAC, drenagem, reconexão e parada | Processos reais com relay loopback e banco temporário |
| Operação real | Restart, IPC, backups, quick_check, migração e chat autenticado | Backend equivalente ao publicado V597 |

Warnings finais: depreciação existente de `mss.mss` e do argumento timeout no Starlette TestClient. Os quatro skips permanecem visíveis no log; a rodada foi executada sem `-rs`, portanto não se atribuem individualmente motivos não registrados. Há testes explicitamente bloqueados de síntese/semântica LLM na suíte; não foram removidos para obter aprovação.

Rodadas intermediárias tiveram falhas reais preservadas nos logs: inserção JS com encoding incorreto, fixture de isolamento sem outro admin, colisão entre canais de QA, expectativa incorreta do PID do launcher pythonw e assinatura incompleta do mock de catálogo no harness. Foram corrigidas sem remover testes ou silenciar erros. A suíte final passou após os ajustes. Depois dela, mudaram somente operadores/QA/documentação, não o código de aplicação testado.

O Chrome final capturou zero alertas/erros JavaScript. Um 401 anterior ao login é esperado; avisos DOM de senha fora de form no chat legado permanecem. Não se declara console de rede sem erros em todos os fluxos. Screenshots em `qa-artifacts/v5981/admin-*.png`; relatórios sanitizados `admin-browser.json`, `admin-tabs.json`, `admin-browser-sqlite.json`, `operational-summary.json` e `research-e2e-persistence.json`.

Encerrados o servidor/PC Agent temporários pelo canal de QA e o Chrome de teste. Inventário final dirigido encontrou somente o PID13712 de produção. Verificação de 81 arquivos de fonte/evidência contra valores secretos configurados não encontrou coincidências; arquivos de fonte/documentação examinados passaram em UTF-8 estrito. Isso não é varredura de todos os segredos possíveis nem de todo o histórico Git. Compilação dos novos operadores, sintaxe do verificador JS e git diff --check passaram.

## Pesquisa real: aprovação limitada

Saudação e TaskGroup responderam; TaskGroup trouxe explicação e link oficial, mas leitura integral não foi comprovada. Pesquisa científica terminou partial, **zero fontes lidas**, sem síntese científica válida. Notícias municipais trouxeram outras cidades. Imagens retornaram links sem galeria JDUI. Compras não obtiveram oferta/preço verificados e reconheceram bloqueio do provedor. O painel publicado ainda mostrou estado antigo após término.

Não há prova de leitura original, JDUI completo, oferta real ou qualidade próxima de Perplexity nesses cenários. Não houve captura de chunks SSE em produção; testes locais do contrato SSE e mensagens renderizadas/persistidas têm escopos distintos. Ver `docs/v5.9.8.1/AUTHENTICATED_RESEARCH_E2E.md` e o recorte proposto em `RESEARCH_NEXT.md`.

## Arquivos alterados

Aplicação: `agent_runtime.py`, `admin_console.py`, `admin_http.py`, `admin_migration.py`, `pc_agent.py`, `server.py`, `julia_auth.py`, `iniciar-agente.bat`, `public/app.js` e `public/admin.{html,css,js}`.

Testes: `tests/test_agent_runtime_v5981.py`, `tests/test_admin_v5981.py`, fixtures em `tests/test_isolamento.py` e `tests/test_research_quality_lab.py`. Asserções de isolamento foram mantidas; os fixtures agora respeitam o último admin e a reauth exigida.

Operação/QA: `tools/ops_restart_v597.py`, `ops_controlled_restart_v5981.py`, `ops_migrate_admins_v5981.py`, `serve_admin_qa_v5981.py`, `verify_admin_ui_v5981.cjs`, `verify_admin_tabs_v5981.cjs`, `finalize_v5981_evidence.py`, documentação e evidências em `docs/v5.9.8.1/` e `qa-artifacts/v5981/`.

`.gitignore` exclui metadados locais/stop de QA. `qa-runtime-private.json` havia sido incluído no commit externo 7181b7e durante a sessão; removido somente do índice, preservando o arquivo local. Contém caminhos e PIDs, não credenciais. O histórico externo não foi reescrito. Recibos operacionais reais, chaves, SQLite e backups não foram adicionados.

## Limites e estado de publicação

O console e o backend V598 continuam locais. Produção recebeu somente o wrapper de controle e a migração de papéis autorizados. Seus endpoints legados ainda não receberam a proteção adicional de reauth deste console. O supervisor antigo não supervisiona o wrapper novo; sua adoção exige trabalho futuro, sem alterar o Studio nesta entrega.

Commits locais anteriores preservados: `cd6e6a9` (runtime inicial) e `7181b7e` (consolidação externa das alterações durante a sessão). A conclusão local acrescenta operadores, documentação e QA final; o SHA dessa conclusão é informado na entrega. Nenhum push foi feito por esta execução.
