# V5.9.6 — JDUI e Chrome

Componentes existentes refinados: galeria responsiva com proporção preservada, crédito/dimensões/licença quando presentes, miniatura separada do original, fontes com leitura explícita e proveniência recolhível. Fonte encontrada, trecho lido, leitura parcial e indisponibilidade não ganham selo de verificação. Composição prioriza mídia/fontes/evidências conforme intenção; layout genérico legado preservado. Comparação bibliográfica só usa publicações recuperadas.

Corrigido bug real nos dois painéis de pesquisa em `public/app.js`: faltava o callback `download` ao montar JDUI, deixando “Baixar CSV” sem ação. Agora usa `downloadFile`, como o chat. A sanitização CSV existente contra fórmulas foi preservada. Não houve redesign geral do chat.

## Executado

- Chrome real local, Playwright CLI, componentes de produção e capturas externas reais. Servidor isolado temporário: nenhuma sessão, conta, chave ou banco real servido. Script `tools/preview_v596_research.py`.
- Desktop 1280, mobile 390/320 e CSS zoom 200%: screenshots inspecionadas; largura do documento igual à viewport nas medições. Cinco miniaturas com `naturalWidth=960` no primeiro teste; arquivo original aberto no zoom. Proporções preservadas.
- Abrir imagem e Escape; link da página original abriu aba no Commons. Proveniência foi expandida e restaurada após reload com armazenamento fornecido pelo harness. Isso não prova persistência das expansões nos painéis de produção, que permanece uma limitação de UI.
- Tabela de duas publicações reais renderizada; CSV efetivamente baixado, `comparison-browser.csv`. Campos experimentais ausentes não preenchidos.
- Falha de rede injetada para miniaturas reais mostrou quatro fallbacks observados. Não são mídias fictícias nem prova de indisponibilidade das fontes. Interceptação removida ao fim.
- EventSource recebeu replay explícito de eventos capturados e cancelamento interrompeu a reprodução. **Não é cancelamento de pesquisa em produção.** SSE/cancelamento/reload/checkpoints de jobs reais são cobertos separadamente pela suíte Python.
- Foco por teclado chegou ao seletor; detalhes nativos e links mantêm interação acessível. Não houve auditoria completa com leitor de tela/contraste automatizado.

Evidências: `browser-interactions.json`, `ui-gallery-metrics.log`, `browser-screenshots.log`, `jdui-*.png`, snapshots e scripts em `qa-artifacts/v596/`. Erros de rede deliberados fazem parte do cenário de fallback; não declarar console inteiramente limpo.

## Limites

Não foi teste autenticado do aplicativo inteiro. Markdown principal, permissões/API, sync, SSE e exportação autenticada dependem dos testes reais existentes do backend/contratos; a fixture de Chrome foca componentes e usa seu próprio contexto de download/storage. Não foi aprovado playback/transcrição/análise de vídeo real, pois nenhum vídeo pertinente foi recuperado. Nenhum card foi criado para simular esse sucesso.

A comparação científica não mostra mais uma galeria separada para links de referências não lidas quando as publicações recuperadas já estão nos SourceCards. Metadados permanecem no job/exportação; é refinamento de composição, sem apagar evidência.
