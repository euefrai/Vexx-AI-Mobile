# V5.9.6 — mídia e ciência

## Imagens reais

Commons já retornava arquivos pertinentes, mas a frase completa dificultava a consulta e o código aceitava somente `upload.wikimedia.org`. A resposta atual também usa `thumb.wikimedia.org`. O adaptador agora pede `extmetadata`, reduz termos de interface na consulta e preserva arquivo original, miniatura, página, descrição, dimensões, MIME, autor e licença declarada quando disponíveis.

Resultado LIVE_EXTERNAL: **cinco imagens da Ponte Estaiada em São Paulo** chegam à galeria; no Chrome, as cinco miniaturas carregaram de fontes externas reais. Estado anterior da V5.9.5: nenhuma imagem solicitada entregue. Direitos observados incluem CC0, CC BY-SA 3.0 e CC BY 2.0; são declarações da fonte, sem auditoria jurídica independente. Não foi afirmada análise visual automática nem usada imagem como prova factual.

O filtro de tópico usa metadados e tipo solicitado. Canal/homepage do YouTube não é vídeo específico; não deve preencher VideoCard. Metadados `VideoObject` reais em JSON-LD podem fornecer título, autor, thumbnail, data e duração. `VIDEO_FOUND` difere de `METADATA_READ`; transcrição/análise audiovisual não foram implementadas nem alegadas. O pedido externo NASA/James Webb continuou indisponível. Os testes de VideoObject são FIXTURE, não recuperação real de vídeo.

Referências técnicas consultadas: [Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo) e [CommonsMetadata](https://www.mediawiki.org/wiki/Extension:CommonsMetadata). Campos ausentes continuam ausentes; licença não é inferida da plataforma.

## Documentos e ciência

Dois PDFs públicos abertos na investigação real sobre baterias: DOI `10.64876/radi.v24.52-58` e `10.26876/ikergazte.vi.05.25`. Links exatos, direitos e trechos estão em `live-model-acceptance/comparison.json`. Um declara CC BY-NC-SA; não presumir uso comercial autorizado. Extração limitada, sem afirmar leitura integral, número de páginas não medido ou comparação experimental concluída.

Seções realmente extraídas de HTML podem receber rótulos de método/resultados/limitações/conclusão, com trecho e página quando conhecida. Classificar cabeçalho não extrai automaticamente amostra ou instrumentos ausentes. Preservados DOI, autoria, tipo/publicação e status de revisão; preprint não é promovido a artigo revisado. O teste de extração/classificação de seções é local; não há alegação de que os dois PDFs forneceram todas essas seções.

No JDUI, só há tabela de métodos quando seções existem. Com dois textos completos parciais, mas sem seções suficientes, mostra-se comparação bibliográfica com escopo explícito, sem fabricar métricas ou normalizar condições experimentais.

Links HTML comuns de navegação da documentação não são mais cards de arquivo duplicados. Permanece a fonte original nos SourceCards. Downloads de conteúdo protegido, paywall/CAPTCHA e código arbitrário do modelo não foram habilitados.
