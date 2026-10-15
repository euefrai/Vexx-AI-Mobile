# JÚLIA Live Research 2.0 (V4.7)

## Transporte: SSE push + polling fallback (decisão auditada)

Polling 2 s funcionava, mas entrega com atraso e tráfego inútil. SSE real:
agente faz push (`research_event_push` via tailer no worker) → relay
fan-out por `(job_id, owner)` com teto (20 subs, fila 200, descarte
contado) → `GET /api/research/stream` (backlog autoritativo + live +
pings + fechamento em evento final). Polling preservado (mesmo contrato,
mesmos `seq`) como fallback automático. Sem conexão pública direta: tudo
passa pelo relay autenticado; PC guarda o definitivo.

Garantias: ordem por `seq`, dedupe no cliente, replay por `apos_seq`,
cancelamento, isolamento por dono, sem reexecução ao reconectar,
backpressure (descarte contado), memória limitada, Render sem estado.

## Painel (§7)

Barra compacta com fases reais (Planejando/Pesquisando/Abrindo/
Extraindo/Verificando/Contradições/Replanejando/Gerando/Finalizado/
Interrompido/Falhou) + expandível com filtros (Tudo/Buscas/Fontes/Erros),
timeline limitada a 30 nós no DOM, fontes com links, evidências expansíveis
(trecho + abrir original), erros e divergências. Sem sidebar permanente;
sem raciocínio privado do modelo.

## Intervenção (§8)

`POST /api/research/intervene` (+ chat): `escopo_add`, `escopo_remove`,
`priorizar_dominio`, `investigar_divergencia`, `parar_topico`,
`adicionar_metrica`. Nova versão do plano, feitas preservadas,
incompatíveis invalidadas e listadas. Worker sincroniza a cada etapa
(transientes preservados). Sem LLM: conjunto estruturado; com LLM
indisponível, interpretação livre informa o bloqueio.
