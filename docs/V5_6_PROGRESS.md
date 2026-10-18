# V5.6 — Progresso e contexto

Objetivo: evoluir o 3D da V5.3/V5.4 para (1) acabamento visual claro e bonito,
(2) interação mais rica por conversa e por botões e (3) geração de modelos
aproximados e honestos a partir de catálogo local, templates paramétricos e
pesquisa pública. Sem deploy, sem mudança de identidade/modelo/credenciais do
Lucas, sem tocar na extensão da Júlia ou no Fajulto Studio, sem precisão falsa,
sem assets de terceiros e sem APIs pagas.

## Fases

| Fase | Estado | Evidência |
|---|---|---|
| 1. Auditoria | concluída | leitura de `model3d.py`, `model3d_education.py`, schema/viewer/education JS, `pc_agent.cmd_model3d`, `intent.py`, testes congelados e docs `JULIA_3D_*`; QA real disponível em `tools/3d` (Playwright 1.64.1 + Chrome) |
| 2. Polimento visual | concluída | commit `0ba0fe4`: sombras suaves PCF (mapa 512, atualização só quando há movimento), luz de recorte, chão com `ShadowMaterial`, arestas discretas nos cubos, tone mapping ACES, fov 38 e palco mais claro; motor Three reconstruído (gz 146978 < 150000) |
| 3. Interação inteligente | concluída | commit `7479bad`: “mostre apenas as peças internas/externas”, “deixe só X”, “esconda X”, “mostre como isso se conecta”, “explique como funciona”; destaque de conexões; botões Ver só internas/externas e Ver conexões |
| 6.1–6.3 Catálogo local | concluída | `model3d_catalog.py` com 14 cenas aproximadas (consoles, celular, controle, placa-mãe, gabinete, monitor, teclado, headset, mesa, suporte, motor V8, notebook) e rota de pedido/continuação; doc `docs/V5_6_CATALOGO_VALIDACAO.md` |
| 6.4 Geração por pesquisa | concluída | `model3d_research.py`: provedores públicos via orçamento curto (1 consulta, ~7 s), medidas mm/cm/m/pol em triplo, template paramétrico por família, rótulo `aproximado`/`conceitual`, cache TTL em memória, sem template → sem busca e indisponível → limitação honesta; gancho em `cmd_model3d` só fora do catálogo e com `pesquisa_web` |
| 7. Fundações de montagem | parcial | por peça: `role` (structural/functional/optional), `group` (internal/external), `order`; relações `related`; etapas com vista/explodido; modo separado. Tutorial de montagem guiado fica para depois |
| 8. JDUI | parcial | chips de fidelidade (Modelo aproximado/conceitual/educativo) e fonte controlada; ações rápidas extras pendentes de revisão |
| 9. Roteamento conversacional | concluída (novos comandos) | continuações e reconstrução preservadas; dispositivos entram por verbos 3D; isolamento por dono/conversa coberto por teste |
| 10. Testes + QA real | parcial | 78 testes 3D verdes (21 na V5.6); suíte completa em `qa-artifacts/3d-catalog-tests.txt` (pré-pesquisa); QA em Chrome/WebGL da fase pendente (`tools/3d/qa-v56.cjs`) |
| 11. Desempenho | parcial | sem novos assets públicos; sombras estáticas; limites de 20 KB/32 peças/8 etapas seguem; passada final pendente |
| 12. Entrega | pendente | docs `JULIA_3D_VISUAL_POLISH`/`MODEL_GENERATION`/`ASSEMBLY_FOUNDATION`, `RELATORIO_JULIA_5.6.md` e roadmap |

## Contratos preservados

- `KINDS`, `MODEL_ID` e `VIEWS`; frases congeladas da V5.4.1 (computador vira
  `education: computer`); `respond('Mostre um dragão em 3D')[1] is None`;
  `{'source': 'Inventada'}` continua inválida; paridade Python/JavaScript.
- Um único contexto WebGL ativo; renderer importado sob demanda; `sw.js` sem
  novos assets; nenhuma dependência nova.

## Decisões

- Precisão declarada: `exato` (primitivas/GLB), `educativo` (cenas clássicas),
  `aproximado` (catálogo e pesquisa com medidas) e `conceitual` (pesquisa sem
  medidas confirmadas).
- Fontes novas exigem prefixo editorial fixo e são validadas nos dois lados.
- Pesquisa só fora do `model3d.py`: no caminho do `pc_agent`, com orçamento
  curto, cache por assunto e resultado rotulado; indisponível → limitação
  honesta, sem geometria inventada.
- Sem rótulos flutuantes em 3D; os detalhes ficam na lista de partes
  (desempenho).
- Pesquisa: sem template de forma defensável não há busca (evita scraping
  inútil); listagens em triplo são lidas como L×P×A e, em disco/drone, a menor
  medida vira altura; triplo só vale com 1–500 cm e sem razão > 100; cache
  positivo de 6 h e negativo de 30 min, no máximo 32 assuntos em memória.

## Ferramentas de QA

- `tools/3d/qa-v54.cjs` e futuro `qa-v56.cjs`: Playwright com Chrome real
  (`channel: chrome`), workspace descartável `tests/preview_workspace.py`,
  métricas de buffers WebGL e screenshots em `qa-artifacts/`.

## Pendências de contexto

- Orçamento da geração por pesquisa estabelecido: 1 consulta, timeout total
  ~7 s, até 3 provedores, `max_resultados` 8 (decidido na FASE 6.4).
- Escrever e executar o QA Chrome/WebGL da V5.6 antes do relatório final.
- Reexecutar a suíte completa depois da pesquisa e anexar a evidência nova.
