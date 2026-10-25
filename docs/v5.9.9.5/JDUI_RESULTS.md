# JDUI — evidência de renderização e persistência

Chrome real, autenticado no runtime temporário. As pesquisas autônomas renderizaram cobertura pendente sem fontes inventadas. Para isolar cards de falhas de descoberta, foi usado um teste explicitamente controlado com URL MDN: leitura HTTP real, SQLite, entrega ao chat e IndexedDB. Não usar esse resultado para afirmar descoberta/síntese autônoma.

- Screenshots de tabela inspecionados: 1280 px (mensagem 760), 390 px (350), 320 px (288); largura da raiz igual ao viewport nos três casos.
- CSS zoom 200% em 320: rolagem interna da tabela de 114 px, sem overflow da página; verificados lados esquerdo/direito.
- Ordenação por Enter, CSV baixado, ausência de botões de edição em card readonly, reduced motion e texto da tabela idêntico após reload.
- Dois cards de fontes lidas com links reais; popup abriu MDN. Não há alegação de revisão humana independente das afirmações.
- IndexedDB `messages` tinha 9 registros na captura da tabela; texto/IDs do fluxo foram comparados após reload. Chat comum posterior confirmou 2 IDs únicos no novo chat.
- Sem `pageerror` nos testes. Sem alteração cosmética grande ou nova funcionalidade nesta rodada.

Artefatos: `visual-qa.json`, `source-links-reconnect.json`, `coverage-card-{1280,390,320}.png`, `coverage-zoom-card-{left,right}.png`, `coverage-export.csv`. Capturas emuladas em desktop, não telefone físico. Não se auditou novamente cada componente JDUI, cada exportador ou cada preferência de acessibilidade; suíte existente e recortes exercitados delimitam a conclusão.
