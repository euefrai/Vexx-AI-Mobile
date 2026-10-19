# Relatório Júlia V5.7.1 — Hotfix de Confiabilidade da Descoberta (Shopping)

Data: 18/10/2026 • Base publicada: `020c85f` (V5.7) • Hotfix **local** —
commit desta entrega no topo de `git log` • **Sem push e sem deploy** •
Alterações restritas a `shopping.py`, um arquivo de testes novo, este
relatório e os 3 docs citados; nada mais foi tocado.

## Pedido

Corrigir o curto-circuito da descoberta de compras: resultados irrelevantes
de ddg/ddg-lite (anúncio, blog, índice) encerravam a cadeia antes do
provedor web → 0 produtos em consultas que antes encontravam ofertas reais.
Sem reescrever o Research Engine, sem neutralizar provedores no E2E, sem
mascarar falhas; gate de utilidade comercial genérico, testes determinísticos
com fixtures congeladas, E2E real como critério de aceitação, observabilidade
estruturada e preservação das validações V5.7 / correspondência V5.5.

## 1. Causa-raiz (exata)

Dois curto-circuitos encadeados, **pré-existentes** (auditoria confirmou
código idêntico no commit `a77bbeb`, antes da V5.7):

1. `shopping.buscar_com_fallback` (antigo, linhas 1393–1395):

   ```python
   ddg, detapas = buscar_ddg_chain(consulta)
   etapas.extend(detapas)
   if ddg:                 # QUALQUER resultado não-vazio — lixo incluso
       return ddg, etapas  # → nunca chega ao buscar_web_v55
   ```

2. `shopping.buscar_ddg_chain` (antigo, linhas 1347–1349): “primeira base
   com resultado vence” — lixo do DDG impedia até a tentativa do DDG-Lite.

Reprodução real (smoke oficial da manhã, `020c85f`): para “me mostre um
notebook…” e “me mostre um fone bluetooth”, as etapas terminaram em
`ddg: sem resultados (bloqueio?)` + `ddg-lite: 6 resultados` (**lixo**: `y.js`
de anúncio, guia de blog, índice/dicionário) — **nenhuma etapa `web:`** e
`produtos: []` / `confirmadas: 0`. O provedor web tinha ofertas reais
(KaBuM), mas nunca era consultado. Evidência:
`smoke-v57-pos-publicacao-2026-10-18.json`.

## 2. Correção (local exato)

Tudo em `shopping.py`:

- **Gate comercial** — bloco novo antes de `buscar_ddg_chain` (linha ~1338):
  `classificar_candidato(item)` + `_contagem_classificacoes`,
  `_ordenar_candidatos`, `_mesclar_candidatos`. Classifica o **tipo** da URL
  do candidato:

  | Classe | Regra (resumo) | Decisão na cascata |
  |---|---|---|
  | `PRODUCT_CANDIDATE` | marcador de produto no caminho (`/produto/`, `/p/`, `/dp/`, `/item/`…) | comercial — encerra |
  | `COMMERCIAL_LISTING` | host `loja./shop./store.…`, `lista.*`, listagem de categoria/busca de loja, marketplace conhecido | comercial — encerra |
  | `EDITORIAL_REFERENCE` | portais/blogs/guias/reviews/agregadores (host ou segmento blog/autor/tag/guia/review…) | rebaixado — **não** encerra |
  | `GENERIC_INDEX` | home, página de buscador, login/conta/sobre | rebaixado — **não** encerra |
  | `IRRELEVANT` | anúncio (`duckduckgo.com/y.js…`), não-http, URL inválida | descartado — nunca baixado nem vira referência |
  | `UNKNOWN` | sem sinal claro | candidato fraco — **nunca** justifica parada |

  O gate é **tipo de descoberta, não validação de oferta**: preço, estoque,
  variante e identidade continuam 100% com o validador V5.7 (o selo “Link
  verificado” segue exigindo página de item real, aberta e compatível).
- **`buscar_ddg_chain`** (linha ~1451): acumula o útil das duas bases
  (mescla/dedup por host+caminho) e só retorna cedo quando já há candidato
  comercial (`COBERTURA_COMERCIAL_MINIMA = 1`); etapas agora registram
  `“<base>: N resultados (C comerciais)”`.
- **`buscar_com_fallback`** (linha ~1479): assinatura ganhou `diag=None`;
  classifica o retorno de ddg+ddg-lite, decide o web com base em candidato
  comercial real, mescla e ordena (comerciais primeiro). Caminho rápido
  preservado: com comercial encontrado, o web **não** roda.
