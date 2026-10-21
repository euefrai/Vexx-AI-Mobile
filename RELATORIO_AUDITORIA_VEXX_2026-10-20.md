# Auditoria do Vexx AI — 20/10/2026

## Resultado e autorização

**Há problemas confirmados de segurança, recuperação/sincronização e persistência que justificam uma rodada de correção antes de recomendar uma nova publicação.** A suíte existente passa, mas não cobre todos os cenários reproduzidos nesta auditoria.

Nenhuma correção de produção foi aplicada. Foram criados apenas este relatório e os artefatos de auditoria. A próxima etapa depende da autorização do usuário.

O push do catálogo 3D já tinha sido concluído em outra execução: `9519df6` é ancestral de `origin/main`, verificado com `git merge-base --is-ancestor`. Não houve novo push nesta auditoria.

### Estado auditado

- HEAD local: `607ff1f10fa66dd32906505ae1cc8ccb5ed37184`.
- Remoto `origin/main` após fetch: `ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`.
- Três commits locais adicionais, de hardening/documentação V5.7.3, ainda não publicados. A autorização anterior era para 3D; esses commits não foram enviados.
- Alterações locais preexistentes em `research_agents.py` e arquivo não rastreado `media_evidence.py`, além de relatórios/evidências anteriores. Preservados. O achado A13 é específico desse trabalho em andamento.
- Não foram lidas credenciais de produção nem alterados bancos reais. As reproduções usam SQLite temporário ou navegador descartável.

## Evidências executadas

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte completa do workspace, `pytest -q -rs` | **929 passed, 4 skipped, 2 warnings**, 118,74 s | `qa-artifacts/auditoria-20261020/pytest.txt` |
| Compatibilidade das dependências instaladas, `pip check` | Sem requisitos quebrados | Saída do terminal desta execução; não é varredura de CVEs |
| Reproduções de histórico, exclusão, ACK, revogação, persistência e catálogo | Comportamentos defeituosos confirmados | `probes.py` e `probes.json` na pasta de auditoria |
| SVG no Chrome real, com CSP do servidor | Conteúdo sanitizado ainda redirecionou a página | `svg-probe.cjs`, `svg-probe.json`; todas as requisições interceptadas em memória |
| Preview descartável com login real da fixture | Documentos, Estudos e Ajustes acessíveis em **320, 390 e 1280 px** | `ui-smoke.cjs`, `ui-smoke.json` |
| Responsividade dos nove casos acima | Sem overflow horizontal nem erros `pageerror` | `ui-smoke.json`; `settings-mobile.png` inspecionada |

Os quatro skips dependem de Hermes real e buscas comerciais externas: dois testes de inferência não tiveram provedor, DDG não retornou resultados e o diagnóstico comercial encontrou HTTP 403/bot-wall. Não são aprovação dessas integrações. Os dois warnings são de APIs depreciadas em `mss` e `TestClient/httpx2`.

## Bugs confirmados e pontos acionáveis

**P1:** segurança, perda/corrupção de dados ou recuperação incompleta. **P2:** confiabilidade, comportamento incorreto ou UX. **P3:** consistência visual/textual. “Reprodução” significa execução observada; “inspeção” significa caminho concreto no código, sem afirmar exploração em produção.

### A01 — P1 — Conteúdo marcado como SVG pode injetar HTML e redirecionar o chat

- **Evidência:** `public/app.js:437` (`sanitizeSvg`) e `:576` (inserção com `innerHTML`).
- O sanitizador remove algumas tags por regex, mas não exige uma árvore SVG válida nem restringe todos os elementos. Um SVG seguido por `<meta http-equiv="refresh">` sobrevive.
- **Reprodução no Chrome:** após a sanitização, a página navegou de `https://audit.invalid/app` para `/redirect`, mesmo usando a CSP atual de `server.py:353`. Todo tráfego foi interceptado; nenhum site externo foi acessado.
- **Impacto:** uma resposta do modelo ou conteúdo indireto pode tirar o usuário do aplicativo, induzir navegação e permitir HTML fora do desenho. Não foi demonstrada execução de JavaScript nem roubo de sessão; não se deve confundir esta prova com XSS completo.
- **Correção proposta:** validar com parser e allowlist estrita de elementos/atributos SVG, rejeitar conteúdo externo à raiz, ou renderizar o SVG isolado como imagem; incluir testes no browser, não somente verificações de strings.

