# RELATÓRIO VEXX AI V5.7.2 — FINAL ACCEPTANCE & RELEASE READINESS

- **Data:** 2026-10-19
- **Base:** commit local `772ec3a` (V5.7 FINAL), árvore limpa no início
- **Commit de entrega:** `e98d316` (local, sem push/deploy)
- **Escopo:** auditoria dirigida + correções dos checkpoints A–I, sem novas
  funcionalidades, sem push/deploy, sem modelo pago
- **Decisão final:** **READY_WITH_LIMITATIONS**

## Resumo executivo

A V5.7.2 fecha as pendências materiais da V5.7: preço numérico com `Decimal`
(incluindo `R$ 2.974,15`), filtros de orçamento verificáveis, extração de
conteúdo principal sem menu/sidebar, consulta de pesquisa sem o verbo do
pedido, inferência/streaming/grounding reais no Hermes (modelo free) e
validação no Chrome real (desktop + mobile emulado). O smoke integrado dos 6
cenários passou **7/7**; a suíte completa passou **891 passed, 4 skipped**; os
benchmarks congelados seguem **34/34** e **59/59**; o smoke externo confirmou
**2/2 ofertas com preço numérico**.

Nada foi publicado. A decisão é `READY_WITH_LIMITATIONS` porque o serviço
publicado não foi exercitado (deploy proibido), o mobile foi emulado (não
físico) e os provedores externos variam (403/bot-wall/429), com fallback
honesto. Não há bloqueador de código conhecido.

## Os 20 itens exigidos

| # | Item | Status |
|---|---|---|
| 1 | Escopo, base e método | **PASS** |
| 2 | Preço numérico (BRL, milhar/decimal, moeda) | **PASS** |
| 3 | Filtros de orçamento (≤500, 1.000–2.000, >3.000) | **PASS** |
| 4 | Sem preço, moeda diferente, variante, promocional | **PASS** |
| 5 | Extração de conteúdo principal (Trafilatura avaliada) | **PASS** |
| 6 | Latência do shopping (instrumentar antes de otimizar) | **PASS** |
| 7 | Hermes — descoberta de modelos | **PASS** |
| 8 | Hermes — inferência real | **PASS** |
| 9 | Hermes — streaming | **PASS** |
| 10 | Hermes — resposta fundamentada (grounded) | **PASS** |
| 11 | Entrega no frontend (FRONTEND_DELIVERY) | **PASS** |
| 12 | Paridade JDUI Python × JS | **PASS** |
| 13 | Chrome desktop real | **PASS** |
| 14 | Chrome mobile emulado | **PASS (emulado)** |
| 15 | Smoke integrado — 6 cenários | **PASS 7/7** |
| 16 | Regressão completa (suíte/benchmarks/bateria) | **PASS** |
| 17 | Segurança preservada | **PASS** |
| 18 | Release readiness (contratos, migrações, deps, estáticos) | **PASS** |
| 19 | Sequência de publicação e rollback | **DOCUMENTADA** |
| 20 | Decisão final e limitações | **READY_WITH_LIMITATIONS** |

---

## 1. Escopo, base e método

- Base `772ec3a`; nenhum push/deploy; portas de produção (5000/8000/5173/8645)
  intocadas; todo E2E em portas livres + SQLite temporário.
- Método por checkpoint: ANALISAR → REPRODUZIR → CORRIGIR → TESTAR →
  DOCUMENTAR; cada correção tem teste que falha antes e passa depois.
- Evidência separada por rótulo: MOCK, LOCAL REAL, EXTERNO REAL, BLOQUEADO.
- Fora de escopo preservado: motor 3D, extensão da Júlia, Fajulto Studio,
  identidade Lucas, Apify/redes sociais, credenciais.
- Alterações: `shopping.py`, `web_extract.py`, `research.py`,
  `tools/smoke_externo_v57f.py`; 4 arquivos de teste novos; 2 harnesses de
  evidência. Sem mudanças em `server.py`, `pc_agent.py`, `public/*`.

## 2. Preço numérico

