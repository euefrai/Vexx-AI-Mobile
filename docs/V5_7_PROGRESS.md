# V5.7 — Pesquisa: Precisão e Resultados Inteligentes — Progresso e contexto

Objetivo: elevar a qualidade real das pesquisas (precisão, cobertura, links
exatos, imagens corretas, interpretação de conteúdo, respostas visuais),
reutilizando Search Orchestrator V5.5, Research Agents, Evidence Graph,
Shopping, Intent Engine, JDUI, memória, SSE e Document Intelligence.
Sem deploy/push, sem mudar identidade/modelo/credenciais do Lucas, sem tocar
na extensão da Júlia ou no Fajulto Studio, sem contornar CAPTCHA/bot-wall,
sem GitHub Intelligence, sem inventar fontes/preços/imagens/testes.

## FASE 1 — Auditoria real (concluída)

Estado de partida: `HEAD 4854496` (V5.6), árvore limpa exceto
`qa-artifacts/followups/failure.png` (staged pelo usuário; intocado).
Baseline da área de pesquisa: `266 passed, 4 skipped` (subconjunto
search/research/shopping/source/web/intent/evidence/structured/academic/units);
baseline completo V5.6: 670 passed, 4 skipped.

Método: leitura de código (subagente de exploração com linha exata) + sondas
reais de rede executadas contra os módulos (`search_orchestrator`,
`search_providers`, `shopping`, `source_check`, `research`) com orçamentos
curtos. Nada foi alterado antes das reproduções.

### Problemas reproduzidos (com evidência)

| # | Problema | Evidência real | Causa raiz |
|---|---|---|---|
| P1 | Consulta em forma de pergunta recebe lixo lexical e é declarada "ok" | `pesquisar('como funciona o freio ABS')` → 6/6 resultados de dicionário sobre a palavra "funciona"; `correspondencia 0.333`; `estado ok`; `consultados: bing` — Wikipedia (escolhida) nunca consultada; `pesquisa_rapida` entregava 3 páginas de dicionário como "fontes lidas e utilizáveis" | `_ESTOPO` sem verbos de pergunta ("funciona" contava como termo de correspondência); `_util_para_pedido` aprova por qualquer termo; early-stop após o 1º provedor; recuperação enxuta só disparava com `correspondencia ≤ 0.15` |
| P2 | Shopping pode misturar variantes e expor página de loja como "produto" | `buscar_web_v55('notebook lenovo ideapad 3i 8gb 512gb')` → Magalu/Casas Bahia/KaBuM **categorias** + "Gemini Notebook" (rel. 10.3); em `shopping.pesquisar`, `criterios.marcas=['lenovo']` mas produtos Asus Vivobook e Dell Alienware aparecem; `marca` extraída como "KaBuM!" | Filtro por marca não descarta marca desconhecida/errada; relevância de índice geral fraca; card JDUI tem fallback para a URL da página analisada (`shopping.py:1292-1293`/`1372`, `jdui.js:1998-2001`) — `url_item` só quando existe |
| P3 | ~~Mojibake nos títulos do Bing~~ **descartado** | `repr`/`unicode_escape` mostram `\xe7\xe3` íntegros e nenhum `U+FFFD`; o "�" era só o console do Windows | Artefato da auditoria, não do produto |
| P4 | Bloqueios de loja confirmados | MLB API → `ResearchErro 403`; Magalu → 403 bot-wall; KaBuM listagem → `reprovado/sem_sinais_produto`; Wikipedia ABS → `parcial` (termos) | Esperado/sem bypass; validação honesta funcionando |
| P5 | Sinônimos pt-PT × pt-BR derrubam veredito | `validar_link(pt.wikipedia.org/wiki/Freio_ABS, termos=['ABS','freio'])` → `parcial: não menciona "freio"` (artigo usa "travagem") | Checagem de termos por substring, sem equivalência de variante |
| P6 | Erro interno mascarado como indisponibilidade | chamada com assinatura errada (sonda) → `erro: provedor_indisponivel`, `etapas: ["busca indisponível (TypeError)"]` | `except Exception` genérico vira `codigo` igual a provedor; melhoria de honestidade (baixo impacto) |

### Também confirmado no código (subagente de exploração)

- `anexar_fontes` decide por substring `"Fontes:" not in texto`
  (`pc_agent.py:2046-2050`) → risco de duplicar ou omitir o bloco.
- `run_reuso` de "essas fontes" não confere o tópico da run anterior
  (`pc_agent.py:1977-1986`).
- `imagem_veredito` chega ao JDUI (`jdui.js:334`) mas não é renderizado no
  card (`jdui.js:1979-2014`).
- `source_check` só é consumido pelo shopping; a pesquisa geral não gera
  veredito de link/imagem.
- SSE de pesquisa corta em 360 s (`server.py:1927-1929`) vs. modo
  investigativa 300 s + replan.