### A02 — P1 — Duas falhas temporárias desativam a verificação de revogação

- **Evidência:** `server.py:145–165`; reconexão do agente restaura o flag em `agent_ws`.
- Após duas falhas de consulta, `suportado=False` elimina novas verificações até reconectar o agente. Não há recuperação periódica enquanto a conexão permanece aberta.
- **Reprodução:** três requisições foram permitidas, apenas duas consultas RPC foram tentadas e o flag terminou desativado.
- **Impacto:** uma sessão revogada e ainda não presente no cache pode continuar aceita até a expiração/reconexão. A checagem de conta bloqueada no agente não resolve revogação de uma sessão específica de uma conta ativa.
- **Correção proposta:** negociar capacidade explicitamente; distinguir agente antigo de falha transitória; retentar com backoff e definir política restritiva para ações sensíveis quando a validade não pode ser confirmada.

### A03 — P1 — Apenas as 500 revogações mais recentes são lembradas

- **Evidência:** `julia_auth.py:425`, `server.py:155`.
- A lista é truncada a 500, sem restringir primeiro às sessões ainda não expiradas; o relay substitui seu conjunto por essa lista.
- **Reprodução:** com 501 sessões revogadas, a primeira desapareceu do resultado.
- **Impacto:** sob volume suficiente de revogações, um cookie revogado ainda dentro de sua validade pode voltar a ser aceito. O teste confirma a omissão; não representa um ataque realizado em produção.
- **Correção proposta:** validar a sessão por SID, ou garantir um conjunto completo de revogações relevantes à janela de validade, com expiração e paginação corretas.

### A04 — P1 — Recuperação em outro aparelho omite mensagens antigas

- **Evidência:** `pc_agent.py:338`, `server.py:927`, `public/app.js:1534`.
- O agente entrega no máximo 200 mensagens da conta inteira. O filtro por conversa é aplicado **depois** desse corte. Não existe cursor nesta API.
- **Reprodução:** uma mensagem antiga continuava no SQLite, mas a API da sua conversa retornou zero após criar 200 mensagens mais recentes em outro chat.
- **Impacto:** aparelho novo ou cache apagado não recupera o histórico completo. O usuário pode interpretar isso como perda de conversas, embora os dados ainda estejam no PC.
- **Correção proposta:** paginar por proprietário/conversa no SQL, aplicar o filtro antes do limite e carregar páginas adicionais no cliente.

### A05 — P1 — Sincronização atrasada pode regravar dados de chat excluído

- **Evidência:** `workspace_store.py:56–81`, `pc_agent.py:311`, `server.py:1154`.
- A exclusão do workspace cria tombstone e apaga mensagens, mas a entrada de mensagens não consulta esse tombstone. A rota antiga de exclusão também não unifica toda a semântica.
- **Reprodução:** chat excluído passou de zero para uma mensagem no SQLite depois de reenviar uma mensagem antiga; o tombstone permaneceu `deleted=true`.
- **Impacto:** exclusão não é definitiva no armazenamento diante de aparelho atrasado/retry. O frontend tenta ocultar chats excluídos, portanto a reprodução não prova que o chat reaparece visualmente.
- **Correção proposta:** verificar tombstone na ingestão e geração, centralizar a exclusão e resolver respostas em andamento e dispositivos atrasados de forma transacional.

### A06 — P1 — Corte de JSON serializado pode corromper pesquisas salvas

- **Evidência:** `research_agents.py:260–279`; padrão semelhante em `research.py:672` e `:1248`.
- Campos são salvos como `json.dumps(... )[:limite]`. Isso pode cortar dentro de string/objeto e gerar JSON inválido.
- **Reprodução:** achados serializáveis com cerca de 61 KB foram aceitos por `salvar_job`; `carregar_job` falhou com **“pesquisa corrompida”**.
- **Impacto:** perder a retomada de pesquisas grandes. O caminho de persistência foi reproduzido com estado sintético; não foi executada uma pesquisa externa até atingir esse tamanho.
- **Correção proposta:** limitar itens/textos antes da serialização ou rejeitar o estado acima do teto; validar JSON antes do commit e prever recuperação dos registros já inválidos.

