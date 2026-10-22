# VEXX AI V5.9.3 — Precision Search & Real-world Intelligence

Entrega local de 22/10/2026. HEAD inicial **78dae77**, árvore inicialmente limpa; código final **80d0aea**. HEAD de entrega é o commit que contém este relatório (`git log -1`). Sem push/deploy/reinício de produção. Identidade Lucas, 3D, extensão e Fajulto preservados.

## Ganhos medidos

No Quality Lab v2, **8 consultas / 12 documentos sintéticos**, precisão micro dos documentos efetivamente retornados subiu de **11/13 (84,62%) para 11/11 (100%)**, preservando os 11 acertos. **nDCG@10: 0,925589 → 0,982614**. P@5 **0,275**, P@10 **0,1375**, recall **0,916667** e MRR **1** permaneceram iguais.

P@K divide por K fixo; esses resultados não medem precisão universal ou qualidade web. Holdout adicional de três consultas congeladas: precisão/recall dos candidatos elegíveis **0,388889/0,666667 → 1/1**, nDCG@10 **0,843401 → 1**; P@5 permaneceu **0,4**. Conjunto pequeno, sem alegação de generalização. Definições, hashes e comparação reproduzível em [BENCHMARK](docs/v5.9.3/BENCHMARK.md).

## Causas corrigidas

1. FTS cortava candidatos antes de reclassificar e favorecia cópias curtas. Agora recupera candidatos limitados e reclassifica por cobertura, declaração explícita de republicação e ranking original antes do corte.
2. Termos presentes como substring, modelo errado ou acessório recebiam relevância. Usadas fronteiras de token, identidade de modelo e contexto do produto; relevância antecede bônus de fonte primária.
3. Consultas com “notícias de” não preservavam localidade; cidade/estado e janela recente agora são estruturados, com RSS público adicional no orquestrador existente.
4. Turismo podia contar como evento/rota. Evento exige data do acontecimento; transporte exige contexto de transporte no título ou itinerário estruturado. Uma página turística inicialmente aceita na sonda aérea foi identificada e rejeitada, preservando o registro do falso positivo.
5. Fontes abertas irrelevantes ocupavam os primeiros lugares e escondiam fontes úteis posteriores. Reclassificação agora ocorre antes do limite final de fontes.
6. Fonte RSS era tratada como página ilegível. Permanece manchete encontrada/não lida e resposta parcial, com zero fatos confirmados a partir do índice.
7. Ciência parava no abstract. Uma tentativa de PDF OA declarado agora usa downloader/PDF existentes, limite de 2 MiB, identidade de título/DOI e texto suficiente; falhas conservam abstract e motivo. Metadados irrelevantes são filtrados antes do download. Escopo/URL real persistem em evidências, grafo e checkpoint.
8. Evidências não lidas podiam gerar buscas de contradição; agora são excluídas. Datas/modelos/metodologia são condições explícitas a conferir. Regressão de “consumo” versus “consome” foi reparada para preservar contraevidências reais.
9. Shopping passou a reconhecer novas famílias e rejeitar conflitos explícitos de tipo, acessório, capacidade em litros e tensão; limites/variantes/preço/estoque mantidos. Links de licença/schema não gastam orçamento de candidatos.
10. Cards contextuais reaproveitam `sources`, com autores/DOI/veículo/evento/rota e links de texto quando existentes. Data de acesso deixou de parecer publicação no comando de fontes do chat. Validação Python/JS, escape, estado vazio e links seguros preservados.

## Resultados externos e limites

