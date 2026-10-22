# Vexx AI V5.9.1 — Retrieval Recovery

Data: 22/10/2026. Execução local; sem push, deploy ou reinício de produção.

## Resultado

- Pesquisa científica: baterias passou de **0 para 3 resumos pertinentes**; semicondutores, de **0 para 3** pelo critério lexical do motor. Metadados públicos efetivamente recuperados, com DOI, autores, datas e proveniência. **Nenhum desses nove resultados científicos foi contado como texto completo ou página original aberta.**
- Ranking documental: a fonte temporal do Quality Lab v2 passou de **0/1 para 1/1** recuperada. Fixtures e gabaritos preservados.
- Shopping: **0/3 consultas com oferta confirmada antes e depois**. Foram corrigidos defeitos reais de seleção e validação, mas não houve aumento da cobertura comercial externa. Não considerar esse gargalo resolvido.
- **Suíte completa final: 1.035 passed, 4 skipped, 2 warnings, 125,25 s**, sem falhas. Os dois warnings já existiam: depreciação de `mss.mss()` e timeout no TestClient.

## Baseline e causas

Checkout inicialmente limpo em `82a18ea`, com V5.9.0 local. Log anterior confirma 1.018 testes aprovados, 4 skipped e 2 warnings. A baseline externa foi repetida antes das alterações: `qa-artifacts/v591/baseline-real.json` e `baseline-semiconductors.json`.

1. **Descoberta comercial:** categorias genéricas podiam encerrar a cadeia; o teto de candidatos era aplicado antes de ordenar todas as URLs. O JSON-LD também podia perder um produto compatível por limitar a saída aos quatro primeiros registros.
2. **Critérios e validação:** Galaxy como categoria impedia inferir o armazenamento de “A56 256 GB”. A sequência “novo” dentro de Lenovo acionava condição de produto novo. RAM desconhecida podia coexistir com contagem de oferta confirmada. Após abrir o item declarado por uma categoria, preço e identidade atualizados não passavam novamente pelos filtros.
3. **Pesquisa científica:** a busca rápida não aproveitava o normalizador bibliográfico existente. Provedores gerais devolviam dicionários de “avanços” e lojas de baterias. Uma primeira integração Crossref sem filtro de tipo/resumo recuperou principalmente metadados de livros, sem leitura útil; esse experimento foi registrado e corrigido.
4. **Documentos e tempo:** o fallback lexical não era ordenado quando o FTS estava instalado, mas não encontrava resultados. A consulta AND podia excluir o documento novo por não repetir “trial”. A intenção temporal da pergunta se perdia entre pergunta e subconsulta do Quality Lab. O ranking web usava anos em snippets para bônus de recência, sem consultar corretamente a publicação normalizada.

## Correções

### Shopping

- Ordenar candidatos antes do corte, preservando o teto de páginas e duas ondas. Para pedidos específicos, categorias não bastam para encerrar descoberta.
- Reutilizar a segunda consulta existente para destacar o modelo quando a primeira não entrega cobertura. Preservar marca, modelo, armazenamento, RAM e orçamento; manter a primeira consulta ampla sem teto de preço, conforme contrato legado.
- Selecionar até quatro produtos entre até 64 registros estruturados, priorizando compatibilidade com o pedido, sem downloads adicionais. Essa seleção não verifica ofertas.
- Manter parâmetros de identidade como `sku` e `variant` na comparação de recursos; continuar ignorando rastreamento.
- Extrair armazenamento explícito de celulares, inclusive Galaxy A56 sem a palavra “celular”. Distinguir capacidade exata de pedidos “pelo menos”. Corrigir detecção de palavras completas nas condições.
- Reaplicar critérios depois da validação do item e usar identidade/preço da própria página. Manter pendências como correspondência parcial, sem contagem de confirmada.
- Respeitar `priceValidUntil`: preço expirado não é confirmado, não é reutilizado do cache e não aparece como valor atual no JDUI. Follow-up de consulta expirada pede nova verificação.
- Preservar Decimal na normalização existente, moeda, identidade, estoque desconhecido, imagem e proveniência. Exercitar o fallback OpenGraph já existente; não adicionar inferência de preços de texto livre.
- Registrar URLs, consultas, classificação de candidatos, diagnósticos por página, origem da extração, duração e descarte. Diferenciar `DISCOVERY_EMPTY`, `SEARCH_IRRELEVANT`, `PROVIDER_BLOCKED`, `PRODUCT_PAGE_UNAVAILABLE`, `STRUCTURED_DATA_MISSING`, `PRICE_UNVERIFIED`, `VARIANT_MISMATCH`, `PRODUCT_MISMATCH` e `BUDGET_MISMATCH` quando demonstráveis. O harness registra o payload JDUI; nenhuma falha de entrega foi observada nas fixtures.
- Não tentar DDG Lite após bloqueio explícito do DDG. Respeitar o circuito compartilhado. Comparar o status antes/depois da chamada para não interpretar um bloqueio antigo como resultado da consulta atual.

