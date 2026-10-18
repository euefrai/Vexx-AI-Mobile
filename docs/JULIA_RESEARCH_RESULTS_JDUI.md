# Júlia — Resultados de pesquisa no JDUI (V5.7)

Como resultados de pesquisa aparecem na interface: cards de fonte clicáveis,
cards de produto com links exatos, selos honestos de link/imagem, galerias,
tabelas e gráficos — sem Markdown cru quebrado, sem URL gigante e sem
duplicação de fontes. Tudo com os componentes existentes do JDUI
(`public/jdui.js`, contrato validado por `public/jdui.py`).

## 1. Fontes (`R.sources`)

Cartão por fonte:

- **título** do documento;
- **badge de estado**: `Encontrada` / `Aberta` / `Utilizada`
  (classe `jdui-badge st-*`);
- **domínio · data**;
- **trecho literal** (proveniência — na V5.7 nunca mais vindo de
  referências/bibliografia);
- botão **"Abrir fonte ↗"** (`target="_blank"`,
  `rel="noopener noreferrer"`) — fonte sempre clicável, nunca URL crua como
  texto no meio da resposta;
- `renderProvenance` mostra as origens usadas.

## 2. Cards de produto (link e imagem exatos)

`productcard` / `productgrid` / `productcompare` / `productdetails` /
`productgallery` (contrato 1..8 imagens) usam dados já validados pelo
`shopping.py` — a interface não inventa nem "conserta" dado ausente:

- **Preço** ausente aparece como "Preço não confirmado" (nunca chute).
- **Selo de link** (`productSelo`/`SELO_LINK`): `verificado`,
  `verificação parcial`, `link não verificado`, `link REPROVADO` e o aviso
  de listagem ("link do item veio de listagem — página do item NÃO
  aberta"). O botão de compra usa `url_item > url_final > url`.
- **Selo de imagem (novo na V5.7, `productImgSelo`)**:
  - `verificado` → sem selo (estado neutro);
  - `parcial` → "Imagem não confirmada";
  - `nao_verificado` → "Imagem não verificada";
  - `reprovado` → "Sem foto confirmada" (a imagem foi removida pelo
    backend) com o motivo no `title`.
  Foto não verificada **nunca** aparece como confirmada.
- **Galeria**: como `verificar_imagens` remove a imagem `reprovado` do
  produto, a galeria só consegue exibir imagem aprovada ou não verificada
  (com o selo do card).

## 3. Links no chat (Markdown)

- **Autolink** (`rotuloUrl`, novo): URL longa vira rótulo curto
  `host + caminho` (ex.: `moura.com.br/blog/sistema-de-freios`), com
  `title` da URL completa e `href` intacto — fim do layout quebrado.
- **Citações `[S1]`** viram links reais quando o mapa de fontes existe
  (`class="citation"`); `[S2]` sem fonte permanece texto.
- **Imagens**: `chat-img` com `loading="lazy"`, `decoding="async"`,
  `referrerpolicy="no-referrer"`; nenhum `onerror` inline (XSS do smoke).
- **Tabelas**: `table-wrap` responsivo (unidades são responsabilidade do
  conteúdo/proveniência; a tabela só renderiza o que veio).
- **Código/blocos**: fence segura sem executar HTML (`widget-iframe` com
  `sandbox=""` sem scripts; SVG sanitizado; dual-view Interface|Código para
  quizzes).

## 4. Bloco "Fontes:" da resposta (novo na V5.7)

`pc_agent.anexar_fontes` só omite o bloco estruturado quando já existe um
**cabeçalho** "Fontes:" (com ou sem `#`/`**`) seguido de link http em até
1500 caracteres. Antes, qualquer menção à palavra na resposta escondia as
fontes reais; agora menção solta não esconde e lista real não duplica.
Testes: `tests/test_pc_agent_fontes_v57.py`.

## 5. Visualizações de dados (herdadas, mantidas)

`chart` (SVG a partir de dados reais, nunca série inventada), `dashboard`
(com cartões/citações), `compare`, `table`, `evidencegraph`, `diagram`,
`roadmap`. Sem dependências novas e sem tocar no motor 3D.

## 6. Verificação V5.7

- `node --check public/app.js public/jdui.js` — sintaxe ok.
- Suíte JDUI (`test_jdui*.py`): 34/34.
- Smoke de frontend (`test_frontend_smoke.py`): 14/14 (Markdown, autolink,
  citações, imagens, XSS, tabelas, dual-view).
- Regressão completa: 700 passed / 4 skipped.

## 7. Pendências honestas

- O selo de imagem cobre os 3 primeiros produtos com imagem por busca
  (`verificar_imagens(maximo=3)`); os demais mantêm imagem **sem selo** —
  estado neutro, nunca "confirmada".
- Listas de fontes em formatos exóticos (tabela Markdown) não são
  reconhecidas como bloco "Fontes:" e o bloco estruturado é anexado — nunca
  esconde nem duplica link.
