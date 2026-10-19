# RELATÓRIO V5.7 FINAL — Research Stabilization & Production Quality

Data: 2026-10-18 · Base: `HEAD b91ab31` (V5.7.1) · Sem push, sem deploy,
sem reinício de serviços, sem contornar bloqueios, sem tocar em motor 3D /
Fajulto Studio / extensão da Júlia.

## Resumo executivo

Esta rodada fechou o GAP de qualidade de pesquisa que mais afetava o uso
real, com correções pequenas e verificáveis — não uma reescrita:

1. **Grounding com conteúdo lido** — páginas abertas passam a levar até
   1.200 chars do conteúdo real (ancorados no trecho relevante) ao prompt,
   em vez de um resumo de 400 chars do índice.
2. **"Analise esta página (URL)"** — capacidade mínima e honesta: lê UMA
   página com o mesmo `baixar` seguro (SSRF/redirect/teto), entrega o
   conteúdo real e avisa quando não consegue (bloqueio/ilegível/rede).
3. **Paridade JDUI do produto** — as 3 divergências reais entre
   `jdui.py` e `public/jdui.js` foram corrigidas (preço com fallback, tipo
   de `specs`, coerção de `item_de_listagem`).
4. **Correção de raiz na extração** — `trecho_usado` podia ficar fora do
   texto guardado (janela escolhida antes do corte de 8.000 chars); agora é
   sempre um fragmento do texto real, e a consulta da URL é limpa
   (palavras de pedido fora, URL decodificada) para não casar com menu.

Tudo verificado antes/depois com bateria determinística (10/16 → 16/16),
suíte **851 → 868 passed** (4 skipped), benchmarks congelados intactos
(34/34 e 59/59) e smoke externo real com provedores habilitados.

## Evidência (antes → depois)

| Verificação | Antes | Depois |
|---|---|---|
| Bateria de experiência (16) | 10/16 | **16/16** |
| Suíte completa | 851 passed | **868 passed / 4 skipped** |
| Paridade JDUI produto (Node) | 5 falhas | **0** |
| Página do usuário (URL) | inexistente | funcional e honesta (Wikipédia aberta; Magalu com aviso) |
| Grounding real | trecho ≤400 | conteúdo ≤1.200 (smoke: grounding 4.388 chars) |
| Root cause trecho⊆texto | `find = -1` (fallback) | `find = 5201` (artigo) |
| Shopping real | — | 2/2 confirmadas (URL + preço); bench 59/59 |
| Bench pesquisa | 34/34 | 34/34 (sem alterar gabaritos) |

Testes novos que **falham antes e passam depois** (17 no total):
`test_pagina_usuario_v57f.py` (6), `test_grounding_conteudo_v57f.py` (5),
`test_jdui_paridade_produto_v57f.py` (4, inclui harness Node),
`test_bench_experiencia_real.py` (1, roda a bateria inteira),
`test_web_extract_v57.py` (+1, trecho ⊆ texto guardado).
Artefatos: `qa-artifacts/v57/bench-experiencia-real-2026-10-18-antes.json`,
`...-depois.json`, `qa-artifacts/v57/smoke-externo-v57f-2026-10-18.json`.

## Avaliações por área

- **RESEARCH ENGINE** — funciona de verdade no fluxo principal (busca real →
  3 fontes lidas → prompt com conteúdo). Ficou mensuravelmente mais útil:
  o modelo passa a ver o conteúdo, não só manchetes.
- **SOURCE VALIDATION** — inalterado e respeitado: página aberta vs só
  encontrada têm marcas diferentes; nada foi promovido a "verificado".
- **SHOPPING** — smoke real 2/2 ofertas confirmadas na página do item, com
  URL e preço exibido; limitação honesta: `preco_valor` numérico ausente
  nesses cards (filtro de orçamento numérico limitado nesse caso).
- **DOCUMENT INTELLIGENCE** — já funcional via `docs_agent` (uploads/WS);
  bateria cobre TXT e CSV; OCR de PDF escaneado não existe (limitação
  declarada, sem texto inventado).
- **EVIDENCE GRAPH** — fence honesta (SUPPORTED exige quantidade com unidade
  compatível + tokens em comum); não exercitado em smoke real nesta rodada.
- **AGENT RESEARCH** — jobs com agentes e hipóteses cobertos pela suíte;
  hipóteses seguem fora do chat síncrono (PARTIAL declarado).
- **JDUI** — paridade do productcard corrigida e testada (Python + Node);
  validação em navegador real (mobile+desktop) **não executada** nesta
  rodada — pendência declarada, não mascarada.
- **PERFORMANCE** — números reais: busca 4,1s; leitura de URL 2,3s;
  shopping 41,5s; prompt com página 2,5s; sem browsers pesados no relay.
- **SECURITY** — nenhum caminho novo fora dos guardas existentes: URL do
  usuário usa o mesmo `baixar` (SSRF/DNS/redirects/teto/tipo); bloqueios
  nunca contornados; auth/RBAC/CSP/segredos intocados.
- **PRODUCTION READINESS** — **não aprovado para produção nesta rodada**:
  melhorias verificadas localmente; o serviço publicado não foi testado
  (deploy não autorizado) e faltam as validações de navegador real e de
  respostas via LLM.

## Limitações e riscos

- Extração determinística em páginas grandes (ex.: Wikipédia) traz resíduos
  de sidebar/marcação; instalar trafilatura/extruct exigiria avaliação de
  dependências (fora do escopo desta rodada).
- `preco_valor` numérico pode faltar em cards reais; preço exibido continua
  correto, mas gates numéricos não agem.
- Provedores externos bloqueados hoje (DDG/Magalu/MLB) — por regra, não
  contornados; a busca degrada para os saudáveis (bing).
- SSE (duplicação potencial no tail-emit), métricas sem chamador em produção
  e source_check só no shopping seguem documentados na matriz.

## Próximos passos sugeridos

1. Validação visual do JDUI em Chrome real (mobile + desktop) com o app
   rodando localmente — checklist de cards/imagens/tabelas/comparações.
2. Avaliação de respostas com LLM (Hermes já disponível) em bateria curta,
   com custo aprovado, medindo citações [S…] e honestidade sem fontes.
3. Avaliar trafilatura/extruct (licença/deps/RAM/Windows) para limpar a
   extração; decidir com benchmark antes/depois da bateria.
4. Gate de orçamento: extrair número quando o preço vier só em texto
   (regex já existente no shopping pode ser estendido com teste).
5. Só então preparar deploy autorizado e repetir o smoke no serviço
   publicado (distinção local × publicado documentada).

## Anexos

- `docs/V5_7_FINAL_PROGRESS.md` — progresso por checkpoint (A–I).
- `docs/RESEARCH_CAPABILITY_MATRIX.md` — matriz de estados por capacidade.
- `docs/RESEARCH_E2E_RESULTS.md` — bateria + smoke + 12 cenários.
- `tools/bench_experiencia_real.py` — bateria reproduzível (16 checagens).
- `tools/smoke_externo_v57f.py` — smoke externo reproduzível.
- Commit local nesta rodada (sem push): ver `git log -1`.
