# JDUI de pesquisa

A referência enviada foi tratada como proposta visual, não como evidência de resultados do Vexx. Mantido o chat existente: superfícies escuras discretas, bordas leves, tipografia/hierarquia compactas, espaçamento consistente, cards de mídia proporcionais e fontes legíveis. Nenhuma foto de exemplo virou dado de produção.

Estilos limitados aos resultados/painel de pesquisa em `public/interface.css`. Não houve redesign de administração, identidade Lucas, motor 3D ou outras áreas. O progresso continua ligado aos eventos existentes, sem percentual artificial nem espera decorativa.

Galeria usa o componente media allowlisted, com fonte, direitos disponíveis, alt text, lazy loading e falha honesta. Modal tem navegação anterior/próxima quando há mais de uma imagem, setas de teclado, Escape, foco restaurado e link da origem da imagem ativa. Redução de movimento respeitada; animações curtas sem atrasar dados.

Composição por intenção: mídia simples primeiro, fontes de notícias/documentos nos cards existentes, ofertas só pelos registros do shopping. Galerias automáticas foram removidas de consultas sem intenção de mídia. Cards media/sources emitidos pelo modelo são removidos no caminho de pesquisa e reconstruídos a partir dos dados recuperados. Tabelas e componentes existentes continuam sujeitos à validação já presente.

Nenhum preço, disponibilidade, transcrição ou análise visual é inferido da existência de um card. Vídeos ausentes geram limitação, não miniaturas fictícias. A UI nova não comprova qualidade factual da redação do modelo.
