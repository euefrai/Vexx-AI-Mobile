# VEXX AI V5.4 — Interactive 3D Intelligence

Data: 16/10/2026. Base: `3d0ef53` (`3d quase completo`). Working tree inicialmente limpa; nenhuma alteração concorrente encontrada. Não houve push/deploy, alteração de modelos/provedores/credenciais/identidade, controle remoto, extensão Júlia ou Fajulto. Bases reais não foram usadas no QA.

## Implementação

- Schema educativo em Python e JS: partes com IDs, transformações, categorias, descrições, relações e metadados limitados; etapas e estado interativo declarativos. Compatibilidade com snapshots V5.3 preservada.
- Raycasting real, seleção com toque/mouse/teclado, destaque, isolamento, ocultar/revelar, transparência, foco, quatro vistas, separação/remontagem e reset.
- Sequência com seleção de etapa, anterior/próxima, reprodução/pausa, velocidade e transições. Respeita movimento reduzido e visibilidade da aba/viewer.
- Computador com quatro componentes; cubo com 26 partes (6 faces, 12 arestas, 8 vértices); recorte solar com três corpos e órbitas conceituais.
- Comandos determinísticos pelo chat, integrados ao Intent Engine existente. Snapshot imediato no pedido SSE/POST elimina a espera pelo sync de UI para conhecer a cena ativa.
- Persistência por conta/conversa/mensagem/slot, restauração após reload, mesmo canvas e buffers para comandos sem mudança estrutural.
- Toolbar compacta, menu secundário, detalhes por seleção, etapas legíveis e sem botão redundante de tela ampliada nas cenas educativas. Não foi redesenhado o chat inteiro.

## Problemas encontrados e corrigidos

1. Um comando baseado somente na última resposta perderia interações locais ainda não sincronizadas ou escolheria outra cena. O pedido agora identifica a mensagem ativa, envia seu estado limitado e o agente verifica propriedade/conversa antes de aplicá-lo. Sem esse contexto, consulta o estado persistido.
2. O horário definitivo vindo do SQLite após SSE alterava a assinatura do DOM, destruindo o canvas mesmo quando o conteúdo era igual. O horário é atualizado separadamente; o teste real confirma identidade do canvas antes/depois do comando e do sync.
3. A recriação dos botões de partes perdia foco de teclado. O foco é restaurado por ID, sem alterar scroll.
4. Gravações tardias de um viewer de outra conta poderiam usar o proprietário global atual. O contexto captura o proprietário original e recusa gravações após troca de conta.
5. O novo schema JS precisava rejeitar também chaves herdadas como `toString`/`__proto__`. A validação agora exige propriedades próprias autorizadas, com paridade Python/JS testada.
6. A pausa orbital inicialmente voltava à posição inicial. A posição agora é mantida na sessão; o teste compara pixels após pausa. O enquadramento solar considera o trajeto inteiro e os corpos foram ampliados visualmente, com aviso explícito de escala conceitual.

## Testes executados

| Verificação | Resultado |
|---|---|
| Baseline completo antes das alterações | **490 passed, 5 skipped**, 2 warnings, 100,50 s |
| Suíte completa após integração | **502 passed, 5 skipped**, 2 warnings, 130,34 s |
| Focados: model3d, V5.4 e streaming/UI | **56 passed** |
| V5.4 após ajuste final das cenas | **12 passed** |
| QA Chrome V5.4 | **Passou**, WebGL real, 20 buffers criados e 20 liberados |
| Regressão Chrome V5.3 | **Passou**, 35 buffers criados e 35 liberados, zero canvas após descarte |
| Diff whitespace | `git diff --check` sem erros |

O baseline informado pelo pedido era 488/5; o checkout já continha dois testes adicionais e confirmou 490/5 antes da implementação. Nenhum teste foi removido. Os cinco skips são dois testes de inferência sem provedor e três dependências de pesquisa/shopping bloqueadas por rede/bot-wall/HTTP 403. Warnings existentes: depreciação de `mss` e timeout no TestClient.

