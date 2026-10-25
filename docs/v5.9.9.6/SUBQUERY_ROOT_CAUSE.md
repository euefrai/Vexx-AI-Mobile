# Causa reproduzida

`research.dividir_subconsultas` dividia a pergunta em `e`, vírgula, ponto de interrogação e hífen, depois removia palavras curtas. `_subconsultas_unicas` deduplicava esses fragmentos sem recuperar a entidade. A proteção anterior em `constrain_discovery` só repunha local/região/tema de notícias.

Na execução externa baseline de Math.hypot, o provedor recebeu `como usar math.hypot`, `qual sintaxe`, `valor retornado`. A candidata enviou `Math.hypot Sintaxe ou assinatura`, `Math.hypot Valor retornado`, `Math.hypot Comportamento da operação`.

A solução inicial conserva uma pergunta inteira quando não há decomposição segura, e usa requisitos da Query Intelligence para atributos explícitos. Nomes com hífens e escopos numéricos/negativos não são desmontados. O replanejamento usa a mesma proteção do envio.

Reprodução automatizada inicial: 31 failed, 9 passed (`qa-artifacts/v5996/context-before.log`, local). Após a primeira correção: 40 passed. Os testes foram ampliados posteriormente; consulte o resumo de validação final.

Importante: correção sintática do planejamento não demonstrou melhora de recuperação externa. Não confundir contagem de testes com aceitação funcional.
