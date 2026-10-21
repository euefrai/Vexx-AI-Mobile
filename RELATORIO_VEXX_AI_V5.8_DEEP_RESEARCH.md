# Relatório Vexx AI V5.8 — Deep Research & JDUI 4.0

**Data:** 2026-10-20  
**Escopo:** incremento local V5.8 sobre a base V5.7.3  
**Branch:** `main`  
**Classificação local:** **READY_WITH_LIMITATIONS**  
**Produção:** não atualizada, não reiniciada, não validada  
**Push/deploy:** não realizados

---

## 1. Resumo executivo

A V5.8 foi implementada como uma extensão da arquitetura existente, não como
uma plataforma paralela. O incremento entrega uma investigação profunda
completa no caminho determinístico/local:

- plano estruturado, subquestões não redundantes, prioridades, dependências,
  critérios de conclusão e regras de parada;
- busca e leitura com proveniência de fonte, orçamento, timeout, cancelamento,
  pausa, retomada e replanejamento limitado por lacunas reais;
- evidências com os cinco estados exigidos, contagens de fontes
  encontradas/lidas/usadas e trecho efetivamente usado;
- hipóteses apresentadas como `HIPÓTESE → EVIDÊNCIAS → LACUNAS → PRÓXIMOS
  PASSOS → CONCLUSÃO`, com `Testes executados: não`;
- descoberta conservadora de mídia (imagem/vídeo/documento) com metadados e
  proveniência, **sem** tratar mídia como evidência;
- JDUI 4.0 com quatro componentes validados no backend e no frontend:
  `researchplan`, `evidence`, `media`, `filecard`;
- workspace “Pesquisas” com lista de jobs salvos, visão estruturada, progresso,
  links de exportação e ação “Acompanhar no chat”;
- exports reais em Markdown/CSV/JSON, renderizados no servidor, com isolamento
  de dono, limite de 2 MB e proteção contra injeção de fórmula em CSV;
- testes unitários, integração, contrato, segurança, benchmark congelado,
  Chrome real desktop e mobile emulado, exports por bytes reais e medições de
  performance;
- documentação completa em `docs/v5.8/` e avaliação de PDF.js, ECharts,
  Video.js e Docling.

O que **não** foi entregue ou comprovado: inferência semântica real, análise de
imagem/vídeo/transcrição, download/rehost de mídia, OCR/layout de PDF, adoção
das bibliotecas pesadas, reload ao vivo no Chrome, dispositivo físico,
E2E externo completo, produção/Render e push/deploy. Essas ausências estão
declaradas nas limitações e não foram mascaradas como sucesso.

**Resultado de testes:** `954 passed, 4 skipped, 2 warnings in 172.87s` na suíte
local completa. Benchmark congelado de pesquisa: `34/34`. Segurança/isolamento:
`33 passed`. Chrome E2E: `ok: true`.

---

## 2. Ponto de partida e método

### 2.1 Baseline

Antes das alterações V5.8, a suíte local foi executada na base V5.7.3:

```text
929 passed, 4 skipped, 2 warnings in 227.42s
```

Artefato: `qa-artifacts/v573/baseline-v58.txt`.

O HEAD original era `607ff1f10fa66dd32906505ae1cc8ccb5ed37184`, três commits à
frente de `origin/main` (`ed0d44fd8b40e9fa32c2cdf727bba997760ce2fe`).

### 2.2 Ordem seguida

1. auditoria/inventário e baseline;
2. Deep Search (plano, orçamento, lacunas, replan, cancelamento/retomada);
3. Evidence Intelligence (estados, contagens, proveniência, hipóteses);
4. JDUI 4.0 (schemas, componentes, validadores, renderizadores);
5. documentos/arquivos e mídia descoberta;
6. workspace de pesquisas, relatórios e exports;
7. SSE/continuidade;
8. performance e recursos;
9. QA (unitário, integração, contrato, segurança, benchmark, Chrome);
10. documentação e relatório.

A prioridade foi **uma investigação profunda completa** antes de ampliar o
catálogo visual. Bibliotecas multimodais pesadas foram avaliadas, mas não
adicionadas ao runtime.

### 2.3 Preservação do trabalho concorrente

O índice já continha um snapshot de auditoria de 2026-10-20. Para não misturar
esse trabalho com a V5.8, ele foi preservado primeiro no commit local
`52e3195` (`audit: snapshot concurrent 2026-10-20 corrections and QA evidence`).
Os artefatos não rastreados de auditoria/QA também foram mantidos. Nada foi
apagado com reset/clean.

