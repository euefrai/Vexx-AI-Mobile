# Fidelidade dos provedores

observe_searches é diagnóstico opt-in, isolado por ContextVar, sem arquivo
global compartilhado entre usuários. Registra consulta original, consulta do
adaptador, horário, provedor, limite/timeout, quantidade, títulos/URLs,
latência e códigos. Helpers observados registram parâmetros permitidos,
destino final e erro HTTP quando exposto. Remove credenciais, parâmetros
arbitrários e padrões de segredo. Não registra corpo de erro nem tokens.

Limite importante: o downloader legado não retorna o status de sucesso e
DDG/Wikipedia usam outros helpers. HTTP null significa indisponível, nunca 200.
A instrumentação não afirma observar todos os redirects intermediários.

64 eventos na nova amostra de doze perguntas, com separação UNJUDGED_DISCOVERY,
PROVIDER_EMPTY/BLOCKED/RATE_LIMITED/PARSE_ERROR/ERROR conforme observado.
Rótulos semânticos são atribuídos apenas na amostra revisada, não por contagem
de palavras do próprio motor. Não afirmar que todas as categorias ocorreram.

Amostra manual: dois primeiros resultados da primeira chamada Bing com
resultados por pergunta, 24 itens. Seis títulos/URLs pertinentes (25%);
demais genéricos ou alheios ao requisito. É seleção não aleatória, julgada pelo
agente; não precisão global do provedor nem qualidade das páginas lidas.

Exemplo diagnóstico: consulta pathlib.Path.unlink com limitações devolveu
Hotels.com; entidade e parâmetros enviados foram registrados. Outros casos
mostraram dicionários de "ano", "peso" ou "sintaxe". Consultas completas ainda
continham a entidade, portanto não se presume QUERY_BAD só pelo resultado ruim.
Localidade/período e origem original não foram verificados por esse julgamento
de metadados. Não há licença para usar os snippets como resposta.

Não foi adicionado provedor, aumentado orçamento nem implementado retry
adicional sem benefício demonstrado. As estratégias limitadas já existentes
continuam disponíveis; não há ganho de descoberta confiável para publicar.
