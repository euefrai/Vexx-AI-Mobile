# V5.3 — progresso em 2026-10-16

Base confirmada: HEAD f6ad97f, Git inicialmente limpo. Baseline executado:
431 passed, 10 deselected, duas advertências, 218,22 s.

Implementados: contrato Python/JS, JDUI model3d, Three.js lazy, quatro primitivas,
GLB original CC0, controles, seleção, fallback, cleanup, cache, gzip pré-gerado,
Intent Engine e respostas completas/SSE persistidas por conversa/dono.

QA Chrome real passou em GPU Intel UHD/WebGL2: pixels mudam ao girar, seleção,
zoom/reset/pausa, expansão, quatro formas, GLB, toque e largura 390 px, parada
fora da tela, 35 buffers criados/deletados e zero canvases após descarte,
fallback sem WebGL e conversa real com recarga. QA ampliado concluído com sucesso:
reduced motion, CPU 4x, perda de contexto, tamanho do modelo e cache offline
na sessão aberta. Recarga integral offline continua sujeita à autenticação existente.

Uma regressão intermediária ocorreu porque outro trabalho modificou
`pc_agent.py`, `hermes_bridge.py` e adicionou `providers.py` durante a suíte:
10 falhas de NameError (providers ainda não importado naquele instante).
O import apareceu posteriormente. Nenhuma alteração concorrente foi desfeita.
A repetição completa passou: 488 passed, 5 skipped, duas advertências em 160,66 s.
Os skips dependem de LLM real ou DDG/lojas indisponíveis. Foco final: 57 passed.
HEAD avançou externamente de f6ad97f para 4f968eb durante a execução.

Implementação V5.3 e relatórios concluídos. Próxima validação recomendada:
executar tools/3d/qa.cjs em Android físico modesto e Safari/iOS, medir energia,
RAM GPU e sessão prolongada. Não houve push/deploy por esta rodada.
