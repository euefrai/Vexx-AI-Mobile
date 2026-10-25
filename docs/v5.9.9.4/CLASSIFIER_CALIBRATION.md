# Calibração e limites

Reutilizados Query Intelligence, requirement_coverage, Evidence Graph e os
stores existentes. Nenhum classificador/serviço LLM novo por passagem.

Correções gerais: entidade com limites completos (inclusive II/III), predicado
depois do nome (não confundir o substantivo Fábrica com verbo), auxiliares
limitados, prototype normalizado sem apagar pontuação de frases, contexto
imediatamente adjacente para pronome/nome de operação e condição de peso com
bateria/cartão. PARTIAL_SUPPORT é retido, mas não confirma o requisito.
Seleção com o mesmo teto de três passagens prefere diversidade e mantém todos
os requirement_ids de uma passagem compartilhada.

| DEV 74 exemplos | Antes | Candidato beab357 |
|---|---:|---:|
| TP / FP / FN / TN | 8 / 2 / 5 / 59 | 13 / 0 / 0 / 61 |
| Precisão de retenção | 0,8000 | 1,0000 |
| Recall de retenção | 0,6154 | 1,0000 |
| F1 | 0,6957 | 1,0000 |
| FPR / FNR | 0,0328 / 0,3846 | 0 / 0 |
| Precisão de DIRECT | 0,6000 | 1,0000 |
| Recall dos dois PARTIAL | 1,0000 | 1,0000 |
| Parciais promovidos a completos | 2 | 0 |

VALIDATION 34: TP 4 FP 0 FN 0 TN 30 antes/depois; não contém PARTIAL, portanto
partial recall é null. Os arquivos JSON incluem matriz e métricas por domínio.
O conjunto é pequeno, sintético e anotado pelo próprio agente. Não estimar
precisão real da web a partir desses números.

Falha externa descoberta depois do freeze: "campanha levou à revolta" entrou
como consequência da revolta. f5f1561 vincula direção/sujeito e preserva a causa
inversa. No mesmo texto congelado, CAUSES passa a SUPPORTED e CONSEQUENCES a
DISCOVERED. O novo conjunto de oito mostrou trade-off: 7→3 leituras elegíveis,
com perda de duas passagens parcialmente úteis e rejeição de duas candidatas
problemáticas (alternativas não confirmadas/relação causal trocada).

Há falhas restantes: exercícios de múltipla escolha podem contaminar o trecho,
referências pronominais/enumerações amplas não são resolvidas universalmente e
os padrões não validam toda condição temporal/local ou data completa.
Não ajustar os gabaritos para esconder essas limitações.

Uma causa estrutural foi reproduzida: o mini-DOM reordenava texto inline e
parâmetros. a91c113 preserva fragmentos na ordem do documento, separa blocos e
evita duplicar texto de parágrafos. Reprodução: cinco falhas/um aprovado antes;
seis aprovados depois. Os testes anteriores de extração/retrieval passaram.
O texto continua limitado a8k e normaliza espaços; não é garantia de preservar
todo layout/indentação de código nem todos os contextos semânticos.

Microbenchmark sintético de 1000 parágrafos: 62,77→68,10 ms por extração em cinco
execuções; pico de alocações Python separado 1.938.094→2.677.744 bytes. Custo
medido de aproximadamente5,33 ms/0,74 MB, não ocultado como ganho de performance.
É uma amostra local, sem intervalo de confiança, não RSS/produção. Limites de
HTML, bytes, páginas e paralelismo mantidos. Preservar fatos/assinaturas é o
benefício concreto; não declarar menor RAM ou menor latência de rede.
