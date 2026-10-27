# Reprodução local e limites

PowerShell no worktree `vexx-v598-dev`; Python do ambiente `..\.venv\Scripts\python.exe`. Desative leitura de `.env` real nos testes: `JULIA_ENV_FILE` aponta para arquivo inexistente de QA. Preserve a configuração gratuita; não use fallback pago.

```powershell
$env:JULIA_ENV_FILE=Join-Path $env:TEMP 'v5910-none.env'
$env:PYTHONIOENCODING='utf-8'
..\.venv\Scripts\python.exe -m pytest tests/test_autonomous_v5910.py tests/test_synthesis_transport_v5910.py tests/test_research_tailer_v5910.py -q
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe tools/bench_pesquisa_v57.py --sem-salvar
..\.venv\Scripts\python.exe tools/bench_shopping_v4.py
..\.venv\Scripts\python.exe tools/bench_experiencia_real.py
```

`tools/probe_discovery_v5910.py` captura consultas internas além das externas do probe existente. Use `--track B --artifact-version v5910 --case ar-01 --dataset benchmarks/autonomous_v5910_holdout.json --output <arquivo-novo>`. Conjunto já aberto: repetir agora é diagnóstico, não outro holdout cego. O probe não faz síntese LLM. Os arquivos completos ficam ignorados; agregação via `tools/summarize_autonomous_v5910.py`.

`tools/replay_autonomous_v5910.py --baseline --output <arquivo-novo>` e sem `--baseline` usam pool/records congelados, sem rede. `tools/replay_document_v5999.py --output <arquivo-novo>` reexecuta sete fontes conhecidas locais. Exigem os corpos/registros ainda presentes em `qa-artifacts/.../raw/`; não foram distribuídos como fixtures integrais no Git. As regressões unitárias não dependem deles.

`tools/contrast_synthesis_v5910.py` executa B e depois A com os mesmos argumentos de evidências/vereditos; recusa repetir sobre o arquivo de resultado existente. `synthesis_capture_v5910.py` é opt-in somente em ferramentas de QA; não é importado por produção. Remove headers/endpoint/reasoning da captura. Mensagens e conteúdo retornado ficam locais e ignorados.

QA autenticado:

```powershell
..\.venv\Scripts\python.exe tools/serve_admin_qa_v5981.py --research-live --evidence-dir qa-artifacts/v5910 --capture-dir qa-artifacts/v5910/raw/live
```

Cria relay loopback, conta Alice QA e SQLite temporário. Configuração privada de URL/runtime em arquivo ignorado. Para C controlado, adicione `--synthesis-fixture` e use diretório de captura separado: isso semeia a fonte Math.hypot e **não é descoberta autônoma**. Para todos os testes externos/E2E, iniciar sem essa opção. Não reutilize cookie de outra instância. O segredo de sessão agora é único por sessão QA.

`tools/probe_authenticated_v5910.py` usa login/CSRF e `/api/research/start`; não injeta diretamente o resultado no DB. `setup_qa_v5910.cjs` e `qa_discovery_v5992.cjs`, via Playwright CLI/Chrome, enviam os nove cenários pelo composer. `qa_ui_v5910.cjs`, `qa_ui_extra_v5910.cjs` e `gallery_focus_v5910.cjs` verificam UI/exports/foco. O último usa imagem e remount declaradamente controlados; a galeria externa é testada separadamente.

Encerrar somente esse harness via arquivo `qa-stop`; aguardar seu processo sair. `tools/verify_shutdown_v5910.py` é observação de paths/processos com o Python local que possui psutil; não termina processos. Relatório `qa-shutdown.json` confirma remoção dos dois DBs/runtimes temporários, nenhum processo QA remanescente. O primeiro harness C precisou descartar seu próprio launcher após timeout de drain; o posterior live terminou normalmente. Essa diferença não é uma repetição bem-sucedida da síntese que falhou.