### A07 — P1 — Prompt e contexto sensível seguem na URL do streaming

- **Evidência por inspeção:** `public/app.js:1891–1909`, `server.py:2033`.
- `text`, cidade, coordenadas quando autorizadas e estado 3D entram em `URLSearchParams` de um GET. Não é necessário acessar logs reais para confirmar que esses valores fazem parte da URL.
- **Impacto:** URLs podem ser registradas por servidor, proxy, CDN e ferramentas de monitoramento. Mensagens longas também podem exceder limites de URI e produzir erro 414, dependendo da infraestrutura.
- **Limite da prova:** não foram inspecionados logs de produção nem reproduzido 414 em seu proxy.
- **Correção proposta:** POST com body para iniciar/consumir streaming, mantendo CSRF, cancelamento e idempotência; verificar também redaction de logs.

### A08 — P2 — Estado JDUI antigo pode sobrescrever estado mais novo

- **Evidência por inspeção:** `pc_agent.py:5188–5208`; `public/app.js:188`.
- O cliente compara datas no download, mas o `ON CONFLICT(k)` no PC atualiza incondicionalmente. Um aparelho antigo envia seus estados antes de receber os novos.
- **Impacto:** progresso de quizzes ou posição/interação 3D pode voltar ao estado anterior entre aparelhos.
- **Correção proposta:** aplicar versão/data e desempate no servidor, com ACK da versão vencedora e teste de dois clientes em ordens opostas.

### A09 — P2 — Estados JDUI além do lote de 300 podem nunca ser enviados

- **Evidência por inspeção:** `public/app.js:192–194`.
- `getAll()` seguido de `slice(-300)` é usado em toda sincronização, sem paginação de pendências. A ordem do object store é por chave, não uma fila de alterações.
- **Impacto:** ao acumular muitos componentes, alterações fora desse recorte podem ficar somente no aparelho.
- **Correção proposta:** fila de estados modificados, lotes paginados e ACK por chave/versão.

### A10 — P2 — Confirmação de mensagem não garante que o conteúdo foi persistido

- **Evidência:** `pc_agent.py:311–335`.
- `INSERT OR IGNORE` é seguido de ACK mesmo quando o ID já existe com dados diferentes.
- **Reprodução:** um retry com o mesmo ID e outro texto recebeu confirmação; o texto no banco continuou sendo o anterior.
- **Impacto:** divergência silenciosa em bugs de retry, colisões ou edição reutilizando ID. Não foi comprovada colisão espontânea dos UUIDs gerados pela UI.
- **Correção proposta:** ACK somente de repetição idêntica; retornar conflito para ID com outra identidade/conteúdo.

### A11 — P2 — “Apagar todo o cache” deixa dados locais para trás

- **Evidência por inspeção:** `public/app.js:252–256` e handler `clearCache`.
- A rotina limpa mensagens, sessões e itens salvos, mas não inclui `UISTATE` e `META`, que armazenam estados JDUI e metadados de organização.
- **Impacto:** a promessa de apagar todo o cache não corresponde ao resultado; projetos/estados podem sobreviver. Não é uma prova de leitura entre contas pela interface.
- **Correção proposta:** definir claramente limpeza da conta atual versus de todo o aparelho, incluir os stores correspondentes e explicar o destino das mensagens ainda não sincronizadas.

### A12 — P2 — Catálogo 3D substitui o objeto pedido por outro

- **Evidência:** aliases de `model3d_catalog.py:17–30` e integração em `model3d.request/respond`.
- **Reprodução:** “Xbox Series X” retorna título de aproximação do **Xbox Series S**; “motor elétrico” retorna **Motor V8**.
- **Impacto:** renderização tecnicamente válida, mas semanticamente errada. O aviso de “aproximação” não explica a troca de modelo/tipo.
- **Correção proposta:** aliases específicos, verificação de variante e fallback honesto quando não há a cena solicitada; oferecer o modelo genérico com clareza.

