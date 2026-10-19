# VEXX AI V5.7.2 — Resultados E2E (2026-10-19)

Evidência executada nesta rodada. Rótulos: **MOCK** · **LOCAL REAL** ·
**EXTERNO REAL** · **BLOQUEADO**. Nada foi executado contra o serviço
publicado (deploy proibido nesta rodada).

## Ambiente

| Item | Valor |
|---|---|
| Repositório | `C:\Users\efrai\Documents\julia-mobile-v0.2-offline-sqlite\julia-mobile-v0.2` |
| Base | `HEAD 772ec3a` (V5.7 FINAL) |
| Python | 3.14.4 |
| Chrome | 155.0.8059.82 (instalado, headless via CDP) |
| Hermes | `http://127.0.0.1:8645/v1` |
| Modelo | `poolside/laguna-s-2.1:free` (custo 0) |
| Isolamento | portas livres + `JULIA_SQLITE_PATH` temporário + perfil Chrome temporário |
| Produção | portas 5000/8000/5173/8645 **não tocadas** |

## 1. Chrome real — desktop e mobile emulado

Harness: `tools/chrome_e2e_v572.py` (CDP + `websockets`, sem Playwright).
Artefato: `qa-artifacts/v572/chrome/chrome-e2e-20261019-150401.json`.

| Etapa | Resultado |
|---|---|
| Login pela interface | OK (`#loginForm` → sessão; overlay oculto) |
| Chat real (streaming) | **4,04 s**, 197 chars; pergunta “o que é fotossíntese?” respondida corretamente |
| Card JDUI | produto **real** da KaBuM, **R$ 110,12**, imagem **verificada**, link **parcial** |
| Fonte com origem declarada | “original declarado: Manual do fabricante” renderizado |
| Desktop 1280×900 | inner 1264; `scrollWidth 1264 = clientWidth 1264` → **sem overflow** |
| Mobile emulado 390×844 | DPR 2, touch; `scrollWidth 390 = clientWidth 390` → **sem overflow** |
| Console | 1 erro esperado **401 antes do login**; 2 `ERR_ABORTED` de reload; **0 exceções JS** |

Screenshots:

- `qa-artifacts/v572/chrome/desktop-chat.png`
- `qa-artifacts/v572/chrome/desktop-card.png`
- `qa-artifacts/v572/chrome/mobile-card.png`

> **Limite declarado:** mobile é emulação de viewport do Chrome, **não** teste
> em aparelho Android/iOS físico.

## 2. Smoke integrado (6 cenários + entrega)

Harness: `tools/smoke_integrado_v572.py`.
Artefato final: `qa-artifacts/v572/smoke-integrado-20261019-152951.json` (**7/7**).

| # | Cenário | Rótulo | Dados observados |
|---|---|---|---|
| 1 | Produtos (“fone bluetooth até R$ 300”) | EXTERNO REAL | 1 oferta confirmada **R$ 134,29**, card JDUI válido; alternativas **R$ 304,23** (1% acima) e **R$ 466,66** excluídas; 11,59 s |
| 2 | Pesquisa geral (fotossíntese) | EXTERNO REAL + LLM REAL | 3 fontes lidas (biologianet, brasilescola, todamateria); resposta **1.393 chars**; sem tool call; 19,19 s |
| 3 | URL direta (Wikipédia) | EXTERNO REAL | título `Fotossíntese – Wikipédia, a enciclopédia livre`; **1.200 chars**; trecho contido; sem resíduos de menu; 1,83 s |
| 4 | Comparação técnica (docs.python.org) | EXTERNO REAL + LLM REAL | turno 1 lê a doc oficial (**2.212 chars**); turno 2 compara listas×tuplas (**2.282 chars**); 28,01 s |
| 5 | Continuação (“agora os mais baratos”) | LOCAL REAL (dados guardados) | ordem **R$ 150 → 200 → 300**; fence JDUI válido; tentativa externa sem produtos foi honesta; 0,02 s |
| 6 | Falha externa | LOCAL REAL + DNS REAL | DNS inválido + provedor indisponível → “Não consegui consultar ofertas agora…” sem preço/fence inventados; 0,01 s |
| — | Entrega no frontend | FRONTEND DELIVERY | Chrome E2E ok (seção 1) |

