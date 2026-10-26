# Três trilhas independentes

| Trilha | Entrada | Resultado | Aceitação |
|---|---|---|---|
| A Leitura | Dez fontes conhecidas; sete snapshots acessíveis | Perdas literais corrigidas em API; perdas de identidade, schema e janela persistem em outros domínios | Parcial |
| B Descoberta | Holdout congelado de 12 perguntas sem URL | Zero evidências retidas efetivamente lidas; nove referências de feed não contam | Reprovada |
| C Síntese | Evidência real congelada de Math.hypot, todas as facetas parseadas suportadas, modelo gratuito real | Primeira revisão timeout; segunda redação rejeitada por quantity_mismatch | Reprovada |

C no Chrome confirma entrega/persistência da resposta parcial, não aprovação do texto do modelo. Consulta adicional inédita Array.prototype.flat descobriu quatro fontes e preservou resultado bloqueado por timeout; é um cenário real positivo de descoberta, não repetição aprovada das três trilhas.

Ferramentas: probe_source_quality_v5998.py separa A/B; probe_synthesis_v5998.py exige cobertura de entrada e modelo :free sem fallback pago. SQLite somente temporário. Métricas, limitações e SHA nos resumos de qa-artifacts/v5998.