- Autolink imprime URL crua (`app.js:413-419`).

## FASE 2 — Search Orchestrator 4.0 (em andamento)

### Incremento 1 — reformulação de pergunta e correspondência honesta (concluído)

Mudanças em `search_orchestrator.py`:

1. `_ESTOPO` ganhou verbos/funcionais de pergunta ("funciona", "faz", "serve",
   "significa", "existe", "foi", "era"…) — não provam correspondência temática.
2. `consulta_conteudo()` (nova): remove apenas a moldura de pergunta
   ("como funciona", "o que é", "quanto custa"…) e artigos iniciais; devolve
   `""` quando não sobra termo distintivo — nunca inventa consulta.
3. `pesquisar()`: quando um provedor devolve resultados sem correspondência
   (ou vazio), tenta **a mesma fonte** uma vez com a consulta reformulada
   antes de trocar de provedor (etapa registrada: `nome (consulta reformulada '…')`).
4. `pesquisar()`: consulta enxuta passa a ser declarada também com
   `correspondencia < 0.5` (antes só `≤ 0.15`).
5. `pesquisar_com_recuperacao()`: `correspondencia < 0.5` também dispara a
   rodada de recuperação (investigar em vez de fingir ok).

Testes: `tests/test_search_orchestrator_v57.py` (7 casos, sem rede) cobrindo
stopword de pergunta, reformulação conservadora, retry na mesma fonte,
provedor vazio reformulado, enxuta declarada e recuperação melhorando
correspondência fraca. Suíte focada da área: verde (ver seção de evidências).

Prova antes/depois (rede real, 2026-10-17):

- Antes: `pesquisar_com_recuperacao('como funciona o freio ABS')` →
  `correspondencia 0.333`, `estado ok`, top-8 = dicionários de "funciona";
  `etapas: ["bing: 6 resultados (como funciona o freio ABS)"]`.
- Depois: `correspondencia 1.0`, `estado ok`, topo = Moura (sistema de freios),
  Kalatec, **Wikipédia — Freio**, Dicio/Freio, Justos; lixo antigo rebaixado
  ao fim (nunca apagado); `etapas` inclui
  `bing (consulta reformulada 'freio ABS'): 6 resultados`.

Contratos preservados: consulta original continua a primeira tentativa;
nenhum resultado é apagado (apenas rebaixado/descartado por dedupe);
`variantes` não mudou; estados continuam no vocabulário V5.5.

### Incremento 2 — duplicatas e republicações (concluído)

`deduplicar()` agora, além da URL canônica, sinaliza **republicações**:
título praticamente idêntico (Jaccard ≥ 0.9, ≥ 4 termos) entre URLs
distintas → a versão posterior vira descarte com motivo
(`republicação de <url>`) e a mantida ganha `republicacoes: [urls]`.
Títulos curtos (< 4 termos) nunca entram na regra. Nada é apagado:
tudo fica em `descartes` com a origem (base para o Evidence Graph).
Testes: 2 casos novos em `tests/test_search_orchestrator_v57.py`.

### Incremento 3 — conteúdo desatualizado em consultas temporais (concluído)

Quando a consulta tem recorte temporal (ano explícito, ex.: "eleições 2026",
ou classe temporal do intent), cada item com **ano conhecido** ganha
`ano` + `desatualizado`; a regra é a **única** do `evidence_graph`
(`fonte_desatualizada`: ano ≤ alvo−2, **sem data conhecida NÃO acusa**) e o
item velho é apenas rebaixado (penalidade ≤ 4.5), nunca apagado. O relatório
da busca ganha `temporal` e `desatualizados: [urls]`; a rodada de
recuperação preserva o recorte temporal no re-rank. Consulta sem recorte
temporal não muda nada.

Testes: 3 casos novos (sinalização + ordem, sem data não acusa, consulta
sem recorte não marca). Benchmark ganhou o grupo `desatualizado` (2 casos).

### Incremento 4 — erro interno nunca mascarado (P6, concluído)

`pesquisa_rapida` rotulava qualquer exceção da busca como
`erro: provedor_indisponivel` — um bug interno (ex.: `TypeError`) parecia
problema de provedor. Agora: exceção com `codigo` (provedor/rede) continua
`provedor_indisponivel`; exceção sem `codigo` vira `erro_interno` com a
causa real na etapa (`erro interno na busca (TypeError)`). Estado segue
`indisponivel` (a busca realmente não aconteceu).

Testes: `tests/test_research_v57.py` (3 casos).

### Incremento 5 — parada por ganho real de informação (concluído)

Critério de parada novo, baseado em **informação nova** (domínio novo e/ou
tema do pedido coberto a mais), não em quantidade:

