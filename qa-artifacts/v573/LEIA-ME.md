# Evidências V5.7.3

- **Data:** 2026-10-19
- **Commit de código/testes:** `63e12c00370c6b13b328e6836d5b3af9b7b45ff6`
- **HEAD final:** ver `final-head.txt`, gerado após o commit documental.
- **Produção:** não usada, não atualizada, não reiniciada.

## Conteúdo

| Arquivo | Evidência | Rótulo |
|---|---|---|
| `smoke-integrado-20261019-222528.json` | 6 cenários + checagem de entrega (7/7) | `LOCAL_E2E` + `EXTERNAL_E2E` |
| `bench-pesquisa-v57-2026-10-19.json` | benchmark congelado 34/34 | `DETERMINISTIC_FIXTURE` |
| `bench-shopping-v4-20261019.txt` | benchmark congelado 59/59 | `DETERMINISTIC_FIXTURE` |
| `bench-experiencia-20261019.txt` | 16/16 (Python + Node) | `DETERMINISTIC_FIXTURE` |
| `chrome/chrome-e2e-20261019-222056.json` | Chrome final: login, chat, card, desktop/mobile | `CHROME_E2E` |
| `chrome/chrome-e2e-20261019-221928.json` | falha inicial por crash do network service do Chrome | `CHROME_E2E` (harness) |
| `chrome/*.png` | screenshots desktop/mobile da execução final | `CHROME_E2E` |

## Observações de proveniência

1. O JSON de sucesso do Chrome foi gravado originalmente em
   `qa-artifacts/v572/chrome/`; depois foi copiado para `v573/` e a pasta
   histórica `v572/` foi restaurada. Por isso, os campos internos
   `screenshot_*` ainda apontam para `qa-artifacts/v572/...`. As imagens
   correspondentes desta rodada estão em `qa-artifacts/v573/chrome/` e foram
   preservadas sem edição.
2. O smoke integrado (`tools/smoke_integrado_v572.py`) tem a checagem
   `frontend_delivery` acoplada a `qa-artifacts/v572/chrome/`; ela referencia um
   artefato histórico V5.7.2. A validação de frontend V5.7.3 é o Chrome novo
   acima. O smoke **não** foi usado como prova do Chrome desta versão.
3. O Chrome final registrou 1 erro de console (401 esperado antes do login) e
   2 `net::ERR_ABORTED` de reload; não houve exceção JS.
4. A primeira execução do Chrome falhou antes de concluir o login porque o
   network service do navegador caiu. O POST `/api/login` já havia retornado
   200; a reexecução limpa passou.
5. Nada aqui foi executado contra o serviço publicado. `/api/health` e
   `/api/diag` de produção foram apenas leitura (`PRODUCTION_OBSERVATION`) e
   continuam no commit antigo `ed0d44fd8b40`.

## Reprodução

```powershell
$py = "C:\Users\efrai\Documents\julia-mobile-v0.2-offline-sqlite\.venv\Scripts\python.exe"
& $py -m pytest -q
& $py -m pytest -q tests/test_trust_v573.py
& $py tools/bench_pesquisa_v57.py
& $py tools/bench_shopping_v4.py
& $py tools/bench_experiencia_real.py
& $py tools/smoke_integrado_v572.py
& $py tools/chrome_e2e_v572.py
```

Os harnesses usam portas livres, SQLite temporário e perfil Chrome temporário;
não tocam a produção.
