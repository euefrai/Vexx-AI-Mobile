# V5.9.6 — recuperação de fontes

HEAD inicial: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`. A arquitetura existente foi mantida: Query Intelligence → plano → Search Orchestrator/provedores → leitor seguro → evidências → lacunas → síntese → JDUI.

## Causas corrigidas

- RSS Google descartava o endereço do publicador. Agora conserva `publisher_url` e continua sendo `feed_metadata`, nunca artigo lido.
- A descoberta genérica não usava a manchete como pista específica. Agora há até duas pistas por título/domínio, dentro dos limites originais de tempo/tentativas, sem decodificar endpoints privados do agregador.
- Se a busca não encontra o original, o mesmo orçamento permite visitar o publicador declarado e usar links pertinentes ou RSS/Atom realmente declarado por ele. Não são adivinhados endpoints `/feed`, URLs de artigo, dados ou datas. Cada fetch precisa obter um slot antes de executar. Ausência de acesso/feed/ganho encerra a tentativa.
- Candidato recebe `source_recovery`, com método e proveniência; só vira `original_read` após leitura de conteúdo pertinente. Metadados sobrevivem ao SQLite. Redirects e validação SSRF continuam no downloader existente; canonical/JSON-LD/Open Graph continuam no extrator. Não foi introduzido seguimento irrestrito de canônicas entre domínios.
- `/noticias/`, `/news/` e `/ultimas-noticias/` exatos agora são índices; suas páginas de artigo subordinadas não são bloqueadas por esse critério. Corrige falha do baseline, sem alterar gabarito.

## Resultado obrigatório: Ubatã

Pergunta real: “Quais notícias aconteceram em Ubatã, Bahia, nos últimos sete dias?”. Foram descobertas seis entradas no Google News; três registros de descoberta permaneceram na investigação. Manchete recente sobre atendimento jurídico foi encontrada; outras entradas eram antigas e não podem satisfazer o período.

Busca por manchete/domínio e tentativa no RSS do publicador foram executadas e registradas em `live-recovery-final/news_local.json`, `search_events[].meta.recovery_steps`. **Zero artigo original lido.** Não se confirmou cobertura dos acontecimentos municipais. A notícia sobre dois municípios também não deve ser apresentada como acontecimento exclusivamente de Ubatã. O orçamento encerrou tentativas adicionais; não houve contorno de bloqueio.

## Produto e contexto

`shopping._ram_do_produto` agora reconhece campos estruturados e títulos inequívocos de notebook (`8GB, SSD 512GB`), separa RAM virtual e não escolhe o maior valor para resolver declarações conflitantes. O anúncio real da V5.9.5 foi reprocessado offline: sai do grupo aceito para pedido de 16 GB, com conflito de RAM. Replay não é oferta nova. Categorias, orçamento, variantes e verificação de links/estoque continuam exigidos; `identity_state` é diagnóstico adicional, preservando contratos antigos.

No plano científico, frentes como “métricas” ou “lítio” isoladas perdiam a pergunta. Agora cada frente conserva o assunto; tradução técnica existente pode ser usada como descoberta. O pedido de métodos/texto completo não fecha lacuna apenas com resumo. Orçamento, replanejamento, cancelamento e checkpoints existentes permanecem.

Pendente: ampliar leitura de artigos locais por estratégias legítimas com ganho mensurável; conflitos além de RAM e modelos precisam continuar sendo tratados conservadoramente. Nenhum ganho de cobertura universal foi comprovado.
