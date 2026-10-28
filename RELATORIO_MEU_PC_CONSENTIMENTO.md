# Meu PC — interface por aparelho e autorização local

Data: 27/10/2026. Base: `1cd7589`, branch `codex/v598-autonomous-research`.

## Resultado implementado

- Computador: preparação do agente, nome real do PC conectado, guia de dependências, **Permitir acesso pelo celular** e **Revogar acesso**. A tela de controle fica oculta e não há captura automática.
- Celular/tablet: **Conectar**, tela, toque/clique esquerdo, toque longo/clique direito, movimento do ponteiro, texto, Enter, Backspace, rolagem e tela cheia quando suportada.
- Detecção por sinais do dispositivo/navegador, incluindo iPad. Largura continua definindo responsividade; não define autorização. Redimensionar o PC mantém a experiência de preparação.
- A confirmação no Windows identifica a conta, o hostname e um código. O agente salva a aprovação por conta no SQLite. Aparelhos/sessões da mesma conta usam essa aprovação; outras contas continuam sem acesso.
- Tela limpa, conexão explícita, estado de autorização legível, instruções compactas após permitir e guia sem estilos inline incompatíveis com a CSP.

## Problemas corrigidos

| Problema | Correção |
|---|---|
| Mesmos controles em PC e celular | Apresentação separada com preparação no PC |
| Controle dependia de variável de ambiente e grant manual | Confirmação local por conta; modo legado preservado |
| Risco de o controle remoto clicar na confirmação | Bloqueio de toda entrada remota enquanto o diálogo existir |
| Revogação durante um pedido poderia ser seguida de aprovação tardia | Invalidação do pedido; prazo de 120 segundos; resposta tardia descartada |
| Permissão local poderia contornar o administrador | Gate `users.remote_ok` e estado da conta continuam sendo verificados |
| Botões esquerdo/direito invertidos no Windows | Flags do mouse corrigidas e testadas |
| Coordenadas do frame incluíam barras da imagem | Cálculo pela área efetiva da imagem; toques nas barras descartados |
| Teclado podia enviar Unicode truncado para emoji | Unidades UTF-16 preservadas; falha de SendInput reportada |
| Rajadas de movimentos/teclas excediam os limites | Fila limitada, texto agregado, compactação de movimentos e ritmo de 550 ms |
| Tela podia permanecer visível após sair | Abort de captura, limpeza de imagem/fila em desconexão, navegação, troca de conta e perda de visibilidade/conectividade |
| Preparação sem orientação de dependências | Guia `/remote-setup.html`, comando com o Python do agente e limitações explícitas |

## Segurança e persistência

`remote_access.py` cria `remote_bindings(owner_id, enabled, updated_at)` por migração aditiva no banco do agente. Não há exclusão de mensagens, contas ou dados reais. A confirmação roda em thread separada, com conexão SQLite própria e fechamento explícito.

O navegador somente solicita a confirmação. Não existe endpoint de aprovação. Login, CSRF/origem, verificação de sessão, dono derivado da sessão, gate do agente, validação de comandos e limites existentes continuam ativos. A API ignora tentativas de indicar outro `owner` ou enviar `approved` no corpo. Uma confirmação por vez e limite global no agente reduzem abuso de diálogos.

O Windows usa [MessageBoxW](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-messageboxw), Sim/Não, com Não como botão padrão. Falha, recusa, expiração, conta excluída/bloqueada ou revogação não concedem acesso. Enquanto o diálogo continuar aberto, o controle permanece pausado, mesmo após expirar o pedido; é necessário fechá-lo no PC.

## Arquivos alterados/criados

