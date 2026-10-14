# JÚLIA MOBILE 4.1.5 — Minimal Premium UI

## Identidade Visual

Tokens reais em `:root` (`public/styles.css`): `--bg #0b0b0f`,
`--surface-1 #101016`, `--surface-2 #15151d`, `--accent #a78bfa`,
`--text-1 #f4f2fa`, `--text-2 #a7a5bd`, `--text-3 #6d6c85`,
`--border-subtle rgba(255,255,255,.06)`, raios 8/12/18px, `z-pop 60`,
transições 150/220ms com `--ease`, `prefers-reduced-motion` herdado.

## Princípios

1. **Minimalismo no chat** — prioridade absoluta. Sem bordas excessivas,
   sem cards gigantes para mensagens de texto comuns, sem indicadores
   técnicos permanentes na conversa.
2. Outras telas (login, admin, perfil) podem ter efeitos mais ricos,
   mas sempre suaves e consistentes.
3. Sem neon exagerado, sem excesso de gradientes na conversa.
4. Cantos arredondados, bordas discretas, espaçamento equilibrado.
5. Respeitar `prefers-reduced-motion`.

## Componentes

- **Button** — padding 8px 16px, radius 12px, transição 120ms.
- **Input** — border-bottom, foco violeta, sem label flutuante fixa.
- **Modal / Dialog** — backdrop blur, entrada em 200ms.
- **Popover / Dropdown** — position: absolute, z-index 1000.
- **Drawer** — slide-in lateral, 320px mobile, 400px desktop.
- **Toast** — canto inferior direito, auto-dismiss 4s.
- **Empty State** — ícone discreto + texto.
- **Loading State** — skeleton shimmer.
- **Status Indicator** — dot 6px, cor por estado.
- **User Avatar** — 32px, fallback por inicial.
- **Data Table** — sticky header, hover #1e1e1e.
- **Form Field** — label + input, erro inline.

## Animações

| Tipo               | Duração |
|--------------------|---------|
| Interações comuns  | 120–240ms |
| Entrada de cards   | 240ms     |
| Transição de página| 320ms     |
| Hover / foco       | 120ms     |

## Layout Mobile-First

### Header
- Abrir menu (hambúrguer)
- Título curto da conversa (truncado)
- Novo chat / menu contextual

### Área de Mensagens
- Mensagens com boa tipografia (16px base)
- Espaçamento confortável (1.5x lineHeight)
- Markdown com código estilizado (background #1a1a1a, radius 6px)
- Bolhas de usuário compactas (max-width 80%)
- Conteúdo de IA ocupa largura útil naturaleza
- Rolagem suave, sem saltos de layout

### Campo de Digitação
- Composer flutuante, bottom-safe-area
- Botão anexar (esquerda)
- Campo expansível (central)
- Botão enviar (direita)
- Botão interromper quando gerando

### Ações Contextuais
- Implementadas no menu `···` por mensagem: Copiar, Regenerar, Continuar
  (última resposta), Tentar novamente (falha). Sem hover: toque abre o menu.
- Editar/compartilhar/avaliar: AUSENTES (sem botão decorativo).
