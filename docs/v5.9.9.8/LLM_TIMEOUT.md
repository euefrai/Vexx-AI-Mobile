# Síntese gratuita e limites

Fonte congelada real: Math.hypot MDN. Entrada sem descoberta autônoma, três facetas parseadas suportadas. Redator real configurado :free, sem fallback pago. Nenhum limite ampliado.

| Execução | Escrita | Revisão | Resultado |
|---|---|---|---|
| Isolada | 4.607 caracteres de entrada; 1.882 de saída; finish=stop; 12,56 s, timeout 15 s | 6.448 caracteres, timeout 12 s, falha em 12,025 s | blocked/timeout |
| Entrega QA | 4.607 entrada; 1.736 saída; finish=stop; 13,77 s | Não chamada | quantity_mismatch; parcial extrativo persistido |

Primeira chegou à revisão: falha não foi extração vazia ou truncamento do redator. Segunda falhou na validação numérica antes da revisão. Texto rejeitado não foi guardado; não é possível concluir se houve alucinação ou falso positivo do validador. Segurança foi preservada.

Bug do instrumento corrigido: carregar_job retorna objeto compacto, síntese terminal mora no checkpoint. Probe agora usa _resumo. Campos antigos synthesis_llm/fallback_detail não eram conclusivos; checkpoint QA foi recuperado antes do encerramento e confirmou llm=false/quantity_mismatch. Checkpoint isolado já removido; transporte/calls provam timeout da revisão, não conteúdo final.

API não faz streaming neste caminho: TTFT indisponível. Tempo até headers não identifica fila, cold start ou processamento interno. Contexto pequeno não prova que timeout seja causado por tamanho. Não recomendar simplesmente elevar prazos. Próximo diagnóstico deve capturar rejeição privada com proveniência antes de corrigir validator/prompt.
