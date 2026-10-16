# Vexx AI V5.3 — 3D Engine Foundation

## Resultado

JDUI `model3d` integrado ao chat: cubo, esfera, cilindro, pirâmide, combinações
limitadas e um GLB local original. Three.js único, lazy e local. Rotação por mouse,
toque e teclado, zoom, centralizar, restaurar, animar/pausar, seleção, detalhes,
anotações e tela ampliada funcionais. Fallback 2D e conteúdo textual preservados.

Pedidos explícitos e follow-ups são determinísticos no PC Agent, sem LLM ou rede,
e passam pelo fluxo habitual completo/SSE e pela persistência. Referência é
isolada por dono/conversa. A interface não executa código, shaders ou HTML do LLM.
Modelos externos não são aceitos. Identidade Lucas e permissões remotas preservadas.

## Auditoria e correções

- HEAD inicial confirmado: `f6ad97f`, V5.2; Git limpo ao começar.
- Baseline executado: **431 passed, 10 deselected**, duas advertências, 218,22 s.
- JDUI foi estendido por registry, sem recriação. CSP continua same-origin, sem
  unsafe-inline, unsafe-eval ou novo host externo.
- Não havia cabeçalhos duplicados V5.3–V5.5 no roadmap desse HEAD; mantida uma
  entrada canônica para cada versão e atualizada a entrega V5.3.
- Bug encontrado na QA: sync desmontava mensagem enquanto o motor importava.
  Mensagens 3D inalteradas agora retêm DOM; a intenção de abertura sobrevive à
  substituição, usando chave de dono/conversa/mensagem/componente.
- Uma única instância ativa descarta a anterior; canvas removido libera recursos.
  Fora da tela/aba oculta não há animação; reduced motion respeitado.
- Motor pré-comprimido em build, 142,7 KiB transferíveis via gzip; Render não
  renderiza 3D nem comprime por requisição. Sem armazenamento temporário de modelos.

## Arquivos desta entrega

- `model3d.py`: schema, normalização, reconhecimento de pedidos e snapshots.
- `jdui.py`, `intent.py`, `pc_agent.py`: registry e integração aos caminhos de chat.
- `public/model3d-schema.js`, `public/model3d-viewer.js`: validação e renderer.
- `public/jdui.js`, `public/app.js`: montagem lazy, preservação e atualização ativa.
- `public/index.html`, `public/interface.css`, `public/sw.js`: loader, estilo/cache.
- `server.py`: somente rota estática do motor com gzip pré-gerado nesta entrega.
- `public/vendor/*`, `public/models/*`: motor, licença MIT, GLB/SVG originais CC0.
- `tools/3d/*`: build reproduzível com lockfile, gerador GLB e QA Chrome.
- `tests/test_model3d.py`: contratos Python/JS, limites, segurança, routing,
  persistência/isolamento, SSE e entrega comprimida.
- `docs/JULIA_3D_ENGINE.md`, `docs/JULIA_3D_PERFORMANCE.md`,
  `docs/V5_3_PROGRESS.md`, roadmap e este relatório.
- `qa-artifacts/3d/`: screenshots reais e métricas; `failure.png`, se presente,
  registra uma tentativa anterior e não é a evidência da execução aprovada.

## Validação

1. Schemas equivalentes executados em Python e Node, quatro geometrias,
   combinações, GLB autorizado, versão, IDs, numéricos finitos, cor, anotações,
   campos arbitrários, URL maliciosa, modelo ausente e limites de tamanho.
2. SQLite real reaberto: mensagens persistem; follow-up não cruza dono/conversa;
   replay não regenera; fluxo SSE salva resposta completa sem chamar LLM.
3. Chrome instalado, WebGL2 **Intel UHD / ANGLE D3D11**: screenshots, mudança real
   de pixels ao girar, mouse, teclado, toque, zoom, reset, seleção, pausa, expansão,
   quatro primitivas, GLB e combinação. Sem overflow em 390×844.
4. QA de recurso: zero import de motor antes de abrir, uma canvas ativa, desenho
   cessa ao pausar/sair da tela, 35 buffers criados e 35 deletados, zero canvases
   após desmontar. Reduced motion e CPU throttling 4× testados.
5. Perda de contexto WebGL, recuperação, GLB acima do limite e fallback sem WebGL.
6. Login → composer → relay real → PC Agent real → SSE → IndexedDB → JDUI,
   follow-up “Amplie”, recarga e abertura. Sem inferência externa necessária.
7. Cache offline verificado na sessão aberta. Recarga completa offline continua
   sujeita ao login já existente; não se alterou autenticação para contorná-lo.

Comandos:
```text
python -m pytest -q -m "not e2e_real"
python -m pytest -q -m e2e_real -rs
python -m pytest -q -rs
python -m pytest -q tests/test_model3d.py tests/test_ui_polish.py tests/test_frontend_smoke.py
node tools/3d/qa.cjs
```

Resultados intermediários: **99 testes focados aprovados** antes da última
extensão de QA; **57 aprovados** no foco final schema/chat/frontend. Os E2Es
existentes foram executados separadamente: **5 passed, 5 skipped** (dois testes
LLM já marcados como bloqueados no projeto; três dependentes de DDG/lojas, rede
sem resultados ou HTTP 403). Não foram removidos testes nem marcadores.

**Suíte completa executada: 488 passed, 5 skipped, duas advertências, 160,66 s.**
Os cinco skips são os mesmos bloqueios externos descritos acima. Após os últimos
limites do schema, o foco final passou com 57 testes. A QA Chrome foi repetida
após o ajuste de enquadramento e passou; screenshots mobile foram revisados.
`git diff --check` passou. As advertências existentes são depreciações de mss
e timeout do TestClient; não houve falha mascarada.

## Trabalho concorrente e rastreabilidade

Durante a execução, outro trabalho alterou `hermes_bridge.py`, adicionou
`providers.py`/`tests/test_providers.py` e modificou catálogo/configuração de
modelos em `pc_agent.py`, `server.py`, `public/app.js`, `public/index.html`,
`public/styles.css`, `.env.example` e `tests/test_ai.py`. Essas mudanças foram
preservadas e não fazem parte da implementação 3D. Uma suíte intermediária
capturou o arquivo em transição e teve 10 falhas NameError por providers ainda
não importado; depois houve uma falha de contrato do catálogo enquanto o teste
correspondente era atualizado. A validação final usa o checkout atualizado. O HEAD avançou externamente para
`4f968eb` durante esta execução, incluindo trabalho 3D e de provedores. Não foi
criado commit nem executado push/deploy por esta rodada do assistente. Edições
concorrentes adicionais em research.py, tests/test_research_agents.py e
docs/JULIA_PROVIDERS.md também foram preservadas.

## Limitações

Sem Android/iOS físico, Safari ou leitor de tela real. CPU emulada não equivale a
celular modesto. Medições curtas não certificam ausência de vazamentos prolongados,
RAM GPU ou consumo de bateria. Não há geração 3D arbitrária, catálogo remoto,
texturas nem upload. A interpretação dos comandos usa snapshots persistidos, não
o gesto de câmera local ainda não incorporado ao snapshot conversacional.

Nenhum push/deploy, exclusão de dados reais, mudança na extensão Júlia ou no
Fajulto Studio foi realizado nesta entrega. Ambientes de QA usam SQLite temporário.