- **16 sondas externas** e repetições pontuais com motivo registrado; sem loops contra bloqueios.
- Aéreo/ônibus: nenhuma tarifa, assento ou disponibilidade confirmados; datas/rotas/passagens de retorno preservadas. Guia turístico não conta como rota.
- Ubatã/Salvador/Feira: manchetes municipais/regionais datadas descobertas; links de agregador, artigos originais não lidos. Três replays demonstram apresentação parcial correta, sem nova chamada de rede.
- Recife: nenhuma agenda/ingresso confirmado; turismo passou a ser rejeitado.
- Baterias/semicondutores: três abstracts pertinentes em cada consulta, sem full text útil confirmado. PDF RSC bloqueado; Transformer excedeu 2 MiB. Um PDF de outro assunto foi extraído, mas rejeitado: não conta como ganho de evidência científica útil.
- Documentação: duas fontes úteis FastAPI/Django. Câmbio diário/histórico real preservado e exercitado no Chrome; não é cotação negociável intradiária.
- Shopping: zero ofertas externas confirmadas em geladeira/ferramenta/livro. Diagnóstico mantém etapa de perda, listagens, JSON-LD, item individual, orçamento/variante e bloqueios. **7/7 pipelines sintéticos** das novas famílias extraem produtos e geram JDUI; isso não confirma ofertas externas.
- REAL_MODEL: endpoint loopback consultado não forneceu catálogo JSON válido; nenhuma inferência executada. Sem mudança de modelos/credenciais/serviços pagos.

## Testes e apresentação

Resultado final da suíte: **1089 passed, 4 skipped, 2 warnings**, 265,98 s. Primeira regressão completa: **1 failed, 1086 passed, 4 skipped**, por inflexão consumo/consome; teste antigo preservado e causa corrigida. Logs em `qa-artifacts/v593/`.

Focados: 55 testes de fontes/segurança/paridade; 74 de integração/recuperação/shopping; 44 aprovados e um ignorado no reparo de contraevidência. Benchmarks congelados **34/34 pesquisa, 59/59 shopping, 16/16 experiência**; gabaritos antigos não alterados.

Chrome local real: reload/SSE, 43 eventos, barra encerrada, exportação 200/1983 bytes, imagem/zoom/Escape, cards contextuais fixture, câmbio externo e gráfico persistido. Desktop 1280/mobile emulado 390/320; zero erros registrados. [JDUI_RESULTS](docs/v5.9.3/JDUI_RESULTS.md) distingue dados reais e fixtures; screenshots inspecionadas. Sem validação em aparelho físico ou vídeo analisado.

## Arquivos, segurança e continuidade

Principais alterações: `docs_agent.py`, `query_intelligence.py`, novo `search_verticals.py`, `search_orchestrator.py`, `search_providers.py`, `web_extract.py`, `academic_research.py`, `research.py`, `research_agents.py`, `shopping.py`, `research_view.py`, `jdui.py`, `pc_agent.py`, `public/jdui.js`, `public/styles.css`. Testes em `tests/test_precision_v593.py`; ferramentas `tools/*v593.py`; artefatos `qa-artifacts/v593/`.

Commits locais: `e9cb923` (documentos/baseline), `c6b056d` (precisão/verticais/OA), `07e170d` (cards/produtos/testes), `80d0aea` (contexto de rota e contraevidência), mais commit final de documentação/evidências.

SQLite, Render/PC Agent, rate limiting, CSRF, RBAC, SSRF, grants, circuit breaker, SSE/reconciliação, cancelamento e checkpoints mantidos. Nenhum paywall/bot-wall contornado. Limites de download não elevados; cache 5.9.3 invalida respostas do algoritmo anterior sem apagar dados reais. Artefatos de QA não contêm credenciais de produção; contas/perfis/bancos de Chrome são temporários.

Pendentes: leitura dos artigos originais de notícias, agenda futura verificável, fontes de inventário/tarifas, ofertas comerciais confirmadas, full text científico útil dentro dos limites e inferência real. Topônimos sem estado/região continuam ambíguos; não houve geocodificação universal. Critérios de unidades/compatibilidade de produtos além dos extraídos ainda exigem expansão validada; não há promessa de precisão universal. Não anunciar suporte completo com base em contratos ou fixtures. Próximo passo em `docs/v5.9.3/PROGRESS.md`.