### Ciência e evidência

- Integrar Crossref ao orquestrador da busca rápida, reutilizando `academic_research.normalize_crossref`, o downloader seguro e o orçamento existente. Uma chamada por tentativa; bloqueio/429 abre circuito, sem retry ou espera adicional nessa integração.
- Usar equivalentes determinísticos para baterias de estado sólido, materiais semicondutores e arquitetura Transformer. Outros assuntos mantêm seus termos.
- Pedidos recentes filtram datas de publicação dos últimos dois anos, até a data UTC atual. A busca privilegia registros `journal-article` com resumo, sem presumir revisão por pares. Referência: [filtros oficiais Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/).
- Reutilizar o resumo efetivamente fornecido pela API. Preservar DOI, autores, ano, tipo declarado, URL original e URL da consulta bibliográfica. `abstract_only`, `metadata_only` e `full_text_fetched=False` seguem até as fontes e o grounding.
- Metadados sem resumo não encerram a busca como evidência útil. Deduplicar DOI entre URLs distintas; títulos iguais com DOIs distintos não são automaticamente fundidos.
- Preservar o Evidence Graph existente e persistir tipo e origem da data no caminho acadêmico. A integração OpenAlex/Crossref opt-in dos agentes continua existente; não foi ativada globalmente.

### Datas e documentos

- Separar publicação de atualização/indexação/recuperação: estas últimas não substituem publicação. Preservar precisão e origem das datas Crossref, escolhendo a publicação válida mais antiga entre online, impressa e issued.
- Interpretar ISO, ano, mês e RFC com normalização de fuso para comparação. Ignorar datas futuras e inválidas no bônus de recência; não inventar uma publicação ausente.
- Usar relevância antes da preferência por fonte primária. Aplicar recência somente a pedidos temporais.
- Ordenar o fallback documental mesmo com FTS disponível. Passar a pergunta como contexto opcional à recuperação; em pedidos temporais, ampliar candidatos OR de forma limitada e priorizar datas explicitamente declaradas no conteúdo entre trechos pertinentes. Data de upload não entra na ordenação.

## Shopping externo antes/depois

| Cenário | Ofertas confirmadas antes → depois | Tempo antes → depois | Chamadas finais / bloqueadas |
|---|---:|---:|---:|
| Lenovo 16 GB RAM até R$ 3.000 | 0 → 0 | 6,513 → 8,516 s | 15 / 4 |
| Samsung Galaxy A56 256 GB | 0 → 0 | 10,611 → 12,123 s | 18 / 1 |
| Tênis de basquete até R$ 300 | 0 → 0 | 8,830 → 6,666 s | 14 / 5 |

São snapshots únicos, não um ensaio estatístico. A baseline Samsung incluía o prefixo “Celular”; a execução final usa literalmente o pedido sem esse prefixo. Não atribuir a diferença de tempo desse caso exclusivamente ao código. Chamadas representam operações instrumentadas de download/API, sem contagem de cada redirect ou conexão de transporte.

