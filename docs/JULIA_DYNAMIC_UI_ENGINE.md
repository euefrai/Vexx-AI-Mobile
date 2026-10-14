# fajulto DYNAMIC UI ENGINE — JDUI 1.0

Interfaces declarativas geradas pela IA dentro do chat. A IA **descreve**;
o frontend **renderiza com componentes nativos**. Nenhum JavaScript do modelo
é executado em nenhum caminho.

## 1. Arquitetura

```
Modelo (Hermes) → texto + fences ```jdui (JSON)
    → pc_agent normaliza (jdui.py: mantém válidos, remove inválidos, loga)
    → guarda texto canônico no SQLite → sync/ACK
    → celular (IndexedDB) extrai+valida (jdui.js) → monta componentes
    → estado em IndexedDB `ui_state` → sync idempotente → SQLite `ui_state`
```

O Render continua sem banco. O protocolo de mensagens **não mudou**:
fences viajam dentro do texto (offline-first preservado).

## 2. Schema `fajulto-ui-message/v1`

```json
{
  "version": "fajulto-ui-message/v1",
  "blocks": [
    { "type": "text", "content": "Veja:" },
    { "type": "ui", "component": "quiz", "props": { "title": "…", "questions": [] } }
  ]
}
```

Limites: ≤6 fences/mensagem, ≤8 blocos/fence, ≤24KB/fence, profundidade ≤8,
12 perguntas/quiz, 30 itens/checklist e linhas/tabela, 8 cards/colunas.

## 3. Component Registry

| Componente | Props principais | Estado local | Ação IA |
|---|---|---|---|
| quiz | title, questions[{q,options[2..6],answer,explain}] | answers, idx, done | Explicar meus erros (chat) |
| checklist | title, items[{label,checked}] | checked[] | — |
| calculator | kind: basic\|imc\|porcentagem\|juros | display/valores | — |
| cards | items[{title,desc,value,badge,url,action{chat}}] | — | Detalhar (chat) |
| diagram | direction v\|h, nodes[{id,label,desc,status}], edges | open por nó | — |
| table | columns[], rows[[]] | sort local | — |
| form | fields[{name,label,type,options,required}], calc | valores | — |
| progress | label, value, max | — | — |
| tabs | tabs[{title,markdown}] | aba ativa | — |
| accordion | items[{title,markdown}] | abertos | — |

Cálculos (`OPS` em `jdui.js`, espelho conceitual em `jdui.py`/`pc_agent`):
`soma`, `porcentagem`, `imc`, `juros` (+ parser próprio de expressões no
`basic` — **sem `eval`**). `form.calc` só aceita esses nomes.

Desconhecido/inválido → bloco descartado + erro logado; o texto ao redor
continua (fallback). `widget-html` legado continua renderizando (histórico),
mas o modelo não é mais instruído a usá-lo.

## 4. Renderer (`public/jdui.js`, ~700 linhas, zero deps)

- `validateMessage` (espelho de `jdui.py`), `extractBlocks` (só fences fechados),
  `mount(root, slots, ctx)`, `calcExpr`, `OPS`.
- Tudo via `textContent`/DOM; URLs só `http/https`; `srcdoc` não é usado aqui.
- Ações locais nunca chamam IA. Ações de chat usam `ctx.onChat` (mensagem
  autenticada normal). Sem ações externas além de links `https` explícitos.

## 5. PresentationEngine (`pc_agent.fajultoPresentationEngine`)

Intenção → componente: quiz, checklist, calculator, cards, diagram, table,
form. Pergunta simples → **só texto**. Catálogo compacto injetado só quando há
intenção (economia de tokens). Regras anti-pergunta-de-volta embutidas.

## 6. Streaming

Fence aberto = placeholder `[JDUI: montando interface…]` (sem JSON bruto).
Fence fechado válido monta ao final de cada repaint; remontagem só quando
surgem novos slots (sem reconstruir a cada delta, sem duplicar, sem rolar
sozinho). Falha no stream preserva o texto; inválido some no `ai_done`.

## 7. Persistência e sync

- Celular: `ui_state` (IndexedDB), chave `messageId#slotIdx:componente`,
  gravação imediata + POST `/api/ui-state` com debounce de 4s.
- PC: tabela `ui_state`, upsert por `k`, estados ≤8KB.
- Merge newer-wins por `updated_at` nos dois lados. Offline: tudo local funciona.

## 8. Segurança

Conteúdo da IA = não confiável. Sem `eval`/`Function`, sem `innerHTML` com
dado bruto (só renderer markdown seguro e DOM), sem scripts/eventos do modelo,
URLs validadas, tamanhos/profundidade limitados, auth+CSRF nos endpoints,
`ui_state` nunca guarda credenciais.

## 9. Limitações honestas

- Modelo free gera JSON inválido às vezes → fallback Markdown (by design).
- Sem gráficos bitmap (charts): use `table`/`progress`/`cards`.
- Sem dispositivos físicos testados (ver relatório).
- `widget-html` antigo ainda executa JS **isolado** (sandbox, origem opaca);
  novos conteúdos usam JDUI.

## 10. Adicionar um componente

1. Validador em `jdui.py` (`_v_novo` + registro em `VALIDADORES`).
2. Espelho em `jdui.js` (`V.novo` + `R.novo` + `COMPONENTS`).
3. Exemplo em `docs/fajulto_DYNAMIC_UI_EXAMPLES.md`.
4. Testes nos dois lados com o mesmo payload.
5. CSS em `styles.css` herdando as variáveis do tema.
