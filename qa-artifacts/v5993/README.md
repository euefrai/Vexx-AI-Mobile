# Evidências V5.9.9.3

**Não aprovam publicação.** Separar fixture, replay, rede viva, inferência e E2E autenticado.

| Artefato | Escopo |
|---|---|
| `baseline-sealed/` | Vinte perguntas congeladas, antes dos algoritmos, rede real; fonte `1f5ff18` |
| `accepted-holdout/`, `code-freeze.json` | Vinte posteriores, motor `af400f1`, relógio ancorado no baseline, sem LLM/chat |
| `comparison.json` | Contadores mecânicos via `tools/evaluate_answer_aware_v5993.py`; não é juiz factual |
| `holdout-judgments.json`, `holdout-review-material.json` | Julgamento rastreável pelo agente sobre trechos; âncoras são só índice, não gold humano |
| `frozen-replay.json` | Reclassificação de leituras únicas V5992; sem nova descoberta/modelo |
| `post-evaluation-guard.json` | Guard de interface `86462e9` posterior, motivado por QA; sem nova aprovação independente |
| `e2e-stage1-*.log` | Tentativas iniciais reais com modelo gratuito; inclui rate_limit e erros de roteamento |
| `e2e-retrieval-*.log` | Onze fluxos reais, síntese de pesquisa desativada após limite; não REAL_MODEL |
| `e2e-accepted-*.log` | Quatro repetições af400f1, corrigindo entrega e poluição de mídia |
| `e2e-qualified-interface.log` | Final `86462e9`, referência da API correta, parcial extrativo persistido, sem inferência |
| `e2e-qualified-malformed-case.log` | **Falha do harness**, configuração achatada enviou caractere ao chat; não conta como pesquisa |
| `visual-accepted.log`, `extra-accepted.log`, `coverage-visual.log` | Chrome real, galeria/tabela readonly/erro/teclado/IndexedDB/exportações |
| `coverage-zoom-before-wait.log` | Falha do harness por DOM durante reload, não passe |
| `coverage-zoom-fix.log`, `coverage-zoom-card.log` | Zoom CSS200% e scroll interno verificados, capturas do componente inspecionadas |
| `qa-retrieval-evidence.json`, `qa-public-evidence.json` | Fontes/passagens públicas dos jobs descartáveis; não banco/cookies de produção |
| `full-suite-stage1.log`, `full-suite-stage2.log`, `full-suite-final.log` | Falhas e regressões preservadas; não substituem a suíte final |
| `full-suite-qualified-final.log` | Final: 1575 passed/4 skipped/2 warnings em247,87s no código86462e9 |
| `frozen-{search,shopping,experience}.log` | 34/34, 59/59, 16/16; verificações determinísticas antigas |
| `qa-performance*.json` | Amostras locais ociosas, não pico/ganho causal/produção |
| `qa-cleanup*.json`, `secret-scan.json` | Limpeza do QA e varredura com escopo explícito |

Reprodução: definir `JULIA_ENV_FILE` para arquivo isolado e `PYTHONIOENCODING=utf-8`; usar `..\.venv\Scripts\python.exe -m pytest -q`. Pesquisa: `tools/bench_discovery_v5992.py --live --dataset benchmarks/answer_aware_v5993_holdout.json --output <pasta> --sealed`; relógio comparável com `--reference-dir <baseline>`. Repetir rede viva pode mudar resultados. Não abrir novos resultados para otimizar o conjunto já aberto.

Capturas e downloads vieram de contas de fixture e conteúdo público real. A senha fixa QA nos drivers não autentica produção. Metadados privados de runtime/gatilho de parada/cookies/SQLite não são versionados. Logs crus mantêm whitespace de falhas e hard breaks dos exports; verificação de whitespace de código/documentação exclui esses logs literais. Nenhum push/deploy foi executado.
