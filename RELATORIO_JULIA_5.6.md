# Relatório Júlia V5.6 — 3D Visual Polish + Smart Assembly Foundation + Model Generation

Data: 17/10/2026 · Commits locais `0ba0fe4`, `7479bad`, `9519df6`, `41173a9`,
`bc26f12`, `a76b49b` (mais o commit do usuário `d74b669`, preservado entre as
fases) · **Sem push/deploy**

## Pedido

Evoluir o 3D existente da V5.3/V5.4 (base validada, não recriar) com:
(1) acabamento visual claro e bonito; (2) interação por conversa e por botões
(“mostre só a interna”, “esconda X”, “mostre como isso se conecta”);
(3) geração de modelos aproximados quando o objeto não está no catálogo, com
rótulo de fidelidade honesto (exato/aproximado/conceitual/educativo);
(4) fundações de montagem (papel, grupo interno/externo, ordem, conexões,
etapas, separado); (5) JDUI mais claro; (6) testes **incluindo QA real em
Chrome/WebGL** — JSON/schema sozinho não conta como sucesso. Sem deploy, sem
mexer na identidade/modelo/credenciais do Lucas, sem tocar na extensão da Júlia
ou no Fajulto Studio, sem assets de terceiros, sem APIs pagas, sem precisão de
engenharia falsa e sem contornar proteções de sites.

## Entregas por fase

### Fase 1 — Auditoria
Contratos congelados mapeados (primitivas, cenas clássicas, frases da V5.4.1,
paridade Python/JS, `provedores_reais()`), ferramentas de QA reais disponíveis
(Playwright 1.64.1 + Chrome já instalados em `tools/3d`).

### Fase 2 — Polimento visual (commit `0ba0fe4`)
Sombras suaves PCF (mapa 512, atualização só com movimento), luz de recorte,
chão `ShadowMaterial`, contornos `EdgesGeometry` com raio desativado, tone
mapping ACES (exposição 1,12), materiais 0,52/0,08, fov 38, palco com
gradiente. Motor Three reconstruído deterministicamente: 574.582 bytes crus /
146.978 bytes gzip (teste trava abaixo de 150.000).
Detalhes: [docs/JULIA_3D_VISUAL_POLISH.md](docs/JULIA_3D_VISUAL_POLISH.md).

### Fase 3 — Interação inteligente e fundações (commit `7479bad`)
Campos `role`/`group`/`order` por peça, operações de grupo
(`onlyGroup`), conexões (`related` + comando “mostre como isso se conecta”),
“explique como funciona”, botões “Ver só internas/externas” e “Ver conexões”,
linha de identificação da peça nos detalhes.
Detalhes: [docs/JULIA_3D_ASSEMBLY_FOUNDATION.md](docs/JULIA_3D_ASSEMBLY_FOUNDATION.md).

### Fase 6 — Catálogo local (`9519df6`) e geração por pesquisa (`41173a9`)
- `model3d_catalog.py`: 14 cenas procedurais originais (consoles, celular,
  controle, placa-mãe, notebook, gabinete, monitor, teclado, headset, mesa,
  suporte de celular, motor V8), ≤ 7.139 bytes cada, com grupos, papéis,
  ordem e ≥ 3 etapas. Frases congeladas da V5.4.1 preservadas (notebook e
  placa-mãe entram na família `computer`).
- `model3d_research.py`: assunto fora do catálogo → família de forma
  (disco/drone/ferramenta/cilindro/caixa) → **uma** consulta de dimensões em
  provedores públicos (orçamento ~7 s, 3 provedores, 8 resultados) → triplos
  mm/cm/m/pol viram proporção (rótulo `aproximado`) ou forma genérica
  (`conceitual`); sem template, sem resultado ou sem rede → limitação honesta
  (`None`), nunca geometria inventada. Cache em memória (6 h positivo/30 min
  negativo/32 assuntos). Gancho único em `cmd_model3d` com `pesquisa_web`
  (ambiente `JULIA_WEB_SEARCH`, padrão `1`).
Detalhes: [docs/JULIA_3D_MODEL_GENERATION.md](docs/JULIA_3D_MODEL_GENERATION.md).

### Fases 8/9 — JDUI e roteamento
Chips de fidelidade e fonte controlada nas mensagens; botões de grupo e
conexões adaptativos (desabilitam quando não se aplicam); continuações e
reconstrução preservadas; isolamento por dono/conversa coberto por teste.

### Fase 10 — QA real em Chrome/WebGL (commit `bc26f12`)
`tools/3d/qa-v56.cjs` (novo) e `qa-v54.cjs` (regressão) com Chrome real:
- Catálogo montado, grupo alternado com **diferença real de pixels**,
  conexões lidas, modo separado exercido, limpeza de buffers (33 criados/33
  deletados), zero erro de console.
