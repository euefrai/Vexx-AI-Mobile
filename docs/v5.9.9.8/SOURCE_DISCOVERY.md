# Descoberta

Problema reproduzido: buscas por Math.hypot podiam parar em calculadoras genéricas. O fallback agora rejeita incompatibilidade de operação qualificada, mantendo operação explícita em título/trecho/caminho. Documentação pai continua disponível para navegação existente; isso não a transforma em evidência direta.

Uma primeira implementação excluía índices pais e derrubou o replay de API a zero. Foi corrigida ANTES de abrir o holdout e ganhou teste negativo/positivo. Não foram criados provedores, agentes ou novos limites.

Live de desenvolvimento: baseline encontrou cinco evidências; rodada posterior não encontrou nenhuma, com respostas de provedores diferentes. A rede mudou: comparação NÃO causal. No replay de HTML genérico, leituras caíram 6→0, evidências ficaram 0→0. Redução de desperdício, não ganho informacional.

Consulta nova no Chrome, Array.prototype.flat: quatro fontes lidas, incluindo documentação MDN e proposta TC39; sintaxe/retorno/comportamento classificados com suporte, limitações não. Uma observação positiva não compensa o holdout de 12 perguntas sem evidência retida lida.

Limitação de escopo: a regra depende da entidade parseada, não resolve automaticamente linguagem natural, notícias, história, comércio ou direitos legais. Extração de entidades falhou em perguntas externas; registros preservados, sem ajuste posterior ao holdout.
