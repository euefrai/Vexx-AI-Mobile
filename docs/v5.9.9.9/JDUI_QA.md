# JDUI e acessibilidade

Sem reconstrução visual. Cards acrescentam contexto de até duas seções/headings reais pelo componente sources existente; parcial/direto permanece explícito. Nikon mostra “Suporte parcial: Peso e unidade, Bateria” e “Nikon Z f Digital Camera”. Card mantém um trecho compacto; todas as passagens ficam no registro, não se declara que o card mostra cada valor integralmente.

Chrome emulado 1280/390/320: tabela de cobertura dentro da raiz, sem overflow; ordenação por Enter, CSV, readonly, reduced motion, reload idêntico. Zoom CSS 200%: rolagem horizontal interna observada. Não é zoom nativo nem dispositivo físico.

Galeria: imagens carregadas, ArrowRight muda item, Escape fecha; erro de imagem injetado mostrou fallback e recuperação. Primeira verificação de retorno de foco deu false. Repetição instrumentada deu true, botão conectado/visível e ativo. Causa intermitente não reproduzida; **pendência explícita**, sem patch especulativo nem garantia de foco perfeito.

Exportações MD/CSV concluídas; IndexedDB com mensagens estruturadas/resultados. Links públicos Nikon abriram destino correto. page_errors=[] nos fluxos observados, excetuando erros de rede deliberadamente injetados e falha de configuração inicial do harness.

Screenshots de cards 320/1280 inspecionados; demais geometria e capturas em qa-artifacts/v5999. source-card 320/1280 e diálogo da galeria também foram inspecionados; geometria 390 foi verificada. O primeiro seletor de conversa falhou por usar título não truncado; foi corrigido no script QA e a verificação concluída. Resultados parciais não equivalem a pesquisa completa aprovada.
