# V5.9.5 — JDUI

Componentes e schema existentes preservados. Cards de fonte usam corte por limite de token para evitar alteração de números; distinguem resumo, HTML e PDF com extração limitada. Tarifa declarada mantém aviso prioritário de disponibilidade não confirmada, sem repetir a mesma linha. Cobertura de pesquisa separa execução concluída de dados completos. Sem execução de código do modelo.

A inspeção a 200% revelou botões estreitos quebrando palavras. `public/styles.css` agora permite empilhar as ações das fontes por espaço disponível; recaptura com CSS final confirmou rótulos legíveis e largura contida.

## Provas executadas

- Testes de schema, paridade e pesquisa: 116 aprovados no conjunto JDUI/contexto; regressões adicionais no conjunto final focado (72, sobrepostos). Suíte completa final: 1.354 aprovados, quatro ignorados.
- `node --check public/jdui.js` e `node --check public/app.js`: passaram; JavaScript desses arquivos não alterado.
- Playwright CLI, Chrome headless, fixture local servida exclusivamente com CSS/JS e quatro cards: dois PDFs reais e dois casos sintéticos identificados (tarifa e HTML). JSON preservado em `qa-artifacts/v595/jdui-fixture.json`.
- Desktop 1280 × 900, mobile 390 × 844 e CSS zoom 200%: capturas em `qa-artifacts/v595/jdui-*.png`. Mobile `scrollWidth=390`, `innerWidth=390`, sem overflow horizontal medido.
- Dez links, nenhum protocolo inseguro; Tab alcançou link real do primeiro PDF. Cards montados após validação JS; quatro itens válidos. Logs `ui-*.log`.
- Console registrou favicon 404 do servidor de fixture; não houve erro de componente observado. Não declarar console totalmente limpo.

## Limites

Não houve login, navegação autenticada completa, compra/reserva, playback de vídeo, análise de imagem ou teste de leitores de tela. Zoom CSS não equivale a todas as opções de zoom/acessibilidade do sistema. Testes visuais comprovam estes quatro cards, não todos os componentes do produto. Não foram modificados sidebar, projetos, 3D, identidade, Studio ou extensão nesta fase de pesquisa.
