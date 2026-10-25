# Modelo real: revisão bloqueada; E2E completo pendente

Executado `probe_synthesis_v5994.py` na pasta V5.9.9.6, com fonte MDN baixada realmente, modelo `poolside/laguna-s-2.1:free` e fallbacks desativados. Redação: 11,175 s, 1349 caracteres; chegou à revisão separada, cuja chamada recebeu `rate_limit` em 0,589 s. Resultado externo do wrapper: SYNTHESIS_REJECTED / semantic_review_unavailable. Para aceitação, classificar como **BLOCKED pela revisão limitada**, sem síntese aprovada. Não houve retry ou fallback pago. Resposta textual do modelo fica local, manifesto contém hash.

Houve Chrome autenticado no stack FastAPI/PC Agent/SQLite temporário para cancelamento e fixture de entrega com URL explícita. Não houve síntese real aprovada nem os seis E2Es A–F completos. Resultado parcial extrativo não é sucesso de síntese.

Próximo: seis casos A–F do pedido, incluindo caso autônomo multietapas, conta QA e modelo gratuito autorizado; registrar IDs, citações, persistência e falhas sem paid fallback.
