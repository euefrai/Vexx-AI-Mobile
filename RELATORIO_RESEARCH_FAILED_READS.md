# Pesquisa: evitar downloads repetidos após falha e retomada

## Problema

Uma fonte com bloqueio ou falha de rede podia ser aberta novamente por outra etapa ou após retomar o mesmo job. Isso gastava orçamento sem produzir nova evidência. Baseline reproduzido: **4 falharam, 4 passaram** antes da correção.

## Correção

- Histórico limitado a 80 hashes SHA-256 de URLs canônicas no campo `usados` do job. Não armazena URLs, parâmetros nem mensagens de exceção nesse histórico; eventos anteriores continuam registrando as causas existentes.
- Downloads com `ResearchErro` (exceto cancelamento) ou `OSError`/timeout concluídos como falha antes do prazo são lembrados dentro da mesma pesquisa. A próxima etapa filtra essas candidatas antes de consumir páginas.
- A persistência normal do job preserva o histórico após a retomada. Nenhuma alteração de schema ou escrita adicional por download.
- Histórico separado por job e proprietário. Uma pesquisa nova pode tentar a fonte novamente; não há bloqueio permanente ou global.
- Cancelamento, prazo vencido e erros internos inesperados não alimentam esse histórico. Irrelevância, metadados e páginas vazias também não são falhas de download permanentes: outra subpergunta pode ter resultado útil.
- Evento agregado `source_failed_read_skipped` informa quantas fontes foram poupadas. Evidências já lidas continuam reutilizadas.
- Inclui também a substituição limitada de fontes da etapa anterior, documentada em `RELATORIO_RESEARCH_SOURCE_REPLACEMENT.md`.

## Verificação

- **130 testes focados passaram**, incluindo nove casos novos para histórico, retomada, URL canônica, cancelamento e separação de jobs/usuários.
- Smoke de rede real com SQLite temporário: primeira rodada fez duas tentativas (URL inexistente e página oficial de asyncio); após salvar e recarregar o job, **zero downloads extras**, mesma evidência reutilizada e contador mantido em duas páginas. Nenhuma chamada de modelo. Resultado: `qa-artifacts/failed-reads-public-smoke.json`.
- Suíte completa: **1.298 passaram, 4 ignorados, 2 avisos em 275,27 s**. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. Log local: `qa-artifacts/failed-reads-full.log`.
- `git diff --check`: sem erros.
- Após a suíte completa, o PC Agent ocioso foi recarregado pelo supervisor existente. Confirmados: uma instância, novo processo iniciado após a edição, mesmo banco, ambiente crítico equivalente e controle remoto desativado. `/api/diag` confirmou `pc_online=true`. Registro sem segredos: `qa-artifacts/failed-reads-agent-reload.json`.

## Limites

Falhas temporárias de rede também deixam de ser repetidas nas etapas seguintes desse job; uma pesquisa nova pode tentar novamente. O histórico só sobrevive quando o job foi salvo pelo fluxo normal, não oferece garantia para queda abrupta antes de salvar a etapa. O smoke comprova leitura e retomada dessas fontes, não qualidade semântica geral ou interface autenticada. Resultado de push, CI e recarga será informado na entrega.
