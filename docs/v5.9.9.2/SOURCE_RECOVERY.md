# Recuperação, leitura e preservação

Correções novas: preservação das oportunidades de leitura antes do corte de doze; reuso da seleção V5991 de seis leituras, sem duplicá-la; recuperação por entidade após incompatibilidade; publicador declarado/feeds antes de pesquisa adicional de manchete; trace de descoberta anterior ao corte disponibilizado separadamente do pool lido. IDs de candidatos continuam derivados da URL. Diagnósticos são limitados e podem indicar omissões; não constituem segunda base de evidências.

RSS/Atom, links do publicador, canonical, redirects, JSON-LD, Open Graph, PDFs e HTML usam a infraestrutura existente. Canonical externo continua declaração não verificada; não é leitura automática do original. Links relativos e URL final, publicação versus atualização e rótulos de leitura foram corrigidos anteriormente e preservados. Não se decodificam links opacos do Google nem se contornam paywalls, CAPTCHA, login ou 429.

Pedidos explícitos de PDF agora aplicam o mesmo contrato de conteúdo na pesquisa rápida e na profunda. HTML temático não passa como PDF lido. A leitura existente de PDF exige tipo/assinatura, limites de páginas/caracteres e não afirma leitura integral. A passagem do `content_scope` efetivamente extraído à validação profunda é necessária para evitar tanto falso positivo HTML como falso negativo PDF.

O QA real de história corporativa revelou um aviso de manutenção como trecho, apesar de o corpo conter a fundação. Para pedidos históricos, quando existe campo explícito de fundação/inauguração no texto lido, a janela contígua é ancorada nesse campo, preservando contexto, tokens, nomes e números. Não há resumo inventado ou concatenação de trechos. O limite continua 1500 caracteres e a origem continua rastreável. A regra não prova por si só que toda data ou fundação pertence à entidade correta.

Bloqueios externos são limitações legítimas. Relevância textual não transforma Wikipédia em fonte primária, homepage em artigo, menção de cidade em acontecimento local ou atualização em publicação. Esses limites são considerados no julgamento manual e na decisão de publicação.
