# JÚLIA MOBILE 4.1.5 — Minimal Premium UI

## Identidade Visual

| Token          | Valor         |
|----------------|---------------|
| preto          | `#000000`     |
| grafite        | `#121212`     |
| roxo           | `#5e4ae3`     |
| violeta suave  | `#7a6fb8`     |
| superfície     | `#1e1e1e`     |
| borda          | `rgba(255,255,255,0.08)` |
| texto primário  | `#ffffff`     |
| texto secundário| `#999999`     |

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
- Copiar, regenerar, continuar, editar, compartilhar, avaliar
- Ações secundárias em menus contextuais
- Acesso por toque no mobile (sem hover)
