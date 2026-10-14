# Controle remoto — tela ao vivo + mouse/teclado (MVP honesto)

A aba **Meu PC** mostra a tela real do computador (~2 fps, JPEG 800px) e envia
toque/teclado de verdade. Não é vídeo 30 fps nem WebRTC — é polling simples e
confiável sobre o WSS já existente.

## Como ativa

```powershell
$env:JULIA_REMOTE="1"   # sem isso: somente visualização
python pc_agent.py
```

O agente avisa no log quando o controle está ATIVO. Cada comando executado é
registrado (`remoto: click executado` etc.).

## Gestos no celular

| Gesto | Ação no PC |
|---|---|
| Toque | Clique esquerdo |
| Segurar 600ms | Botão direito |
| Arrastar | Mover o mouse |
| Botão Teclado | Abre o teclado do celular; digita no PC (Unicode real) |
| Atualizar | Força um frame |

Texto e teclas nomeadas (enter, backspace, setas...) via `POST /api/input`;
tudo exige login + CSRF, validado no relay e de novo no agente.

## Segurança

- Padrão **desativado** (`JULIA_REMOTE` ausente = `input` recusado com
  `desativado`, e o app avisa na tela).
- Coordenadas normalizadas 0..1 com clamp; texto até 200 chars; teclas por
  allowlist; rate limit (1/50ms, 120/min).
- Sem execução de terminal/arquivos — só eventos de mouse/teclado.
- Nenhum byte de tela ou comando passa sem sessão autenticada.

## Limites do MVP

~2 fps (captura + JPEG levam ~0,3s); sem áudio, sem arrastar-arquivos,
sem multi-monitor (tela principal); acentos via Unicode OK; `Ctrl+Alt+Del`
é interceptado pelo Windows (limite do SO). WebRTC ficaria para fase futura.
