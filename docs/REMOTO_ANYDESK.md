# Meu PC — preparação no computador e controle no celular

## Fluxo

1. Atualize site e PC Agent juntos. No Windows do agente, entre na conta e abra **Meu PC**.
2. Clique **Permitir acesso pelo celular**. Confira hostname, conta e código na janela do Windows. Confirme em até 120 segundos.
3. No celular, entre na mesma conta, abra **Meu PC** e toque **Conectar**.
4. **Desconectar** encerra a visualização neste aparelho. **Revogar acesso** retira a autorização da conta no agente, inclusive em outras sessões.

A escolha da interface usa sinais do navegador/dispositivo (incluindo iPad), independentemente da largura. É uma heurística de apresentação, nunca uma decisão de segurança. Redimensionar o PC não o transforma em controlador. No desktop não há captura automática da própria tela.

## Dependências e instalação

Windows com sessão interativa aberta, Python do agente e Pillow; mss é opcional, com fallback ImageGrab. O guia `/remote-setup.html` fornece o comando das dependências e orientações de atualização. O site não instala software silenciosamente nem recebe o segredo do agente.

O relay comporta **um PC Agent por instalação**. Um usuário pode autorizar sua conta nesse PC com confirmação física; entrar no site em outro computador não registra automaticamente outro agente. Instalador, pareamento de múltiplos PCs e seleção de máquinas exigem evolução da arquitetura.

## Autorização e segurança

- O browser solicita autorização; não pode concedê-la por API. O agente abre `MessageBoxW` (Sim/Não, Não como padrão), indicando conta, máquina e código. [Referência Microsoft](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-messageboxw).
- O diálogo roda fora do loop do relay e não bloqueia chat/pesquisa.
- Enquanto existir diálogo, **toda entrada remota é bloqueada**, inclusive grants legados. Isso impede confirmar o próprio pedido por mouse/teclado remoto.
- Uma confirmação por vez, 3 solicitações por 10 minutos no agente, mais limites no relay. Após expirar, é necessário fechar o diálogo antigo; uma resposta tardia nunca concede acesso.
- `remote_bindings(owner_id, enabled, updated_at)` permanece no SQLite do PC. A confirmação atualiza também `users.remote_ok`, preservando a revogação pelo administrador. Conta bloqueada/excluída não obtém acesso.
- Revogar invalida o pedido pendente e prevalece sobre grants legados, inclusive para `local`. Um Sim tardio não restaura a autorização revogada.
- Endpoints exigem sessão + CSRF + verificação de revogação; o dono vem da sessão, nunca do JSON enviado pelo browser. Outra conta não recebe o código nem a tela.
- Grants legados continuam funcionando; `JULIA_REMOTE=1` é necessário apenas para entrada legada, sem pareamento local. A autorização local permite entrada **somente para a conta aprovada**.
- O cliente aborta capturas, limpa a imagem e esvazia comandos ao desconectar, sair da página/conta ou perder conectividade. Eventos de visibilidade interrompem a transmissão.

## Protocolo

| Rota | Função |
|---|---|
| GET `/api/remote/status` | Capacidades e autorização da conta; com CSRF |
| POST `/api/remote/request` | Solicita confirmação local, nunca aceita dono/permissão do navegador |
| POST `/api/remote/revoke` | Revoga a conta e invalida pedido pendente |
| GET `/api/screen` | JPEG autenticado, até 960 px, com CSRF e autorização |
| POST `/api/input` | Mouse/teclado autenticado e validado no agente |

## Controles

| Gesto/botão | Ação |
|---|---|
| Toque | Clique esquerdo |
| Segurar 600 ms | Clique direito |
| Arrastar | Mover ponteiro, sem arrastar arquivos/janelas |
| Teclado | Texto Unicode, incluindo pares UTF-16 para emojis |
| Rolar ↑/↓ | Rolagem vertical |
| Enter / Apagar | Enter / Backspace |
| Atualizar | Captura adicional sem requisições sobrepostas |
| Tela cheia | Amplia quando suportado; botão de saída sobre a imagem |

Fila limitada, texto agregado, movimentos consecutivos compactados e espaçamento mínimo de 550 ms para respeitar 120 comandos/minuto. Coordenadas consideram as faixas vazias da imagem em tela cheia; toques nelas não viram comandos.

## Limites reais

JPEG periódico, intervalo de 1,6 s acrescido da latência/captura, **não vídeo contínuo**. Somente monitor principal; sem áudio, multi-monitor, arrastar arquivos/janelas, atalhos de múltiplas teclas ou controle de UAC/tela bloqueada. A janela alvo pode recusar entrada pelo nível de integridade do Windows. Falha de SendInput na digitação é reportada.

O QA cobre relay/SQLite/sessões com consentimento e entrada simulados, captura JPEG real em teste separado e Chrome com celular emulado. **Celular físico, confirmação humana nativa e o percurso completo de controle de uma aplicação real ainda exigem validação operacional.**
