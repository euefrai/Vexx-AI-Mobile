# V5.9.6 — checkpoint

- HEAD inicial verificado: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`. Sem alterações rastreadas; artefatos anteriores não rastreados preservados.
- Escopo: recuperação profunda e JDUI dentro dos módulos existentes. Sem push, deploy, reinício de produção, novo motor, APIs pagas ou mudança de identidade/clima.
- Baseline integral iniciado em `qa-artifacts/v596/baseline.log`.
- Diagnóstico: `search_providers.py:buscar_google_news` descarta URL do publicador; `search_orchestrator.py:pesquisar` continua após RSS sem explorar manchete/publicador; `research_agents.py:agente_analista` não abre RSS como artigo (correto, preservar).
- Diagnóstico comercial: `shopping.py:_ram_do_produto` só reconhece sufixo RAM; anúncio Lenovo real com `8GB, ... SSD 512GB` fica como RAM desconhecida em vez de conflito com pedido 16GB. Reprodução congelada disponível em `qa-artifacts/v595/live-shopping/lenovo.json`.
- A seguir: recuperação limitada por título/domínio com proveniência; RAM por campos/título, sem inferir RAM de armazenamento; testes focados e checkpoint local. Depois mídia, ciência/adaptação, JDUI, benchmark externo, Chrome e suíte integral.

- Fases B/C: correções e 11 regressões novas; conjunto focado: 258 aprovados, dois ignorados. Baseline desta rodada revelou falha preexistente `/noticias/` não reconhecido como índice (1 falha/1.353 aprovados); corrigida sem mudar gabarito. Parser RAM físico/virtual ajustado, sem escolher maior valor entre declarações conflitantes.

- D–G: Commons preserva licença/autor/dimensões declarados; metadados VideoObject, canais genéricos rejeitados, relevância de mídia por tópico; schemas Python/JS e galeria/proveniência refinados. Seções científicas somente quando extraídas. Plano científico mantém entidades/contexto e lacuna de texto completo não fecha por resumo. UTF-8 do SSE corrigido para fragmentos entre bytes. Último conjunto focado: 121 aprovados.
- Diagnóstico limitado: 160 tokens => HTTP 200 SSE sem resposta pública; orçamento normal de pesquisa (1.800) => 184 chunks reais, 14,571s. Dois diagnósticos, sem troca de modelo/infraestrutura. Primeira Deep Research real executou uma chamada mas síntese foi rejeitada; plano corrigido depois, validação final pendente. Artefatos separados em model-stream*.json/live-model-deep.
- Em execução: 13 categorias externas com modelo desabilitado explicitamente para medir recuperação; próxima etapa: Deep Research final após correção de contexto, Chrome local 320/390/desktop/zoom, regressão integral e documentação.

- H/I: Chrome real com 5 imagens carregadas, desktop/390/320/zoom200 sem overflow; Escape, proveniência com storage de QA/reload, download CSV, abertura da fonte e fallback de rede testados. SSE/cancelamento no navegador são replay explícito; job real coberto separadamente em pytest. Corrigido callback de download ausente nos dois painéis reais de pesquisa.
- Regressões preservadas/corrigidas: schema de leitura aplicado indevidamente ao filecard, paridade Python/JS e ordem genérica legada. 65 testes de apresentação passaram; suíte completa 1.373 aprovados/4 ignorados/2 avisos (223,42s), nova confirmação integral após ligação CSV em execução. Benchmarks 34/34, 59/59, 16/16; Quality Lab executado.
- Ganhos reais: imagens pertinentes 0 → 5; diagnóstico de inferência 184 chunks; 2 PDFs OA limitados recuperados na investigação final, síntese bloqueada por rate_limit e sem retry. Notícias Ubatã: 0 artigos originais lidos; ofertas/tarifas confirmadas 0. Não declarar cobertura universal.

- Checkpoint final de implementação: `7a8a707c22d2bfdbaa944d0252e64681d83852df`. Sem alterações fora do escopo. Referências de arquivos não lidos removidas da composição duplicada, conservadas no job/exportação. Conjunto final de apresentação: 67 aprovados. Documentação completa em elaboração final; apenas validação integral pós-ajuste visual e commit de evidências pendentes.

- J concluída: suíte final 1.374 aprovados, quatro ignorados, dois avisos (205,64s), logs preservados; sintaxe JS/diff e scan de credenciais passaram. Todos os documentos e evidências presentes. Chrome/servidor temporários próprios encerrados; produção não alterada. Commit documental local final em seguida.
- Pendências reais para próxima etapa: artigo local original (0), oferta/tarifa (0), vídeo pertinente (0), síntese profunda bloqueada por rate_limit; expansão persistente nos painéis reais não comprovada. Sem push/deploy. Próximo passo detalhado no relatório e SOURCE_RECOVERY.md.