### A13 — P2 — Mídia de pesquisa não persiste no trabalho local em andamento

- **Escopo:** alteração **não commitada** em `research_agents.py`, com dependência não rastreada `media_evidence.py`; não atribuir isso à versão publicada.
- `criar_job` inclui `midia`; o SELECT lê a coluna, mas o retorno de `carregar_job` não a inclui e `salvar_job` não a atualiza.
- **Reprodução:** uma mídia atribuída ao job resultou em zero mídias depois de salvar/recarregar.
- **Correção proposta:** completar contrato de criação, gravação, leitura, checkpoints e limites antes de publicar esse trabalho; incluir a dependência no commit apropriado.

### A14 — P3 — Identidade/rebrand ainda inconsistentes em ações secundárias

- **Evidência:** `public/app.js:2359–2366` compartilha respostas como “Júlia” e “Conversa com Júlia”; `public/index.html:327` mostra “Aprender sozinha”.
- **Impacto:** interfaces secundárias divergem da identidade Lucas e da marca Vexx AI. Não implica que o prompt central de identidade esteja errado.
- **Correção proposta:** centralizar strings de marca/assistente também em exportação, compartilhamento e labels.

### A15 — P1 — Logout da sessão legada não tem revogação durável correspondente

- **Evidência por inspeção:** `server.py:403–415` autentica o proprietário legado e chama `emitir_sessao` diretamente; essa função gera um SID aleatório, mas não registra sessão no SQLite. `logout` solicita revogação por SID; `julia_auth.revogar_sessao` apenas atualiza linhas existentes.
- **Impacto condicionado:** uma cópia de um cookie legado válido pode continuar utilizável após logout. O cookie é removido do browser que saiu, mas não há linha correspondente para invalidar sua cópia no servidor.
- **Limite da prova:** não houve replay de cookie real nem exploração na conta do usuário. A conclusão decorre do caminho de criação e revogação inspecionado.
- **Correção proposta:** registrar e validar todas as sessões, inclusive a legada, ou manter revogação durável no relay; preservar o login offline de forma explicitamente definida.

## Riscos futuros / dependentes de ambiente

Estes itens não são apresentados como incidentes já observados.

| ID | Prioridade | Risco e evidência | Como confirmar / reduzir |
|---|---|---|---|
| R01 | P1 | **DNS rebinding/TOCTOU:** `research.py:92–134` valida DNS público, depois `urllib` resolve o hostname novamente ao conectar. Não foi visto pinning do IP validado. | Teste controlado de resolução alternada e conexão real; conectar ao IP validado preservando Host/TLS/SNI e revalidar redirects. Nenhum alvo privado foi acessado nesta auditoria. |
| R02 | P2 | **Consumo de recursos no relay:** `server.py:2059` usa fila SSE sem `maxsize`; não há teto de streams nesse endpoint; `pc_agent.py:5319` cria thread antes da verificação de quota dentro do worker. Há limites de IA por usuário, mas isso não limita toda alocação anterior. | Teste de carga em ambiente isolado; limitar streams/filas e aplicar backpressure/quotas antes de alocar workers. |
| R03 | P2 | **Operações de documentos bloqueiam o loop RPC:** `pc_agent.py:4914` e `:4966` executam upload/resumo diretamente no loop do agente. PDF e LLM podem demorar; sync e outros comandos compartilham esse loop. | Medir upload/resumo em paralelo com sync; mover trabalho pesado para fila limitada com timeout e cancelamento. Não foi feito stress de PDF hostil. |
| R04 | P2 | **Custo crescente no celular:** `public/app.js:227` usa `getAll()`; renderização, busca e sync filtram coleções completas. `public/organize.js:31` monta texto de busca por conversa. | Benchmark com 10 mil/50 mil mensagens, memória e long tasks; índices por conta/conversa, paginação e virtualização. Não há medição de aparelho físico nesta auditoria. |
| R05 | P2 | **Build/update pouco reproduzível:** `requirements.txt` usa faixas largas e não foi encontrado lock Python; `public/sw.js:1` mantém versão “live-data-1” apesar das evoluções e busca recursos pela rede individualmente. | Fixar conjunto reproduzível, testar atualização PWA com abas antigas e rede interrompida. Não foi reproduzida mistura de versões; `pip check` passou no ambiente atual. |
| R06 | P2 | **Dependência de serviços externos:** quatro testes pulados; HTTP 403/bot-wall e ausência de Hermes impediram confirmação integral de pesquisa, preços e síntese. | Reexecutar integrações em ambiente autorizado com serviços operantes; preservar fallbacks honestos, fontes/datas e monitoramento de taxa de erro. Não confundir indisponibilidade externa com bug confirmado do código. |
| R07 | P2 | **Recuperação operacional não validada:** migrações/SQLite possuem testes, mas esta auditoria não restaurou backup completo de uma instalação real nem simulou disco cheio/falta de energia. | Ensaio de backup/restauração de cópia descartável, integridade, anexos, WAL e versões de schema; definir RPO/RTO. |
| R08 | P2 | **Privacidade de mídia externa:** imagens HTTPS de respostas são permitidas pela CSP; se renderizadas automaticamente, o host recebe requisições do navegador. | Verificar política de carregamento/consentimento e referrer, cache/proxy e links. Não foi demonstrado envio de conteúdo da conversa a um host externo. |

