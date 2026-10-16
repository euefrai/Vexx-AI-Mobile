# Vexx AI V5.3 — 3D Engine Foundation

## Decisão técnica

Um único motor: Three.js 0.180.0, empacotado com esbuild 0.25.10 e lockfile.
model-viewer oferece um bom visualizador GLB, mas as primitivas procedurais e a
seleção de partes exigiriam trabalho adicional ou outro renderer. Three.js atende
a ambos com o mesmo contexto. Não há CDN, runtime Node no Render, processamento
gráfico Python, serviço pago ou troca de modelo de IA para esta funcionalidade.

Referências técnicas consultadas:
- [Three.js: rendering on demand](https://threejs.org/manual/pages/rendering-on-demand.html)
- [Three.js: cleanup](https://threejs.org/manual/pages/cleanup.html)
- [Three.js: responsive design](https://threejs.org/manual/pages/responsive.html)
- [model-viewer: lazy loading](https://modelviewer.dev/examples/loading/)

O contrato leve carrega com o JDUI. O motor e o renderer são importados somente
ao clicar **Explorar em 3D**. Uma resposta textual comum não cria WebGL nem baixa
o motor. Componentes já visitados podem usar o cache do service worker.

## Contrato

Componente `model3d`, no envelope existente `JULIA-ui-message/v1`.
Validação espelhada em `model3d.py` e `public/model3d-schema.js`; JDUI delega ao
contrato e mantém seus fallbacks. Campos desconhecidos são rejeitados, não executados.

```json
{
  "version": "JULIA-ui-message/v1",
  "blocks": [{
    "type": "ui", "component": "model3d",
    "props": {
      "id": "demo", "version": 1, "title": "Cubo",
      "description": "Cubo geométrico interativo.",
      "objects": [{"id": "cube", "kind": "cube", "label": "Cubo"}],
      "color": "#8b9cf7", "scale": 1, "rotation": [15, 25, 0],
      "camera": {"distance": 6}, "lighting": "soft",
      "annotations": [{"objectId": "cube", "text": "O cubo possui seis faces quadradas."}],
      "autoRotate": false, "details": false
    }
  }]
}
```

| Campo | Limites |
|---|---|
| id | 1–40 caracteres ASCII alfanuméricos, hífen ou sublinhado |
| version | 1 |
| title / description | 120 / 500 caracteres Unicode |
| objects | 1–8; IDs únicos; cube, sphere, cylinder, pyramid |
| objeto: position / rotation / scale | três números de −3 a 3 / −360 a 360 graus / 0,25–2 |
| objeto: label / description | 100 / 500 caracteres |
| model | vazio ou `demo-cube`; exige objects vazio se definido |
| color | hexadecimal RGB com seis dígitos |
| scale / rotation | 0,25–2 / três números de −360 a 360 graus |
| camera.distance | 3–12 |
| lighting | soft ou studio |
| annotations | até oito; objeto existente e texto até 300 caracteres |
| autoRotate / details | booleanos estritos |
| source | derivada do catálogo; origem falsa é rejeitada |

Não existem campos src, url, HTML, callback, shader ou script. O texto é inserido
com textContent. Não se executa código do LLM. O teto de fences do JDUI permanece
em 24 KB; cada cena model3d tem teto adicional de 20 KB. Para GLB, a única URL é constante e local, sem fetch Python; o leitor
limita a resposta a 64 KiB antes do parse e rejeita URI, imagens e extensões.

## Catálogo e direitos

`public/models/demo-cube.glb`: cubo original com 24 vértices e 12 triângulos,
1.448 bytes, sem texturas. `tools/3d/create_demo.py` o reproduz. GLB e preview SVG
original estão sob CC0, com licença junto aos assets. O SVG é uma ilustração
genérica identificada como 2D, não uma foto ou render fiel de qualquer cena.
Three.js mantém sua licença MIT em `public/vendor/THREE-LICENSE.txt`.

## Fluxo de chat

- “Lucas, mostre um cubo em 3D.”
- “Mostre uma esfera girando.”
- “Mostre cubo, esfera, cilindro e pirâmide em 3D.”
- “Mostre um cubo GLB em 3D.”
- “Gire.”, “Amplie.”, “Restaure.”, “Pause.”, “Mostre os detalhes.”
- “Explique as partes desse objeto.” revela metadados disponíveis.

`intent.py` reconhece o domínio e `pc_agent.cmd_model3d` resolve a última cena
validada da mesma conversa e do mesmo dono. Os caminhos completo e SSE retornam
e persistem a cena sem LLM, pesquisa ou controle remoto. Um objeto sem modelo
conhecido recebe uma limitação textual; não há geração 3D livre.

Os comandos geram snapshots declarativos novos: o histórico não é apagado.
Se o visualizador dessa conversa estiver aberto, o snapshot seguinte o substitui
como visualizador ativo. Caso contrário, permanece o botão de abertura sob demanda.
Referências conversacionais usam o último snapshot salvo, não movimentos de câmera
ainda restritos ao estado local da interface. Sem cena anterior, comandos curtos
continuam no fluxo normal. “Pause o vídeo” e “Gire o mouse” não são comandos 3D.

A identidade central Lucas, histórico, conta e permissões remotas permanecem.
Os IDs técnicos Júlia/JDUI e a marca Vexx AI não foram renomeados.

## Controles e ciclo de vida

Arrastar com mouse ou toque gira; roda, botões e +/− ajustam distância. Setas dão
rotação acessível por teclado. Há animar/pausar, centralizar, restaurar, detalhes,
seleção por raycast ou lista de partes e ampliação dentro da mensagem (sem modal
que bloqueie o chat). A câmera olha sempre para a origem e o conteúdo é centralizado
por bounds; Centralizar recupera a distância inicial sem apagar a orientação.

Um único visualizador tem contexto GPU. Trocar de visualizador descarta o anterior;
remover a mensagem cancela fetch, frames, observers, listeners e recursos Three.js.
Fora da tela ou com documento oculto, não se agenda desenho. Sem animação, renderiza
apenas sob demanda. Reduced motion impede animação inicial, mas o usuário pode
acioná-la explicitamente. Erros e perda de contexto retornam ao preview 2D.

O estado de câmera/pausa reutiliza a persistência JDUI IndexedDB ↔ SQLite. A
sincronização preserva DOM 3D inalterado; uma substituição durante import retoma
a abertura solicitada, vinculada a dono, conversa, mensagem e ID do componente.

## Build e validação

```text
cd tools/3d
npm ci --ignore-scripts
npm run build
cd ../..
python tools/3d/create_demo.py
python -m pytest -q tests/test_model3d.py
```

Node é apenas ferramenta de desenvolvimento. Os assets versionados bastam para
deploy Python. O endpoint estático do motor entrega o gzip pré-gerado se aceito,
com Vary: Accept-Encoding; não há middleware comprimindo/bufferizando SSE.

Para QA, inicie `python tests/preview_workspace.py` e execute
`node tools/3d/qa.cjs` com Playwright disponível e Chrome instalado. O ambiente
usa conta, SQLite e credenciais descartáveis. Nunca apontar esse runner para
produção. Resultados e screenshots ficam em `qa-artifacts/3d/`.

## Limites desta versão

Não há upload de modelos, URLs externas, texturas, Draco/KTX, exportação 3D,
edição livre de malhas ou geração semântica de objetos. A renderização exige WebGL2;
os demais navegadores recebem o fallback. Mobile foi testado em viewport/toque
emulado no Chrome desktop; Android/iOS físicos continuam pendentes. Recarregar
o aplicativo inteiro offline ainda exige autenticação, conforme a política
existente; esta entrega não contorna essa barreira. A cena já aberta funciona
offline e os assets visitados são recuperáveis pelo service worker.
