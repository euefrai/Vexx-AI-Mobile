# V5.9.2 — apresentação e continuidade

Componentes existentes reaproveitados; validação Python/JavaScript mantida. Nenhum HTML ou código arbitrário do modelo executado.

| Item | Evidência executada | Limite |
|---|---|---|
| Síntese/evidências | Testes de checkpoint, view e Chrome | Chrome usa fonte sintética identificada |
| Fontes | Status encontrada/não lida, lida e utilizada; escopo, relação, publicação e evento separados | Abstract sustenta só seu conteúdo; link não prova leitura |
| Câmbio | Chat → fluxo existente → API externa → cards/gráfico; reload preserva resposta | Referência diária, sem hora da taxa inventada |
| Gráfico mobile | 22 pontos, quatro rótulos sem sobreposição; datas completas em aria-label/tooltips | Até 24 observações reais selecionadas, sem interpolar dias |
| Imagens | Bytes reais de fixture HTTP local, zoom, Escape e retorno de foco | Não comprova disponibilidade de imagens externas arbitrárias |
| Vídeos | Renderer conserva link de origem e thumbnail fornecida | Sem playback/transcrição/análise real executada |
| Arquivo | Download HTTP 200 com 1983 bytes no Chrome | Conteúdo da investigação fixture |
| Streaming | 43 eventos ordenados, interrupção, reconexão e reload durante job | Sem inferência; cancelamento coberto por backend, sem novo E2E Chrome |
| Mobile | Chrome emulado 390/320 px e desktop 1280 px | Não executado em aparelho físico |

Âncora de retomada guarda somente ID/proprietário/timestamp, expira em 24 h e confirma sessão/proprietário no servidor. Logout/stop interrompem UI/streams; callbacks antigos são ignorados por identidade da pesquisa e época da sessão. Mantidos controles de autorização/persistência.

Screenshots finais inspecionadas visualmente:

- [Pesquisa desktop](../../qa-artifacts/v592/research-desktop.png)
- [Fontes desktop](../../qa-artifacts/v592/sources-desktop.png)
- [Pesquisa 390 px](../../qa-artifacts/v592/research-mobile-390.png)
- [Pesquisa 320 px](../../qa-artifacts/v592/research-mobile-320.png)
- [Câmbio desktop](../../qa-artifacts/v592/exchange-desktop.png)
- [Câmbio mobile](../../qa-artifacts/v592/exchange-mobile.png)

`chrome-continuity.json` contém resultado final aprovado e zero erros registrados. `chrome-failure.png` e logs anteriores ficam como diagnóstico, não resultado final.

Revisão visual final encontrou barra de pesquisa encerrada ainda visível, com Cancelar e ações sobrepostas. `researchStop` agora oculta a barra e o layout ativo aceita quebra de linha. Chrome verifica barra ausente antes de iniciar e após encerrar. A verificação adicional reproduziu SSE parado antes do evento terminal. Reconciliação HTTP a cada cinco segundos, sem consultas sobrepostas e somente em job ativo, agora recupera o estado final. Evidência anterior: `terminal-stall-reproduction.json`; final: `terminal_bar_cleared=true`. O atributo hidden já era respeitado pelo CSS: a causa era falta de atualização de estado, não sobreposição de display. Sem refazer telas globais ou 3D. Sem cards de passagens/preços/agenda na ausência de dados verificados.