---

## 3. Deep Search — implementação

### 3.1 Acionamento

O job pode ser criado por pedido explícito de pesquisa ou por sugestão do
layer de intenção. Aliases de modo (`deep`, `deep search`, `deep_research`,
`pesquisa profunda`, `investigativa`, `professional`, etc.) são normalizados
para `rapida`, `pro`, `profunda` ou `investigativa`.

### 3.2 Plano estruturado

`montar_plano` gera etapas com:

- id estável e tipo (`busca`, `ler`, `analisar`, `verificar`, `sintetizar`,
  `auditar`);
- alvo, objetivo da etapa, prioridade e motivo da prioridade;
- dependências explícitas;
- regra de parada e critério de conclusão;
- versão do plano e metadados de orçamento.

Subquestões redundantes são removidas por normalização de consulta. Consultas
já executadas são detectadas contra `consultas_etapas` persistido, evitando
repetição inclusive após retomada.

### 3.3 Execução, orçamento e parada

O loop `executar` é idempotente por etapa: etapas concluídas não são refeitas.
Cada passo salva o job e um checkpoint de contexto. Orçamentos são fixados na
criação do job:

| Modo | Buscas | Páginas | Tempo | Subquestões | Profundidade | Mídia | Replans |
|---|---:|---:|---:|---:|---:|---:|---:|
| rápida | 2 | 3 | 30 s | 1 | 1 | 8 | 1 |
| pro | 4 | 6 | 60 s | 3 | 2 | 12 | 1 |
| profunda | 8 | 12 | 120 s | 4 | 2 | 16 | 2 |
| investigativa | 12 | 20 | 300 s | 6 | 3 | 20 | 2 |

Limites configuráveis por ambiente (`JULIA_RESEARCH_MAX_*` e aliases
`JULIA_DEEP_MAX_*`): buscas, páginas, segundos, subconsultas, profundidade,
mídia, concorrência, replans e bytes por página. O teto de página é 2 MB por
padrão. O campo de concorrência é um teto; a V5.8 executa passos
sequencialmente (paralelismo efetivo 1), sem alegar ganho de concorrência.

Critérios de parada: cancelamento explícito, interrupção do chamador, timeout,
orçamento de busca/página esgotado, ausência de passos pendentes ou fim da
rodada limitada de replanejamento. O estado terminal é persistido **antes** do
evento `research_completed`.

### 3.4 Lacunas e replanejamento

`_lacunas` coleta lacunas reais: evidência ausente, leitura falha, afirmação
não verificada e follow-ups registrados pelas investigações. `replanejar`:

- respeita o máximo de 0–3 rodadas;
- não repete frente ou consulta normalizada já executada;
- cria um conjunto curto de busca/leitura/análise;
- pode reabrir leitura quando novos achados chegaram;
- incrementa a versão do plano e emite `plan_updated`;
- preserva orçamento e timeout originais.

Quando o orçamento acaba ou o limite de replans é atingido, o job encerra com
limitações explícitas, sem fingir completude.

### 3.5 Cancelamento, pausa e retomada

`cancelar` e `pausar` atualizam o estado persistido. O worker verifica o
callback de parada e o status entre etapas. A retomada reidrata evidências do
SQLite e dos checkpoints; ids duplicados são colapsados. A retomada é por etapa
persistida, não no meio de uma requisição HTTP.

### 3.6 Modelo indisponível

A pesquisa continua útil sem LLM. Planejamento, verificação lexical, contagens,
contradições, relatório e exports são determinísticos. A síntese é extrativa e
marcada `llm=false` quando Hermes está indisponível. Nenhum teste ou raciocínio
semântico é inventado.

---

## 4. Evidence Intelligence

### 4.1 Estados

`SUPPORTED`, `CONTRADICTED`, `PARTIALLY_SUPPORTED`, `UNVERIFIED`,
`INCONCLUSIVE`.

Cada afirmação carrega:

- statement/afirmação, estado, método e cobertura lexical quando aplicável;
- ids de evidência, apoios e contradições;
- contagens `found/read/used` calculadas a partir das fontes reais;
- por fonte: relação (`SUPPORTS`, `CONTRADICTS`, `REQUIRES_VERIFICATION`),
  `read`, `access_state`, `used_excerpt`, título, domínio/data.

