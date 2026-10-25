# Inferência e pesquisa completa

Ambiente: FastAPI/PC Agent reais de QA, contas fixture, SQLite temporário e
Chrome real. Nenhuma sessão/credencial/SQLite de produção. Modelo autorizado
poolside/laguna-s-2.1:free; fallbacks desabilitados.

| Caso autenticado (beab357) | Tempo observado | Resultado |
|---|---:|---|
| Tramontina, fundadores/ano/produtos | 23,219 s | SOURCE_INSUFFICIENT, zero fontes elegíveis, sem chamada LLM |
| Vacina, causas/consequências | 21,481 s | SOURCE_INSUFFICIENT, zero fontes elegíveis, sem chamada LLM |
| Memory.grow, sintaxe/uso/limitações | 18,176 s | SOURCE_INSUFFICIENT, zero fontes elegíveis, sem chamada LLM |
| Cancelar pesquisa | 1,067 s | cancelada, nenhum resultado final, sem chamada LLM |

Os três resultados parciais foram entregues por SSE e restaurados após reload.
Isso não é pesquisa completa com modelo. completed_flow do driver indica só
encerramento mecânico; não corresponde a SUCCESS_VERIFIED.

Diagnóstico REAL_MODEL separado: uma leitura HTTP pública MDN de toSorted,
extração e tentativa real de síntese. Modelo retornou 1.388 caracteres em
11,216 s, contexto 2.766 caracteres, timeout 15 s. Validador rejeitou o texto
antes da revisão semântica (SYNTHESIS_REJECTED). Uma chamada; sem retries.
O código fino da exceção não foi preservado nessa execução (error_code unknown).
O probe foi corrigido para registrar failure_detail em futuras execuções,
sem refazer a chamada apenas para obter resultado favorável.

Leitura 0,638 s; extração 0,047 s. Primeiro token indisponível: writer não faz
streaming de tokens da síntese. Não inventar tempos de planejamento/revisão
que não aconteceram, nem atribuir toda falha a rate limit ou SSE.

Teste de entrega com URL explicitamente fornecida: discovery fixture + leitura
HTTP real + pipeline/store reais + fallback extrativo. É
FIXTURE_DISCOVERY_REAL_PUBLIC_READ_SQLITE_DELIVERY_NO_MODEL, separado dos E2E
autônomos. Nenhuma pesquisa completa fundamentada foi aprovada.

Após corrigir a ordem do HTML, a tentativa autenticada de Tramontina foi
repetida com o candidato a91c113:21,894 s, SOURCE_INSUFFICIENT, resultado parcial
persistido/reload, sem chamada LLM. Essa repetição tem correção causal concreta
entre execuções; não é repetição ilimitada buscando um PASS.

Diagnóstico isolado após a correção: contexto2686 caracteres, uma resposta de
691 caracteres em4,765 s, JSON inválido (failure_detail invalid_json),
SYNTHESIS_REJECTED, sem revisão/retry. Leitura0,300 s e extração0,059 s. As duas
tentativas isoladas ficaram rejeitadas; não aceitar texto fora do schema para
simular sucesso. O erro original continua sem detalhe fino, sem reescrever seu
registro. O probe agora recusa sobrescrever evidência anterior.
