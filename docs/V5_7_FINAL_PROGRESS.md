# V5.7 FINAL — Research Stabilization & Production Quality — Progresso por checkpoint

> **Atualização V5.7.2 (2026-10-19):** `preco_valor` numérico normalizado e
> extração reescrita (sem resíduos). As menções abaixo são históricas da V5.7;
> evidências em `docs/V5_7_2_PROGRESS.md`.

Objetivo: tornar o Research Engine utilizável de verdade (busca confiável,
recuperação de páginas/documentos, fontes verificáveis, shopping exato, JDUI
real, E2E honesto), consolidando o existente — sem nova arquitetura, sem
push/deploy, sem contornar CAPTCHA/bot-wall, sem tocar no motor 3D, Fajulto
Studio ou extensão da Júlia, sem inventar/mascarar testes.

- Base: `HEAD b91ab31` (V5.7.1) — nada foi pushado ou deployado.
- Data: 2026-10-18. Formato de evidência: defeito reproduzível → menor
  correção robusta → teste que falha antes e passa depois → regressões →
  commit local.

## Baseline (checkpoint A — auditoria)

- Suíte completa de partida: **851 passed, 4 skipped** (2 warnings, 173s).
- Nova bateria de experiência real (`tools/bench_experiencia_real.py`, 16
  checagens determinísticas, sem rede, DNS mockado): **10/16 ok**. As 6
  falhas eram legítimas e viraram o escopo desta rodada:
  1. `geral_grounding_carrega_conteudo_lido` — prompt recebia só trecho ≤400;
  2. `pagina_usuario_lida_entra_no_prompt` — "analise esta página (URL)" não existia;
  3. `pagina_usuario_bloqueada_honesta` — idem (sem aviso honesto de URL);
  4. `jdui_js_preco_fallback` — JS sem fallback `preco`;
  5. `jdui_js_item_de_listagem` — JS com `=== true` em vez de coerção;
  6. `jdui_js_specs_tipo` — JS ignorava `specs` inválido em vez de recusar.
- Auditoria (subagentes + leitura direta): as divergências reais de paridade
  JDUI produto são **exatamente 3** (as acima); a alegação de unwrap
  divergente em productgrid/productcompare era falsa (Python também
  desembrulha). Demais achados (SSE duplicação no tail-emit, métricas sem
  chamador em produção, hipóteses só em jobs, source_check só no shopping)
  foram classificados na matriz de capacidades, sem expansão de escopo.
- Artifícios de auditoria descartados: bateria tinha 3 bugs próprios,
  corrigidos antes do "antes" limpo (sem eles o "antes" seria desonesto).

## Checkpoint B — Busca e recuperação

Sem mudança de produção nesta rodada (o orquestrador V5.7.1 já é a base).
Verificado:

- Bateria: `geral_sem_resultados_honesto` (provedor vazio → estado
  `sem_resultados` + aviso honesto) — ok antes e depois.
- Smoke externo real (2026-10-18): `pesquisa_rapida` → estado `ok`, provedor
  **bing** saudável, 3 fontes **abertas** com conteúdo lido (4,2s).
- Ambiente externo (não contornado): DDG com bot-wall, Magalu 403, MLB 403 —
  registrados como bloqueio, nunca como "sem resultados".

## Checkpoint C — Extração de páginas e documentos

Defeito reproduzível (sonda real, Wikipédia): `trecho_usado` era escolhido
sobre o texto completo e podia ficar **fora** de `texto[:teto]` (8.000) —
`find` falhava (-1) e o conteúdo lido caía no fallback (menu de navegação).

- Correção na origem (`web_extract.extrair_pagina`): `trecho_usado` agora é
  calculado sobre o mesmo texto guardado (`texto_final = texto_art[:teto]`).
  Sonda depois: `find = 5201` (conteúdo do artigo).
- `research._janela_lida(texto, ancora)`: conteúdo lido começa no trecho
  relevante (≤1.200 chars), não nos primeiros chars crus da página.
- `research._consulta_limpa`: remove palavras de pedido ("analise", "página",
  "link"…) e decodifica a URL ("Fotoss%C3%ADntese" → "fotossíntese"), para a
  âncora não casar com menu.
- Teste novo `test_trecho_usado_fica_dentro_do_texto_guardado` (falha antes,
  passa depois) + `test_consulta_limpa_tira_pedido_e_abre_a_url` +
  `test_janela_lida_comeca_no_trecho_relevante`.
- Documentos (PDF/DOCX/TXT/MD/CSV/TSV/XLSX/HTML/JSON) permanecem no
  `docs_agent` (uploads/WS); bateria cobre `contrato.txt` (2.649 chars) e
  `vendas.csv` (42 chars, 1 chunk). OCR de PDF escaneado não existe —
  sinalizado como limitação, sem inventar texto.

## Checkpoint D — Evidências e fontes

- Grounding honesto: página **aberta** usa `texto_lido` (≤1.200, real);
  página **só encontrada** mantém trecho ≤400 com a marca "NÃO lida".
- Nenhuma promoção FETCHED→VERIFIED: claims continuam exigindo quantidade com
  unidade compatível + tokens em comum (regressões da suíte intactas).
- Cache antigo sem `texto_lido` cai no comportamento anterior (retrocompatível).