**Causa raiz:** parsing com float/heurística de separador; `R$ 2.974,15`
podia virar 2,974 ou 2974.15; o smoke media a chave errada (`preco_valor` em
`res["produtos"]`, que usa `preco`).

**Correção:** `normalizar_preco` com `Decimal`; “o último separador é o
decimal”; grupos de 3 dígitos são milhar; `$`/`US$` → `USD`; inválido/ambíguo
→ `None`; moeda e proveniência preservadas; nunca mistura variantes.

**Evidência:** `tests/test_precos_filtros_v572.py` 12/12; smoke externo
**2/2 com preço numérico** (R$ 28,60 / R$ 68,32); smoke integrado R$ 134,29;
card JDUI expõe `preco_valor` numérico.

## 3. Filtros de orçamento

**Correção:** `aplicar_filtros` + `separar_alternativas` cobrem:
`≤ R$ 500`, `R$ 1.000–2.000`, `> R$ 3.000`, teto explícito do pedido.

**Evidência:** testes 12/12; ao vivo, itens acima do teto aparecem como
“fora” com motivo (`R$ 304,23 — 1% acima`, `R$ 466,66 — acima`), sem entrar
no conjunto principal. Nenhum item fora do orçamento foi promovido.

## 4. Sem preço, moeda, variante e promocional

- Sem preço interpretável → `preco_nao_confirmado`, **fora** do conjunto
  principal e devolvido como alternativa explícita (não conta como “dentro do
  orçamento”).
- Moeda ≠ BRL → `moeda_diferente`, sem comparação numérica com o teto em BRL.
- Variante incompatível não entra no conjunto principal.
- Preço “a partir de”/promocional sem confirmação não vira preço único:
  `preco_confirmado=False`, `preco_a_partir_de=True`, texto honesto.
- **Evidência:** `test_sem_preco_nao_entra_no_orcamento_mas_fica_explicito`,
  `test_moeda_diferente_nao_vira_orcamento_brl`,
  `test_variantes_marcam_a_partir_de`,
  `test_produto_sem_preco_confirmado_nao_inventa_valor` (todos verdes).

## 5. Extração de conteúdo principal

**Causa raiz:** `melhor_bloco` dava vitória ao contêiner total (body), com
boilerplate; perda de inline; título podia ser headline-descrição.

**Correção:** propagação `1.0/0.8/0.6`, bônus `article/main/[role=main]`,
multiplicador de link-density, penalização `body/#root ×0.35`;
`_texto_bloco` ignora `_IGNORAR`; `_texto_bloco_inline` preserva
negrito/itálico/links; `_titulo_plausivel` rejeita descrição.

**Trafilatura:** avaliada, **não instalada**; não foi adicionada dependência.
A reescrita determinística entregou o resultado sem serviço novo.

**Evidência:** `tests/test_web_extract_v572.py` 5/5; Wikipédia
`Fotossíntese – Wikipédia, a enciclopédia livre` (1.200 chars, sem menu);
docs.python.org `5. Data Structures` (1.200 chars); Magalu bloqueada com
aviso honesto.

## 6. Latência do shopping

Instrumentação por etapa antes de qualquer otimização:

| Medição | Resultado |
|---|---|
| Notebook ≤ R$ 3.000 | 7,99–8,73 s; 4 ofertas > R$ 3.000 excluídas; 0 produtos honesto |
| Fone ≤ R$ 300 | 10,07 s (2 ondas) |
| `_validar_itens_declarados` | 1,04 s / 2 páginas (paralelo) |
| `verificar_imagens` | 0,42–0,82 s / 2 (paralelo) |
| Smoke externo final | 11,7 s com 2 confirmadas |
| Smoke integrado (fone) | 6,17–11,59 s |

Nenhuma otimização especulativa; nenhuma verificação reduzida; SSRF/limites/
rate limiting mantidos. Os 41,5 s da V5.7 eram variância externa.

## 7. Hermes — descoberta de modelos

`/v1/models` **200**; **428 modelos**; `poolside/laguna-s-2.1:free` presente.
Descoberta não foi confundida com inferência.

## 8. Hermes — inferência real

