# Vexx AI V5.9.0 — Search Coverage

Data: 22/10/2026. Base verificada: `661d508`. Implementação local, sem push, deploy, reinício de produção, serviços pagos ou alterações de credenciais.

## Resultado

A pesquisa passou a recuperar o resumo científico correto de Transformer e as documentações oficiais de FastAPI, Django e asyncio, preservando a intenção do pedido até a leitura. O shopping recupera ofertas válidas na segunda onda quando as primeiras estão fora das restrições, mantém a fonte da oferta na saída JDUI e indica dados obrigatórios ainda desconhecidos como correspondência parcial.

**Não houve aumento comprovado de ofertas comerciais confirmadas nas três sondagens reais: continuaram em zero.** Bloqueios, listagens e falta de dados verificáveis foram mantidos como limitações. A consulta científica sobre baterias também continua sem fonte útil nesta rede; resultados genéricos não são mais tratados como pesquisa bem-sucedida.

## Auditoria direcionada e causas-raiz

Fluxo confirmado: `intent.py / pc_agent.py → research.py ou shopping.py → search_orchestrator.py → search_providers.py → download seguro → web_extract.py / source_check.py → research_agents.py / evidence_graph.py → grounding e JDUI existentes`.

| Problema comprovado | Correção |
|---|---|
| Qualquer palavra compartilhada encerrava a busca; `api` podia casar com `capital`. | Correspondência por limites de palavras, normalização de acentos/números e descarte de termos de instrução como prova de assunto. Ranking distingue correspondências e mantém o fallback diante de resultados fracos. |
| Limpeza removia “Compare” e a preferência por fontes, prejudicando a leitura e classificação. | Pedido original preservado na descoberta e avaliação; consulta limpa continua disponível para os contratos legados. |
| Pesquisa retornava sucesso por abrir páginas, mesmo sem utilidade para o pedido. | Leitura e utilidade são estados separados. `fontes_lidas`, `fontes_uteis` e relevância registram a diferença; grounding e digest filtram pertinência. |
| Orquestrador geral não aproveitava o DuckDuckGo já existente. | Adaptador existente reutilizado como fallback, com circuito de bloqueio e sem contornar CAPTCHA. Documentação oficial recebe prioridade de descoberta em casos reconhecidos. |
| Fallback podia exceder o prazo e a recuperação perdia tentativas/falhas anteriores. | Prazo compartilhado, histórico de tentativas, orçamento total explícito e agregação do diagnóstico. Mantido o limite legado por rodada; no máximo uma recuperação. Stack Exchange compartilha o prazo entre seus sites e respeita bloqueios/backoff. |
| Extrator do artigo sobre Transformer escolhia promoção do arXivLabs. | Resumo semanticamente identificado recebe prioridade quando não há artigo completo identificado; `abstract_only` impede confusão com texto completo. |
| Tabelas, seções e autoria extraídas se perdiam na pesquisa rápida. | Dados preservados nas fontes, com limites de tamanho; consulta original também chega à seleção do trecho. PDF textual reutiliza o leitor e parser existentes, com validação de tipo/assinatura e limites. |
| Cache comercial identificado apenas por categoria e marca. | Reaproveitamento exige os mesmos critérios, incluindo modelo, orçamento e texto do pedido, com isolamento por dono preservado. Cache antigo de pesquisa geral não ignora a nova validação. |
| Mercado Livre vazio encerrava o fallback; bloqueio podia ser repetido em cada variante. | Vazio continua a cadeia; bloqueio já observado na mesma pesquisa evita nova chamada à API. Falhas de rede e HTTP têm diagnóstico próprio. |
| Segunda onda era truncada e parava ao extrair qualquer produto, inclusive fora do orçamento. | Fila mantém candidatos das duas ondas; parada depende de oferta confirmada que passe nos filtros existentes. Nenhuma validação financeira/identidade foi enfraquecida. |
| Fonte de oferta válida encontrada tarde ficava fora das primeiras oito fontes. | Fontes dos produtos utilizados recebem prioridade na saída de grounding/JDUI. |
| RAM não informada podia parecer pedido plenamente atendido. | `EXACT_MATCH`, `PARTIAL_MATCH`, `ALTERNATIVE` e `IRRELEVANT` representam o resultado da correspondência; pendências aparecem no card existente e no grounding. Confirmação de preço continua independente de correspondência com o pedido. |

