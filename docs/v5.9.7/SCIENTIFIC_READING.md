# V5.9.7 — leitura científica limitada

O leitor de pesquisa extraía até 200 páginas antes de cortar o resultado em 8.000 caracteres. Agora passa limites explícitos pela API existente de documentos: até 12 páginas e 8.000 caracteres, interrompendo a extração ao atingir o limite. Uploads mantêm seus limites anteriores.

Trechos de PDF preservam o número da página. Cabeçalhos científicos explícitos, quando efetivamente presentes nas linhas extraídas, permitem separar métodos, resultados, limitações e conclusões. A ausência de um cabeçalho no trecho limitado não significa ausência dessa informação no estudo inteiro.

Prova controlada: um PDF simulado com 30 páginas só invoca o extrator da primeira página quando o limite de caracteres é alcançado. Outro teste mantém página, URL e trechos literais de métodos/resultados, sem inventar limitações.

Prova externa em `direct-pdfs.json`: duas URLs OA previamente descobertas foram abertas novamente com o leitor limitado; 7.967 e 7.999 caracteres recuperados. Um PDF usou fallback pypdfium2 porque o pypdf local não dispunha da dependência AES; a limitação foi registrada. Ambos ficaram como leitura parcial, com seções genéricas por página; não houve comparação experimental aprovada.

Na busca completa desta versão, os cenários científico/PDF não chegaram a fontes aceitas. A leitura direta não foi somada à taxa de descoberta. Não foram inferidos causalidade, equivalência de ensaios, métricas ausentes ou conclusão integral dos estudos.