A UI e o componente JDUI distinguem fonte **encontrada**, **lida** e
**usada como apoio**. Fonte sem trecho não é apresentada como prova.
`UNVERIFIED` não é promovido a positivo.

### 4.2 Hipóteses

`_hipotese_publica` gera a cadeia:

```text
HIPÓTESE
EVIDÊNCIAS
LACUNAS
PRÓXIMOS PASSOS
CONCLUSÃO
```

O campo `testes_executados=false` e a frase “Testes executados: não” aparecem na
visão e nos exports. Conclusões são rotuladas como “SUPORTADA pelas evidências
registradas (não é prova causal)”, “ENFRAQUECIDA”, “INCONCLUSIVA” ou “EM ABERTO”.

### 4.3 Proveniência e honestidade

O verificador registra fontes lidas, trechos usados e relações. A auditoria
detecta citações fantasmas. O resumo de evidências não converte fonte apenas
encontrada em fonte lida. A contagem de “usadas” deriva dos registros, não de
um número fornecido pelo modelo.

---

## 5. JDUI 4.0

### 5.1 Componentes novos

| Componente | Função | Validação principal |
|---|---|---|
| `researchplan` | plano e progresso real | 1–24 passos, ids únicos, progresso recalculado; percent spoofado ignorado |
| `evidence` | tabela de afirmações e fontes | 1–10 claims, 12 fontes/claim, `SUPPORTED` exige fonte real, contagens derivadas |
| `media` | galeria de descoberta | imagem/vídeo/documento, URL real, `evidence=false` forçado, `analysis_state=not_analyzed` |
| `filecard` | exports/arquivos reais | 1–8 arquivos, `http(s)` remoto ou rota exata de export; demais caminhos rejeitados |

### 5.2 Contrato e segurança

- versão `JULIA-ui-message/v1`;
- allowlist de componentes e propriedades;
- nenhum HTML/JS fornecido pelo modelo é executado;
- blocos inválidos são omitidos com nota textual; o JSON bruto não é retornado;
- limites de blocos, passos, claims, fontes, mídia e arquivos;
- frontend `public/jdui.js` espelha as regras do backend, com testes Node;
- o harness cobre o allowlist de `filecard` (incluindo a rota de export) e a
  regra de mídia não-evidência.

### 5.3 Renderização

O renderer mostra barra de progresso acessível (`role=progressbar`, valores
ARIA), estados de passo, badges de estado, detalhes de fonte expansionáveis,
trecho usado, galeria com fallback textual, aviso “não é evidência”, links de
export e proveniência. Mídia usa `loading="lazy"` e não é rehospedada.

---

## 6. Documentos, arquivos e mídia

### 6.1 Mídia descoberta

`media_evidence.py` lê HTML já obtido pelo caminho seguro existente. Ele
descobre `<img>`, `<video>`, poster e Open Graph, normaliza apenas `http(s)`,
rejeita credenciais/esquemas inseguros, deduplica por URL canônica e preserva:

- tipo, título, URL final/original, página de origem, publisher, data, direitos;
- estado de acesso, validação e análise;
- trecho quando existir;
- `analysis_state="not_analyzed"` e `evidence=False` por padrão.

Não há download, thumbnail no servidor, transcrição, análise visual ou rehost.
Vídeo é descoberta, não entendimento de vídeo.

### 6.2 Documentos existentes

A extração de documentos existente foi preservada. PDF textual continua
coberto por `docs_agent` e testes; OCR não existe e não é prometido. Docling foi
avaliado, mas não adotado.

### 6.3 Arquivos e exports

O `filecard` aponta para URLs remotas reais ou para a rota restrita de export.
Os formatos são Markdown, CSV e JSON. O renderer é puro, em memória, com limite
de 2 MB e 200 itens; CSV neutraliza fórmulas. O servidor autentica, resolve o
dono e aplica `Content-Disposition`, `nosniff` e `no-store`.

---

## 7. Workspace, relatórios e exports

A página “Pesquisas” foi adicionada ao menu lateral. Ela:

- lista jobs salvos do dono com objetivo, modo, status e data;
- abre um job e monta a visão JDUI validada;
- mostra progresso, orçamento, fontes, evidências, hipóteses, mídia e limitações;
- oferece downloads MD/CSV/JSON;
- mantém a ação “Acompanhar no chat”;
- exibe estados vazios/erro sem inventar dados.

O workspace é um visualizador de jobs salvos com exports, não um caderno
colaborativo completo com anotações/versionamento. Essa distinção está na
matriz e nas limitações.

---