- **`pesquisar`** (linhas ~2270+): onda de consulta de páginas com limite
  `MAX_ONDAS_PAGINAS = 2` — se a 1ª onda não render **nenhuma** oferta
  estruturada, a 2ª onda consulta os candidatos seguintes com fase SSE real
  `"recuperando"` antes de declarar ausência; resumo novo
  `resultado["descoberta"]` (observabilidade §6). Referências passam a usar
  as páginas efetivamente consultadas (as duas ondas).
- Constante nova: `MAX_ONDAS_PAGINAS = 2`. Nada mais mudou de limite:
  teto por onda (`MAX_PAGINAS = 6`), pool `[:teto+4]`, ThreadPool 3,
  timeouts por provedor, dedup antes de downloads — intactos.
- `research.py`, `research_agents.py`, `source_check.py`, JDUI
  (`jdui.py`/`public/jdui.js`), benchmarks e schemas: **intocados**. Os
  `buscar_com_fallback` do research/acadêmico são outros fluxos e não foram
  alterados.

## 3. Antes × depois (comportamento)

| Cenário | Antes (V5.7) | Depois (V5.7.1) |
|---|---|---|
| ddg/ddg-lite só lixo | cadeia parava → 0 produtos (smoke manhã) | continua ao web; lixo fica como candidato fraco (teste crítico 1) |
| ddg/ddg-lite comercial | caminho rápido | caminho rápido preservado, sem chamar o web (testes 2 e 3) |
| vazio/bloqueado | seguia ao web | segue ao web; motivo `provider_blocked` estruturado (teste 8 / E2E) |
| tudo editorial/índice | 0 ofertas sem motivo estruturado | 0 confirmadas **com motivo**: `irrelevant_results` + `no_confirmed_offers` (teste 4) |
| página “produto” que cai em home | não confirma (correto) | idem — gate não valida, validador rejeita (teste 5) |
| 1ª onda sem ofertas | declarava ausência direto | 2ª onda real `"recuperando"` recupera candidatos (teste 7) |
| erro interno no web | engolido sem distinção | etapa `web: falhou (ValueError)` + diag `provider_error` ≠ bloqueio (teste 8) |
| nenhum provedor entrega | `provedor_indisponivel` | idem + `descoberta.motivo_final = provider_unavailable` |

## 4. Testes

Novo: `tests/test_shopping_discovery_v571.py` (9 testes — cenários A–G do
briefing + tabela de classificação; fixtures congeladas do incidente real,
sem rede). Contra o código antigo: **5 falhavam** (1, 4, 7, 8, 9 —
reprodução), 4 passavam (guardas). Com a correção: **9/9**.

- Suíte completa: **851 passed / 4 skipped** (base 842/4) — os 842 testes
  antigos passam **sem nenhuma edição** (incluindo os que usam fixture
  `loja.com/p`, hoje classificada `COMMERCIAL_LISTING`).
- Subáreas: shopping **173 passed/2 skipped**; JDUI + pesquisa + acadêmico +
  autenticação/isolamento **186 passed**.
- Benchmarks congelados: `tools/bench_shopping_v4.py` **59/59**;
  `tools/bench_pesquisa_v57.py --sem-salvar` **34/34** (artefatos congelados
  do repo não foram regravados).

## 5. E2E real (cadeia natural, sem neutralização)

Script novo `smoke_v571_corrigido.py` (mesmo caminho do agente:
roteamento → `_shopping_executar` → `_shopping_aplicar`/fence → render node
com `public/jdui.js` + checagem HTTP independente de imagens e páginas),
executado com **rede real**, **sem neutralizar ddg/ddg-lite**, 4 consultas
mínimas do briefing. Artefato:
`qa-artifacts/v57/smoke-v571-descoberta-2026-10-18.json` (+ log em
`%TEMP%\opencode\smoke-v571-log-2026-10-18.txt`).

**Resultado: APROVADO — 4/4 consultas, 16 ofertas confirmadas, 16 imagens
verificadas ao vivo, 12 páginas de item abertas independentemente, render
node ok em todas.**

