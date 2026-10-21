# UI polish — checkpoint de trabalho

Atualizado em 15/10/2026. Relatório principal: `../RELATORIO_UI_POLISH.md`.

## Implementado

1. Auditoria objetiva de Git, testes, envio, SSE, renderização e registro JDUI.
2. Replay/identidade, cancelamento, EOF parcial, deduplicação de deltas, checkpoints,
   recuperação no reinício e falhas recuperáveis. Mantido envio sem aguardar sync completo.
3. Persistência JDUI, componentes estáveis durante streaming, Markdown com células
   vazias, links e fontes correspondentes. HTML do modelo não executa scripts.
4. Status de geração simplificado, métricas sem denominadores inventados,
   EvidenceGraph com zoom real, filtros traduzidos e ativação por teclado.
5. Testes focados e navegação real com banco descartável; suíte completa final:
   **328 passaram, 2 ignorados sem provedor LLM, 2 avisos de depreciação**, em 189,05 s.
   Nenhuma falha nessa execução. Ambiente de preview encerrado; sem push/deploy.

## Evidência visual e de integração

- Quiz respondido, recarregado e sincronizado para outra origem de navegador.
- Tabela mantém a célula vazia entre duas colunas com conteúdo.
- EvidenceGraph aplica filtro e zoom; Enter seleciona um nó.
- Layout de 390 px não transborda horizontalmente no fluxo verificado.
- Login, Estudos e Meu PC inspecionados; sem comandos remotos ou contas reais alteradas.

## Próxima etapa exata após esta rodada

Executar uma matriz manual dos 19 componentes JDUI em Android e iOS reais,
começando por `exam`, `lesson`, `studyplan` e `flashcards` com registros de teste
criados pelas APIs. Verificar teclado virtual, leitores de tela, retenção de foco
nas remontagens por sincronização e retomada após suspender o aplicativo.
Depois medir tempo até o primeiro trecho com o Hermes efetivamente conectado,
separando gravação local, fila, relay e geração; não usar o preview sem provedor
para concluir desempenho da IA.

## Cuidados para continuar

- Há outro trabalho alterando e commitando neste mesmo checkout. Inspecionar Git antes de editar.
- Não reverter alterações de quality lab/benchmarks/documentos atribuídas ao trabalho concorrente.
- Não apagar IndexedDB/SQLite reais para testar; usar `tests/preview_workspace.py`.
- Não declarar validação visual completa dos 19 componentes: nesta rodada, o teste
  visual de interação concentrou-se em quiz, tabela e EvidenceGraph.
- Sem push/deploy. Para implantação futura, atualizar frontend, servidor e agente juntos.


## Atualização de 20/10/2026 — auditoria e correções autorizadas

- Base desta rodada: HEAD `607ff1f`; alterações preexistentes de mídia/pesquisa preservadas.
- A01–A15 receberam correções incrementais; GET SSE legado permanece compatível e
  registros antigos já corrompidos não foram alterados. R01/R02 receberam proteções.
- Suíte final: **941 passed, 4 skipped, 2 warnings**, 214,70 s.
- Chrome: composer POST, relógio determinístico, SQLite, SVG isolado, drawer clicável
  em 320/390/1280 px, cache limpo e cookie revogado rejeitado. Evidências em
  `qa-artifacts/correcoes-20261020/`. Sem inferência Hermes real no preview.
- Relatório: `RELATORIO_CORRECOES_AUDITORIA_2026-10-20.md`. Sem push/deploy.
- Próximo passo exato: reproduzir R03 em banco descartável, medindo resumo/upload de
  documento em paralelo com `/api/sync`; implementar fila limitada com conexão SQLite
  própria somente depois de medir o bloqueio, mantendo autenticação e cancelamento.
- Depois: benchmark de histórico grande e Android/iOS reais; lock de dependências,
  restauração completa e política de mídia externa continuam pendentes (R04–R08).
