# V5.9.3 — cards contextuais

Reaproveitado `sources`, preservando os demais componentes e o layout global. Campos novos validados em Python e JavaScript: publicador, autores, DOI, imagem, favicon fornecido, URL do texto recuperado e até seis detalhes. Sem HTML/JS arbitrário do modelo.

- Source/News: título, veículo/domínio, publicação, trecho e estado encontrado/lido/utilizado; imagem só quando recuperada. RSS permanece encontrado/não lido.
- Event: data do evento independente da publicação, local/organizador somente quando declarados na fonte. Turismo genérico não produz confirmação de agenda.
- Travel: rota/operadora/horários somente quando recuperados; preço só com origem, destino, data e adultos correspondentes. Declaração de tarifa não prova inventário atual.
- Scientific: autores/ano/DOI/tipo quando disponíveis, escopo abstract ou texto de PDF, link de texto somente se recuperado. Sem presumir peer review ou artigo completo a partir de abstract.
- Product: preço, variante, loja, imagem, vereditos e pendências existentes preservados; sete famílias passaram no pipeline sintético de extração até JDUI.

`source_card` centraliza o formato para a visão de pesquisa, fontes do chat e fallback sem inferência. O card usa data da publicação; acesso ao documento não é rotulado como publicação. Sem campos ausentes preenchidos como se fossem reais. Sem favicon buscado por adivinhação; imagens com falha são removidas.

## Verificações executadas

Chrome real headless, relay e PC Agent locais, SQLite/perfil temporários. Nenhuma conta de produção ou permissão de controle remoto alterada.

- Worker de pesquisa real com conteúdo fixture explicitamente identificado, reload durante execução, interrupção/reconexão SSE, 43 eventos ordenados e encerramento da barra.
- Imagem servida realmente pelo servidor local, zoom/Escape e exportação HTTP 200 com 1983 bytes.
- Cards de notícia/evento/transporte/ciência com **dados fictícios de QA claramente identificados**. Montagem DOM real, imagem carregada e checagens de overflow a 1280/390/320 px.
- Câmbio externo pelo chat, cards/gráfico e persistência após reload; 23 pontos reais na execução final, quatro rótulos sem sobreposição.
- Zero erros registrados no resultado final. Paridade Python/JS e sanitização de links testadas; uso de `javascript:` rejeitado.

Screenshots inspecionadas:

- [Cards desktop](../../qa-artifacts/v593/contextual-1280.png)
- [Cards mobile 390](../../qa-artifacts/v593/contextual-390.png)
- [Cards mobile 320](../../qa-artifacts/v593/contextual-320.png)
- [Fontes](../../qa-artifacts/v593/sources-desktop.png)
- [Câmbio mobile](../../qa-artifacts/v593/exchange-mobile.png)
- [Pesquisa desktop](../../qa-artifacts/v593/research-desktop.png)

Limites: Chrome mobile emulado, não aparelho físico; dados de evento/transporte/ciência do teste visual são fixtures, não recuperação externa confirmada. Links dessas fixtures apontam a um recurso local realmente servido para testar navegação/segurança, não a notícias ou itinerários reais. Vídeos não foram assistidos/analisados. REAL_MODEL não executado. Cancelamento permanece coberto por backend; não houve novo E2E Chrome específico de cancelar.
