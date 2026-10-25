# Evidências V5.9.9.2

Veredito: **melhora consistente de cobertura não demonstrada; não publicar**. Logs verdes não substituem leitura das fontes.

## Rodadas que sustentam a comparação

- `baseline-diagnostic` (12), `baseline-historical` (20), `baseline-sealed` (15): código `2c6a324`, antes das correções de recuperação.
- `accepted-diagnostic` (12), `accepted-historical` (20), `accepted-holdout` (15): núcleo de busca congelado `ad16f21`. `accepted-historical-completion.log` conclui a rodada interrompida antes do primeiro caso.
- `comparison.json`: contadores mecânicos produzidos por `tools/summarize_discovery_v5992.py`.
- `holdout-judgments.json`: leitura/julgamento do agente após congelamento. Não é ouro humano independente e não redefine perguntas ou aprovação do motor.
- `after-*`/`final-*`: iterações anteriores, não usadas para escolher a melhor pontuação. Preservadas para rastrear falhas.

Cada caso inclui revisão, hash do conjunto, consulta/pedido resolvido, chamadas de provedor e extração limitada realmente devolvida. O relógio final foi ancorado ao baseline, mas índices/rede são vivos. Conteúdo público foi limitado para diagnóstico; não há garantia de corpo integral. Não inferir ausência na publicação a partir de ausência no trecho capturado.

## Validação

- `baseline-tests.log`: falha original de fixture UTC/Bahia; não é baseline verde.
- `full-suite-release-check.log`: 1554 passed, 4 skipped, 2 warnings, antes da proteção de saída.
- `model-output-safety.log`: 53 passed, inclui dois testes da proteção Unicode.
- `full-suite-final-safety.log`: 1556 passed, 4 skipped, 2 warnings em 438,98 s após `1ce380a`, sem ignorar falhas anteriores.
- `frozen-delivery-{search,shopping,experience}.log`: benchmarks determinísticos antigos, preservados.
- `e2e-delivery-*.log`, `e2e-accepted-museum.log`, `e2e-accepted-technical.log`: Chrome autenticado, agente e inferência pública gratuitos reais, resultados parciais. `e2e-safety-technical.log`: nova instância após proteção, timeout do modelo e nenhuma resposta final; `e2e-safety-evidence.log` não confirmou dados no painel, capturado cedo demais.
- `visual-accepted.log`, `extra-accepted.log`, `research-*.png`, `research-export.*`: galeria/teclado/erro/IndexedDB/exportações efetivamente executados.
- `runtime-observation.json`: metadados de produção somente leitura; revisão/jobs desconhecidos.
- `qa-performance-storage.json`: amostra ociosa local, não pico nem benchmark de produção.
- `qa-cleanup-*.json`: encerramento do QA descartável e ausência do banco temporário.
- `secret-scan.json`: escopo e resultado da varredura de credenciais, com limitações.

Comandos reproduzíveis: `..\.venv\Scripts\python.exe -m pytest -q`; `tools/bench_pesquisa_v57.py --sem-salvar`; `tools/bench_shopping_v4.py`; `tools/bench_experiencia_real.py`. Definir `JULIA_ENV_FILE` para arquivo isolado, nunca `.env` real. Para sondas externas, usar `tools/bench_discovery_v5992.py --help`; repetir rede viva não reproduz necessariamente os mesmos documentos.

O arquivo privado de runtime, gatilho de parada, cookies e bancos temporários não são artefatos de entrega. Logs contêm senha **fixa de fixture QA**, sem acesso à produção. Não há push/deploy nem teste autenticado de produção nesta entrega.