## 8. SSE e continuidade

O stream existente foi preservado: cursor monotônico, replay, entrega
ordenada, deduplicação, flush terminal e eventos persistidos. O painel de
pesquisa usa polling/refresh do relay e eventos reais do backend. Não há
“thinking” inventado nem exposição de cadeia de pensamento privada.

O teste `test_sse_entrega_ordenada_com_replay_e_fechamento` cobre replay e
fechamento. A recarga de página durante um stream de modelo ao vivo **não** foi
repetida no Chrome V5.8; esse caso permanece parcial.

---

## 9. Performance e recursos

### 9.1 Medições locais

`python tools/bench_v58.py` (Windows, Python 3.14.4, RSS ~22 MB):

| Operação | Entrada | Média | Pico Python | Saída |
|---|---|---:|---:|---:|
| View JDUI validada | 24 passos, 10 claims, 12 mídias, 8 hipóteses | **7,35 ms** | 0,11 MB | 6 blocos |
| Export Markdown | 200 evidências, 50 hipóteses | **21,70 ms** | 0,48 MB | 64.486 B |
| Export CSV | idem | **33,81 ms** | 0,46 MB | 62.071 B |
| Export JSON | idem | **9,01 ms** | 0,43 MB | 112.699 B |

Nenhuma biblioteca pesada foi importada. São medições de módulos puros, não
latência de rede, render de navegador ou produção concorrente.

### 9.2 Avaliação das bibliotecas exigidas

Versões/licenças verificadas em 2026-10-20:

| Biblioteca | Versão | Licença | Tamanho publicado | Decisão |
|---|---|---|---|---|
| PDF.js (`pdfjs-dist`) | 6.4.299 | Apache-2.0 | pacote 34,9 MB; main 458.904 B; worker 1.264.342 B | não adotado; exige `worker-src` e cuidado com WASM/CSP |
| Apache ECharts | 6.1.0 | Apache-2.0 | pacote 60,3 MB; dist completo 1.121.883 B | não adotado; gráficos JDUI determinísticos existentes |
| Video.js | 10.1.0 | Apache-2.0 | pacote 48.496 B, mas ESM modular com `@videojs/*` | não adotado; mídia é descoberta/link |
| Docling | 2.141.0 | MIT | dependências/modelos de centenas de MB a >1 GB | não adotado; pesado para Render Free |

Todas as licenças são permissivas; a rejeição é por peso, superfície CSP e
ausência de caso de uso real de mídia/PDF analisado. Se adotadas no futuro,
devem ser lazy-loaded, com SRI/CSP e medição real de RAM — nunca no caminho
inicial do Render Free.

---

## 10. Segurança

- Rotas de pesquisa exigem sessão; o dono vem da sessão/revogação, nunca do
  cliente.
- O relay repassa `owner`; consultas SQLite filtram `owner_id`.
- Exports: formatos allowlist, 2 MB, 200 itens, filename sanitizado, CSV
  anti-fórmula, `nosniff`, `no-store`.
- `filecard`: apenas `http(s)` remoto ou a rota exata
  `/api/research/export?job_id=…&formato=md|csv|json`.
- `media`: não pode ser evidência; análise visual forçada a `not_analyzed`.
- `evidence`: afirmação `SUPPORTED` sem fonte real é rejeitada.
- Nenhum HTML/JS arbitrário do modelo é executado.
- SSRF/DNS/redirect/CSP/RBAC/isolamento não foram enfraquecidos.
- 403/429/bot-wall permanecem `BLOCKED`; sem CAPTCHA bypass, proxy ou serviço
  pago.
- Produção, credenciais, identidade Lucas, engine 3D, extensão Júlia, Fajulto
  Studio, social/Apify: intocados.

Testes de segurança/isolamento: `33 passed`, incluindo rotas V5.8, SSRF,
exports, auth e isolamento entre donos.

---

## 11. QA e evidência

### 11.1 Suítes

| Evidência | Resultado |
|---|---|
| Baseline pré-V5.8 | 929 passed, 4 skipped, 2 warnings, 227,42 s |
| Alvo pesquisa/JDUI/servidor | 156 passed, 1 skipped |
| Suíte completa local | **954 passed, 4 skipped, 2 warnings, 172,87 s** |
| Benchmark congelado de qualidade | **38 passed, 1 skipped** |
| Benchmark congelado de pesquisa | **34/34**, taxa 1.0 |
| Segurança/isolamento | **33 passed** |
| Contratos V5.8 | **13 passed** |
| Node syntax | `node --check public/jdui.js` e `public/app.js` OK |
| Chrome E2E | **ok: true** |

