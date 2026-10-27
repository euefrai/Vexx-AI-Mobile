# Síntese e provedor

Modelo real gratuito configurado: poolside/laguna-s-2.1:free, sem fallback pago. Duas tentativas justificadas: diagnóstico isolado e entrega autenticada. Nenhum retry automático de aprovação.

Isolada: três facetas de Math.hypot suportadas a partir de snapshot público real; escrita 4.607 caracteres de entrada, 1.521 saída, 13,040 s/timeout 15 s; revisão 6.107 entrada, 221 saída, 7,761 s dentro do restante 11,956 s. llm=true, revisão aprovada, citações/quotes validados. Captura foi revalidada localmente com os novos guardas numéricos, sem novas chamadas.

Autenticada: mesma entrada conhecida; escrita retornou vazia em 15,043 s com HTTP 200. Estado blocked/provider=vazia, resultado parcial preservado. Não foi chamada revisão e não se declara sucesso completo. Sintetizar novamente não foi usado para esconder a falha.

Caminho não streaming: TTFT indisponível. Tempos até headers não identificam fila, cold start ou processamento interno. Não foram observados 429/rate limit nessas duas chamadas; isso não comprova ausência global. Contexto pequeno não explica sozinho indisponibilidade. Timeout e revisão permanecem nos limites existentes. PROVEDOR DISPONÍVEL em uma execução não implica estabilidade entre execuções.
