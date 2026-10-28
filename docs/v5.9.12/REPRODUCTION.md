# Reprodução e fronteiras de prova

Executar em `vexx-v598-dev`, com venv do diretório pai. Definir `JULIA_ENV_FILE` para caminho temporário inexistente e `PYTHONIOENCODING=utf-8`. Não usar contas, bancos ou agentes de produção.

```powershell
$env:JULIA_ENV_FILE = Join-Path $env:TEMP 'v5912-none.env'
$env:PYTHONIOENCODING = 'utf-8'
& ..\.venv\Scripts\python.exe -m pytest -q
& ..\.venv\Scripts\python.exe tools/bench_pesquisa_v57.py --sem-salvar
& ..\.venv\Scripts\python.exe tools/bench_shopping_v4.py
& ..\.venv\Scripts\python.exe tools/bench_experiencia_real.py
& ..\.venv\Scripts\python.exe tools/replay_completion_v5912.py --baseline
& ..\.venv\Scripts\python.exe tools/replay_completion_v5912.py
& ..\.venv\Scripts\python.exe tools/summarize_completion_v5912.py
```

Replays exigem snapshots locais ignorados pelo Git. O clone apenas com sumários não reproduz os HTMLs exatos. Antes/depois usam os mesmos hashes; reextração pode mudar, consultas/ranking/rede não estão sendo comparados. `reading-stage-one-summary.json` preserva a etapa anterior; o sumário final não é nova descoberta.

| Artefato em `qa-artifacts/v5912/` | Escopo |
|---|---|
| `reading-before-summary.json`, `reading-after-summary.json` | CONTROLLED_REPLAY, mesmo HTML de desenvolvimento, sem modelo. |
| `development-summary.json` | LIVE_EXTERNAL desenvolvimento antes/depois, redes diferentes. Baseline recarregou módulo e perdeu wrapper interno; não comparar inner_calls. |
| `holdout-summary.json` | LIVE_EXTERNAL16 congelado antes de implementar, código53d4154, sem redação LLM/gold humano. |
| `authenticated-before-summary.json` | QA fase ef97dfc; marco parcial e falha de encerramento. |
| `authenticated-stage-two-summary.json` | QA fase53d4154; omissões, JSON inválido e vazio. |
| `authenticated-stage-three-summary.json` | QA fase1fee389; redações ainda parciais e falha de descoberta Acer. |
| `authenticated-summary.json` | QA final3938bee, duas completas/uma parcial/uma bloqueada. |
| `transport-summary.json` | REAL_MODEL, somente metadados allowlisted. Não publicar prompts/headers/reasoning. |
| `tests-summary.json` | Todas as suítes, incluindo falhas/interrupção; não somar execuções sobrepostas. |
| `ui-*-summary.json`, screenshots e CSV | Chrome real em viewport emulada, exportação e IndexedDB. |
| `provider-endpoint-summary.json`, `bing-query-summary.json`, `history-loss-summary.json` | Diagnósticos de desenvolvimento, não benchmarks causais. |
| `qa-shutdown.json` | Remoção/encerramento apenas das quatro sessões descartáveis desta tarefa. |

QA: `serve_admin_qa_v5981.py --research-live --evidence-dir qa-artifacts/v5912 --capture-dir qa-artifacts/v5912/raw/verified`. Exige modelo configurado `:free`; sem fallback pago. Não imprimir credenciais. Abrir URL loopback privada do harness em Chrome CLI com sessão própria `v5912`; `setup_release_v5912.cjs` configura quatro casos. Executar `qa_discovery_v5992.cjs` uma vez por caso, inspecionando falhas; não reenviar cegamente. Casos finais: Gerdau,Natura,WEG,Nvidia. Acer ficou preservada na fase anterior, não foi excluída como se tivesse passado.

`qa_release_ui_v5912.cjs` verifica source cards e link; `qa_ui_extra_v5910.cjs` aceita versão5912 para exports/IndexedDB. Antes de encerrar, `collect_v5910.py --artifact-version v5912 --log-prefix verified` abre apenas SQLite QA read-only. Guardar runtime/status privados, fechar o próprio browser e criar `qa-stop`; aguardar launcher. `verify_shutdown_v5910.py --artifact-version v5912` usa psutil e só verifica processos/arquivos.

Modelo faz escrita/revisão nas mesmas chamadas existentes. O flag interno `semantic_coverage` ativa respostas por requisito com spans literais; não pode ser ligado pelo texto do usuário/modelo. Fontes não vinculadas, dados ausentes, IDs desconhecidos, datas sem ano e objetivos não decompostos não viram cobertura completa. Normalização JSON só remove um delimitador final isolado na escrita e fica registrada; revisão continua estrita.

Os registros antigos completos, exportação MD e logs ficam locais, com hashes no manifest. MD não foi reescrito para eliminar os espaços de Markdown. URLs dos sumários são sanitizadas; nenhuma nova medição de desempenho de produção ou teste em celular físico foi declarada.
