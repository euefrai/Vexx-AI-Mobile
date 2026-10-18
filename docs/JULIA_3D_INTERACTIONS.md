# Interações 3D — V5.4

O componente JDUI `model3d` mantém `version: 1` e compatibilidade com as cenas da V5.3. `education` habilita as extensões validadas. Three.js continua local, carregado somente ao abrir o visualizador; o servidor não renderiza imagens nem precisa de GPU.

## Contrato

- Até 32 partes educativas (8 objetos nas cenas antigas), 8 etapas e 8 anotações. Snapshot normalizado: máximo 20 KB UTF-8.
- Cada parte: `id`, `kind`, `label`, `description`, `position`, `rotation`, `scale`, `dimensions`, `color`, `category`, `related`, `metadata`.
- Categorias: component, face, edge, vertex, body. Metadados permitem somente `conceptual` booleano e `note` textual. Relações devem apontar para IDs existentes, sem duplicatas ou autorreferência.
- Anotações usam `objectId` e `text`. São apresentadas nos detalhes da parte selecionada, sem HTML executável.
- `interaction`: selected, hidden, isolated, exploded, transparent, view, focus, step, speed, lessonPlaying. Referências, tipos e limites são verificados em Python e JavaScript.
- Vistas: free/front/back/side/top. Velocidade: 0,5–2. Etapas: índices válidos da cena.

## Uso

Peça “Mostre um computador em 3D” e abra **Explorar em 3D**. Arraste para girar; selecione com clique/toque sobre a geometria ou com Tab e Enter nos botões de partes. Setas giram o canvas; +/− ajustam zoom. A seleção usa raycasting real, identifica o mesh e destaca seu material.

**Mais opções** reúne vista, isolamento, ocultação, revelação, transparência, foco e separação/remontagem. Operações sobre partes ficam desabilitadas sem seleção. Restaurar limpa os estados interativos e retorna à câmera inicial. O menu primário mantém zoom, reset e detalhes; cenas educativas não exibem o botão redundante de tela ampliada.

Exemplos determinísticos aceitos: “Lucas, destaque a memória RAM”, “Mostre a parte traseira”, “Separe as peças”, “Remonte as peças”, “Explique o processador”, “Deixe a placa-mãe transparente”, “Próximo passo”, “Volte ao passo anterior”. O Intent Engine existente reutiliza `model3d.request`; sem uma referência 3D, comandos de continuação não tomam o lugar da conversa normal.

Os comandos suportados usam nomes/IDs/aliases conhecidos. Não há interpretação semântica geral nem geração arbitrária de peças. Referência desconhecida ou operação incompatível retorna uma limitação. O texto informa que o ajuste foi preparado; o viewer confirma sua aplicação ao estado local. Essa confirmação não é um recibo de execução remoto.

## Estado e segurança

O cliente envia `scene_state` junto ao pedido SSE/POST, com ID da mensagem ativa, ID da cena e interação/câmera atuais. Assim, um comando não precisa esperar o sync periódico de UI. O PC Agent busca a mensagem **do proprietário autenticado e da conversa solicitada**, valida o JDUI e somente então aplica o estado. Um ID vindo do cliente nunca confere propriedade. A busca é limitada às 50 últimas respostas: uma referência mais antiga retorna indisponível.

Sem contexto imediato, o agente recupera o snapshot UI persistido em SQLite. O estado local usa o cache e IndexedDB existentes, com chave de proprietário/conversa/mensagem/slot e fila de sincronização. Salva em ações, fim de gesto, mudança de etapa e descarte, nunca a cada frame. Uma troca de conta bloqueia gravações tardias do viewer anterior. Após reload, abrir a cena restaura o snapshot; não se abre GPU automaticamente em uma sessão fria.

Comandos que mantêm a estrutura transferem o mesmo canvas para a resposta nova. O horário definitivo recebido após SSE atualiza apenas o texto do horário, sem recriar o viewer. Alterações estruturais descartam a cena anterior. O renderer compartilha geometrias por tipo, limita pixel ratio, pausa fora da tela e libera recursos ao fechar/remover/perder contexto.

Scripts, shaders, URLs externas e HTML do modelo continuam proibidos pelo schema. Não houve mudança em CSP, autenticação ou permissões de controle remoto. O único GLB permitido continua sendo o catálogo local V5.3.

## Verificação

`tests/test_model3d_v54.py`: paridade Python/JS, IDs inválidos, limites, comandos, contexto local ainda não sincronizado e isolamento por conta/conversa. `tools/3d/qa-v54.cjs`: Chrome/WebGL real, pixels, raycast, teclado/toque, operações, etapas, reuso de canvas/buffers, cleanup e chat autenticado com SSE/IndexedDB/reload. Executar contra `tests/preview_workspace.py`, que utiliza SQLite temporário, nunca a base real.

## V5.6 — deltas

- Operações novas: “mostre apenas as peças internas/externas” (op `onlyGroup`),
  “mostre como isso se conecta” (relações `related`) e “explique como funciona”.
- Botões “Ver só internas/externas” (desabilitados quando a cena não tem
  grupos) e “Ver conexões” (ativa com peça selecionada) no menu de opções.
- Peças ganharam papel/grupo/ordem; os detalhes mostram “Estrutural/Opcional ·
  Interna/Externa · Montagem #N”
  ([JULIA_3D_ASSEMBLY_FOUNDATION.md](JULIA_3D_ASSEMBLY_FOUNDATION.md)).
- Cenas de dispositivo (catálogo local e pesquisa) usam exatamente as mesmas
  operações, limites e isolamento por dono/conversa descritos acima.
