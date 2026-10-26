# Rendimento e perdas de passagens

As sete páginas acessíveis foram comparadas com o MESMO snapshot público, SHA registrado; três acessos falharam. Rótulos são heurísticos, não verdade factual independente.

| Fonte conhecida | Resultado/causa |
|---|---|
| MDN Object.assign | Trecho de retorno de 18 caracteres descartado; whitespace de seções impedia alinhamento literal. Corrigidos. Retorno DISCOVERED→PARTIALLY_SUPPORTED; comportamento DISCOVERED→SUPPORTED; sintaxe mantida. Vínculos 9→15, três passagens selecionadas. |
| MDN Math.hypot | Três facetas continuam SUPPORTED; vínculos 7→8, três passagens. Sem alegar nova cobertura. |
| Tramontina | 681 caracteres lidos; fundadores aparecem com sujeito implícito. Regra exige entidade/relação explícitas; produtos não cobertos. Não é falha de download. |
| NASA Artemis | 5.106 caracteres lidos, seis candidatos; pergunta de datas sem esquema de requisito suportado. Informação não chega a evidência. |
| SQLite WAL | 8.000 caracteres; vantagens/limitações presentes, relação lexical insuficiente. Zero evidência retida. |
| Nikon Zf | Extração padrão 8.000; diagnóstico do MESMO HTML com teto maior apenas na análise revela 12.375 caracteres, bateria na posição 11.510, peso 710 na 12.128. Perda confirmada no corte; nenhuma alteração de teto no produto. |
| Yellowstone NPS | 8.000 caracteres com preço/duração, sem associação suficiente da entidade/atributo; zero retida. |
| WEG / FGV Chibata / PDF NASA | bloqueado / rede / tamanho. Nenhum bypass ou aumento de limite. |

Correções adicionais: título isolado “Return value” deixou de contar como verbo de retorno; “copies/copia” é reconhecido apenas sob guardas existentes de sujeito/operação. Passagens curtas não viraram prova direta automaticamente. Seleção limitada de vínculos agora distribui facetas antes de truncar.

Não existem precisão/recall/FPR/FNR humanos independentes neste conjunto. Testes negativos cobrem título sem relação, método errado, texto não adjacente e fonte genérica; não demonstram ausência universal de falsos positivos. Próxima perda prioritária: seleção de seções tardias sob orçamento constante, não aumento global de texto.