## Cobertura por área

| Área | O que foi examinado | Limite |
|---|---|---|
| Contas, sessões, permissões | Rotas login/logout, revogação, CSRF, guardas do agente, testes auth/isolamento/trust | Sem teste de penetração contra produção; sem cookie real reutilizado |
| Chat, IndexedDB, SQLite, SSE | Ingestão/ACK, recuperação, exclusão, persistência e cancelamento, suíte completa | Sem teste prolongado de vários aparelhos reais/offline |
| Projetos, menus e responsividade | Merge/tombstones e navegação de preview em três larguras | Não é auditoria WCAG completa; sem leitor de tela ou teclado virtual de celular |
| Markdown, SVG, JDUI | Pipeline de renderização, isolamento HTML, validação e estados; prova SVG em Chrome | Não houve fuzzing exaustivo de todos os componentes |
| Pesquisa, compras, evidências, agentes | Persistência e limites, código local em edição, testes de grounding/provedores | Inferência real e parte das buscas externas ficaram bloqueadas |
| Memória, estudos e documentos | Testes correspondentes, rotas, extração/limites e UI de navegação | Sem revisão semântica de memórias reais ou avaliação pedagógica extensa |
| 3D | Commit publicado, testes de schema/interação e duas reproduções de correspondência | Sem nova inspeção WebGL de todas as cenas/modelos |
| Meu PC / remoto | Guardas de permissão, código e testes existentes | Nenhum comando de mouse/teclado executado pela auditoria; sem nova sessão remota manual |
| Dependências e operação | Estado Git, `pip check`, logs da suíte e arquitetura de cache/relay | Sem scanner atualizado de CVEs, carga de produção ou validação de deploy |

**Aspectos positivos confirmados:** suíte ampla sem falhas; navegação testada sem overflow; rotas sensíveis usam CSRF e autenticação; controle remoto possui grant próprio; documentos têm limites de tamanho/ZIP; o renderer HTML usa iframe com sandbox; schema 3D restringe estruturas. Essas proteções não eliminam os achados específicos acima.

## Ordem proposta para correção — aguardando autorização

1. **Segurança e privacidade:** A01, A02, A03, A15 e A07; teste controlado de R01.
2. **Integridade e recuperação:** A04, A05, A06 e A10.
3. **Estados entre aparelhos:** A08, A09 e A11.
4. **Qualidade das respostas/UI:** A12 e A14; A13 apenas junto com a conclusão do trabalho de mídia em andamento.
5. **Robustez operacional:** R02–R08, com métricas e testes de carga/recuperação proporcionais.

Cada bloco deve ter testes de regressão que falhem antes da correção, verificação focada depois e suíte completa ao final. Nenhum achado deve ser “corrigido” removendo sua cobertura ou escondendo falhas.

Uma auditoria ampla não garante encontrar todo defeito presente ou futuro. Este relatório separa o que foi executado, o que foi confirmado no código e o que ainda exige teste específico, para orientar uma correção verificável.
