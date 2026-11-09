# Manual Operacional do Instagram Web — VEXX AI Architecture & Vision

Este documento detalha o funcionamento completo da interface Web do Instagram para o VEXX AI, servindo de base de conhecimento para automações visuais, leitura por visão computacional, navegação orgânica e execução de comandos táticos.

---

## 1. Topografia de Layout do Instagram Web

O Instagram Web opera como uma Single Page Application (SPA) responsiva com três regiões principais em desktops/notebooks:

```
+---------------------------------------------------------------------------------------------------+
| [Barra de Guias do Navegador: "(7) Instagram • Mensagens" | URL: https://www.instagram.com/...  ] |
+-------+----------------------------------+--------------------------------------------------------+
|       | Painel Lateral / Gaveta Direct   | Área Central / Stream de Chat / Feed                   |
| S     | (Largura: ~380px)                |                                                        |
| I     |----------------------------------+--------------------------------------------------------|
| D     | [eu.efrai v]        [(+) Mensagem| [Avatar] Gustavo Oliveira   [Online agora] [📞] [📹] [ℹ️] |
| E     | [🔍 Pesquisar...]                |--------------------------------------------------------|
| B     |----------------------------------|                                                        |
| A     | Notas: (êfrai) (Andressa) (Marii)|   [Bolha Cinza - Recebida]                             |
| R     |----------------------------------|   Gustavo enviou um anexo. · 58 min                    |
|       | Abas: [Mensagens] [Pedidos]      |                                                        |
| (Logo)|----------------------------------|                                                        |
| [Home]| • Meta AI                        |                          [Bolha Azul - Enviada]        |
| [🔍]  |   Eai! Tudo tranquilo por aqui...|                          Beleza, já estou olhando!     |
| [🧭]  | • Gustavo Oliveira (🔵 Não Lida) |                                                        |
| [🎬]  |   Gustavo enviou um anexo.       |                                                        |
| [💬🔴]| • wzz (🔵 Não Lida)              |--------------------------------------------------------|
| [❤️]  |   3 new messages                 | [😀 Emoji] [Mensagem...              ] [🎤] [🖼️] [❤️]   |
+-------+----------------------------------+--------------------------------------------------------+
```

---

## 2. Mapa de Rotas e Acesso Direto

| Recurso | URL Canônica | Finalidade / Elementos |
|---|---|---|
| **Feed Principal** | `https://www.instagram.com/` | Linha do tempo, stories horizontais no topo, posts. |
| **Direct Inbox** | `https://www.instagram.com/direct/inbox/` | Caixa de entrada completa, lista de conversas, badge com contagem. |
| **Conversa Direta** | `https://www.instagram.com/direct/t/{id}/` | Chat direto com pessoa ou grupo. |
| **Explorar** | `https://www.instagram.com/explore/` | Grade de conteúdos virais, tendências, categorias. |
| **Perfil** | `https://www.instagram.com/{username}/` | Biografia, número de seguidores, posts, botão de mensagem/seguir. |

---

## 3. Elementos do Direct e Indicadores Visuais

### 3.1 Badges de Notificação e Mensagens Pendentes
1. **Título da Aba do Navegador:** O Instagram exibe a contagem exata de mensagens não lidas no título da aba em formato numérico entre parênteses: `(7) Instagram • Mensagens`.
2. **Ícone do Direct na Sidebar:** Um círculo vermelho com o número de mensagens (`mask_red`: `R > 120, R - G > 50, R - B > 50`) aparece sobre o ícone de balão do Direct.
3. **Bolinhas Azuis de Mensagem Não Lida:** Ao lado direito de cada conversa na lista (`x ≈ 325px`), o Instagram renderiza um indicador azul vibrante (`mask_blue`: `B > 80, B - R > 35, B - G > 25`).

### 3.2 Status de Presença e Atividade
O Instagram mostra o status em duas áreas:
- **No card da lista:** Sob o nome do usuário pode aparecer `"Online agora"` ou `"Online há X min"`.
- **No cabeçalho da conversa aberta:** Logo abaixo do nome do contato, no topo da tela à direita, com os textos:
  - `Online agora` (indica atividade em tempo real).
  - `Online há 1 min` / `Ativo(a) há 2 h` (indica última vez visto).
  - `Visto por último hoje às 14:10`.

---

## 4. Protocolo de Ações do VEXX AI

### 4.1 Foco de Janela e Ativação
Antes de executar qualquer clique ou leitura, o VEXX AI traz a janela do navegador padrão (Brave, Chrome, etc.) para o primeiro plano via `WScript.Shell.AppActivate('Instagram')`.

### 4.2 Rolagem Tática (Scroll Orgânico)
- **Rolagem da Lista de Conversas:** O cursor se move até `x ≈ 20%` da largura da tela e rola para baixo com `pyautogui.scroll(-350)` para revelar mensagens antigas ou ocultas.
- **Rolagem do Histórico de Mensagens:** O cursor se posiciona em `x ≈ 65%` e rola para cima (`scroll(400)`) para ler o contexto prévio da conversa.

### 4.3 Digitação Segura com Suporte a Emojis e Acentos
Para evitar que layouts de teclado (ABNT2 vs US International) corrompam caracteres acentuados ou emojis, o VEXX AI:
1. Copia o texto para o buffer de área de transferência (`pyperclip.copy(mensagem)`).
2. Foca o campo `contenteditable="true"` ("Mensagem...").
3. Executa a colagem instantânea (`Ctrl + V`).
4. Dispara a tecla `Enter`.

### 4.4 Pesquisa de Pessoas, Lojas e Negócios
1. O cursor clica no ícone de busca da sidebar (`x ≈ 35px, y ≈ 165px`) ou no campo da gaveta de busca.
2. Digita o termo buscado (ex.: `"loja de informática"`, `"restaurante"`, `"@usuario"`).
3. Aguarda 1.5s a 2s para renderização dos cards com avatares, nomes e descrições.
4. O OCR lê e estrutura os resultados para o usuário.
