# Console administrativo local

`/admin` no composer é interceptado antes de salvar mensagem ou chamar IA. A página reutiliza `/api/login` e a sessão existente. O HTML é um shell público; dados operacionais exigem autorização nas APIs. Não há senha mestra, novo banco de usuários ou segredo no JavaScript.

Cada chamada exige sessão válida e conta admin ativa/aprovada, verificada novamente no PC. Reautenticação usa a senha atual, scrypt no fluxo normal e Argon2 no legado. O proprietário legado passa a ter o sid da sessão registrado no `user_sessions` existente após confirmação, permitindo revogação. Tentativas são limitadas; role enviada pelo cliente não concede acesso.

O grant adicional dura 10 minutos, é assinado e vinculado à sessão e à revisão de segurança. Cookie HttpOnly, SameSite Strict, Secure em produção e path `/api/admin`. Atualizar a tela não prolonga sua validade. POST exige CSRF e validação de origem; bloqueio, rebaixamento, reprovação, senha e revogação invalidam acesso. Bloquear console limpa os dados renderizados e o grant.

As seis abas exibem agregados reais: visão geral, PC Agents, usuários, pesquisas, modelos/fontes e auditoria. Não carregam conteúdo de chats privados, senhas, hashes, tokens ou detalhes antigos de auditoria potencialmente sensíveis. Admin não habilita controle remoto nem ultrapassa ownership das conversas. Métricas sem amostra aparecem indisponíveis; modelo configurado não é inferência validada, CPU acumulada não é porcentagem instantânea, ausência de pesquisas não vira 0/0.

Alterações sensíveis reutilizam endpoints existentes, com confirmação digitada do username. Botões protegem o próprio papel/status e o proprietário na UI. O backend serializa alteração de papel, bloqueio e exclusão para preservar o último admin ativo/aprovado mesmo sob concorrência. Não foi criada política nova que torne o proprietário absolutamente imutável em todos os endpoints legados.

QA em Chrome real: login, reauth, reload, seis abas, teclado, 1280/390/320 px, zoom CSS 200%, tabela com rolagem interna, conteúdo XSS tratado como texto, limites confirmados, cancelamento de modal, `/admin` sem gravação nem chamada de IA e bloqueio explícito. Zero alertas/erros JavaScript capturados. Houve 401 esperado antes do login e avisos DOM preexistentes de campos de senha no chat.

Testes HTTP/SQLite cobrem sessão expirada/revogada, role/status/aprovação, vínculo de grant, CSRF/origem, throttling, legado, cookie Secure, isolamento e permissões remotas. Esses resultados não equivalem a pentest externo.

O console e sua proteção adicional estão somente no worktree local. Não houve push/deploy. O servidor publicado V597 continua com seu fluxo administrativo anterior até publicação futura explicitamente autorizada.