- **Lenovo:** seis páginas candidatas. Uma categoria forneceu quatro produtos estruturados; os itens não atenderam conjuntamente marca/RAM/orçamento. O item Lenovo observado custava R$ 5.532,99 na categoria e não teve sua página individual confirmada. Não é oferta válida para o pedido. Foram três páginas bloqueadas, duas listagens sem item aproveitável e uma página com extração estruturada.
- **Samsung:** armazenamento final corretamente extraído como 256 GB, modelo A56. Seis páginas, sem ofertas extraídas: três sem dados estruturados, uma listagem e duas respostas acima do limite permitido. Isso não é “tudo bloqueado”.
- **Basquete:** seis páginas, quatro bloqueadas e duas sem dados estruturados úteis.
- Mercado Livre respondeu 403 nas sondas. Não houve contorno. Listas/categorias dominaram a descoberta; não se confirmou URL individual compatível com preço, variante e demais requisitos.
- Quantidades finais de ofertas válidas, correspondências exatas/parciais exibidas e preços confirmados: zero. Métricas condicionadas a uma oferta aceita — imagem acessível e estoque — não podem ser estimadas; não inventar percentuais de sucesso.
- A fixture do pipeline completo prova que um item compatível após nove categorias chega à leitura, validação, SQLite e `productcard`. Outra fixture prova que um preço atualizado acima do teto é barrado antes da entrega. Isso **não** representa uma compra ou oferta externa real.

## Pesquisa científica externa

| Consulta | Fontes úteis antes → depois | Tempo antes → depois | Leitura final |
|---|---:|---:|---|
| Estudos recentes de baterias de estado sólido | 0 → 3 | 5,099 → 2,153 s | Três resumos Crossref, duas chamadas |
| Estudos recentes de materiais semicondutores | 0 → 3 | 7,208 → 2,882 s | Três resumos Crossref, cinco chamadas |
| Estudos sobre arquitetura Transformer | Sem baseline equivalente → 3 | — → 0,778 s | Três resumos Crossref, uma chamada |

Exemplos efetivamente recuperados:

- Baterias: *Advances in All-Solid-State Batteries Based on Chloride Solid Electrolytes*, publicado em 04/02/2026, DOI [10.3390/batteries12020051](https://doi.org/10.3390/batteries12020051).
- Semicondutores: *Band Gaps of HoxSc1−xN, HoxY1−xN, and YxSc1−xN Semiconductor Alloys*, publicado em 22/09/2026, DOI [10.3390/ma19194037](https://doi.org/10.3390/ma19194037).
- Transformer: estudos de aplicações, como classificação de malware com Vision Transformer, DOI [10.14421/csecurity.2025.8.1.5107](https://doi.org/10.14421/csecurity.2025.8.1.5107). Não equivalem ao artigo fundador.

O pedido técnico original sobre Transformer continua recuperando o resumo do trabalho original arXiv, com uma fonte útil; FastAPI/Django continuam com duas fontes oficiais úteis e asyncio com uma. Não foram produzidas conclusões científicas novas por LLM nesta avaliação. Os resumos e dados bibliográficos são a evidência recuperada; desenho experimental, revisão por pares e qualidade editorial não são inferidos do DOI. “Útil” nas métricas significa correspondência lexical do motor, não avaliação científica independente. Um registro de mercado de materiais e metadados de série de conferências também aparecem nos resultados de semicondutores; a seleção fina e a qualidade editorial permanecem limitadas.

## Ranking temporal medido

Quality Lab v2, dataset congelado, local e sintético:

| Métrica | V5.9.0 | V5.9.1 |
|---|---:|---:|
| Fonte temporal mais recente recuperada | 0/1 | 1/1 |
| Precision@5 | 0,250000 | 0,275000 |
| Recall@5 | 0,854167 | 0,916667 |
| nDCG@5 | 0,816970 | 0,925589 |

O runner agora entrega a intenção da pergunta ao recuperador; não foram alteradas respostas esperadas, documentos ou relevâncias do dataset. A melhoria também inclui ordenação correta do fallback, portanto não atribuir todos os ganhos apenas à recência. Quality Lab v1: precision 0,266667, recall 1,0 e nDCG 1,0. Esses números não medem a Internet.

## Testes, escopo e evidências

- 17 regressões novas, incluindo documentos novos/antigos/irrelevantes/sem data, publicação versus indexação, fuso, datas inválidas, variantes, produto depois do corte, preço alterado, validade, fallback OpenGraph, DOI e bloqueio acadêmico.
- Rodada relacionada: 549 passed, 4 skipped; rodada final dos critérios: 113 passed, 2 skipped. Logs de falhas intermediárias preservados; correções verificadas com testes focados.
- Benchmarks congelados, executados novamente após a última correção: pesquisa **34/34**, shopping **59/59**, experiência **16/16**.
- **FIXTURE:** extração HTML/JSON-LD/OpenGraph, filtros, ranking, SQLite, payload JDUI, falhas e contratos. O teste antigo que exigia DDG Lite após bloqueio foi atualizado para exigir ausência dessa tentativa; nenhum gabarito de benchmark foi modificado.
- **LOCAL_E2E limitado:** testes da aplicação via TestClient cobrem jobs de pesquisa, isolamento, cancelamento e SSE com replay/fechamento. Dependências externas são controladas nesses testes; isso não prova um Hermes real ou interação visual no navegador.
- **EXTERNAL_E2E sem LLM:** consultas, provedores, páginas e metadados públicos reais pelo pipeline Python. A resposta final é determinística. O smoke não utiliza conta de produção nem inferência paga.
- **BLOCKED:** recusas 403/CAPTCHA e conteúdo indisponível são diagnósticos, não recuperação bem-sucedida.
- Não houve teste visual novo, integração com Hermes real nem verificação editorial independente. Falhas de provedor/ausência de evidência são cobertas pelos contratos existentes; não alegar disponibilidade real de todos os serviços.

Evidências: `qa-artifacts/v591/final-validated-real.json`, `comparison.json`, `baseline-real.json`, `baseline-semiconductors.json`, `quality-lab-v2-final.json`, `full-suite.txt` e benchmarks. `tools/retrieval_recovery_v591.py` reproduz as sondas com SQLite em memória e teto de 75 segundos por caso. Não há preços fictícios misturados ao snapshot externo.

## Limitações e próximos gargalos

1. Recuperação comercial ainda precisa de descoberta de itens específicos acessíveis. Não aumentar retries nem flexibilizar verificação para preencher cards. Algumas páginas grandes foram corretamente recusadas pelo limite atual.
2. Ranking temporal web ainda usa granularidade anual no peso de atualidade; parsing mais preciso não equivale a ordenação editorial perfeita dentro do mesmo ano. Datas do conteúdo documental são declarações, não prova de publicação; fuso ausente é normalizado internamente para comparação.
3. Equivalentes científicos são limitados; relevância fina, tradução ampla, qualidade editorial e classificações experimentais exigem evolução posterior. Resumo não substitui análise do artigo completo.
4. Os tempos externos variam com rede/provedores. Shopping total observado ficou mais lento e não ganhou ofertas; não anunciar ganho global de desempenho.
5. Nenhuma configuração de produção, credencial, permissão remota, rebrand, memória, 3D, extensão Júlia ou Fajulto foi modificada.

## Arquivos e commits locais

Código: `academic_research.py`, `docs_agent.py`, `research.py`, `research_agents.py`, `research_quality_lab.py`, `search_orchestrator.py`, `search_providers.py`, `shopping.py`.

Validação: `tests/test_temporal_recovery_v591.py`, `tests/test_retrieval_recovery_v591.py`, `tests/test_shopping_discovery_v571.py`, `tools/retrieval_recovery_v591.py`, `qa-artifacts/v591/`.

Documentação: este relatório e `docs/V5_9_1_PROGRESS.md`.

- `95ccbb8` — recuperação bibliográfica e intenção temporal.
- `779e941` — seleção comercial, filtros finais, validade e diagnóstico.
- `32d167c` — correção comprovada dos critérios Galaxy/Lenovo.
- Relatório e evidências registrados em commit local de documentação após a validação final.