A primeira consulta comercial ampla, sem preço no texto, foi preservada por ser um contrato intencional de descoberta. O orçamento continua obrigatório na filtragem e aparece na consulta de preço. Os gabaritos existentes não foram alterados.

## Baseline e resultado real

Mesmos sete pedidos, bancos SQLite descartáveis, sem LLM. Uma sondagem inicial e uma final por cenário, além de checkpoints de diagnóstico limitados. Artefatos: `qa-artifacts/v59/baseline-real.json`, `final-real.json` e `comparison.json`.

| Pedido | Antes | Depois | Tempo antes → depois |
|---|---|---|---|
| Lenovo 16 GB até R$ 3.000 | 0 ofertas confirmadas | 0; seis páginas tentadas, bloqueios/listagens/dados insuficientes | 13,78 → 14,63 s |
| Samsung A56 256 GB | 0 ofertas confirmadas | 0; seis páginas tentadas, sem confirmação suficiente | 11,42 → 13,74 s |
| Tênis de basquete até R$ 300 | 0 ofertas confirmadas | 0; seis páginas tentadas, bloqueios e ausência de dados | 7,89 → 10,95 s |
| Arquitetura Transformer | Três páginas de arquitetura civil; estado incorreto `ok` | Resumo real do artigo original lido; uma fonte útil, estado parcial | 5,59 → 6,63 s |
| FastAPI × Django, documentação | Três fontes sobre FastAPI; Django ausente | Duas documentações oficiais úteis, cobrindo ambos | 13,61 → 5,54 s |
| Estudos recentes de baterias sólidas | Portais genéricos de estudos; estado incorreto `ok` | Resultados genéricos rejeitados; zero fonte útil | 4,99 → 5,44 s |
| Python asyncio, documentação | Maps/Prime Cursos; estado incorreto `ok` | Documentação oficial lida; uma fonte útil, estado parcial | 8,48 → 6,13 s |