Requisição real de `chat/completions`: **5,81 s**, resposta “A capital do
Brasil é Brasília.”, `free_path`, **custo 0**. Nenhum modelo pago ativado.

## 9. Hermes — streaming

**5,51 s**, **38 deltas**; resposta consistente; sem corpo vazio com o
`max_tokens` padrão (1500). Observação: `max_tokens=40` em modelo de
raciocínio devolve corpo vazio por artefato do modelo — não é defeito do
bridge.

## 10. Hermes — resposta fundamentada

**27,15 s**; fontes reais todamateria/brasilescola/biologianet; resposta com
equação e cloroplastos; artefato
`qa-artifacts/v572/grounded-fotossintese.json`.

**Defeito crítico corrigido:** a consulta crua levava “explique” ao buscador,
trazendo dicionário. `research.consulta_de_pesquisa` separa PEDIDO de TEMA;
`tests/test_consulta_pesquisa_v572.py` **4 falhas antes → 4/4 depois**.

Um **429** externo foi observado uma vez; o app devolveu erro honesto e a
reexecução passou.

## 11. Entrega no frontend (FRONTEND_DELIVERY)

Chrome real, stack isolado, login pela interface, chat real com streaming
(**4,04 s**, 197 chars) e card JDUI de produto real da KaBuM (**R$ 110,12**)
com imagem **verificada**, link **parcial** e fonte “original declarado:
Manual do fabricante”. Screenshots em `qa-artifacts/v572/chrome/`.

## 12. Paridade JDUI Python × JS

O JS já renderizava imagem, selos honestos (parcial/não verificada) e
“original declarado: …”; o Python expõe o mesmo contrato. Teste
`test_jdui_visual_v572.py` (Node + paridade) **2/2**. `origem_declarada`
**nunca** ganha selo de fonte verificada. Estilo Minimal Premium preservado.

## 13. Chrome desktop real

Chrome **155.0.8059.82** via CDP (sem Playwright), viewport 1280×900
(inner 1264). Sem overflow horizontal (1264/1264). Console: 1 erro esperado
**401 antes do login** e 2 `ERR_ABORTED` de reload; **0 exceções JS**.

## 14. Chrome mobile emulado

`Emulation.setDeviceMetricsOverride` 390×844, DPR 2, touch. Sem overflow
(390/390). Card e fonte continuam renderizados. **Não é teste em Android/iOS
físico** — declaração explícita no artefato.

## 15. Smoke integrado — 6 cenários

Artefato `qa-artifacts/v572/smoke-integrado-20261019-152951.json` (**7/7**):

1. **Produtos** (fone ≤ R$ 300): 1 confirmada R$ 134,29, card válido;
   alternativas R$ 304,23/R$ 466,66 excluídas.
2. **Pesquisa geral**: 3 fontes lidas, resposta 1.393 chars.
3. **URL direta**: Wikipédia, título correto, 1.200 chars, sem menu.
4. **Comparação técnica**: docs.python.org lida (2.212 chars) e comparação
   listas×tuplas (2.282 chars).
5. **Continuação**: “agora os mais baratos” → R$ 150 → 200 → 300, fence
   válido; tentativa externa vazia honesta.
6. **Falha externa**: DNS inválido + provedor indisponível → aviso honesto,
   sem preço/fence inventados.
7. **Entrega no frontend**: Chrome ok.

Execução anterior com **429** externo registrada em
`smoke-integrado-20261019-152738.json`; reexecução 7/7.

## 16. Regressão completa

| Verificação | Resultado |
|---|---|
| Suíte completa | **891 passed, 4 skipped** (102,51 s) |
| Benchmark pesquisa | **34/34** (taxa 1.0, falhas 0) |
| Benchmark shopping | **59/59** (taxa 1.0, falhas 0) |
| Bateria de experiência | **16/16** |
| Testes novos V5.7.2 | **23/23** |
| Node/JDUI, Shopping, Research, Evidence Graph, segurança | verdes na suíte |
| Fixtures/skips | nenhum removido/artificial |

Nenhuma regressão crítica; nenhum teste alterado para “passar”.

## 17. Segurança preservada

