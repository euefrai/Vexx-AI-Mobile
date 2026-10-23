# VEXX AI V5.9.6 — Deep Retrieval & Premium Research Experience

Entrega local com ganhos medidos e limitações externas explícitas. **Sem push, deploy, reinício de produção, troca de modelo/identidade ou API paga.**

## Git e escopo

HEAD inicial: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`.

HEAD final de implementação: `7a8a707c22d2bfdbaa944d0252e64681d83852df`; relatório/evidências são salvos no commit documental posterior. Commits locais: `883a76c` (originais/RAM), `d5344a4` (contexto, mídia e JDUI), `fbbb392` (regressões e CSV), `7a8a707` (composição sem galeria de referências duplicadas). Código evoluiu nos módulos existentes; nenhum motor paralelo criado.

Arquivos de código alterados: `search_providers.py`, `search_orchestrator.py`, `research_agents.py`, `shopping.py`, `academic_research.py`, `media_evidence.py`, `hermes_bridge.py`, `research_view.py`, `jdui.py`, `public/jdui.js`, `public/styles.css`, `public/app.js`. Acrescentados testes focados, dataset de 14 categorias, instrumentos de avaliação/preview e documentação. Clima/geografia, identidade, extensão, Studio, 3D, contas e permissões não alterados.

## Ganhos e causas

- Imagens solicitadas: **0 → 5** relacionadas à Ponte Estaiada, recuperadas por adaptador real e carregadas no Chrome. Corrigidos termos da consulta, metadados descartados e host novo de thumbnails do Commons.
- Lenovo real de 8 GB não permanece aceito como pedido de 16 GB no replay congelado. RAM física/virtual, campos estruturados, títulos e conflitos tratados conservadoramente. Diagnóstico de identidade adicional sem afrouxar preço/variante/link/estoque.
- Feed agora conserva publicador e pode orientar busca por manchete e RSS/Atom/links declarados no site, com orçamento rastreável. **Ubatã continua com zero artigo original lido**; os caminhos adicionais foram tentados, não aprovados por presença de código.
- Plano científico mantém entidades e pergunta em todas as frentes; resumos não fecham lacuna de texto completo quando métodos/métricas são exigidos. Na comparação final foram abertos dois PDFs OA com texto limitado; não foi comprovado aumento geral de cobertura científica sobre a V5.9.5.
- Streaming UTF-8 não descarta caracteres quando um código multibyte é dividido entre blocos. Teste envia cada byte separadamente. Raciocínio do provedor nunca foi convertido em conteúdo público.
- JDUI mostra fontes/proveniência e galeria contextual, preserva schema/sanitização, não cria dados visuais ausentes. Corrigido “Baixar CSV” inerte nos painéis, por callback ausente.

## Modelo real

Diagnóstico curto de 160 tokens: HTTP 200 SSE, zero chunks públicos. Diagnóstico limitado com os 1.800 tokens já usados pela pesquisa: **184 chunks reais ordenados**, 14,571 s. O prefixo capturado contém eventos de raciocínio; o limite curto pode consumir o orçamento antes da resposta. A captura de transporte é prefixo limitado a 64 KiB, nunca o corpo completo ou credenciais. A resposta não passou no critério literal de citação; streaming funcional não equivale a síntese aprovada.

Deep Research real foi executada. A primeira separava o contexto e recuperou página genérica de lítio; após correção, dois PDFs OA foram lidos. Na tentativa final de síntese o provedor retornou `rate_limit`: estado **BLOCKED**, sem nova tentativa, modelo alternativo ou serviço pago. Não aprovar Deep Research completa com modelo por causa do diagnóstico de streaming.

## Testes e medições

- Baseline fresco: 1.353 aprovados, quatro ignorados e uma falha preexistente de índice `/noticias/`; o resultado anterior de 1.354 não foi presumido atual. Causa corrigida sem alterar gabarito.
- Testes focados por fase; 258 no conjunto comercial/recuperação, 121 mídia/stream, 65 apresentação (sobrepostos, não somar).
- Regressões desta etapa foram detectadas e corrigidas: campo de leitura no schema errado, paridade Python/JS, ordem genérica antiga e callback de CSV. Logs de falhas preservados, sem excluir testes.
- Suíte completa final: **1.374 aprovados, quatro ignorados, dois avisos**, 205,64 s. Última confirmação após CSV e composição em `qa-artifacts/v596/full-suite-final-acceptance.log`.
- Congelados preservados: Search **34/34**, Shopping **59/59**, Experience **16/16**; Quality Lab reexecutado, sem mudar datasets/gabaritos. Esses resultados são locais, não cobertura web.
- Chrome desktop/390/320/zoom, galeria, Escape, fonte, reload, CSV e erro de rede exercitados. Harness é componente com capturas reais; não sessão autenticada do app. Detalhes em `docs/v5.9.6/JDUI_RESULTS.md`.
- `node --check` de app/JDUI e diff de código/documentação verificados. Logs brutos preservam whitespace do pytest. Sem perfil de RAM/custo ou alegação de redução global não medida.

## Resultado externo e próximo passo

Avaliação separa FIXTURE, FROZEN_REPLAY, LIVE_EXTERNAL, REAL_MODEL e CHROME_E2E de componentes. As 14 categorias e suas restrições, leituras, cards/schema, latência, chamadas observadas e motivos estão em `docs/v5.9.6/BENCHMARK.md` e `qa-artifacts/v596/assessment.json`.

**Ofertas exatas confirmadas: 0. Tarifas/inventários confirmados: 0. Artigos locais originais lidos: 0. Vídeo solicitado confirmado: 0.** Cinco imagens pertinentes e dois PDFs limitados não representam cobertura universal. Links/mídias genéricas não são evidência elegível. Métodos, amostras e métricas ausentes não foram fabricados; persistência de expansão nos painéis reais ainda precisa de integração com seu contexto de estado.

Próximo passo preciso: usar a pista recente de Ubatã para melhorar acesso legítimo ao artigo do veículo, com uma estratégia limitada e prova de texto original; depois validar a síntese profunda quando o provedor estiver disponível, sem retry de rate limit. Aprofundar identidade comercial além de RAM conforme conflitos reais forem encontrados. Não ampliar indiscriminadamente provedores ou limites do PC.
