# Avaliação independente

Doze perguntas novas congeladas antes da implementação em bc3bc27: benchmarks/deep_document_v5999_holdout.json. Referência de criação 26/10/2026; execução live 27/10/2026, relógio real não congelado para notícias. Nenhuma alteração das perguntas nem adaptação do retrieval depois de abrir resultados.

Abrange produto extenso, API, empresa, história, notícia local/nacional, manual PDF, tabela, referência tardia, ausência de resposta, entidade ambígua e múltiplas facetas. Track B não recebe URLs. Track A usa sete capturas conhecidas separadamente; Track C usa evidência Math.hypot com origem semeada explícita.

Resultado observado: **2/12 com passagens úteis**, ambas APIs. reduceRight reteve cinco registros lidos com quatro URLs únicas; inclui espelhos MDN e repetição de URL, sem alegar corroboradores independentes. allSettled reteve três registros lidos. Biblioteca baiana: um registro lido, nenhum trecho com número de visitantes, classificado apenas como contexto. Nove restantes sem informação útil retida.

Facetas: reduceRight sintaxe suportada, retorno/comportamento parciais. allSettled sintaxe/comportamento suportados; “retorno” e comparação não foram inteiramente representados pelo parser, portanto complete não aprova a pergunta toda. Sem síntese LLM nessa ferramenta.

external-summary.json distingue candidatos, documentos extraídos, registros retidos/lidos, URLs únicas, passagens, requisitos, tempos e eventos. Precisão/recall globais indisponíveis sem gold humano. Perguntas/rede diferem das 12 anteriores: 0→2 não é uma comparação causal controlada. Cobertura insuficiente mantém NO_GO.