## Checkpoint E — Shopping e links exatos

Sem mudança de produção nesta rodada (V5.7.1 é a base). Smoke externo real:

- `shopping.pesquisar("fone bluetooth até R$ 300")` → **2/2 ofertas
  confirmadas na página do item**, com URL do produto e preço exibido
  (R$ 25,74 / R$ 110,12, KaBuM); página de categoria da Amazon ignorada com
  log honesto. 41,5s.
- Limitação registrada na V5.7 (**resolvida na V5.7.2**): `preco_valor` numérico
  ausente nos 2 cards do smoke (preço em texto); na V5.7.2 a normalização usa
  `Decimal` e os 2/2 cards do smoke externo têm preço numérico.

## Checkpoint F — Respostas e JDUI

- Paridade backend×frontend do productcard (contrato canônico `jdui.py`):
  1. `preco` numérico sem `preco_valor` agora tem fallback no JS;
  2. `specs` lista não vazia/string/true **recusam** (lista vazia/falsy → {});
  3. `item_de_listagem` usa coerção booleana (igual a `bool()`), não `=== true`.
- Harness Node em teste (`tests/test_jdui_paridade_produto_v57f.py`): falha
  antes, passa depois; lado Python coberto no mesmo arquivo.
- Página do usuário no prompt: "analise esta página: URL" lê UMA página e
  entrega o conteúdo real com aviso de fonte; bloqueio vira aviso honesto
  (`bloco_pagina_usuario`) e **não** dispara pesquisa genérica por cima.

## Checkpoint G — Agentes, hipóteses e continuidade

Sem mudança de produção. Estado real (na matriz):

- `hypothesis_engine` roda em jobs (não no chat síncrono); agentes de
  pesquisa via `/research` existem e a suíte os cobre (SSE ordenado/replay).
- Fases SSE reais existem no shopping ("🔎 {fase}…"); risco de duplicação no
  tail-emit (`pc_agent.py:3951-3957`) permanece documentado como pendência.

## Checkpoint H — Performance e segurança

- Leitura de URL do usuário reusa o MESMO `baixar` (SSRF/DNS/redirects
  revalidados/teto de tamanho/tipo) — nenhuma exceção para URL do usuário.
- Tempos reais do smoke: busca 4,1s; URL 2,3s; shopping 41,5s; montagem de
  prompt com página 2,5s. Limites e gates do Render Free preservados.
- Bloqueios (bot-wall/403) não são contornados em nenhum caminho novo.

## Checkpoint I — E2E real e aceitação

- Bateria: **16/16** (antes 10/16) — artefatos `-antes.json` / `-depois.json`.
- Suíte completa: **868 passed, 4 skipped** (17 testes novos).
- Benchmarks congelados: pesquisa **34/34**, shopping **59/59**.
- Smoke externo leve com rede real (`tools/smoke_externo_v57f.py`): Hermes
  disponível (porta 8645, `/v1/models` HTTP 200); pesquisa real ok; página
  do usuário lida (Wikipédia); Magalu bloqueada com aviso honesto; shopping
  real 2/2 confirmadas; prompt contém a amostra do texto lido.
- **Serviço publicado NÃO foi testado** (sem deploy autorizado) — a
  distinção local × publicado está em `docs/RESEARCH_E2E_RESULTS.md`.

## Números consolidados

| Métrica | Antes | Depois |
|---|---|---|
| Suíte completa | 851 passed / 4 skipped | **868 passed / 4 skipped** |
| Bateria de experiência (16) | 10/16 | **16/16** |
| Benchmark pesquisa (congelado) | 34/34 | 34/34 |
| Benchmark shopping (congelado) | 59/59 | 59/59 |
| Divergências de paridade JDUI produto | 3 | **0** |
| Página do usuário (URL) | não existia | funcional e honesta |

## Pendências honestas (na matriz, sem expansão de escopo)

- ~~Extração determinística de páginas grandes (Wikipédia) tem resíduos de
  sidebar/marcação no início da janela lida (trafilatura não instalada).~~
  **Resolvido na V5.7.2** (extração reescrita; sem resíduos).
- ~~`preco_valor` numérico ausente em cards reais do smoke (preço em texto).~~
  **Resolvido na V5.7.2** (normalização Decimal; 2/2 com preço numérico).
- JDUI em navegador real (Chrome mobile/desktop) não executado nesta rodada.
- Respostas via LLM não exercitadas no smoke (Hermes disponível; custo não
  autorizado); SSE duplicação, métricas sem chamador e hipóteses job-only
  seguem na matriz como PARTIAL.

## Arquivos alterados/criados

- Produção: `research.py`, `pc_agent.py`, `web_extract.py`, `public/jdui.js`.
- Testes: `tests/test_pagina_usuario_v57f.py`, `tests/test_grounding_conteudo_v57f.py`,
  `tests/test_jdui_paridade_produto_v57f.py`, `tests/test_bench_experiencia_real.py`,
  `tests/test_web_extract_v57.py` (+1).
- Ferramentas: `tools/bench_experiencia_real.py`, `tools/smoke_externo_v57f.py`.
- Artefatos: `qa-artifacts/v57/bench-experiencia-real-2026-10-18-antes.json`,
  `...-depois.json`, `qa-artifacts/v57/smoke-externo-v57f-2026-10-18.json`.