O delta 929→954 inclui os testes V5.8 **e** o snapshot de auditoria; não é
atribuído integralmente à V5.8. Os 4 skips não são contados como passes.

### 11.2 Chrome real

`tools/chrome_e2e_v58.py` sobe um stack isolado (uvicorn + pc_agent + SQLite
temporário + perfil Chrome temporário), faz login real, abre “Pesquisas”,
renderiza o job e busca o export pela rota autenticada.

Resultado:

- Chrome 155.0.8059.85 headless;
- desktop 1280×900 e mobile emulado 390×844;
- 5 slots JDUI, 6 nós de plano, 3 cartões de mídia, 8 badges;
- export Markdown de **1.839 bytes** via Chrome;
- mobile sem overflow horizontal; botões com altura mínima;
- nenhuma exceção JS não capturada;
- screenshots em `qa-artifacts/v58/*.png`.

O job foi pré-persistido localmente para exercitar a UI/rota real; não é uma
investigação aberta na web. Mobile é emulação, não dispositivo físico.

### 11.3 Os 20 casos de qualidade

O mapeamento completo está em `docs/v5.8/QUALITY_CASES.md`. Cobertura real:
factual, multi-hop, contraditório, técnico, científico (metadados), notícia
(fixtures), comercial, hipóteses, PDF textual, gráficos existentes, imagens,
vídeos (descoberta), exports, cancelamento/retomada, Hermes 429, fontes
bloqueadas, evidência insuficiente, JDUI inválida, reload/replay e export por
bytes reais.

Casos parciais declarados: notícia/comercial ao vivo, PDF com OCR, vídeo
entendido, reload no Chrome ao vivo, dispositivo físico e produção. Nenhum
teste foi alterado para inflar score.

### 11.4 Tipos de evidência separados

| Tipo | V5.8 |
|---|---|
| Determinística/simulada | testes e fixtures congeladas |
| Externa | não reexecutada como passe V5.8; BLOCKED preservado |
| Inferência/LLM | indisponível; nenhuma alegação semântica |
| Chrome | real, stack local isolado, desktop + mobile emulado |
| Mobile físico | não realizado |
| Produção/Render | não testado, não atualizado |
| Export por bytes | provado localmente no Chrome e em testes de rota |

---

## 12. Matriz de capacidades (resumo)

| Capacidade | Estado |
|---|---|
| Deep search estruturado, sem redundância, com lacunas/replan | FUNCTIONAL |
| Orçamento, timeout, cancelamento, pausa, retomada | FUNCTIONAL |
| Modelo indisponível com síntese extrativa honesta | FUNCTIONAL |
| Cinco estados de evidência + found/read/used | PARTIAL (semântica BLOCKED) |
| Hipóteses com cadeia e “testes não executados” | FUNCTIONAL |
| Mídia descoberta, sem virar evidência | FUNCTIONAL |
| JDUI 4.0 validada (4 componentes) | FUNCTIONAL |
| Workspace de pesquisas + exports reais | FUNCTIONAL (local) |
| SSE/replay/terminal | FUNCTIONAL (browser reload parcial) |
| Chrome desktop + mobile emulado | FUNCTIONAL (local) |
| Performance/recursos medidos | FUNCTIONAL (local) |
| PDF.js/ECharts/Video.js/Docling | avaliados, não adotados |
| Produção/Render | NOT_TESTED |

Matriz completa: `docs/RESEARCH_CAPABILITY_MATRIX.md` e
`docs/v5.8/CAPABILITIES.md`.

---

## 13. Limitações e riscos residuais

1. Sem LLM real exercitado; sem entailment semântico; síntese extrativa.
2. Verificação de claim é majoritariamente lexical; `SUPPORTED` não é prova
   causal.
3. Provedores externos variam; 403/429/bot-wall permanecem BLOCKED.
4. Sem download/thumbnail/transcript/análise visual de mídia.
5. Sem OCR/layout de PDF; Docling não adotado.
6. Sem concorrência real; o teto configurado não paraleliza.
7. Retomada por etapa, não no meio de uma leitura HTTP.
8. Workspace é visualizador de jobs salvos, não caderno completo.
9. Sem PDF/DOCX export; apenas MD/CSV/JSON.
10. Chrome E2E local; mobile emulado; sem dispositivo físico.
11. Reload durante stream ao vivo não refeito no Chrome.
12. Sem validação de produção/Render; sem push/deploy.
13. 4 skips históricos; benchmark semântico bloqueado.
14. Performance é de módulos puros, não carga concorrente.
15. O snapshot de auditoria concorrente está separado, mas ainda há artefatos
    não rastreados no worktree que precisam de decisão posterior.

