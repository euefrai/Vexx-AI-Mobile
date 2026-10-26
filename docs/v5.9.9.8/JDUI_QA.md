# JDUI — validação sem redesign

Chrome real: cards de cobertura a 1280, 390 e 320 px ficaram dentro do viewport, sem overflow da raiz. Inspeção visual dos PNGs de 320 e 1280 e do diálogo da galeria executada; 390 foi verificado geometricamente. Zoom CSS 200% permitiu rolagem horizontal interna (224/110 px); não equivale a testar zoom nativo de navegador ou dispositivo físico.

Tabela: ordenação por Enter, download CSV, ausência de controles de edição, reduced motion, tabela idêntica após reload. Texto “Trecho pertinente recuperado” não declara aprovação do modelo. Fontes MDN abriram destino correto em nova aba.

Galeria: cinco thumbnails carregados; imagem ampliada carregou, ArrowRight mudou item, Escape fechou, foco retornou. Falha Wikimedia injetada exibiu fallback e recuperou após remoção do bloqueio. MD e CSV da pesquisa baixados. Sem reconstrução do visual.

Arquivos: coverage-card-320.png, coverage-card-390.png, coverage-card-1280.png, coverage-zoom-card-left/right.png, gallery-dialog.png. Registro resumido e2e-summary.json. A interface validada contém resultados parciais/bloqueados; não é comprovação de pesquisa completa.
