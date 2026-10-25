# JDUI e visual

Cobertura em uma tabela compacta, sem edição dos estados calculados, usando o componente existente `table`. Backend e JavaScript validam a opção `read_only`. Estado de edição/filtro anterior não pode adulterar a tabela; ordenação por teclado e CSV permanecem funcionais. Fontes indicam aspectos com passagem, preservam URL/publicador/data/estado de leitura. Não há HTML/JS do modelo executado.

A mídia descoberta continua acessível no espaço de pesquisa, mas não vira galeria na resposta textual sem intenção de imagens/vídeo. A galeria pedida mantém origem, direitos, zoom/modal e estados de erro. O CSS refina borda, tipografia, espaçamento e botões da cobertura; em 320px com CSS200%, há rolagem horizontal **interna** em vez de quebrar cada palavra.

## Executado em Chrome real

- Galeria real: 1280/390/320px, raiz com mesma largura, cinco imagens carregadas. Cards 245/350/288px. Modal/próxima/seta/Escape/foco/reduced motion e metadados após reload passaram.
- Erro de imagem explicitamente injetado: mensagem de indisponibilidade e recuperação ao retirar bloqueio. Não se chama o erro de rede injetado de console global limpo.
- Cobertura real da pesquisa técnica: quatro linhas, incluindo autoridade não verificada. Sem botão de editar; ordenação por teclado, CSV e dados após reload passaram.
- Zoom CSS200%: raiz320px, tabela com área110px/conteúdo224px, scroll interno confirmado. Inspecionadas as imagens da tabela inteira à esquerda/direita; primeiro harness teve elemento destacado do DOM durante reload, não conta como passe.
- IndexedDB da instância de quatro cenários: duas bases, dez mensagens, três estruturadas, dois resultados. Downloads MD/CSV do job e CSV da cobertura realmente concluídos.
- Drivers registraram zero `pageerror`. Screenshots de galeria, modal, erro, cobertura desktop/mobile/zoom foram abertos e inspecionados; detalhes em `qa-artifacts/v5993`.

Não foram executados celular físico, zoom nativo, FPS ou auditoria integral de acessibilidade/todas as telas. A resposta ainda tem diagnóstico excessivo e trechos de código podem perder ordem no extrator; isso impede chamar a experiência inteira de Premium concluída. Os visuais principais foram executados em `af400f1` e no ajuste CSS `5127977`; o último guard de interface mudou seleção de fonte, não o renderer.