---

## 14. Trabalho pendente

Prioridade:

1. autorização explícita para push/deploy e validação publicada;
2. E2E externo real e Hermes real (429/quota/stream/cancel), sem mascarar
   BLOCKED;
3. reload ao vivo no Chrome e dispositivo móvel físico;
4. pipeline real de mídia com direitos, bytes, SSRF, isolamento e estado
   `analyzed` comprovado;
5. avaliação real de PDF/OCR (PDF.js vs Docling) com RAM e CSP medidos;
6. verificação semântica quando houver modelo;
7. concorrência bounded se houver ganho real;
8. workspace com anotações/versionamento, PDF/DOCX e auditoria de
   acessibilidade;
9. decisão sobre artefatos de auditoria não rastreados;
10. manter matriz/limitações sincronizadas com evidência de deploy.

Nada disso está declarado como feito.

---

## 15. Commits locais

| Commit | Conteúdo |
|---|---|
| `52e3195` | snapshot do trabalho concorrente de auditoria (preservação) |
| `de0597d` | backend V5.8: deep search, mídia, view, exports, schemas, rotas |
| `e4cf84d` | frontend V5.8: workspace, renderers, estilos, smoke |
| `634511d` | QA V5.8: Chrome E2E, benchmark, artefatos |
| commit de documentação | `docs/v5.8/`, matriz e este relatório |

Nenhum commit foi enviado ao origin. O push/deploy depende de autorização
posterior.

---

## 16. Artefatos

### Documentação

- `docs/v5.8/README.md` — índice;
- `docs/v5.8/ARCHITECTURE.md` — arquitetura e fluxo;
- `docs/v5.8/REUSE_AND_GAPS.md` — reuso, lacunas e escopo intocado;
- `docs/v5.8/CAPABILITIES.md` — matriz detalhada;
- `docs/v5.8/QUALITY_CASES.md` — 20 casos;
- `docs/v5.8/EXAMPLES.md` — contratos JDUI e export;
- `docs/v5.8/TESTS.md` — testes e tipos de evidência;
- `docs/v5.8/BENCHMARKS.md` — benchmarks;
- `docs/v5.8/SCREENSHOTS.md` — capturas;
- `docs/v5.8/PERFORMANCE.md` — performance e bibliotecas;
- `docs/v5.8/SECURITY.md` — segurança;
- `docs/v5.8/LIMITATIONS.md` — limitações;
- `docs/v5.8/PENDING.md` — pendências;
- `docs/v5.8/COMMITS.md` — commits.

### Código principal

- `research_agents.py` — jobs, planos, orçamentos, evidências, mídia,
  hipóteses, resumo;
- `media_evidence.py` — descoberta de mídia;
- `research_view.py` — visão JDUI validada;
- `research_exports.py` — exports reais;
- `jdui.py` — schemas/validadores;
- `server.py` — rotas autenticadas;
- `public/jdui.js`, `public/app.js`, `public/index.html`,
  `public/interface.css` — UI;
- `tests/test_v58_deep_research.py` — contratos V5.8;
- `tools/chrome_e2e_v58.py`, `tools/bench_v58.py` — QA reproduzível.

### Evidência bruta

`qa-artifacts/v58/`: suíte completa, benchmarks, segurança, Chrome JSON/texto,
5 screenshots, performance. Baseline: `qa-artifacts/v573/baseline-v58.txt`.

---

## 17. Conclusão

A V5.8 entrega o incremento **Deep Research & JDUI 4.0** no escopo
determinístico/local: uma investigação profunda com plano, evidências
rastreáveis, hipóteses honestas, mídia descoberta, visão JDUI validada,
workspace e exports reais. A implementação preserva a arquitetura V5.7.3, não
enfraquece segurança/isolamento e mantém falhas externas como `BLOCKED`.

A classificação local é **READY_WITH_LIMITATIONS**. Ela não é uma declaração de
prontidão para produção: não houve push/deploy, E2E externo completo, inferência
real, análise multimodal, dispositivo físico ou validação Render. O próximo
passo correto é revisar os commits locais e, somente com autorização explícita,
executar a validação publicada.