Auth/sessão/CSRF, RBAC e isolamento por `owner_id`, SSRF/DNS/redirects/
limites de download, rate limiting, CSP, anti prompt-injection, segredos no
backend, controles do PC Agent: **inalterados**. Nenhum script de página
externa executado; nenhum serviço pago novo; nenhuma credencial exposta.
A suíte completa cobre esses controles.

## 18. Release readiness

- **Contratos relay × PC Agent:** inalterados (endpoints, payloads, WS,
  variáveis de ambiente).
- **Migrações:** nenhuma (`CREATE/ALTER` ausentes no diff); schema SQLite
  compatível.
- **Dependências:** `requirements.txt` inalterado; nada novo em runtime.
- **Estáticos/SW:** `public/*` inalterado; `sw.js` permanece
  `VEXX-shell-live-data-1`; network-first + bypass de `/api/*`; sem bump
  necessário.
- **Rollback:** redeploy de `772ec3a` no Render + retorno do agente; sem
  migração a desfazer; backup do SQLite recomendado.
- Detalhes: `docs/V5_7_2_RELEASE_CHECKLIST.md`.

## 19. Sequência de publicação e rollback

Quando autorizado: revisar commit/tag → push → Render build/deploy →
atualizar PC Agent → `/api/diag` (`pc_online`) → smoke no publicado (login,
chat, produtos, pesquisa, URL, continuação, falha externa) → monitorar
429/403. Rollback: redeploy de `772ec3a`, reiniciar agente no commit anterior,
restaurar backup se necessário, verificar diag/login/IA.

Nada foi pushado/deployado nesta rodada.

## 20. Decisão final, limitações e riscos

**Decisão: `READY_WITH_LIMITATIONS`.**

**Limitações declaradas:**

1. **Serviço publicado não testado** — deploy proibido nesta rodada; o smoke
   no Render deve ser o primeiro passo após autorização.
2. **Mobile emulado** — viewport 390×844 no Chrome; não é Android/iOS físico.
3. **Provedores externos variáveis** — Magalu/MLB 403/bot-wall, DDG bot-wall
   e um 429 do Hermes; o app responde de forma honesta, sem contornar.
4. **Sintaxe de tool call** — observada uma vez (`<tool_call>webSearch…`) com
   fontes fracas/vazias; não reproduzida nos fluxos aprovados (pesquisa com
   fontes, Chrome, smoke 7/7). Recomendação para próxima versão: sanitizador
   determinístico de `<tool_call>` no texto final, com teste próprio.
5. **Ferramentas opcionais ausentes** — Trafilatura e Playwright não estão
   instaladas; a extração determinística e o CDP cobriram os cenários.

**Riscos residuais:** variância de preço/estoque entre execuções; bloqueio de
lojas; limite de uso do modelo free. Nenhum risco de segurança novo.

**Condição de GO:** autorização de publicação + smoke no ambiente publicado +
monitoramento de 429/403. Sem bloqueador de código conhecido.

## Anexos e evidências

- `docs/V5_7_2_PROGRESS.md` — checkpoints A–I.
- `docs/V5_7_2_E2E_RESULTS.md` — Chrome, smoke integrado, smoke externo,
  Hermes, regressão.
- `docs/V5_7_2_RELEASE_CHECKLIST.md` — release/rollback.
- `qa-artifacts/v572/chrome/` — JSON + screenshots.
- `qa-artifacts/v572/smoke-integrado-20261019-152951.json` — smoke 7/7.
- `qa-artifacts/v572/smoke-integrado-20261019-152738.json` — execução com 429
  (honesta, preservada).
- `qa-artifacts/v572/grounded-fotossintese.json` — resposta fundamentada.
- `qa-artifacts/v57/smoke-externo-v57f-2026-10-19.json` — smoke externo real.
- `tests/test_precos_filtros_v572.py`,
  `tests/test_web_extract_v572.py`,
  `tests/test_consulta_pesquisa_v572.py`,
  `tests/test_jdui_visual_v572.py`.
- `tools/chrome_e2e_v572.py`, `tools/smoke_integrado_v572.py`.