| Consulta | Confirmadas | Latência | Estado dos provedores |
|---|---|---|---|
| “me mostre um notebook” | 4/4 (KaBuM: R$ 2.974,15 / 4.703,04 / 7.299,00 / 9.750,24, `em_estoque`, links `verificado`) | 11,5 s | mlb 403; ddg/ddg-lite vazio (bloqueio); web: 6 resultados, 4 comerciais |
| “me mostre um notebook para trabalhar e estudar” (consulta aprovada antes) | 4/4 (mesmos itens) | 9,2 s | idem; 2ª consulta do web: 16 resultados irrelevantes → ignorada |
| “me mostre um fone bluetooth” | 4/4 (Philips/JBL: R$ 25,74 a R$ 319,90) | 10,3 s | idem |
| “preço fone bluetooth até R$ 500” | 4/4 (todos ≤ R$ 500) | 8,1 s | idem |

- **Nota honesta**: hoje ddg/ddg-lite respondem **vazio** (bloqueio) — o
  caminho “lixo” do incidente não ocorreu ao vivo nesta janela; ele é
  coberto pelos testes determinísticos 1–3 com as fixtures congeladas do
  incidente (e pela evidência “antes” do smoke da manhã). O E2E live prova:
  fallback real até o web, resposta íntegra ponta a ponta, validação V5.7
  mantida e observabilidade estruturada populada de verdade.
- Registro de execução: o script concluiu com artefato completo e
  `resultado geral: APROVADO`; o “exit code 1” exibido pelo PowerShell é
  artefato do shell ao mesclar stderr (logging INFO) no pipeline `2>&1`
  (`NativeCommandError`) — reproduzido com um script trivial que sai com 0.
- Magazine Luiza 403 e demais bloqueios seguem registrados como bloqueio —
  nada foi contornado.

## 6. Observabilidade estruturada

- `resultado["descoberta"]`: `decisoes[]` por provedor (consulta truncada,
  provedor, `resultados`, `comerciais`, `rejeitados`, `rebaixados`, `motivo`,
  `erro`, `ms`) + resumo (`paginas_disponiveis`, `paginas_consultadas`,
  `ondas`, `ofertas_extraidas`, `confirmadas`, `orcamento_esgotado`,
  `motivo_final`).
- Códigos: `useful_candidates_found`, `insufficient_commercial_candidates`,
  `fallback_success`, `irrelevant_results`, `provider_blocked`,
  `provider_error`, `provider_unavailable`, `search_budget_exhausted`
  (teto de páginas esgotado ≠ ausência comprovada), `no_confirmed_offers`,
  `confirmed_offers_found`.
- Etapas de provedor com contagem comercial; nenhuma etapa fictícia no SSE
  (a fase `"recuperando"` só emite quando a 2ª onda roda de verdade).
  Nenhum dado sensível: consulta truncada (80 chars), sem credenciais.

## 7. Latência

8–12 s por consulta no E2E live (antes: 12,2 s no diagnóstico web-only do
mesmo dia; 17 s no E2E V5.7 da mesma família de consulta) — sem regressão
relevante; o caminho rápido continua sem web (testes 2/3), e a 2ª onda só
roda quando a 1ª produz zero ofertas.

## 8. Bloqueios externos (18/10/2026, sem contorno)

mlb API 403; ddg bot-wall; ddg-lite vazio (de manhã, devolvia lixo);
Magazine Luiza 403; Amazon 503/vazio; fontes com CAPTCHA ficam `bloqueado`.
Nada foi contornado; nenhuma fonte foi declarada saudável sem checagem.

## 9. Segurança e escopo

Sem push, sem deploy, sem reinício do agente de produção (segue na
`020c85f`; o hotfix vive apenas no checkout local), sem credenciais, sem
tocar Hermes/extensão/Fajulto/motor 3D/social/Apify, sem apagar dados nem
alterar permissões, sem contornar bot-walls, sem mascarar testes. Artefatos
congelados preservados (`git checkout` não foi necessário — benchmarks
rodados sem gravar).

## 10. Como reproduzir

```powershell
# testes do hotfix
.venv\Scripts\python.exe -m pytest tests/test_shopping_discovery_v571.py -q

# suíte completa + benchmarks
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe tools\bench_shopping_v4.py
.venv\Scripts\python.exe tools\bench_pesquisa_v57.py --sem-salvar

# E2E real (rede; SEM neutralizar ddg/ddg-lite)
.venv\Scripts\python.exe %TEMP%\opencode\smoke_v571_corrigido.py
```

## 11. Commit local

Commit único desta entrega = **topo de `git log`** (`git status -sb` mostra
`main` à frente de `origin/main` em 1 commit). **Nenhum push, nenhum
deploy.**
