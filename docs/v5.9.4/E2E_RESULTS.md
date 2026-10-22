# V5.9.4 — E2E e evidências

## Ambiente executado

Chrome real headless por CDP, perfis temporários, relay Uvicorn real e PC Agent real, SQLite descartável, autenticação pela interface. Controle remoto desativado no ambiente de QA, sem modificar configuração de produção. Fluxo real do composer com mensagens e respostas persistidas, sem chamar inferência LLM.

Script: `tools/chrome_e2e_v594.py`; worker: `tests/live_fixture_agent_v594.py`. O worker herda o bloqueio de execução fora de diretório temporário/flag de teste. Apenas pesquisa profunda usa fonte fictícia Bateria ZX e leitura atrasada em 10 s para permitir reload; clima, IBGE, geocodificação e câmbio usam adaptadores externos reais. Os cards adicionais de ciência/notícia/evento/transporte são fixtures identificadas, não acontecimentos/ofertas confirmados.

## Critérios executados

- Login → chat → temperatura em ubata bahia agora: Ubatã, Bahia, Brasil; IBGE 2932309 e GeoNames 3445849; temperatura Celsius, sensação, condição, unidades, fonte e horário válidos. Evidência pública: `live-trace.jsonl`, `chat-transcript.json`.
- “e amanhã?”: conserva Ubatã e apresenta previsão com probabilidade, sem rotulá-la como observação. Um único fetch meteorológico alimenta as duas mensagens por cache; geocodificação subsequente usa cache.
- “oi”: resposta natural; delta de geocodificações = 0.
- Horário: relógio real convertido no fuso legítimo America/Bahia recebido do navegador; data/fuso no card.
- Novo chat: “qual a temperatura?” pede cidade; não herda Ubatã. Novo cumprimento não preenche a cidade pendente.
- Desktop 1280 e mobile emulado 390/320: overflow de página ausente. Card/previsão conferidos em screenshots; data da primeira coluna não quebra no meio após CSS. Tabela mantém rolagem horizontal interna quando necessária.
- Deep Research: start real → worker → interrupção SSE → reload durante execução → replay ordenado → conclusão → barra terminal limpa → cards e imagem → zoom/Escape → exportação Markdown HTTP 200 com 1983 bytes. 43 eventos únicos em ordem.
- Cards contextuais de ciência, notícia, evento e transporte: conteúdo fictício verificado como tal, sem prometer disponibilidade. Viewports 1280/390/320.
- Câmbio real Frankfurter: valor de referência e série de 30 dias, gráfico com 23 pontos datados/4 ticks sem colisão no mobile.
- Nenhuma exceção JavaScript registrada na execução aprovada.

## Tentativas e limites

As tentativas anteriores não foram apagadas: `chrome-attempt1/2/3` registram capitalização CSS da badge e duas esperas ausentes do harness ao criar chat. As respostas estavam corretas nas imagens. O harness passou após aguardar o chat vazio antes de medir a próxima resposta. `chrome-before-css.json` registra o primeiro E2E completo; a execução posterior cobre também a correção visual.

Aprovação local não equivale a teste de produção, dispositivo móvel físico, inferência real de modelo, inventário comercial confirmado ou disponibilidade contínua dos provedores. Notícias/artigos/eventos externos não foram novamente consultados nesta versão; contratos e testes V5.9.3 foram preservados. Não houve CAPTCHA/bypass, scraping agressivo, push ou deploy.


## Fechamento

Última execução no código final `f8c2508`: `chrome-continuity.json` com ok=true, 6 turnos de chat ao vivo, zero geocodificação no cumprimento, 43 eventos e nenhum erro JS. Comparação com `live-trace.jsonl` confirma tanto temperatura atual quanto faixa de previsão exibidas. Consulta oficial por código real em `official-id-live.json`. Suíte completa final: 1129 passed, 4 skipped, 2 warnings; a execução anterior com três falhas foi preservada em `full-suite-first.log`.
