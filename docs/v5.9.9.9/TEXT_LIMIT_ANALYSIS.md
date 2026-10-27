# Limites reais — V5.9.9.9

Base 8ccbbe0. Informação tardia Nikon já estava nos bytes públicos disponíveis; nenhum novo download necessário no replay.

| Etapa | Limite/contrato observado |
|---|---|
| Rede | research.MAX_PAGINA_BYTES 2 MiB; bytes comprimidos e expandidos verificados; redirects limitados e revalidados |
| Parser HTML | web_extract.MAX_HTML 2 Mi caracteres sobre HTML já recebido; não é permissão para baixar mais bytes |
| Texto disponível | melhor bloco/artigo extraído transiente; Nikon 12.375 caracteres |
| Perda anterior | extrair_pagina: texto_art[:teto] ou melhor_trecho(entity,teto), teto=8.000, ANTES de gerar passagens |
| Estrutura anterior | secoes: primeiras 12; texto por seção 4.000; _paragrafos: cada bloco 1.200 |
| Nova análise | percorre estrutura e gaps do texto já disponível; heaps de até 8 candidatos por requisito, até 8 requisitos; saída até 8 janelas e 8.000 caracteres, sem novo fetch |
| Passagens | ≤1.100 caracteres cada; saída preserva fronteiras não contíguas; offsets próprios e offsets da extração normalizada com SHA |
| Coverage | no máximo 40 candidatos/fonte, 32 vínculos públicos; seleção final até 8 com diversidade de requisito |
| Grafo | passagens selecionadas até 8, nós de seção no tipo document existente; relação REQUIRES_VERIFICATION mantida |
| Síntese | trecho de cada fonte até 1.800 caracteres; contexto não ampliado |
| Card | trecho até 300 caracteres; contexto de até duas seções reais, detalhes existentes |
| PDF | caminho existente até 12 páginas/8.000 caracteres; esta correção HTML NÃO afirma leitura completa de PDF |

A primeira perda confirmada Nikon era a janela textual inicial, não o download. No pipeline corrigido as linhas da tabela são recuperadas, classificadas como parciais e retidas. Informação além do orçamento de rede permanece inacessível: erro de tamanho não equivale a página lida. O trace preserva erro observado e contadores; não inventa uma posição de conteúdo não baixado.

Offsets source_span referem-se a _normalizar(texto do extrator escolhido), não ao HTML. text_span refere-se à saída compacta. source_sha256 identifica a representação; não se guarda outra versão integral no cache. Cache mantém owner/job/query e nova versão 5.9.9.9.
