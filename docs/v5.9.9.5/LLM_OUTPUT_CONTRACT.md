# Contrato e diagnóstico do modelo gratuito

Fluxo: transporte → texto sanitizado pelo protocolo existente → JSON estrito → schema/tipos/IDs → quote literal e span → quantidades/unidades → revisão semântica separada. Não executar código do modelo nem preencher campos/fatos ausentes.

Bridge agora preserva `finish_reason` de vocabulário fechado e uso inteiro não negativo de prompt/completion/total tokens; strings ou metadata arbitrária não são propagadas. `length` também marca truncamento. Writer rejeita truncamento/content_filter, sem acrescentar tentativas. Proxy sem metadata continua sem metadata; não inventar finish_reason ou tokens.

Parser aceita um JSON completo ou uma única cerca Markdown completa, inclusive `JSON`/mesma linha. Rejeita múltiplos valores/objetos, prosa excedente, chaves duplicadas, NaN/Infinity, controles bidi, controles C0 indevidos e surrogate isolado. Não remove `]` excedente nem cria aspas/IDs/quotes. Segurança não foi afrouxada para fazer o modelo passar.

Não há suporte comprovado de schema/JSON mode no proxy atual; nenhum parâmetro presumido foi enviado. A ambiguidade do exemplo fixo E1 foi corrigida no prompt com os IDs realmente permitidos; IDs retornados não são remapeados.

## Chamadas reais isoladas, sem descoberta

Modelo `poolside/laguna-s-2.1:free`, fallbacks desativados, fonte MDN baixada por HTTP real. Capturas limitadas e públicas em `isolated-*-model-output.json`.

| Chamada | Término / tokens | Resultado |
|---|---|---|
| Antes do ajuste de IDs | stop; 1623 entrada, 575 saída; 9,617 s | JSON válido; IDs E1–E6 inventados para fonte S1; afirmações extras sem suporte. Rejeição `reference_mismatch` antes da revisão semântica. |
| Depois do ajuste | stop; 1685 entrada, 476 saída; 11,115 s | `invalid_json`: um `]` após o objeto final. Não houve truncamento de transporte. Sem retry de reparo. |

Não se atribui ao provedor uma falha que é de conteúdo/contrato. O novo diagnóstico separa parse, referência e truncamento, mas **não demonstrou síntese aceita**. Uso registrado: 4.359 tokens nos dois probes; não inclui todo tráfego do chat. Chamadas não streaming não fornecem primeiro token. Próximo passo é confiabilidade da geração com validação mantida; não cortar a revisão nem aceitar dados inventados.