1. Na cadeia de consultas do `pesquisar`: se a consulta anterior não trouxe
   domínio nem tema novo e já há resultado útil, a próxima consulta **não
   roda** — etapa `parada por ganho zero: consulta anterior sem domínio nem
   tema novo` (orçamento não é gasto à toa).
2. Na recuperação (`pesquisar_com_recuperacao`): o ganho da rodada extra é
   medido e declarado em `ganho_informacao`
   (`dominios_novos`/`temas_novos`/`ganho_real`) + etapa
   `recuperação com ganho novo: …` ou `recuperação sem ganho novo: …` —
   nunca fingir melhora só porque a rodada rodou.

Nada é apagado; junk continua em `achados`. Consultas com 1 única rodada
(ou sem repetição de domínio/tema) mantêm o comportamento anterior.

Testes: 4 casos novos em `tests/test_search_orchestrator_v57.py`; benchmark
ganhou o grupo `ganho` (2 casos).

### Incremento 6 — índice geral reclassificado + recuperação dirigida (concluído)

Último item declarado da FASE 2. Detecção conservadora de página de
índice/listagem (`_pagina_de_indice`): título ("Resultados para…",
"Índice de…", "Busca…", "Category/Categoria:") ou caminho
(`/search`, `/busca`, `/resultados`, `/categoria|category`, `/tag(s)`,
`/indice|índice`, `/directory`). Regras:

1. A página de índice é **sinalizada** (`pagina_de_indice`) e **demovida**
   (−2; termos ecoados na querystring não valem ponto de conteúdo) —
   nunca apagada; resultado expõe `indice_geral: [urls]`.
2. Se a rodada inteira (topo) for só índices: etapa honesta "1ª rodada só
   com páginas de índice geral (N sinalizada(s)); fontes primárias não
   alcançadas", lacuna correspondente e a recuperação pede o assunto
   direto (enxuta) — fontes primárias continuam vindo primeiro pela
   cadeia congelada de provedores por classe (sem reordenação).

Testes: 2 casos novos; benchmark ganhou o grupo `indice` (3 casos).

## FASE 7 — JDUI (incremento 1 concluído)

1. `public/jdui.js` — `productImgSelo`: selo honesto de imagem no card.
   `verificado` não ganha selo; `parcial` → "Imagem não confirmada";
   `nao_verificado` → "Imagem não verificada"; `reprovado` (imagem foi
   removida pelo shopping) → "Sem foto confirmada" com o motivo no
   `title`. Nunca apresentar foto não verificada como confirmada.
2. `public/app.js` — `rotuloUrl`: autolink de texto passa a exibir
   host + caminho curto (ex.: `moura.com.br/blog/sistema-de-freios`) com
   `title` contendo a URL completa; o `href` continua a URL inteira.
   Fim das URLs cruas gigantes quebrando o layout do chat.
3. Verificação: `node --check` nos dois arquivos + suíte JDUI
   (`test_jdui*.py`) 34/34 verde.
4. `pc_agent.anexar_fontes` — o teste por substring `"Fontes:" not in texto`
   foi trocado por `_ja_tem_fontes_markdown`: o bloco estruturado só é
   omitido quando já existe **cabeçalho** "Fontes:" (com ou sem `#`/`**`)
   seguido de linha com link http em até 1500 caracteres. Menção solta à
   palavra no meio da resposta não esconde mais as fontes reais; lista real
   do modelo não é duplicada.
   Testes: `tests/test_pc_agent_fontes_v57.py` (7 casos).

## FASE 4 — Links, produtos e imagens (incremento 1 concluído)

Prioridade da missão ("corrigir links errados e produtos misturados").
Mudanças em `shopping.py`:

