# V5.9.7 — JDUI

## Implementação

- Os painéis reais usam o contexto JDUI existente, incluindo IndexedDB e sincronização de estado. Namespace por owner e job, sem apagar o cache do chat ao carregar uma pesquisa.
- As respostas assíncronas são conferidas contra usuário, geração de armazenamento, requisição e pesquisa ativa. Resposta atrasada não substitui painel novo.
- Expansão de publicação usa URL/DOI/título estável, em vez da posição da fonte. Evidências persistem expansão por afirmação.
- Tabelas de pesquisa mantêm colunas legíveis e rolagem horizontal interna no celular.

## Provas executadas

`tools/verify_research_ui_v597.cjs`: quatro contratos assíncronos com funções reais do app e API controlada: corrida entre pesquisas, mudança de job, troca de owner e estado isolado/salvamento obsoleto. Não é browser autenticado.

Chrome real via Playwright, servidor local `tools/preview_research_v597.py`: componentes e funções reais de persistência IndexedDB, com capturas externas públicas. Comparação usa os PDFs capturados na V5.9.6; documentação usa captura nova V5.9.7. Não foi executado login do aplicativo nesse harness.

- Proveniência aberta por clique, recarga, troca owner-a → owner-b → owner-a: estado restaurado apenas para o dono.
- Troca entre pesquisas preservou detalhes. IndexedDB real confirmou chave e owner; fila de persistência esvaziada.
- Desktop 1.280 px e mobile emulado 320 px sem overflow da página. Em 320 px: documento 320, tabela com viewport 296 e conteúdo 565 px; rolagem interna exercitada.
- Zoom CSS 200% sem overflow horizontal da página; não representa zoom nativo ou celular físico.
- Zero fallback de renderização; console sem erros/avisos no escopo observado.

Artefatos: `ui-*.log`, `mobile-320.png`, `mobile-final.png`. CSV, galeria, links e vídeo estruturado mantêm os componentes anteriores e cobertura automatizada; não foram apresentados como novos testes de vídeo assistido, download ou app autenticado nesta rodada.
