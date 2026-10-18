# Júlia 3D — polimento visual (V5.6)

Data: 17/10/2026 · Commit local `0ba0fe4` (+ ajustes posteriores da V5.6) ·
**Sem push/deploy**

Este documento descreve o que mudou no acabamento visual do 3D na V5.6, por que
cada mudança existe, o que ficou de fora por decisão e como o resultado foi
verificado em Chrome real. Ele complementa
[JULIA_3D_ENGINE.md](JULIA_3D_ENGINE.md) (motor e import sob demanda),
[JULIA_3D_INTERACTIONS.md](JULIA_3D_INTERACTIONS.md) (contrato de interação) e
[JULIA_3D_PERFORMANCE.md](JULIA_3D_PERFORMANCE.md) (orçamentos medidos).

## Princípios

- **Claro e bonito sem mentir**: o visual melhora a leitura da forma e da
  profundidade; cor e medida continuam ilustrativas e nunca viram promessa de
  engenharia.
- **Sem assets de terceiros**: nenhuma textura, HDR, imagem ou modelo externo
  entrou no repositório. Tudo continua procedural e local.
- **Renderização sob demanda**: o desenho acontece por interação, animação
  explícita ou redimensionamento; nada de loop contínuo em segundo plano.
- **Um contexto WebGL**: abrir outro visualizador descarta o anterior; a V5.6
  não mudou essa regra.

## O que mudou

### Luz, sombra e palco

- **Sombras suaves reais** (`PCFSoftShadowMap`) com mapa de 512 px na luz
  principal. O mapa é estático (`shadow.autoUpdate = false`) e só é atualizado
  quando a cena se move (arraste, zoom, animação, etapas) — o custo não corre
  sozinho.
- **Luz de recorte (rim light)** discreta para separar silhuetas do fundo
  escuro, especialmente em peças escuras internas.
- **Chão com `ShadowMaterial` circular**: a sombra aparece sem desenhar um
  piso opaco, mantendo o palco leve e legível.
- **Gradiente de palco** no CSS (`.m3-stage`) para dar profundidade sem
  textura.

### Materiais e contornos

- Materiais com `roughness` 0,52 e `metalness` 0,08: menos brilho plástico,
  leitura melhor das faces; as cores continuam vindo de `color` no schema.
- **Contornos discretos** (`EdgesGeometry` + `LineSegments`) nos cubos e no
  GLB local. As linhas usam detecção de raio desativada (`raycast = () => {}`):
  o contorno nunca “rouba” o clique de uma peça.
- **Tone mapping ACES Film (`ACESFilmicToneMapping`)** com exposição 1,12:
  altas luzes menos estouradas e sombras menos chapadas.
- Câmera com **fov 38** e enquadramento diagonal 2,45: cenas pequenas e
  grandes cabem no quadro inicial sem corte.

### UI da mensagem 3D

- **Chips de fidelidade** (`.m3-chips`): “Modelo exato”, “Modelo aproximado”,
  “Modelo conceitual” conforme `precision`, mais o chip “Cena educativa” para
  cenas com `education`. O usuário sabe de imediato o que está vendo.
- **Linha de identificação da peça** nos detalhes: papel
  (Estrutural/Opcional), grupo (Interna/Externa) e “Montagem #N” (ordem), além
  das relações registradas.
- Botões novos de leitura da cena (“Ver só internas”, “Ver só externas”, “Ver
  conexões”) descritos em
  [JULIA_3D_ASSEMBLY_FOUNDATION.md](JULIA_3D_ASSEMBLY_FOUNDATION.md).

## O que ficou de fora (de propósito)

- Texturas, normal maps, HDR, bloom, sombra por contato, SSAO e pós-processamento.
- Segunda fonte de luz com sombra e sombras dinâmicas contínuas.
- Rótulos flutuantes 3D sobre peças (os detalhes ficam na lista acessível).
- Qualquer ajuste de cor automática “bonita”: a cor da peça é um dado do schema,
  verificável e igual nos dois lados Python/JavaScript.

## Verificação

- **Testes**: paridade Python/JavaScript das props, orçamento de gzip do motor
  (< 150.000 bytes; medido 146.978) e suítes 3D completas (78 testes verdes na
  V5.6).
- **Chrome real / WebGL** (Playwright com canal `chrome`, GPU ANGLE/Intel UHD):
  `tools/3d/qa-v54.cjs` (regressão) e `tools/3d/qa-v56.cjs` verificam pixels
  de verdade — trocar grupos, explodir e isolar mudam a imagem renderizada,
  buffers GL são liberados (33 criados/33 deletados) e não há erro de console.
  Screenshots: `qa-artifacts/3d-v56/` (novos) e `qa-artifacts/3d-v54/`
  (regenerados; o polish aparece também nas cenas antigas).
- **Limite honesto**: as medições são do desktop local com Chrome headless;
  Android/iOS físicos e Safari continuam pendências de medição declaradas em
  [JULIA_3D_PERFORMANCE.md](JULIA_3D_PERFORMANCE.md).