Fontes técnicas efetivamente lidas: [artigo Transformer](https://arxiv.org/abs/1706.03762), [FastAPI](https://fastapi.tiangolo.com/), [Django](https://docs.djangoproject.com/en/stable/) e [asyncio](https://docs.python.org/3/library/asyncio.html). O artigo teve somente o resumo recuperado. O replay do mesmo HTML demonstrou a troca de 518 caracteres promocionais por 1.146 caracteres do resumo, sem nova requisição (`primary-extraction-replay.json`).

Tempo total dos sete pedidos: **65,77 → 63,05 s**. Nos quatro pedidos de pesquisa: **32,67 → 23,74 s**. As buscas comerciais ficaram mais lentas nesta amostra. São snapshots de rede, sem significância estatística; não constituem promessa de ganho de latência.

Relevância/cobertura são heurísticas de assunto e restrições, não probabilidades calibradas. Uma fonte útil não equivale a um pedido completamente respondido. O baseline não instrumentava a API comercial e todos os candidatos com a mesma granularidade posterior; contagens brutas de HTTP e taxas de abertura comercial entre os dois momentos não são comparáveis. Os logs finais registram tentativas, páginas, falhas, extração e fontes utilizadas. Ajustes finais de compatibilidade não mudam as fontes/conteúdo medidos.

## Validação

- Benchmarks congelados: pesquisa **34/34**, shopping **59/59**, experiência **16/16**, preservados. Shopping inicial também foi reproduzido offline com os módulos originais de `661d508`.
- Quality Lab documental existente, com fixtures congeladas: v1 — precision@5 **0,244444**, recall@5 **0,944444**, nDCG@5 **0,990813**; v2 — precision@5 **0,25**, recall@5 **0,854167**, nDCG@5 **0,816970**. São métricas locais, não resultados da Internet nem ganhos atribuídos a esta alteração. No v2, a fonte temporal mais recente teve recuperação **0/1**. Relatórios `quality-lab-v1.json` e `quality-lab-v2.json` preservam os casos e limites.
- Bateria focada de pesquisa/contratos: **232 aprovados, 2 ignorados**; segurança/autenticação/contratos acadêmicos: **57 aprovados**.
- Regressões cobrem fonte irrelevante, substrings, limites, cache, segunda onda, fonte no JDUI, comparação, bloqueios, PDF, escopo de resumo e correspondência parcial. Contratos de renderização Python/JavaScript foram executados; não foi feito teste visual novo em navegador.
- A primeira suíte completa encontrou duas incompatibilidades: código público HTTP 429 e equivalência `3.000`/`3000`. O código foi corrigido e **92 testes focados passaram**; o log inicial permanece em `full-suite-first.txt`. Gabaritos antigos preservados.
- Suíte completa final: **1.018 aprovados, 4 ignorados, 2 avisos**, em **243,81 s**; log em `qa-artifacts/v59/full-suite.txt`. Avisos preservados: descontinuação de `mss.mss()` e de `timeout` no TestClient.
- E2E de qualidade real: consultas e recuperação acima usam serviços externos reais. Ofertas da segunda onda e contratos JDUI usam fixtures determinísticas; não são apresentados como ofertas reais. Parser PDF/integração possuem testes locais; não foi validado um PDF externo ao vivo nesta rodada.

## Arquivos e commits locais

Código: `search_orchestrator.py`, `search_providers.py`, `research.py`, `web_extract.py`, `shopping.py`, `research_agents.py`. Regressões: `tests/test_search_coverage_v59.py`. Medição reproduzível: `tools/search_coverage_v59.py`. Evidências: `qa-artifacts/v59/`. Continuidade: `docs/V5_9_PROGRESS.md`.

- `99560c9` — restrições, relevância, proveniência e cache.
- `35cdb28` — recuperação primária, limites e escopo da evidência.
- `8f268be` — compatibilidade de rate limit e evidência numérica.

## Limitações e próximos gargalos

- **Shopping ao vivo:** aumentar descoberta de páginas individuais acessíveis e confirmação estruturada, sem promover preço de snippet/listagem ou contornar bloqueio. Nesta amostra, o ganho foi demonstrado em regressões do pipeline; a taxa real de confirmação não melhorou.
- **Ciência de materiais:** a busca geral continua insuficiente. OpenAlex/Crossref existentes seguem sob a configuração opt-in original; ela não foi ativada em produção. É necessário validar cobertura acadêmica específica e acesso real ao texto dos estudos.
- **Cobertura geral:** o catálogo conservador de URLs oficiais reconhecidas é pequeno; fora dele a qualidade depende dos provedores e do conteúdo acessível. Snippets não sustentam afirmações específicas sobre páginas não lidas.
- **Extração:** páginas dinâmicas, paywalls, metadados acadêmicos fora dos formatos reconhecidos e PDFs sem texto ainda exigem tratamento adicional. Datas/autor ausentes permanecem desconhecidos.
- **Documentos locais:** o Quality Lab v2 ainda expõe falha de priorização da fonte temporal mais recente e precisão limitada no top 5. Esse ranking documental não foi reescrito nesta fase; precisa de correção específica com as fixtures existentes.

Autenticação, isolamento, SSE, identidade Lucas, 3D, extensão Júlia e Fajulto Studio foram preservados. Nenhum processo de produção foi reiniciado e nenhum push/deploy foi feito.