QA executado com Chrome headless instalado, WebGL 2 via ANGLE/Intel UHD/D3D11. Testa seleção real por raycast, alteração de pixels, teclado com preservação de foco, toque via Chrome Input, transparência/isolamento/ocultação, câmera, anotações, etapas, velocidade, órbitas/pausa, reuso de canvas/buffers, offscreen, movimento reduzido e cleanup.

Fluxo real confirmado: login → composer → relay → PC Agent determinístico → SSE → JDUI → ocultar RAM → comando separar peças preservando o estado local → IndexedDB → reload → reabertura com o mesmo estado. O QA V5.3 também verifica perda de contexto, fallback sem WebGL, GLB limitado e cache offline do motor. A política de login no reload offline frio não foi alterada.

Não houve erros JS inesperados. O QA registra separadamente o **401 esperado de `/api/session` antes do login**, sem ignorar outros erros. Capturas foram abertas e inspecionadas; mobile sem overflow horizontal, controles legíveis e sidebar recolhida antes da captura.

## Recursos e desempenho

- Three.js local inalterado: **572.055 bytes**, arquivo gzip servido de **146.171 bytes**. Nenhuma nova dependência.
- Novo módulo educativo: aproximadamente **7,3 KB**, gzip estimado **2,7 KB**; renderer aproximadamente 17 KB e schema 6,1 KB. Módulo educativo só carrega junto ao viewer; motor segue fora do precache inicial.
- Snapshots normalizados do catálogo: computador ≈2,9 KB, cubo ≈10,5 KB, solar ≈2,1 KB, abaixo do limite de 20 KB.
- Geometrias compartilhadas por tipo; uma cena/canvas ativa; máximo 32 objetos, 8 etapas e 8 anotações. Sem persistência por frame.
- QA V5.4: descarte integral dos 20 buffers alocados ao longo das trocas de cenas; comandos simples não criam buffers/canvas novos. Pausa e offscreen interrompem os draw calls.
- Regressão V5.3 com CPU Chrome 4×: 30 draw calls em 1.003 ms para uma esfera. Essa medição de laboratório não representa FPS garantido em celular físico.

## Arquivos e evidências

- Backend: `model3d.py`, `model3d_education.py`, `pc_agent.py`, `server.py`.
- Frontend: `public/model3d-schema.js`, `public/model3d-viewer.js`, `public/model3d-education.js`, `public/app.js`, `public/interface.css`, `public/sw.js`.
- Testes: `tests/test_model3d_v54.py`, `tools/3d/qa-v54.cjs`.
- Documentação: `docs/JULIA_3D_INTERACTIONS.md`, `docs/JULIA_3D_EDUCATION.md`, `docs/JULIA_MOBILE_ROADMAP.md`, `docs/V5_4_PROGRESS.md` e este relatório.
- Evidências novas: `qa-artifacts/3d-v54/metrics.json`, `computer-desktop.png`, `geometry-mobile.png`, `solar-mobile.png`, `chat-mobile.png`. A execução da regressão também atualizou capturas/métricas existentes em `qa-artifacts/3d/`.

## Limitações e pendências

- Sem teste em Android/iOS físico, Safari ou Render de produção; não houve deploy.
- Comandos seguem vocabulário determinístico e aliases. Não há interpretação 3D semântica aberta nem modelos arbitrários. A busca conversacional fica nas últimas 50 respostas.
- O sistema solar contém somente Sol/Terra/Marte, sem escala física; o computador não comprova compatibilidade técnica. Sem motor físico.
- A fase orbital exata não é persistida por frame: reload restaura etapa/estado, reiniciando a fase orbital.
- Texto de comando confirma preparação; feedback local confirma aplicação ao viewer. Não há novo protocolo de recibo remoto de renderização.
- Próxima validação recomendada: os mesmos fluxos em Android e iOS reais, incluindo perda de conexão e retomada do navegador. Serviços externos continuam sujeitos aos cinco skips documentados.
