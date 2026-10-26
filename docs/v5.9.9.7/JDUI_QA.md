# JDUI e verificação visual

Chrome real em localhost descartável. Nenhuma mudança CSS/DOM do produto foi necessária nesta fase. `ui-summary.json` e PNGs em `qa-artifacts/v5997/` guardam medições e interações; foram inspecionadas as capturas dos cards 1280/390/320, dois lados no zoom e galeria ampliada.

- Fonte MDN aberta em aba real; URL final preservada. Fetch offline falhou e health voltou a 200 após reconectar; isso não valida todos os fluxos offline.
- Tabela somente leitura: ordenação por teclado, CSV, zero botões de edição; persistência após reload e registros IndexedDB reais.
- Root/card: 1280 px [394,1154], 390 px [20,370], 320 px [16,304]. Sem overflow do root. Zoom CSS 200%: tabela com scroll interno 224/110, scrollLeft 114; não equivale a zoom nativo de browser.
- Reduced motion exercitado. Sem pageerror nos cenários instrumentados. Console teve 401 inicial esperado sem sessão, aviso pré-existente de password fora de form e erro offline deliberado; não afirmar console inteiramente silencioso.
- Cancelamento real: estado cancelada, uma mensagem inicial, sem resultado final; persistência após reload.
- Galeria real Wikimedia: cinco cards, cinco miniaturas carregadas a 960 px, imagem completa carregada, setas, Esc e foco restaurado. Imagem descoberta continua marcada como não analisada; não é evidência factual da resposta.

390 px: a captura antiga corria durante a animação de fechamento da sidebar (borda direita +12,69 px). Depois das animações finitas, sidebar -6,40 px e card [20,370], sem corte. Reproduzido com movimento normal. Correção aplicada ao **harness**: aguardar fontes e animações finitas e verificar limites do card antes de capturar. Não alegar que uma regra CSS nova corrigiu um defeito permanente.

Entrega MDN usada para testar tabela/fontes foi explicitamente semeada, com HTTP real e persistência SQLite; não conta como descoberta autônoma nem síntese de modelo. Galeria inicial também foi capturada antes do lazy loading; nova verificação confirmou os bytes decodificados e modal. Erros de invocação/reattach do script de QA permanecem nos logs/manifesto e não foram mascarados como testes de produto.

Shutdown verificado em `qa-shutdown.json`: toda a família do harness encerrou, banco e runtime temporários removidos. Nenhum processo de produção foi reiniciado ou terminado.