- `remote_access.py`: consentimento nativo, limites, isolamento e aprovação persistente por conta.
- `pc_agent.py`: migração, novos comandos e gates de captura/entrada.
- `remoto.py`: grant validado pelo agente, flags de clique e Unicode/SendInput.
- `server.py`: status, solicitação e revogação com sessão/CSRF/limites.
- `public/remote.js`: detecção, estados, captura, controles, fila e cancelamento.
- `public/app.js`: integração com navegação, sessão e conectividade; retirada do bloco remoto antigo.
- `public/index.html`, `public/interface.css`: preparação no PC, conexão no celular e layout responsivo.
- `public/remote-setup.html`: instalação/atualização e uso, sem expor segredo do agente.
- `public/sw.js`: shell atualizado com os novos recursos.
- `tests/test_remote_access.py`: testes de consentimento, sessões, isolamento, revogação, Unicode e geometria.
- `tools/qa_remote_ui.cjs`: QA de navegador com API e tela explicitamente simuladas.
- `README.md`, `docs/REMOTO_ANYDESK.md`: fluxo, protocolo e limites atualizados.

## Validação executada

- Focados: **51 aprovados**, 1 aviso, em `qa-artifacts/remote-access-focused-final.log`.
- Consentimento após fechamento explícito da conexão SQLite: **21 aprovados**, em `qa-artifacts/remote-access-consent-final.log`.
- Integração com relay ASGI/WebSocket e SQLite reais: duas sessões com login na mesma conta compartilham acesso; outra conta recebe 403; revogação em uma sessão bloqueia tela e entrada na outra. Confirmação nativa e entrada/captura dessa integração são simuladas.
- Teste separado `test_captura_jpeg_real`: captura JPEG executada no Windows, sem exportar a tela do operador nos artefatos públicos.
- Chrome real, APIs/tela simuladas: **14 verificações aprovadas**, incluindo preparação no desktop, código de confirmação, redimensionamento, celular emulado, conexão explícita, um clique por toque, Unicode, 390/320 px sem overflow, desconexão, reload e revogação. Nenhum erro de browser no percurso instrumentado.
- Guia carregado com as políticas reais do servidor: estilo externo aplicado, sem overflow nem erros de CSP.
- `node --check` em app/remote/service worker; `py_compile` nos módulos Python alterados; `git diff --check`.
- Suíte completa final: **1.825 aprovados, 4 ignorados, 2 avisos**, em 361,57 s, exit 0. Log: `qa-artifacts/remote-access-full-final.log`; marcador: `remote-access-full-final.exit`. Avisos existentes de depreciação de mss e timeout do TestClient.

Artefatos visuais e resultados: `output/playwright/remote-access/desktop.png`, `phone-ready.png`, `phone-connected-390.png`, `phone-connected-320.png`, `phone-revoked.png`, `ui-summary.json` e `guide-summary.json`. As imagens do controlador identificam a tela como simulada. Não são evidência de celular físico ou transmissão em produção.

## Limitações e próximo passo operacional

- Esta entrega está local. Não houve push, deploy ou reinício do PC Agent de produção neste trabalho.
- Para disponibilizar, publique site e agente compatíveis e atualize/reinicie o agente pelo procedimento controlado da instalação. Um agente antigo não responde aos novos comandos; a interface orienta a atualização.
- O relay continua aceitando **um PC Agent por instalação**. A conta autoriza acesso a esse PC. Fazer login em outro computador não o cadastra como novo agente. Não há instalador universal ou cadastro de vários PCs nesta entrega.
- Transmissão por JPEG a cada 1,6 s, acrescida da latência, não vídeo contínuo. Sem áudio, multi-monitor, arrastar arquivos/janelas, atalhos de múltiplas teclas ou controle de UAC/tela bloqueada.
- **Pendente:** confirmação humana no Windows e uso ponta a ponta de mouse/teclado em uma aplicação real a partir de um celular físico, incluindo teclado virtual Android/iOS, rede móvel, retorno do segundo plano e tela cheia onde disponível. Não declarar essa validação a partir dos testes simulados.
- O mecanismo legado de grants foi preservado; o bloqueio por revogação explícita de pareamento tem precedência sobre ele.

Não foram alterados a extensão Júlia, o Fajulto Studio, a identidade Lucas, a pesquisa, o chat ou os dados reais de usuários.
