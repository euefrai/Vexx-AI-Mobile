# JDUI: entrega, persistência e apresentação

Não houve redesign nem alteração de `public/app.js` nesta versão. A mudança de apresentação é o conteúdo útil preservado até o card: o trecho histórico da WEG deixou de mostrar aviso de manutenção e passou a mostrar uma janela literal com fundação e fundadores. Links continuam os efetivamente recuperados. Pedido de PDF exige documento realmente lido também no fluxo profundo.

## Chrome real, autenticado, dados públicos recuperados

`visual-accepted.log` registra larguras 1280/390/320 px: raiz 1280/390/320, sem overflow horizontal. Cards medidos em 245/350/288 px, respectivamente. Foram inspecionadas as seis capturas `research-1280.png`, `research-390.png`, `research-320.png`, `research-modal.png`, `research-zoom-200.png` e `research-image-error.png` em `qa-artifacts/v5992`.

- Galeria com cinco imagens reais carregadas, créditos, direitos e link de origem.
- Modal: próxima imagem, seta esquerda, Escape e restauração do foco funcionaram.
- Zoom **CSS** 200% em 320 px sem overflow; não é teste de zoom nativo ou celular físico. Header/composer ficam muito comprimidos, embora sem vazamento horizontal.
- Reduced motion resultou em transição de `1e-06s`.
- Metadados expandidos e galeria preservados após reload.
- Falha de imagem explicitamente injetada mostra mensagem útil; removido o bloqueio, a imagem real volta a carregar.
- Nenhum evento `pageerror` nos drivers. Erros de rede da imagem abortada são esperados e não significam console integral sem erros de rede.

`extra-accepted.log`: IndexedDB real com duas bases, treze mensagens, quatro mensagens estruturadas do assistente e três mensagens de resultado. Downloads reais MD e CSV concluíram sem falha; arquivos `research-export.md`/`.csv` contêm fonte oficial e estado parcial, sem inventar síntese aprovada. A leitura agregada do SQLite temporário registrou treze mensagens e quatro jobs (`qa-performance-storage.json`). Contagens são da instância descartável, não dados do usuário.

## Limites

A moldura técnica ainda é extensa (status, cobertura, aviso lexical e mídia); o chat fica menos limpo do que a proposta premium original. O pedido de pesquisa universal plenamente fundamentada não passou. Tabelas de resultado real do modelo e todos os estados vazios não foram exercitados visualmente nesta rodada; os testes determinísticos existentes não substituem essa inspeção. Não há declaração de auditoria visual completa de todas as telas, FPS, acessibilidade integral ou integração em produção.