- Cena de pesquisa determinística (busca falsa injetada) com rótulo e fonte
  visíveis na interface.
- Chat autenticado: pedido de dispositivo → continuação por grupo → canvas
  reutilizado → estado restaurado após reload; mobile sem overflow.
- Achado real da fase: fixture de QA sem `charset=utf-8` quebrava o schema no
  Chrome por causa do regex de fontes acentuado (o app real já declara meta
  charset e cabeçalho); corrigido nos dois fixtures.
Artefatos: `qa-artifacts/3d-v56/` e `qa-artifacts/3d-v54/`.

### Fase 11 — Desempenho (commit `a76b49b`)
Budgets mantidos (≤ 32 peças, ≤ 8 etapas, ≤ 20 KB por cena, gzip do motor
< 150.000). Medições locais (`tools/3d/qa-perf.cjs`): montar + abrir 304 ms na
primeira cena (inclui import do motor), 101 ms e 62 ms nas seguintes; cenas de
4,9–6,2 KB. QA V5.6 sem vazamento de buffers. Deltas em
[docs/JULIA_3D_PERFORMANCE.md](docs/JULIA_3D_PERFORMANCE.md).

### Fase 12 — Docs
Novos: [JULIA_3D_VISUAL_POLISH.md](docs/JULIA_3D_VISUAL_POLISH.md),
[JULIA_3D_MODEL_GENERATION.md](docs/JULIA_3D_MODEL_GENERATION.md),
[JULIA_3D_ASSEMBLY_FOUNDATION.md](docs/JULIA_3D_ASSEMBLY_FOUNDATION.md),
este relatório, [docs/V5_6_CATALOGO_VALIDACAO.md](docs/V5_6_CATALOGO_VALIDACAO.md)
e [docs/V5_6_PROGRESS.md](docs/V5_6_PROGRESS.md); roadmap atualizado.

## O que é implementado de verdade

- **Exato**: primitivas e GLB local (geometria determinística do produto).
- **Catálogo/template**: 14 cenas locais + 5 famílias paramétricas — forma
  desenhada por nós, medida ilustrativa/rotulada.
- **Pesquisa**: medidas citadas textualmente em fontes públicas viram
  proporção; a fonte aparece na mensagem; nada é baixado.
- **Fundações**: papéis, grupos, ordem, conexões, etapas e separado com
  validação estrita nos dois lados Python/JS.

## O que é aproximado/conceitual por decisão

- Proporção fora do triplo confiável: forma genérica rotulada conceitual.
- Ordem L×A×P das listagens pode variar; heurística de altura em disco/drone
  é declarada.
- Cores são ilustrativas; nenhum modelo é o produto oficial.

## O que NÃO foi feito (e por quê)

- CAD/medidas de engenharia, tolerâncias e encaixe físico: proibido pelo
  escopo (sem precisão falsa).
- Tutorial de montagem guiado com travas peça-a-peça: declarado como evolução
  futura sobre a fundação (sem data).
- Texturas/HDR/pós-processamento e download de assets de terceiros: fora.
- Push/deploy: por instrução explícita — tudo permanece em commits locais.

## Métricas

| Item | Valor |
|---|---|
| Suíte completa | **670 passed, 4 skipped** na execução final (os skips são testes de provedores ao vivo pulados honestamente por rede/bot-wall; execução anterior no mesmo dia: 671/3) — `qa-artifacts/3d-research-tests.txt` |
| Testes 3D | 78 (21 novos na V5.6) |
| Motor Three | 574.582 bytes crus / **146.978 gzip** (< 150.000) |
| Cenas do catálogo | 14, ≤ 7.139 bytes cada, ≥ 3 etapas |
| QA Chrome real | 33/33 buffers; centenas de draws; 0 erros de console |
| Montar+abrir | 304 ms (primeira), 101 ms, 62 ms |

## Como replicar

```powershell
# testes
& '..\.venv\Scripts\python.exe' -m pytest -q tests

# QA em Chrome real (com tests/preview_workspace.py ativo na 8770)
node tools\3d\qa-v56.cjs
node tools\3d\qa-v54.cjs
node tools\3d\qa-perf.cjs
```

## Limitações declaradas

- Android/iOS físicos, Safari, leitor de tela real, bateria e rede móvel
  continuam pendências de medição (herdadas da V5.3).
- Provedores públicos variam no tempo; a resposta sem fonte é limitação
  honesta.
- A pesquisa lê texto público no momento da consulta; pode citar medida
  desatualizada — o rótulo e a fonte deixam isso explícito.
- Nenhum resultado fictício foi usado para “fechar” fase: tudo que está aqui
  foi executado localmente e tem teste ou artefato correspondente.
