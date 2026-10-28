# Transmissão e controle mobile — segunda etapa

Base: `907bbe2`. Validação local concluída e envio para `main` autorizado pelo usuário. As mudanças usam o protocolo do agente já instalado; não exigem reinício do PC Agent. O resultado do deploy deve ser verificado separadamente.

## Correções e melhorias

- Cadência mínima de captura de 125 para 100 ms, até 10 quadros/s quando captura/rede permitem. Uma captura por vez; sem fila de imagens; mantém cancelamento, descarte de frames antigos, limites e espera em 429. O intervalo após uma resposta demorada caiu de 16 para 4 ms.
- Perfis de imagem automática, mais leve (960 px/q65) e mais nítida (1920 px/q85). A proteção por latência acima de 900 ms continua reduzindo resolução/qualidade, inclusive no perfil nítido.
- Modo touchpad: movimento relativo enviado durante o gesto, posição local imediata e descarte de movimentos intermediários pendentes. Limite de 10 envios de movimento/s; cliques/texto preservam a fila ordenada. Frames anteriores ao movimento não puxam o cursor de volta. A posição real recebida volta a prevalecer após os comandos.
- Toque direto, duplo toque, botão direito, arrasto e rolagem com dois dedos preservados. No touchpad, tocar clica na posição do cursor; deslizar só move o mouse.
- Corrigida corrida entre clique pendente e digitação: antes de texto/tecla, envia o clique que deve focar o campo remoto.
- Botões de setas esquerda/direita para mover o cursor de texto pelo celular, com os mesmos controles de permissão das demais teclas.
- Ao abrir o teclado pelo botão, o visualizador acompanha altura/largura/offsets de `visualViewport`. Tela, barra de ações horizontal e campo ficam na área visível. Botões de teclas mantêm foco no campo.
- Tela cheia inclui controles e teclado. Fechar/desconectar restaura o layout e remove imagem, foco e cursor.
- Cache do service worker atualizado.

## Arquivos

`public/remote.js`, `public/index.html`, `public/interface.css`, `public/sw.js`, `tools/test_remote_stream.cjs`, `tools/chrome_remote_latency.py` e este relatório. Sem mudanças no protocolo, permissões, banco, extensão ou código do agente.

## Verificação

- Testes focados de controle remoto: **40 aprovados**.
- Harness Node: gestos, frame único em voo, descarte de resposta antiga, blobs, Unicode/IME, lotes, cancelamento, scroll pequeno, clique antes de texto, movimento antes de soltar, coalescência e alinhamento ao viewport.
- Chrome real headless, emulação mobile, HTML do visualizador e CSS do projeto, CSP de produção: JPEG decodificado, cursor, eventos de toque, texto com acentos/emoji, troca de qualidade, desconexão e ausência de erros de página.
- Geometria em 390×420: tela entre y=58 e 291; campo entre y=366 e 410. Testado também 320×320 e fechamento/reabertura do teclado.
- Última medição do componente: **9,73 quadros/s**, 35 frames, fonte JPEG sintética com 40 ms de atraso. A execução anterior desta etapa marcou 9,8. O registro da etapa anterior era 7,66; os cenários incluem interações diferentes, portanto não constituem benchmark controlado da rede real.
- Evidência: `qa-artifacts/remote-touchpad-browser/result.json`, captura local `mobile-component.png`, `qa-artifacts/remote-touchpad-focused.log` e log da suíte completa.
- Suíte completa: **1946 aprovados, 4 ignorados, 2 avisos existentes**, em 249,43 s, saída 0. Avisos de depreciação MSS e Starlette/TestClient; nenhum teste removido. Após os últimos ajustes de interface, o harness Node e o smoke Chrome foram executados novamente.
- Sintaxe JavaScript e `git diff --check` sem erros.

## Limites reais

A emulação reduz o viewport, mas não abre um teclado físico Android/iOS. Não houve sessão remota autenticada pela internet, medição WAN ou acionamento de mouse/teclado no desktop do usuário. A transmissão continua baseada em JPEG pelo relay, com teto de 10 FPS; latência real depende da rede e do PC.

O botão Teclado abre a digitação. Detectar automaticamente campos de aplicativos do Windows não é possível a partir dos pixels da captura atual e não foi simulado como funcionalidade pronta. O modo de toque direto mantém o arrasto atômico ao soltar; o movimento contínuo novo está no touchpad, sem manter botão do mouse pressionado pela rede.
