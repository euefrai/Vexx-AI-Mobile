# VEXX AI V5.9.5 — Verified Source Intelligence & Deep Retrieval

Etapa implementada localmente com aceitação externa parcial. O sistema distingue melhor descoberta, leitura e dado específico verificado; resultados externos ainda não permitem aprovar pesquisa profunda/comercial universal. Sem push, deploy, reinício de produção, serviço pago ou alteração de dados reais.

## Baseline e alterações

HEAD inicial `942e156171e306d80b7ff690960048963905db3b`; baseline herdado de 1.308 testes aprovados/quatro ignorados. Commits locais iniciais: `a5b33cb` (limites de trechos numéricos e evidência anterior), `f5d4897` (contratos e verticais). Complementos de documentação/mídia/circuitos em `4ee7575`; ajuste visual de zoom em `1a86671`. Relatório/evidências no commit local de entrega; consultar `git log`.

| Problema real | Correção / arquivos |
| --- | --- |
| Corte podia transformar 200 em 0 | Janela em limites de tokens, preservando números/decimais; `web_extract.py`, `research_agents.py`, `research_view.py`; regressões `tests/test_excerpt_boundaries.py`. |
| Feed era contado como artigo suficiente, deslocando leitura original | Descoberta continua e artigo precede feed na deduplicação; `search_orchestrator.py`. |
| Plano/retomada podiam perder janela horária e cidade | Contrato original preservado; cidades/UF, datas relativas e horas; `query_intelligence.py`, `research_agents.py`. |
| Página aberta podia encerrar lacuna sem conter dados pedidos | `required_data`, `data_complete`, validação temporal/geográfica, eventos, rota/passageiros/tarifa e expiração; `search_verticals.py`, `research_agents.py`. Sem inventário ao vivo alegado. |
| TV era alternativa de celular | Família comercial/acessórios, priorização de modelo/página individual e trace de ofertas; `shopping.py`. Replay real congelado comprova exclusão da TV. |
| OA se limitava a PDF e podia confundir local aberto com página primária fechada | Leitura HTML OA limitada, identidade DOI/título e localização/licença coerente; `academic_research.py`. Não promete leitura integral. |
| Escopo/seções OA e metadados podiam se perder no SQLite/leitor customizado | Persistência/releitura de formato, escopo, seções e metadados; `research_agents.py`. |
| Pergunta específica TaskGroup usava página genérica | Roteamento de documentação oficial específica e termos relevantes; `search_orchestrator.py`, `research_agents.py`. Fonte real lida: zero → um. |
| URL de mídia desaparecia sem HTML legível | Preservar descoberta com proveniência, licença desconhecida quando ausente, sem alegação de análise/evidência; `media_evidence.py`, `research_agents.py`. |
| Retry repetia provedor bloqueado; registro confundia capacidade com verificação | Circuito existente centralizado e capacidades declaradas separadas de prova; `search_providers.py`. |
| Card repetia disponibilidade e não distinguia HTML/PDF limitado | Texto/escopo/cobertura refinados; `research_view.py`. |
| Botões das fontes quebravam palavras a 200% de zoom | Ações podem empilhar por espaço disponível; `public/styles.css`; recaptura visual local confirmou correção. |

Reutilizados orquestrador, downloader seguro, SQLite, pesquisa acadêmica, shopping, componentes JDUI e controles existentes. Sem motor paralelo, dependência nova ou API paga.

## Verificações

- Suíte final: **1.354 passed, 4 skipped, 2 warnings**, 180,96 s após ajuste CSS. Log `qa-artifacts/v595/full-suite-delivery.log`. Avisos existentes: depreciação `mss.mss` e timeout do TestClient. Ignorados não contam como aprovados.
- Primeira suíte completa: sete falhas/1.343 aprovados. Circuito compartilhado vazava entre testes e uma expectativa requeria duas chamadas após bloqueio; isolamento corrigido e 403/429 parametrizados independentemente. Regressão nova verifica que retry não chama rede novamente. Falhas originais preservadas em `full-suite.log`, sem suprimir teste. Ajuste de duplicação de aviso também validado.
- Testes focados após mudanças; último conjunto 72 aprovados. Conjuntos sobrepostos não somados. Laboratório congelado mantém as métricas do baseline.
- `git diff --check` de código/documentação (logs brutos preservam espaços do pytest), sintaxe JavaScript e validação visual local executados; detalhes em `docs/v5.9.5/JDUI_RESULTS.md`.
- Avaliação externa em SQLite temporário: 15 casos universais, repetições dirigidas e 13 categorias comerciais. Não é E2E autenticado do chat. Evidências e classificação explícita em `qa-artifacts/v595/universal-assessment.json` e `docs/v5.9.5/UNIVERSAL_BENCHMARK.md`.

## Resultado externo e pendências

Dois PDFs públicos realmente abertos com extração limitada e uma página oficial TaskGroup lida. Três resumos acadêmicos não equivalem a textos completos. Clima e câmbio diário responderam pelo caminho existente; módulo de clima/localização não alterado.

**Zero oferta comercial exata confirmada; zero tarifa/inventário verificado; zero artigo local original lido.** Produtos parciais podem ter conflitos título/specs (Lenovo 8 GB diante do pedido 16 GB), que ainda exigem resolução conservadora. Imagem/vídeo solicitados não foram confirmados: URLs genéricas não satisfazem o pedido. Métodos/métricas dos estudos ainda não têm comparação aprovada.

Modelo gratuito configurado foi descoberto no catálogo, mas a tentativa SSE real retornou vazia (zero chunks). Estado `BLOCKED`; não se aprovou inferência, streaming de modelo ou Deep Research completo, nem se trocou para serviço pago. Testes SSE locais não substituem essa integração real.

Próximo trabalho: conflito de identidade/specs comercial; seleção de artigos originais locais e relevância de mídia; depois uma única validação real do modelo quando houver disponibilidade, com revisão de suporte semântico. Não ampliar número de provedores antes de corrigir essas perdas. Matriz declarada/licenças/limites em `docs/v5.9.5/PROVIDER_MATRIX.md`.
