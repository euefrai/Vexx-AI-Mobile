# V5.9.5 — benchmark e aceitação

Executado em 23/10/2026, usando processos locais, SQLite temporário e provedores externos existentes. Não foi teste autenticado do aplicativo completo. Artefato consolidado: `qa-artifacts/v595/universal-assessment.json`; consultas originais em `benchmarks/universal_sources_v595.json` e `benchmarks/shopping_sources_v595.json`.

Rodadas: 15 casos universais, seis repetições temporais após correção do planejador, uma repetição de documentação e duas de mídia. Comércio: 13 consultas adicionais via adaptador web real, sem reconsultar MLB bloqueado. As repetições não são casos independentes para calcular acurácia. Sem compra, reserva ou contorno de bloqueio.

| Pedido | Última evidência real | Aceitação |
| --- | --- | --- |
| Galaxy A56, Lenovo, tênis de basquete, Bluetooth, geladeira, lavadora, livro, ferramenta, autopeça, componente, esporte, móvel, construção | 13 consultas; produtos parciais em autopeça (4), Bluetooth (4), Lenovo (2); zero oferta exata confirmada | Parcial/indisponível; estoque independente = 0 |
| Voo Salvador–São Paulo amanhã, um adulto | Data preservada 24/10/2026; zero fonte lida/tarifa validada | Indisponível |
| Ônibus Salvador–Feira amanhã / Itabuna–Salvador depois de amanhã | Datas/rota preservadas; zero fonte lida/tarifa validada | Indisponível |
| Notícias Ubatã/BA, Salvador, Feira | Respectivamente 3/3/1 registros de feed; zero artigo original lido | Parcial, sem notícia factual confirmada |
| Eventos futuros Recife | Zero fonte lida | Indisponível |
| Estudos creatina/força | Três resumos lidos, nenhum texto completo | Parcial |
| Documentação TaskGroup/cancelamento | Uma página oficial lida após correção; antes zero | Recuperação confirmada; resposta completa não aprovada |
| USD/BRL | Resposta do adaptador diário, referência 22/10/2026 | Confirmado no escopo diário, sem validação independente do valor |
| Clima Salvador | Resposta Visual Crossing, observação agregada 23/10 às 07h; consulta às 07h27 | Confirmado no escopo do adaptador municipal, sem alterar clima |
| Imagem licenciada Ponte Estaiada | Links encontrados não atendem pedido/licença | Indisponível |
| Vídeo NASA/James Webb | Links YouTube genéricos e outras mídias | Indisponível; sem análise audiovisual |
| PDF Attention Is All You Need | Dois resumos; PDF solicitado não lido | Parcial, pedido não atendido |
| Comparação baterias sódio/lítio | Dois PDFs públicos abertos, extração limitada; modelo indisponível | Parcial; comparação de métodos/métricas não aprovada |

## Ganhos comprovados e perdas do pipeline

- Replay offline de produtos reais capturados antes: TV aparecia como alternativa ao Galaxy A56; agora é excluída por categoria. `commercial-replay.json` registra TV 1 → 0. Isso não é oferta externa nova.
- Comércio segue limitado por páginas indisponíveis, busca irrelevante, ausência de dados estruturados e divergência de modelo/variante. `source_trace` preserva página, variante, preço/estoque declarados e validação de link/imagem. Algumas especificações contradizem o título (Lenovo com título 8 GB em consulta 16 GB): produto permanece parcial; não aprovar oferta exata. A correção universal de tais conflitos permanece pendente.
- RSS não encerra descoberta e não supera artigo original na deduplicação. Datas originais/horas e restrições sobrevivem ao plano e retomada; testes locais verificam o contrato, mas o resultado externo ainda não abriu artigos.
- URLs de mídia sobrevivem à ausência de HTML; seguem `unverified`, `not_analyzed`, `evidence=false`. Links genéricos não contam como sucesso semântico.

PDFs realmente abertos: DOI `10.26876/ikergazte.vi.05.25`, [texto](https://aldizkariak.ueu.eus/index.php/ikergazte/article/download/5958/5580), licença declarada CC BY-SA; DOI `10.64876/radi.v24.52-58`, [texto](https://radi.org.ar/index.php/radi/article/download/14/55), CC BY-NC-SA. Extração limitada, não leitura integral nem aprovação comercial. O caminho novo OA HTML possui teste local de identidade/licença; não foi comprovado em fonte externa nesta rodada.

## Modelo, ranking e custos

`model-stream.json`: catálogo 425, modelo configurado encontrado; tentativa SSE de 7,234 s resultou `BridgeErro/vazia`, zero chunks, `BLOCKED`, `deep_research_approved=false`. Não repetido após bloqueio. Nenhuma resposta extrativa foi apresentada como inferência do modelo. Revisão semântica humana de suporte das citações não automatizada; não atribuir precisão de citações a simples link válido.

Laboratório congelado local reexecutado: 11 documentos, oito casos, nove consultas; precision@5=0,266667, recall/MRR/nDCG=1, duplicação=0. Métricas iguais ao baseline (`offline-after.json`). É fixture sintética de recuperação local; não mede qualidade web, superioridade ao Perplexity ou resposta de LLM. Tempos externos são latências pontuais nos JSONs, não SLA; sem afirmação de melhoria global de RAM/custo.

Próximo passo exato: resolver conflitos título/specs do comércio com teste de identidade; depois melhorar seleção de artigos locais originais e relevância da mídia, sem promover feed/link a evidência. Só aprovar síntese profunda após uma inferência gratuita real com chunks e suporte semântico revisado.
