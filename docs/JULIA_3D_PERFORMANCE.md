# V5.3 — desempenho e limites medidos

Medições locais de 2026-10-16, Windows, Chrome headless instalado no computador,
WebGL 2.0 real: **ANGLE / Intel UHD Graphics / Direct3D11**. Não são benchmarks
de Render Free, Android físico ou Safari. Evidência: `qa-artifacts/3d/metrics.json`
e screenshots; runner reproduzível em `tools/3d/qa.cjs`.

## Rede e build

| Asset | Tamanho |
|---|---:|
| Three.js + GLTFLoader, ESM minificado | 572.055 bytes (558,6 KiB) |
| Gzip pré-gerado entregue pelo endpoint estático | 146.171 bytes (142,7 KiB) |
| Schema leve carregado junto ao JDUI | aproximadamente 3,3 KiB |
| Renderer/controles carregados sob demanda | aproximadamente 13 KiB |
| GLB original | 1.448 bytes |
| Preview SVG genérico | 630 bytes |

O motor é importado apenas quando se abre o componente. A QA intercepta os
requests e verifica que não existe download de motor antes dessa ação. O service
worker não inclui o motor nem o GLB no precache: quatro caminhos 3D públicos são
armazenados sob demanda, com chaves canônicas sem multiplicação por querystring.
As APIs privadas seguem fora do cache. Uma nova versão do shell invalida a antiga.

O gzip é produzido no build, servido por FileResponse com Vary: Accept-Encoding.
Um teste confirma equivalência dos bytes descomprimidos e negociação gzip, identity,
q=0 e q=0.5. Não há compressão dinâmica no backend nem interferência no SSE.

## Renderização

- Um contexto/visualizador ativo; abrir outro descarta o anterior.
- GPU em low-power, sem sombras, pós-processamento, texturas ou antialiasing.
- Pixel ratio limitado a 1,5 e largura de framebuffer a 900 pixels; altura lógica
  até 640, escala geométrica e câmera limitadas pelo schema.
- Esfera com 20×12 segmentos, cilindro com 20, pirâmide com quatro lados.
- No máximo oito objetos procedurais; GLB até 64 KiB, com catálogo de um arquivo.
- Sem animação, desenho somente por interação/redimensionamento.
- Animação limita desenhos a aproximadamente 30 Hz. Fora da tela ou com documento
  oculto, requestAnimationFrame deixa de ser agendado.
- Reduced motion inicia pausado. Animação explícita continua disponível.

Na amostra de 1.013 ms com CPU throttling **4×**, uma esfera gerou **31 chamadas
de desenho**. É uma amostra curta de cena simples na GPU integrada do desktop,
não uma promessa de FPS para qualquer celular. A GPU não foi desacelerada pela
configuração de CPU do DevTools. A interação por toque foi exercida por eventos
Chrome Input em viewport 390×844, sem overflow horizontal.

## Recursos e memória

A sequência de cubo, esfera, cilindro, pirâmide, GLB e combinação criou **35
buffers GL** e chamou deleteBuffer para os **35**; ao desmontar, ficaram **zero
canvases**. Geometrias, materiais, texturas eventualmente existentes, render lists,
contexto, listeners e observers têm caminhos explícitos de descarte. Fetch de GLB
é abortável. Não há pool de renderizadores nem vários modelos em paralelo.

Snapshots CDP desta execução:

| Momento | Heap JavaScript usado | Listeners reportados |
|---|---:|---:|
| Um visualizador inicial | 4.821.860 bytes | 68 |
| Depois da sequência, antes de GC | 7.283.324 bytes | 282 |
| Depois de descarte e GC explícito | 4.200.888 bytes | 34 |

Os números abrangem a página de QA, não apenas o componente. GC explícito é
instrumentação de teste, não rotina de produção. Contar buffers e snapshots de heap
não mede RAM da GPU nem prova ausência de vazamentos em sessões de várias horas.
Ainda é necessário soak test em Android/iOS modestos e medição energética real.

## Falhas e compatibilidade

Perda real de contexto WebGL via extensão do navegador restaura o preview e permite
reabrir. Modelo excedendo 64 KiB é recusado sem tela preta. O cenário sem WebGL usa
Chrome com getContext WebGL desabilitado por instrumentação: comprova o fallback,
mas não certifica todos os navegadores sem suporte. Texto e demais mensagens ficam
disponíveis. Preview é identificado como ilustração 2D genérica.

A sessão aberta recuperou o motor via service worker sem rede e abriu uma cena.
Ao recarregar todo o aplicativo offline, a política de autenticação existente
mostra login; isso foi registrado, sem contornar a segurança para liberar 3D.

## Pendências de medição

Android/iOS físicos, Safari, WebGL1-only, leitor de tela real, bateria, limite
de memória sob pressão, rede móvel com latência/perda e ensaio prolongado.
Nenhuma afirmação de “performance excelente” ou certificação mobile é feita.
