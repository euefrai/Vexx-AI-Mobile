# QA autenticado local e pesquisa real

Runtime exclusivo: `serve_admin_qa_v5981.py --research-live --evidence-dir qa-artifacts/v5995`, FastAPI + PC Agent real, conta fixture Alice, SQLite em diretório temporário e modelo gratuito configurado sem fallbacks. Produção não foi usada como sandbox nem reiniciada.

| Fluxo em Chrome real | Observação |
|---|---|
| Chat comum, sem deep search | SSE HTTP 200; frase útil; primeiro delta 3037 ms, total instrumentado 3510 ms; 2 mensagens/2 IDs únicos preservados após reload. |
| WebAssembly.Table.grow, pergunta moderada nova | 14,963 s; parcial/interrompida, zero fontes úteis, sem síntese LLM. Reload durante trabalho e resultado persistido. Falha de qualidade explícita. |
| Intel, múltiplos requisitos | 15,824 s; parcial/interrompida, zero fontes úteis, sem síntese LLM. Reload preservou IDs/textos. |
| Cancelamento | 0,985 s; cancelada, nenhum chat_result_id criado; não ressuscitou resultado após reload. |
| Fonte pública controlada | URL MDN explícita, HTTP real, duas evidências, persistência e cards no chat. **Fixture de descoberta, sem modelo: não autônomo.** |
| Rede | Fetch falhou offline; após reconectar `/api/health` HTTP 200. Não se afirma cobertura de todos os fluxos offline. |

Sem erros `pageerror` nos fluxos. HTTP 401 inicial de `/api/session` antes de login é esperado; avisos do Chrome de password fora de form não foram tratados como falha de busca. Timeout/modelo inválido, SSE com replay, owner, cancelamento e persistência também passam em testes controlados da suíte; **não foi provocada falha real de timeout de provedor neste browser**.

Artefatos JSON E2E, timings e capturas em `qa-artifacts/v5995`. QA foi encerrado via comando gracioso do próprio runtime; `qa-shutdown.json` confirma ausência da árvore de processos e remoção de SQLite/runtime temporários. Browser QA fechado; proxy e produção preservados.

Estado final: mecânica do fluxo verificada em escopo local; pesquisa universal/síntese ainda falha, portanto sem SUCCESS_VERIFIED e sem publicação.
