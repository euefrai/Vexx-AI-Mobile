# Identidade e reuso documental

Reutiliza `research_cache`; nenhuma tabela ou banco novo. Namespace `document:<job>`, com escopo SHA-256 de versão, owner, job, chat, objetivo e identidade do leitor. Consulta SQL também exige owner. Um leitor injetado diferente invalida o cache: isso corrigiu a regressão real encontrada na primeira suíte completa, sem mudar o teste existente.

Somente extração marcada como lida e com texto é elegível. Abstract, feed/metadados, falha, cancelamento e resultado fora do prazo não são promovidos. Documento rejeitado pode ser reavaliado para outro requisito sem novo download. TTL: 60 s para pedido temporal, 6 h nos demais. `fetched_at` original acompanha o reuso; cache stale exige nova leitura.

Chave de URL usa a canonicalização existente. Alias nasce apenas do destino final validado pelo leitor real; `<link rel=canonical>` não confiável não é usado. Parâmetros significativos e versões são preservados. Primeiro encontro de dois aliases ainda desconhecidos pode consumir dois slots; os seguintes podem reutilizar o documento.

Identidade D combina hash exato da extração limitada, título, idioma e marcas de versão. `duplicate_of` não apaga fontes; duas URLs podem manter vínculos e não contar como duas confirmações independentes. Não há fusão por título, similaridade aproximada ou fonte de usuário diferente. Não é um deduplicador universal de HTML completo.

Cache opcional limitado a 60.000 unidades do encoder JSON por registro; exceder o limite não trunca evidência nem falha o job. Limpeza incremental de até 100 entradas documentais vencidas; excluir job/conta limpa apenas o escopo autorizado. Reuso tem custo SQLite: WEG no replay textual passou de 655.360 para 827.392 bytes de banco. Não alegar redução de armazenamento ou RAM.

Ledger: `research.py:781` escopo; `:791` leitura; `:806` gravação. Testes de owner, versão, expiração, redirect, exclusão e confirmação independente em `tests/test_retrieval_efficiency_v5997.py`.
