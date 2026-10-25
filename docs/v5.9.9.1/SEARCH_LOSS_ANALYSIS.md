# Search Loss Forensics

Baseline novo em71e978e, antes de mudar algoritmos. `baseline-losses.json` rastreia os vinte casos com pergunta, intenção/contrato, consultas, provedores, pool de URLs, leituras observadas, destinos, razões e limites. `tools/analyze_source_recovery_v5991.py` é offline, sem modelo ou rede. Síntese e JDUI são NOT_EXECUTED_RETRIEVAL_PROBE; não se inventam falhas nessas etapas não exercitadas.

| Perda reproduzida | Etapa/diagnóstico |
|---|---|
| Histórico/empresa retornam páginas sobre a palavra história | DISCOVERY/LOW_RELEVANCE; não resolvido amplamente |
| Original identificado após seis candidatos genéricos não era aberto | Seleção por posição; corrigida dentro dos mesmos slots |
| Nome do veículo diluía a comparação da manchete | Original recovery; comparação corrigida |
| Leitura de fonte sem publicação suficiente | EVIDENCE_INSUFFICIENT; leitura preservada, elegibilidade não concedida |
| Página/CAPTCHA/tipo/rede não abriu | FETCH_BLOCKED/FETCH_FAILED, sem confundir com tema |
| Corpo vazio | EXTRACTION_EMPTY |
| Data, entidade ou tema incompatíveis | DATE_MISMATCH/HARD_CONSTRAINT_MISMATCH/LOW_RELEVANCE |
| Agregador/índice no destino | REDIRECT_TO_AGGREGATOR/INDEX_PAGE |
| Candidato não selecionado por orçamento | READ_BUDGET_NOT_SELECTED, sem fingir que é automaticamente defeito |
| Feed usado apenas como pista | DISCOVERY_ONLY |
| Rota rápida consumia comando profundo | Roteamento, antes do job; corrigido |
| Job terminava sem mensagem final | Persistência/composição/sincronização; corrigido |
| Frente limitações perdia asyncio.TaskGroup | Filtragem original por entidade; corrigida |
| Pedido de PDF devolvia imagens de manuais genéricos | Composição/tipo/pertinência de mídia; corrigido |

Baseline: 54 fontes abertas entre as devolvidas, mas 91 leituras no pool limitado. São contadores de escopos diferentes. Abertura não certifica originalidade ou suporte factual. Falta de trace do shopping é TRACE_UNAVAILABLE. Cortes anteriores ao pool, corpo histórico não capturado, semântica territorial e correção factual integral não receberam prova completa. Motivos podem coexistir, não devem ser somados como documentos distintos.

`judged-sample.json` registra revisão rastreável por agente com critérios estreitos (tipo documento, identidade API e leitura real). Não é painel humano, gabarito independente, precisão global ou denominador de recall. Falsos negativos/positivos sem julgamento continuam desconhecidos.
