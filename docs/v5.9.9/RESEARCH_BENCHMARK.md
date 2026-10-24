# Avaliação V599

Dataset: `benchmarks/universal_search_v599.json`. Dois conjuntos com vinte categorias cada: desenvolvimento e avaliação com perguntas distintas. Não alteram os benchmarks congelados nem contêm gabaritos de fatos fabricados. Há notícias municipais/nacionais/internacionais, pessoas públicas, empresas, lugares, produtos, tecnologia, documentação, história, eventos, imagens, vídeos, PDFs, comparação, atualidade, contradições, escassez, múltiplos requisitos e multietapas.

`tools/bench_universal_v599.py --live` executa os adaptadores existentes com SQLite em memória, limites curtos e teto de subprocesso de 65 s por caso. Registra fontes, estados, leitura, elegibilidade, chamadas, metadados, candidatos, latência e ofertas confirmadas. Não executa inferência e não mede cards renderizados. Latência não é TTFT.

Separação de escopos:

- FIXTURE: regressões determinísticas de restrições, preservação, galeria/cache e isolamento.
- FROZEN_REPLAY: benchmarks imutáveis de pesquisa/compras/experiência.
- LIVE_EXTERNAL: duas baterias externas; counts e estados não são recall/precisão sem julgamento independente.
- REAL_MODEL: uma sonda explícita com modelo gratuito, 1.800 tokens já previstos na ferramenta; contexto documental curto, sem retry/modelo pago. Resposta pública/ordem observadas, literalidade falhou; qualidade parcial.
- AUTHENTICATED_E2E: Chrome com relay, PC Agent e SQLite temporários, contas QA e modelo gratuito; dados e falhas do que apareceu no chat.

As primeiras baterias ocorreram durante iterações. Não são uma comparação controlada antes/depois nem uma taxa de aprovação universal. Resultados de avaliação devem ser interpretados junto do estado de código registrado e dos limites. RAM/CPU, FPS mobile e precisão de citações não foram medidos por esta bateria; não substituí-los por zero ou 100%.

O baseline completo foi 1443 passed,4 skipped,2 warnings. Rodada intermediária registrou três regressões de reformulação; a mudança de consulta inicial foi revertida, mantendo o gabarito e a consulta original. Resultados finais e detalhes dos skips ficam no relatório principal e nos logs.

Suíte final após a continuação: **1507 passed, 4 skipped, 2 warnings em 147,26s**, revisão de código `ee770ce`, log `full-suite-topical-final.log`. Congelados 34/34, 59/59, 16/16. A avaliação externa com revisão registrada31491a3 teve20casos,168candidatos por pesquisa somados,50aberturas,7leituras elegíveis e0ofertas verificadas; mediana7,364s. Não representa precisão/recall final dos patches posteriores e não recebeu julgamento factual independente.

## Continuação: descoberta temática

`topical-discovery/` preserva seis sondas sequenciais antes/depois da extração de tópico (baseline4b54a26) e uma repetição final de energia solar após o filtro de agregador (ee770ce). Mesmos limites, sem inferência. Inteligência artificial continuou com zero originais lidos; Recife manteve três páginas lidas e nenhuma elegível; energia solar saiu de zero leituras elegíveis para uma matéria original do Canal Solar. A contagem provisória de duas elegíveis em solar-after.json incluía indevidamente Google Notícias/home; o arquivo bruto foi preservado e a correção tem regressão específica. solar-final.json registra três aberturas, uma elegível, duas páginas genéricas rejeitadas.

São diagnósticos de três pedidos, não uma comparação estatística, medição de recall absoluto ou aprovação de síntese factual. A rede pode mudar entre chamadas. A redução de texto da consulta não relaxou cidade/período de Recife nem criou janela de sete dias para “novidades”. Focados adicionais:111passed em4,97s; os três congelados foram repetidos sem regressões. Nenhum novo teste visual foi executado nesta continuação, pois a mudança é no backend de pesquisa.
