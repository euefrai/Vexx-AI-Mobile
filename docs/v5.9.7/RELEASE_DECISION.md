# V5.9.7 — GO_WITH_LIMITATIONS

## Gate local aprovado

- Suíte final: **1.385 passed, 4 skipped**, dois avisos anteriores de depreciação, 180,76 s; `full-suite-release.log`.
- Congelados: Search 34/34, Shopping 59/59, Experience 16/16; Quality Lab preservado.
- JDUI: Chrome real nos componentes, IndexedDB real, reload, isolamento por owner/job, mobile e zoom CSS. Quatro contratos VM passaram. Não é E2E autenticado em Chrome.
- SSE, cancelamento, replay, persistência, segurança e relay/PC Agent cobertos pela suíte, inclusive integração com processos reais e SQLite temporário. O teste determinístico de pesquisa desabilita explicitamente inferência externa.
- Nenhuma dependência paga, alteração de credenciais, migração SQLite ou protocolo novo. Respostas parciais e erros externos mantidos explícitos.
- Scan de padrões de segredos: 241 arquivos, zero ocorrência. Revisão de caminhos/artefatos: capturas públicas e dados sintéticos de teste; runtime local excluído do commit.
- `git diff --check` e sintaxe Node aprovados. Alterações não relacionadas isoladas e preservadas.
- Fetch confirmou main sem divergência: origin/main `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`.

## Preparação operacional

Produção antes: `/api/health` ok/configured; `/api/diag` pc_online=true, commit `ed3b9984b905`. Agente existente não foi reiniciado. APIs de research/ui-state, formato de eventos e estados de lifecycle continuam compatíveis com a versão anterior; mudanças de resultado são aditivas. As correções de backend estão validadas no novo processo isolado; não se alega que o processo antigo recarregou módulos Python automaticamente.

Render mantém build/start existentes e credenciais externas; nenhuma mudança em `render.yaml`, servidor ou dependências. Push pode iniciar deploy automático: observar SHA do relay, health, pc_online e CI. Não disparar deploy manual adicional.

Recuperação preparada: preservar SHA anterior acima; se a publicação causar regressão, reverter os commits publicados por novo commit de revert e publicar normalmente, aproveitando o mesmo mecanismo de deploy. Sem force push, reset remoto, exclusão/restauração de dados ou migração a desfazer. Agente deve permanecer compatível; só reiniciar se houver necessidade e compatibilidade demonstradas.

## Limitações aceitas

Não foi aprovada síntese científica completa. Busca Ubatã não recuperou artigo original aceito; leitura direta de Salvador não representa sucesso do fluxo inteiro. Vídeo específico, contradição externa resolvida e comparação experimental continuam sem confirmação. Chrome validou componentes, não o app autenticado ou celular físico.

## Publicação

Resultado remoto, CI e deploy serão registrados após o push autorizado condicionalmente. Esta seção não afirma publicação antecipada.
