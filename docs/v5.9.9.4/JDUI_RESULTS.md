# JDUI e Chrome

Mantida a interface atual. Cards de fonte distinguem aspectos com passagem e
suporte parcial. Tabela compacta readonly usa Parcial para requisito incompleto.
Seleção preserva vínculos de múltiplos requisitos e passagens literais.

Chrome real, beab357: resultados de pesquisas sem fontes, cancelamento, SSE e
reload; entrega controlada de duas páginas públicas MDN com cards/links reais.
Os links abriram MDN em nova aba; não são duas fontes independentes.

Viewport/root/largura da mensagem: 1280/1280/760; 390/390/350; 320/320/288.
Sem overflow do documento. No zoom CSS 200%, área lógica 110 px/conteúdo224 px,
scroll local114 px; capturas dos dois lados inspecionadas, palavras legíveis.
Também inspecionadas as capturas de cards em desktop e 320 px.

Ordenação por Enter, CSV baixado, zero controles de edição no readonly,
reduced-motion, reload da tabela e IndexedDB (10 mensagens após a entrega)
verificados. Page errors dos fluxos: []. Console inicial tinha401 esperado
antes do login e avisos existentes de senha fora de form.

Rede offline: fetch real rejeitado; reconexão /api/health200. Esse negativo de
transporte não certifica todos os estados offline da interface.

Falhas do harness preservadas: referência de snapshot expirada e screenshot
da mensagem inteira sem mostrar a tabela. O teste foi refeito com localizador
semântico e screenshot do card; imagens antigas não comprovam legibilidade.

Limites: não certifica telefone físico, zoom nativo, todos os modais/teclas,
comparação no chat ou auditoria WCAG completa. Não chamar render de fixture de
pesquisa autônoma concluída. UI executada antes das correções causais/DOM;
novas verificações finais devem ser registradas separadamente.

Verificação final com a91c113: novo runtime descartável, pesquisa parcial
autenticada e nova entrega de documento público com discovery controlada.
visual-order-final.log repete geometria,200%,teclado,CSV,reload e reduced-motion;
IndexedDB do novo runtime com4 mensagens. Links e negativo de rede repetidos
em source-interactions-order-final.log. Cards finais inspecionados novamente.
O JSON direct-delivery.json contém a última execução; os logs/JSON de UI
anteriores continuam separados. O helper foi protegido contra sobrescrita.