**Execução anterior invalidada/honesta:** às 15:27 o cenário 2 falhou por
**429 externo** do provedor (`BridgeErro: Provedor com limite excedido`) —
artefato `smoke-integrado-20261019-152738.json`. Após ~60 s, a reexecução
passou 7/7. O app não inventou resposta no 429.

## 3. Smoke externo real

Harness: `tools/smoke_externo_v57f.py --salvar`.
Artefato: `qa-artifacts/v57/smoke-externo-v57f-2026-10-19.json`.

| Etapa | Resultado |
|---|---|
| Hermes | porta 8645 aberta; `/v1/models` **200**; 0,6 s |
| Pesquisa real (fotossíntese) | `estado=ok`; bing; **3 fontes abertas** com texto (1.200 chars cada); grounding **4.367 chars**; 2,9 s |
| URL Wikipédia | aberta; título correto; 1.200 chars; 1,3 s |
| URL Magalu | **bloqueado (403/bot-wall)**; sem fonte inventada; 0,4 s |
| Shopping real | **2/2 ofertas confirmadas** com URL do item; **2/2 com preço numérico** (R$ 28,60 e R$ 68,32); 11,7 s |
| Prompt com página do usuário | 1 fonte; 5.078 chars; amostra do texto real; sem pesquisa genérica extra; 1,9 s |

## 4. Hermes — quatro etapas separadas

`/v1/models` 200 **não** foi tratado como inferência.

| Etapa | Resultado |
|---|---|
| MODEL_DISCOVERY | 428 modelos; `poolside/laguna-s-2.1:free` presente |
| INFERENCE | 5,81 s; “A capital do Brasil é Brasília.”; `free_path`, custo 0 |
| STREAMING | 5,51 s; **38 deltas** |
| GROUNDED_ANSWER | 27,15 s; fontes reais (todamateria/brasilescola/biologianet); resposta com equação/cloroplastos; `qa-artifacts/v572/grounded-fotossintese.json` |

Notas: `max_tokens=40` devolve corpo vazio em modelo de raciocínio (artefato,
não defeito do bridge); o app usa 1500. Nenhum modelo pago foi ativado.

## 5. Regressão

| Verificação | Resultado |
|---|---|
| Suíte completa | **891 passed, 4 skipped** (102,51 s) |
| Benchmark pesquisa (congelado) | **34/34**, falhas 0, taxa 1.0 |
| Benchmark shopping (congelado) | **59/59**, falhas 0, taxa 1.0 |
| Bateria de experiência real | **16/16** |
| Testes novos V5.7.2 | **23/23** (preços 12, extração 5, consulta 4, JDUI 2) |
| Node/JDUI, Shopping, Research, Evidence Graph, segurança | inclusos na suíte, verdes |
| Fixtures/skips | nenhum teste removido; nenhum skip artificial |

## 6. Bloqueios externos do dia (não contornados)

- Magalu: 403/bot-wall (página de busca e de produto).
- MLB: bloqueio de provedor registrado.
- DDG: bot-wall em algumas consultas; bing seguiu.
- Hermes: 1× HTTP 429 (limite), tratado com erro honesto e reexecutado.

## 7. Como reproduzir

```powershell
# suíte completa
.\.venv\Scripts\python.exe -m pytest -q

# benchmarks
.\.venv\Scripts\python.exe tools\bench_shopping_v4.py
.\.venv\Scripts\python.exe -m pytest tests\test_bench_pesquisa_v57.py tests\test_bench_experiencia_real.py -q

# evidência Chrome (isolado; requer Chrome instalado)
.\.venv\Scripts\python.exe tools\chrome_e2e_v572.py

# smoke integrado (6 cenários)
.\.venv\Scripts\python.exe tools\smoke_integrado_v572.py

# smoke externo real
.\.venv\Scripts\python.exe tools\smoke_externo_v57f.py --salvar
```

Os harnesses de Chrome/smoke usam portas livres, SQLite temporário e nunca
tocam a produção. O smoke integrado usa o Hermes real local quando disponível
e registra BLOQUEADO/429 sem inventar resposta.
