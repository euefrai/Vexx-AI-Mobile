# V5.9.3 — progresso final, 22/10/2026

HEAD inicial 78dae77, árvore inicialmente limpa. Código final 80d0aea; documentação/evidências no commit de entrega que contém este documento. Skills diff-code-writer e token-efficient aplicadas. Sem push, deploy, reinício de produção ou agentes paralelos.

Concluído:

- Baseline Quality Lab v2 definido corretamente: 12 documentos sintéticos / oito consultas, P@K com denominador K, gabaritos/hashes preservados. Holdout adicional de três consultas congeladas antes das alterações, relógio de reprodução fixado em 22/10/2026.
- Documentos: reranking antes do corte, republicações declaradas demovidas, contexto temporal preservado. Precisão micro dos retornados 11/13 → 11/11; nDCG 0,925589 → 0,982614; P@5 0,275 e recall 0,916667 mantidos.
- Web: correspondência de modelo/contexto, preservação de cidade/estado/datas, RSS público adicional, contratos de notícia/evento/transporte, reclassificação após leitura antes do limite de fontes.
- Ciência: PDF OA declarado com identidade conferida, limites e fallbacks; conteúdo irrelevante não alimenta conclusão; escopo real persistido. Nenhum full text útil confirmado externamente nesta fase.
- Shopping: tipos/variantes, litros/tensão/acessórios e links de licença; 7/7 pipelines sintéticos de novas famílias até JDUI, zero novas ofertas externas confirmadas.
- JDUI: fonte/notícia/evento/transporte/ciência pelo schema sources, autores/DOI/veículo/imagem/detalhes, paridade Python/JS e links seguros. Datas de acesso não parecem publicação.
- Universal 3.0: 16 capturas externas, três replays de notícias, 32 contratos; classificações no JSON. Um guia turístico aceito na sonda aérea foi reconhecido como falso positivo e rejeitado; snapshot preservado.
- Chrome real: worker local, SSE/reload/desconexão, encerramento, imagem/zoom/Escape, arquivo e câmbio externo; cards contextuais fixture explícitos; 1280/390/320 px sem overflow e zero erros.
- Suíte final: 1089 passed, 4 skipped, 2 warnings, 265,98 s. Falha inicial de consumo/consome corrigida sem alterar teste antigo; artefato full-suite-first.txt preservado.
- Benchmarks finais: pesquisa 34/34, shopping 59/59, experiência 16/16. Nenhuma alteração em identidade, 3D, extensão, Fajulto ou credenciais.

Pendente / próximo passo exato:

Investigar acesso aos artigos originais descobertos no RSS, preservando URL original e limite de chamadas, e medir leitura factual municipal antes/depois. Transporte/agenda/inventário, ofertas comerciais e full text útil continuam parciais. PDF Transformer excedeu 2 MiB e não foi contornado; RSC bloqueou. Endpoint de modelos consultado não forneceu catálogo JSON válido, sem inferência executada. Não declarar cobertura universal com base em fixtures/contratos. Detalhes no relatório, BENCHMARK.md e JDUI_RESULTS.md.
