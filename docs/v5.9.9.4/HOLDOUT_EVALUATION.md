# Avaliação separada e congelamentos

1. e8f9443 congela 108 exemplos DEV/VALIDATION, 17 operacionais selados e
   doze novas perguntas externas, antes de modificar o matcher.
2. beab357 congela a aplicação antes de abrir os resultados selados.
3. Após descobrir a direção causal incorreta, os conjuntos abertos tornam-se
   diagnósticos. 13b3013 congela oito novas perguntas antes da correção.
4. f5f1561 congela a correção causal antes de abrir a avaliação de oito.
5. 76e6af3 congela seis novas perguntas antes da correção da ordem do DOM.

Nenhum conjunto tem gold humano independente. O grupo sintético selado foi
escrito pelo mesmo agente: é isolamento operacional, não independência plena.

17 selados: retenção TP 5 FP 0 FN 0 TN 12 antes/depois; precisão DIRECT 0,8→1,0;
um parcial deixou de ser promovido. Não houve ganho de recall nessa amostra.
Depois da correção causal esses 17 são apenas diagnóstico aberto.

Doze LIVE_EXTERNAL: 0→1 leituras elegíveis, 36→34 abertas, 67→64 chamadas,
123→122 fetches. Medianas 8,107→7,330 s; não são ganho causal de latência.
A revisão revelou que a única nova elegível estava vinculada ao atributo
errado. Portanto **não houve ganho de qualidade comprovado nessa rodada**.

Oito LIVE_EXTERNAL novos: 7→3 elegíveis, 24→24 abertas, 25→25 chamadas,
67→67 fetches; medianas 6,6555→6,1145 s. Perda de dois parciais úteis e remoção
de dois resultados problemáticos. Os três restantes incluem exercícios e
assinatura extraída de forma defeituosa; não considerá-los respostas validadas.

Diagnósticos externos anteriores, medidos com beab357:

| Conjunto | Casos | Leituras elegíveis | Casos com elegível | Abertas | Chamadas |
|---|---:|---:|---:|---:|---:|
| Históricos | 20 | 12 | 5 | 57 | 107 |
| Antigos doze | 12 | 4 | 2 | 33 | 54 |
| Antigos quinze | 15 | 1 | 1 | 42 | 73 |
| V5993 vinte | 20 | 2 | 2 | 59 | 111 |

Todos sem erro de processo registrado, mas elegibilidade é decisão do motor,
não gold factual. Não somar esses números como precisão/recall universal.
Probes não usam modelo nem verificam cards no chat. Relógio do pedido pareado;
internet/índice/carga não são congelados. FROZEN_REPLAY é outra categoria.

Seis novos LIVE_EXTERNAL após a91c113: 1→1 leituras elegíveis,18→18 abertas,
26→26 chamadas e48→48 fetches; medianas10,5955→7,4205 s (variação de rede,
não efeito causal da correção). Um trecho TC39 passou a manter a ordem do texto,
mas houve passagens com classificação positiva bloqueadas por outros filtros;
não houve ganho consistente de entrega. Não se ajustou o código usando esses
resultados. post-order-guard registra os hashes finais.

Decisão final: **NO_GO**. Contagens do motor não bastam, a avaliação expôs falsos
positivos e perdas úteis e não há pesquisa autônoma completa com modelo.
