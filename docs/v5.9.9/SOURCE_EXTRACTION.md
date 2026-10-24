# Fontes e extração

Mantidos os leitores HTML/semântico, JSON-LD, RSS/Atom, tabelas, links, seções e PDFs acessíveis. Sem navegador renderizando páginas dinâmicas no backend, execução de scripts de sites, CAPTCHA, autenticação ou contorno de paywall. Nenhum novo provedor pago.

A pesquisa rápida passou a transportar a mídia real de `media_evidence.extrair_midia` e do adaptador Commons, incluindo origem, licença/metadados disponíveis e estado não analisado. Títulos/miniaturas/metadados de vídeos não comprovam transcrição ou análise. Fonte não lida conserva metadata_only/feed_metadata e não aumenta contador de artigos lidos.

Corrigida a preservação de publicado_em quando o provedor entrega a data no nível superior. `fontes_relevantes` conserva o registro completo ao avaliar o texto lido. Verbos de instrução como “usar” não são exigidos literalmente no documento inglês. O adaptador oficial de asyncio já existente aceita o identificador do módulo sem exigir também a palavra Python na pergunta.

Uma sonda temática revelou Google Notícias/home classificado como matéria. O agregador agora é índice/discovery, inclusive wrappers, e não artigo confirmado. A fonte conserva `url` de descoberta e `url_final` da leitura; o filtro usa o destino efetivamente lido para reconhecer índices após redirect. Ler uma página não implica que ela seja elegível. A classificação de todas as páginas iniciais de publicadores ainda merece cobertura adicional.

Os tetos de bytes, timeout, páginas, workers e extração limitada foram mantidos. Trechos/PDFs não são apresentados como leitura integral. Bloqueio do site e ausência de conteúdo permanecem resultados possíveis. Não foi criado um crawler nem um leitor dinâmico paralelo. Melhorias amplas de extração e cobertura de documentos difíceis não são inferidas desses ajustes.

Metadados de mídia recuperada rejeitam destinos IP privados/loopback/link-local, hosts localhost/local/internal, aliases numéricos e portas malformadas, sem fazer DNS/fetch extra. Isso não substitui a política de rede do navegador nem certifica todo redirecionamento/DNS de um host público. Leitores HTTP do backend continuam com suas proteções existentes de DNS/redirect/bytes/tipo.
