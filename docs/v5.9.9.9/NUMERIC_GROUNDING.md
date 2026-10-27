# Validação numérica

Falso positivo controlado reproduzido: 1,5 kg versus 1.5 kg rejeitado pela comparação literal anterior. Canonicalização agora aceita decimais inequívocos e formatos monetários mistos com agrupamento inequívoco. 1,234 continua ambíguo e não é convertido em 1234 ou 1.234. Nenhuma conversão de unidades ou moedas foi adicionada.

Guardas reforçadas: unidade g, moedas explícitas USD/BRL/EUR e sufixos de identificadores técnicos hifenizados. 710 g não sustenta 710 kg; USD não sustenta BRL; EN-EL15c não sustenta EN-EL15b. Separadores hifenizados equivalentes de identificador são normalizados sem trocar sufixo. Sinais negativos permanecem.

Testes cobrem inteiro, decimal BR/internacional, milhares com centavos, percentual, moeda, intervalo, data, versão, identificador, negativo, unidades e valores tabulares. Integração controlada garante revisão chamada após equivalência válida e não chamada após unidade/sufixo incorreto. Redator/revisor dessas regressões são fixtures declaradas.

Números iguais em atributos diferentes ainda exigem revisão contextual. Aproximação, preço antigo, entidade, atributo, qualificador e data não são resolvidos por conjuntos numéricos isolados. Revisão separada continua obrigatória; não se afirma validação semântica universal.

Rejeição V5998 original: impossível adjudicar, saída rejeitada não foi capturada naquele momento. Não foi rotulada retroativamente como erro do modelo ou falso positivo. Captura privada nova guarda mensagens/saída de QA sem chaves. A execução real atual foi aprovada; numeric-summary.json registra checagens e replay no validador atual, sem publicar texto integral.
