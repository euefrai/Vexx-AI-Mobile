# V5.9.6 — checkpoint

- HEAD inicial verificado: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`. Sem alterações rastreadas; artefatos anteriores não rastreados preservados.
- Escopo: recuperação profunda e JDUI dentro dos módulos existentes. Sem push, deploy, reinício de produção, novo motor, APIs pagas ou mudança de identidade/clima.
- Baseline integral iniciado em `qa-artifacts/v596/baseline.log`.
- Diagnóstico: `search_providers.py:buscar_google_news` descarta URL do publicador; `search_orchestrator.py:pesquisar` continua após RSS sem explorar manchete/publicador; `research_agents.py:agente_analista` não abre RSS como artigo (correto, preservar).
- Diagnóstico comercial: `shopping.py:_ram_do_produto` só reconhece sufixo RAM; anúncio Lenovo real com `8GB, ... SSD 512GB` fica como RAM desconhecida em vez de conflito com pedido 16GB. Reprodução congelada disponível em `qa-artifacts/v595/live-shopping/lenovo.json`.
- A seguir: recuperação limitada por título/domínio com proveniência; RAM por campos/título, sem inferir RAM de armazenamento; testes focados e checkpoint local. Depois mídia, ciência/adaptação, JDUI, benchmark externo, Chrome e suíte integral.

- Fases B/C: correções e 11 regressões novas; conjunto focado: 258 aprovados, dois ignorados. Baseline desta rodada revelou falha preexistente `/noticias/` não reconhecido como índice (1 falha/1.353 aprovados); corrigida sem mudar gabarito. Parser RAM físico/virtual ajustado, sem escolher maior valor entre declarações conflitantes.
