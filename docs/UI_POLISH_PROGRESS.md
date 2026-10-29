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

## Atualização de 29/10/2026 — UI/UX e testes reais

- Base `main/c42792a`; alterações anteriores e arquivos já preparados no índice
  preservados. Sem push/deploy desta rodada.
- Corrigidos roteamento de memória, comparação no feminino, contexto de ofertas
  do cache entre chats sem renovar validade, notícias semanais de Ubatã,
  descoberta KaBuM e documentação Python, perda de passagens em APIs distintas,
  cards fora da posição Markdown, referências extensas, datas e contraste de ação.
- UI real local completa com rede e modelo configurado: seis ofertas; produto
  aberto com variante/preço corretos; dois cards de comparação; três notícias;
  cinco imagens carregadas; treze mensagens/quinze cards preservados após reload.
- Navegador em 320/390/1280 px sem overflow. Em 390 px: sidebar clicável,
  Configurações acessíveis, referências expansíveis e ordenação persistida.
- Suíte completa final: **2.083 passed, 4 skipped, 2 warnings**, 218,53 s, exit 0.
  Nenhum erro inesperado de console nas execuções finais da interface.
- Pesquisa profunda: leitura e descoberta real melhoraram (0 → 1 fonte lida no
  cenário Python); síntese completa ainda não aprovada. O modelo retornou saída
  vazia e o fallback agora conserva os vários trechos recuperados, mantendo as
  lacunas explícitas. Não reduzir validações para esconder essa limitação.
- Próximo passo exato: reproduzir geração/revisão com os mesmos trechos salvos,
  medir saída vazia versus rejeição semântica e resolver a condição de autoridade
  com evidência independente. Depois repetir A/B/C pela interface.
- Relatório: `RELATORIO_TESTES_REAIS_UI.md`. Evidências: `output/real-ui/`.
- O agente de produção foi atualizado com backup/IPC para o commit **já publicado**
  `c42792a`; as correções novas continuam locais. O laboratório usa banco próprio.

## Continuação autorizada em 29/10/2026 — síntese e publicação conjunta

- Corrigidos: prazo da redação/revisão, escopo real de APIs e métodos aninhados,
  contexto perdido entre catálogo e modelo, autoridade Python com inventário
  independente, perda da proveniência em memória e persistência JSON acima de
  12 mil caracteres. Compactação sem perdas: exemplo de 20.153 → 10.342 caracteres.
- Mantidos dois pedidos ao modelo por síntese, sem retries automáticos; até
  25 s por fase/50 s no par, prazo restante e cancelamento preservados. Funções
  genéricas mantêm o padrão anterior de 25/12 s.
- Corrigido falso positivo real que confundia cancelamento com tratamento de
  exceções. Suporte exige relação explícita no quote e na resposta, contexto
  real, fonte verificada e revisão separada; restrições de versão não são
  ignoradas. Nomes curtos somente quando inequívocos no pedido.
- Seleção por frases para os aspectos técnicos, sem elevar o limite de 1.800
  caracteres por fonte. Contexto tabular anterior preservado. Cards passam a
  reconhecer fontes realmente citadas na redação aprovada.
- **166 testes focados; suíte completa 2.104 passed, 4 skipped, 2 warnings**, exit 0.
- UI real: descoberta sem URL, página oficial lida, resposta assistida em quatro
  parágrafos e preservação após reload. Replay dos dados reais aprovou os quatro
  aspectos. A rodada independente seguinte teve revisão rejeitada; depois o
  provedor gratuito retornou HTTP 429. Não declarar C universalmente estável.
- Próximo passo exato: repetir `tools/live_research_completion.cjs` com quota
  disponível e registrar cobertura, correção factual, citações e reload. Sem
  relaxar validações para obter uma marca de pesquisa completa.
- Publicação conjunta autorizada na `main`; inclui a UI da etapa anterior.
  Relatório desta continuação: `RELATORIO_CONCLUSAO_PESQUISA.md`.