1. `aplicar_filtros`: marca pedida agora é critério obrigatório — produto de
   outra marca vira `marca_diferente` (alternativa explícita "outra marca: X,
   pedido: Y"); sem marca confirmável vira `marca_nao_confirmada`. Nunca
   aparece como se fosse o pedido.
2. `separar_alternativas`: os dois códigos de marca entram como alternativa
   com a diferença escrita; nunca escondida.
3. `extrair_criterios`: par "8gb 512gb" (formato típico de anúncio de
   notebook/celular) passa a virar `ram_fisica_gb`/`armazenamento_gb` — só
   nessas categorias e com faixas sãs (RAM 2–64, armazenamento 64–8192).
4. `_marca_conhecida`: marca do anúncio pela primeira ocorrência (marca do
   anúncio, senão nome) — "Dell Alienware … NVIDIA RTX" é Dell, não Nvidia.
5. `_armazenamento_aparente`: maior valor em GB ≥ 64 — "16GB RAM + SSD 512GB"
   não vira "armazenamento 16GB" (era o valor da RAM).

Evidência real (rede, 2026-10-17), pedido "notebook lenovo ideapad 3i 8gb 512gb":

- Antes: produtos = Asus Vivobook + Lenovo IdeaPad Slim 3 + Dell Alienware +
  Lenovo LOQ (marcas misturadas); `criterios.specs` só `flag_novo`.
- Depois: produtos = **Lenovo IdeaPad Slim 3 e Lenovo LOQ** (link `verificado`,
  `url_item`); alternativas = Asus ("outra marca: asus (pedido: lenovo)") e
  Dell ("outra marca: dell"); `specs` = RAM 8GB + armazenamento 512GB.
- Card JDUI já usa `_link_do_produto` (url_item > url_final > url) e carrega
  `link_veredito`/`imagem_veredito`/`item_de_listagem` — coberto por teste.

Limitação honesta documentada: `marca` do anúncio às vezes vem do vendedor
("KaBuM!"); por isso a marca é confirmada também pelo nome do produto, e o
selo de link já distingue verificado / parcial / REPROVADO / não verificado.

Testes novos: `tests/test_shopping_v57.py` (8 casos, sem rede).

## FASE 5 — Leitura e trechos (incremento 1 concluído)

Problema real reproduzido (2026-10-17): em artigos com seção de referências
(pt.wikipedia.org/wiki/Freio_ABS), o `trecho_usado` exibido vinha de
"Consultado em … Cópia arquivada …" — citações mencionam o tema em frases
curtas e ganhavam o ranking de palavras-chave do `melhor_trecho`.

Correção em `web_extract.py`:

1. `_penalidade_citacoes()` (nova): janelas com marcadores de referência
   (consultado em, cópia arquivada, acesso em, ISBN, doi:, `«»`, `↑`)
   perdem pontos no `melhor_trecho` (3 por marcador, teto 30) — referência
   não é conteúdo.
2. Após a correção, a mesma página real passa a entregar trecho do corpo
   ("as rodas estarão travadas. Dessa maneira, o ABS irá reduzir
   significativamente as chances de derrapagem…").

Testes: `tests/test_web_extract_v57.py` (4 casos, sem rede) — trecho não vem
de referências, fallback sem termos, escolha por termo preservada e teto da
penalidade.

## FASE 9 — Benchmark independente (concluído)

`benchmarks/pesquisa_v57_v1.json` (fixtures congeladas, 34 casos) +
`tools/bench_pesquisa_v57.py` (runner determinístico, provedores injetados,
sem rede) + `tests/test_bench_pesquisa_v57.py` (wrapper pytest que exige
aprovação total). Grupos: reformulação (8), termos de correspondência (4),
fluxo junk→reformulação na mesma fonte (1), republicações (2), marca/specs
de shopping (5), specs pareadas (2), links do card (5), conteúdo
desatualizado em consulta temporal (2), ganho real de informação (2),
índice geral (3).

Resultado 2026-10-18 (offline): **34/34, taxa global 1.0** (inclui os grupos
`desatualizado`, 2 casos); artefato
`qa-artifacts/v57/bench-pesquisa-v57-2026-10-18.json` (o de 2026-10-17 fica
como histórico, 27 casos). Sondas reais no mesmo
artefato: `como funciona o freio ABS` → `correspondencia 1.0`, `estado ok`,
top3 = bemotors/deltafiat/karhub (artigos de freio ABS), etapas com
`bing (consulta reformulada 'freio ABS'): 6 resultados`.

Como comparar antes/depois: o baseline "antes" está na FASE 1 acima
(6/6 dicionário, correspondência 0.333) e a reprodução é
`python tools/bench_pesquisa_v57.py --real` no commit anterior vs. atual.

### Próximos incrementos planejados (FASE 2)

Nenhum item da lista declarada restante — todos implementados nos
incrementos 1–6 (reformulação, correspondência, republicações,
desatualizado, P6, parada por ganho, índice geral). Candidato futuro (não
prometido): preferência de fontes primárias por classe além da cadeia
congelada de provedores.

## Evidências (comandos)

- Suíte da área (baseline e regressões): `pytest -q tests` (filtro
  search/research/shopping/source/web/intent/evidence/structured/…).
- Sondas reais usadas na auditoria: scripts temporários em
  `%TEMP%\opencode\v57_probe*.py` (introspecção + rede); páginas do Bing RSS
  salvas em `%TEMP%\opencode\bing2_*.xml` para inspeção.
- Após o incremento 1: `test_search_orchestrator_v57.py` 7/7 verde e
  `pesquisar_com_recuperacao` real com correspondência 1.0 (saída acima).
- FASE 9 (benchmark): `python tools/bench_pesquisa_v57.py` (offline 34/34;
  `--real` acrescenta sondas de rede) e `pytest -q tests/test_bench_pesquisa_v57.py`.
- FASE 5 (trecho): `pytest -q tests/test_web_extract_v57.py` 4/4; prova real
  no mesmo probe da Wikipédia (trecho do corpo do artigo).
