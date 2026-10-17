# VEXX AI V5.4.1 — Correção de roteamento e execução 3D

Data: 16/10/2026. Base: `b04748a` (`feat(chat): imagens primeiro...`). Sem push/deploy. Nenhuma alteração em identidade Lucas, modelos/provedores/credenciais, memória V5.0, Fajulto Studio ou extensão Júlia. O motor 3D da V5.4 não foi recriado.

## Causa raiz (reproduzida antes da correção)

1. **Continuações caíam sempre no LLM.** `model3d.request('Isso não está em 3D, reconstrua em 3D, por favor.')` retornava `None`: a regra de criação exigia verbos `mostr*/crie/exiba/quero/visualiz*` e não reconhecia "reconstrua", "faça", "faz", "monte", "desenhe". Sem handler determinístico — e com `intent.analisar` retornando `conversa` (a condição em `intent.py` exigia `action == 'create'`) — a mensagem seguia para o LLM, a única etapa capaz de responder com blocos de código e desenhos ASCII (reproduzido).
2. **Variações com "PC" não reutilizavam a cena educativa.** A cena de computador só era reconhecida por `computador|placa-mae`; "crie um PC tridimensional" caía na resposta genérica "Nesta versão posso mostrar cubo, esfera, cilindro e pirâmide..." (reproduzido).
3. **Sem cena persistida**, "reconstrua em 3D" não tinha referência para reemitir — precisava de um caminho determinístico próprio.
4. **Observação honesta:** o pedido exato "Lucas, mostre um computador em 3D." já era roteado de forma determinística no commit base (verificado por reprodução, testes e E2E Chrome real). Não foi possível reproduzir ASCII para essa primeira mensagem no código atual; a hipótese mais provável para o relato é um agente local executando código anterior à V5.4 (processo precisa ser reiniciado para carregar o roteamento determinístico) ou a própria mensagem de continuação. A correção cobre os dois casos: todas as variações naturais agora são determinísticas e a continuação reconstrói a cena real.

## Correção

- `model3d.py`:
  - `request()` reconhece verbos naturais (`quer*`, `faz*`, `faça`, `mont*`, `constru*`, `reconstru*`, `refac*`, `refaz*`, `recri*`, `gerar*`, `gere`, `desenh*`, `renderiz*`, `modela*`) além dos originais.
  - Sinônimos da cena educativa de computador: `pc`, `desktop`, `notebook`, `laptop`, `cpu`, `processador`, `placa-mãe/placa mae`.
  - Nova ação `rebuild` para continuações/correções: "não está/é/ficou/ficava/parece em 3D", "reconstrua", "refaça/refaz/recrie", "de verdade", "realista".
  - `respond()` reconstrói a cena anterior validada (com `autoRotate` para evidenciação visual), preservando estado interativo.
- `intent.py`: `rebuild` também classifica como intenção `model3d` (ferramentas `deterministico`, `jdui`), sem depender de contexto externo.
- `pc_agent.py`:
  - `cmd_model3d` com `rebuild` e sem cena persistida: recria a partir do último pedido 3D do **usuário na mesma conversa/dono** (LIMIT 40) — resolve o cenário em que a resposta anterior foi texto/ASCII. Sem pedido anterior: mensagem de limitação honesta, sem LLM.
  - Diretriz de sistema: quando a intenção é `model3d`, o LLM nunca pode substituir o visualizador por arte ASCII/desenhos/blocos de código; se não houver cena válida, deve declarar a limitação.
- Preservados: fluxo SSE/POST, persistência, snapshots imediatos, isolamento por conta/conversa, nenhuma rede/LLM no caminho 3D, nenhuma dependência nova.

## Testes executados

| Verificação | Resultado |
|---|---|
| Reprodução manual (7 cenários: pedido exato, continuação exata, variação, PC, rebuild sem cena, rebuild após resposta texto, isolamento) | **Corrigida** (LLM bloqueado por monkeypatch; nenhum caminho 3D usa LLM) |
| Focados: `test_model3d.py`, `test_model3d_v54.py`, `test_intent.py`, `test_intent_benchmark.py` | **73 passed** |
| Suíte completa (`pytest tests/ -q -k "not e2e_real"`) | **504 passed, 10 deselected**, 2 warnings, 150,95 s |
| E2E Chrome real (`tools/3d/qa-v541.cjs` contra `tests/preview_workspace.py`) | **Passou** |

Regressões novas em `tests/test_model3d_v54.py` (5): pedidos naturais → cena de computador; continuações → `rebuild` + intenção model3d; fluxo completo pedido+continuação+variação+PC sem LLM e sem ASCII; recriação quando a resposta anterior foi texto; honestidade sem referência + isolamento por dono/conversa.

E2E real (Chrome headless, WebGL 2 via ANGLE, preview descartável com SQLite temporário e **LLM indisponível de propósito** — cobre "funcionamento com LLM indisponível"): login → composer → relay → agente determinístico → SSE → JDUI. Enviou as duas mensagens exatas: o pedido exato gerou a cena `edu-computer` com canvas WebGL2 (draw calls reais), arrasto girou (Δ0,81 rad), scroll ampliou (6 → 6,6), seleção de parte via clique (CPU), a continuação "Isso não está em 3D, reconstrua em 3D, por favor." e a variação "faça em 3D de verdade" geraram novos cartões `model3d` (3 no total), reload restaurou a cena (`edu-computer`, CPU selecionada), mobile sem overflow, **zero arte ASCII, zero blocos de código e zero erros de console**. Capturas: `qa-artifacts/3d-v541/chat-canvas.png` (cena WebGL visível), `chat-mobile.png` e `metrics.json`.

## Limitações e pendências

- Sem Android/iOS físico nem Safari; E2E em Chrome real headless com WebGL2 (ANGLE/Intel UHD/D3D11).
- "PC"/"desktop"/"notebook" apontam para a cena educativa de computador; não há modelos arbitrários nem interpretação 3D aberta.
- Rebuild reutiliza a última cena ou o último pedido 3D da conversa (40 mensagens mais recentes); não há histórico versionado de cenas.
- Se o agente local estiver executando código anterior à V5.4, é preciso **reiniciar o processo** para carregar o roteamento determinístico.

## Arquivos

- Alterados: `model3d.py`, `intent.py`, `pc_agent.py`, `tests/test_model3d_v54.py`.
- Novos: `tools/3d/qa-v541.cjs`, `qa-artifacts/3d-v541/` (2 capturas + métricas), este relatório.
- Intocados: V5.4/V5.3 (engine, cenas, viewer, schema), frontend e fluxos paralelos.
