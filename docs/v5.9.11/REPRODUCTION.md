# Reprodução e limites

Executar na worktree `vexx-v598-dev`, Python do venv pai. Não usar SQLite/agent/contas de produção. Definir env de isolamento e UTF-8. Live exige modelo explicitamente gratuito sem fallback pago; não colocar credenciais em comandos/logs.

| Trilha | Sumário em `qa-artifacts/v5911/` | Fronteira |
|---|---|---|
| Diagnóstico inicial | `previous-loss-summary.json` | Capturas V5.9.10 com zero requisitos; sem páginas integrais. |
| CONTROLLED_REPLAY leitura | `read-before-summary.json`, `read-after-summary.json` | Registros idênticos, hashes/offsets/IDs. Não descoberta. |
| CONTROLLED_REPLAY candidatos | `provider-replay-*-summary.json` | Pool/registros/orçamento iguais; zero ganho de fonte útil. |
| LIVE_EXTERNAL desenvolvimento | `provider-trace-summary.json` | Consultas/candidatos/extrações reais baseline; URLs sanitizadas. |
| LIVE_EXTERNAL holdout | `holdout-summary.json` | Código `71fab67`, não reavalia correção posterior. |
| REAL_MODEL A/B/C | `transport-summary.json` | Requests iguais, três falhas; fonte conhecida semeada. |
| AUTHENTICATED_E2E | `authenticated-summary.json`, `live-synthesis-summary.json` | Nove fluxos; WEG parcial com revisão real. |
| JDUI/persistência | `browser-summary.json`, screenshots, CSV | Viewport/links/teclado/exportação/IndexedDB/reload reais. |
| Desligamento | `qa-shutdown.json` | QA descartável encerrado/removido, sem controle de produção. |

Capturas integrais e logs ficam locais/ignorados em `raw/` e `*.log`. O clone apenas com sumários não reproduz os replays exatos; precisa dos snapshots locais. Manifest preserva hashes, não disponibilidade futura das fontes. MD exportado permanece local com seus espaços originais de Markdown; não foi reescrito para mascarar whitespace.

```powershell
$env:JULIA_ENV_FILE = Join-Path $env:TEMP 'v5911-none.env'
$env:PYTHONIOENCODING = 'utf-8'
& ..\.venv\Scripts\python.exe -m pytest -q
& ..\.venv\Scripts\python.exe tools/bench_pesquisa_v57.py --sem-salvar
& ..\.venv\Scripts\python.exe tools/bench_shopping_v4.py
& ..\.venv\Scripts\python.exe tools/bench_experiencia_real.py
& ..\.venv\Scripts\python.exe tools/diagnose_coverage_v5911.py
& ..\.venv\Scripts\python.exe tools/replay_coverage_v5911.py --baseline
& ..\.venv\Scripts\python.exe tools/replay_coverage_v5911.py
& ..\.venv\Scripts\python.exe tools/replay_provider_v5911.py --baseline
& ..\.venv\Scripts\python.exe tools/replay_provider_v5911.py
& ..\.venv\Scripts\python.exe tools/summarize_coverage_v5911.py
```

Não sobrescrever capturas congeladas. Probes recusam output existente; contraste real recusa repetir resultado existente. Novos experimentos precisam de outro identificador/diretório, código e orçamento registrados antes. `probe_discovery_v5910.py` aceita `--artifact-version v5911`; não reutilizar o holdout para ajuste.

QA: `tools/serve_admin_qa_v5981.py --research-live --evidence-dir qa-artifacts/v5911 --capture-dir qa-artifacts/v5911/raw/live`. `--synthesis-fixture` é somente para C com fonte conhecida. Usar fixtures do harness, nunca conta pessoal. Runtime privado contém porta/caminhos efêmeros; não publicar.

Chrome CLI: abrir URL loopback do QA com sessão própria, `--browser chrome --headed`; usar snapshot ao investigar falhas. `setup_qa_v5911.cjs` configura nove casos; executar `qa_discovery_v5992.cjs` uma vez por caso. Para apenas reabrir chats existentes, `qa_ui_prepare_v5911.cjs`; depois `qa_ui_v5910.cjs` e `qa_ui_extra_v5910.cjs` via `run-code --filename`. Ferramentas recusam URL não loopback.

Antes de parar: `collect_v5910.py --artifact-version v5911` abre SQLite QA somente leitura; guardar cópia privada do runtime/status, fechar a própria sessão Chrome e criar `qa-stop`. Esperar saída do próprio launcher. `verify_shutdown_v5910.py --artifact-version v5911` requer Python local com psutil, verifica processos/arquivos sem encerrá-los. C/bootstrap/live passaram sem timeout de drenagem nesta entrega.

Limites para a retomada: objetivo original pendente não é fato; suporte literal não é gold; matriz ainda perde produtos WEG; história do holdout reteve entidade errada; snippets não contam como leitura; anúncio rejeitado no diagnóstico não prova economia no replay; contraste A/B/C falho continua falho; WEG é outro caso posterior. Reconexão HTTP/desligamento local não esclarecem causa histórica de conteúdo vazio nem validam produção.
