# JDUI e navegação — evidência executada

Componentes existentes exibem a seção recolhível “O que ainda falta confirmar”, com contagens de publicações e ressalva sobre o alcance da extração. Chaves estáveis por tipo preservam estado quando a seção entra/sai; há compatibilidade com chaves anteriores. Conversas normais mantêm o comportamento anterior.

Mensagens com job real oferecem Ver pesquisa. A restauração de histórico não reanexa jobs terminais. Verificações assíncronas conferem usuário, época de autenticação e conversa antes de aplicar estado; cache limitado a 128 entradas. Retomada explícita usa mensagem nova e consulta atualizada.

## Chrome real, harness local de componentes

- Larguras 1280, 390 e 320 px: sem overflow da página ou fallback JDUI; zoom CSS de 200% também verificado.
- Tabela em 320 px: página 320, região 296, conteúdo 565, rolagem horizontal 269 px, sem ampliar a página.
- Expansão de lacunas persistiu após reload e ficou isolada entre usuários de teste.
- CSV realmente baixado e lido; cinco imagens públicas carregaram; imagem do modal carregou e Escape fechou.
- Console final: zero erros e avisos. Servidor temporário e Chrome de QA encerrados.

O harness usa componentes reais, IndexedDB e funções reais de Markdown/download; dados são replay público e fixture identificada. Não é teste autenticado da V5.9.8, aparelho físico ou zoom nativo. MD/JSON protegidos foram cobertos por testes de backend, sem simular APIs no harness. Screenshots finais: qa-artifacts/v598/development/explorer-{1280,390,320}.png. Capturas anteriores gaps-* são diagnósticas e não representam a aceitação final.

A sessão real do aplicativo foi testada separadamente em produção no runtime antigo: seis perguntas e reload de 12 mensagens. Não houve validação visual autenticada da V5.9.8 nas três larguras.
