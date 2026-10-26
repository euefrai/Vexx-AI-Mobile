# VEXX AI V5.9.9.7 — Retrieval Efficiency & End-to-End Context Propagation

Data: 2026-10-26. **Implementação e validação locais concluídas; NO_GO para publicação como Deep Search completa ou Research Ultra.** Há redução demonstrada de leituras repetidas, mas não recuperação externa consistente nem síntese real aprovada.

## Revisão e escopo

HEAD inicial: `ff486edbc8b06a5db297bd735abcb64323542fb7`. HEAD final de código: `203d4d5`.
Commits locais: `c98d4be` (contexto/reuso/passagens/testes) e `203d4d5` (trace preciso, replay HTML e QA). O commit de documentação/evidências que contém este relatório vem depois desses dois; sua identidade é registrada pelo Git, não por uma referência circular neste arquivo.

Branch `codex/v598-autonomous-research`, checkout `vexx-v598-dev`. Sem push, deploy, alteração no SQLite real ou reinício/encerramento do PC Agent de produção. Nenhuma extensão Júlia, Fajulto ou VERY foi alterada. Preservados rebrand, identidade, estrutura existente, autenticação, CSRF, RBAC, grants, validação de URLs/redirects e ausência de execução arbitrária de código do modelo.

## Bugs reproduzidos e correções

1. Consultas internas e retries podiam perder restrições após transformação linguística. Escopo original reaplicado no ponto de chamada interna; registro Q → candidato C → requisitos R → documento/evidência/passagem persistido. Teste exige dois notebooks, 16 GB e exclusão de usados em todas as chamadas observadas.
2. Documento lido e rejeitado para uma faceta era baixado novamente para outra. Cache documental limitado reaproveita extração no mesmo owner/job/chat/contexto/leitor; reavalia relevância sem cobrar nova leitura. Sem compartilhar conteúdo entre usuários, alterar limites ou criar tabela.
3. Identidade baseada somente na URL permitia repetir aliases/contar extrações idênticas como confirmação independente. Alias exige destino real validado; identidade exata preserva idioma/versão e mantém fontes distintas com `duplicate_of`, sem inventar corroboramento.
4. Seção literal de retorno podia perder contexto; novo span conserva heading + corpo existentes. Suporte pelo contexto é parcial, nunca confirmação direta pelo título.
5. Limite padrão de três passagens descartava uma quarta faceta distinta. Seleção limitada até oito conforme requisitos cobertos; teste verifica os quatro vínculos.
6. Trace podia confundir requisitos solicitados com suporte observado. Agora separa intenção, suporte real parcial/direto, passagem e entrega persistida. Acrescentados eventos reais de cache, documento duplicado, lacuna e terminal.
7. Primeira suíte completa detectou regressão ao trocar leitor injetado; identidade do leitor passou a compor o escopo. Teste antigo preservado e regressão corrigida.
8. Captura de 390 px corria durante o fechamento da sidebar. Causa reproduzida e harness corrigido para esperar fontes/animações finitas e conferir geometria. Não foi necessária alteração CSS do produto.

Reprodução inicial: três falhas e um passe; reprodução adicional da quarta faceta também falhou antes da correção. Hashes dos logs de falha permanecem no manifesto/validation-summary; testes não foram removidos ou relaxados.

## Comparação controlada

| Entrada congelada idêntica em cada par | Leituras/slots antes → depois | Evitadas | Evidências antes → depois |
|---|---:|---:|---:|
| API, texto já extraído | 12 → 8 | 4 | 3 → 2 |
| WEG, texto já extraído | 12 → 8 | 4 | 0 → 0 |
| API, HTML com extração real | 12 → 6 | 6 | 0 → 0 |
| WEG, HTML com extração real | 12 → 5 | 7 | 0 → 0 |
| Chibata, HTML com extração real | 10 → 7 | 3 | 0 → 0 |
| API semeada, HTML com extração real | 4 → 4 | 0 | 1 → 1 |

Três pares HTML de desenvolvimento: **34 → 18 chamadas de leitura (16 evitadas; 47,1%)**, sem evidências finais nesses três. URLs solicitadas distintas: API HTML 6/6, WEG 5/5, Chibata 6/6. Isso não é contagem de documentos bem-sucedidos: tentativas fora do corpus são identificadas separadamente. Não confundir leituras locais do replay com downloads de produção.

Exemplo real de alias capturado: `https://en.m.wikipedia.org/wiki/Object` → `https://en.wikipedia.org/wiki/Object`. É um documento genérico e não prova sobre Object.assign; deduplicar não o torna relevante. No replay textual, URLs distintas solicitadas foram 10 → 8 e a sintaxe permaneceu SUPPORTED; retorno passou de DISCOVERED a PARTIALLY_SUPPORTED, comportamento continuou DISCOVERED. Não houve resposta completa. Contagem de linhas de evidência do baseline também variou entre execuções concorrentes (2/3), limitação preservada nos artefatos.

Consultas externas do replay antes/depois: `Object.assign Sintaxe ou assinatura`, `Object.assign Valor retornado`, `Object.assign Comportamento da operação`. O mesmo pool é entregue a cada consulta: o desenho isola reuso/extração e não avalia qualidade da busca. Os três registros Q do candidato preservam referências; zero Q não resolvidos nas evidências. No teste separado de retries, quantidade/RAM/exclusão chegam às chamadas internas.

Cada par verificado contém SHA-256 igual de entrada. Corpus incompleto tem custo explícito `FROZEN_MISSING`; não é defeito atribuído ao site nem omitido do orçamento. API HTML 2/2 antes/depois, WEG 0/0, Chibata 2/2, semeado 3/3; textos API 4/4 e WEG 6/6. HTML original e extração congelada não são tratados como o mesmo teste. Captura explicitamente semeada não conta como descoberta autônoma.

Detalhes e hashes: [replay](docs/v5.9.9.7/CONTROLLED_REPLAY.md), [orçamento](docs/v5.9.9.7/READ_BUDGET.md), [resumo JSON](qa-artifacts/v5997/replay-summary.json).

## Externo e modelo real

Onze perguntas novas, congeladas antes da otimização, com rede real: dez terminaram sem evidência lida persistida; Tramontina reteve uma. Todos os resultados foram parciais, apesar do status técnico concluída. Essa linha não recebeu validação gold independente. ENTITY_MISMATCH, TOPIC_MISMATCH, ausência de passagem e bloqueios continuam relevantes. Não afrouxamos rejeições para aumentar os números.

O conjunto foi escrito pelo agente; não é avaliação humana independente. Não há baseline pareado de rede, portanto não declaramos melhoria causal, precisão ou recall. Perguntas, consultas efetivas, slots, rejeições e hashes estão em [LIVE_EXTERNAL](docs/v5.9.9.7/LIVE_EXTERNAL.md) e [external-summary.json](qa-artifacts/v5997/external-summary.json). As capturas registraram ff486ed com arquivos modificados; hashes dos módulos preservam essa origem, e o comportamento foi depois commitado. Ajustes finais do trace não recalibraram ranking no holdout.

Seis cenários autenticados foram executados via interface e PC Agent real de desenvolvimento, sem URLs pré-fornecidas. A/Object.assign leu três fontes, persistiu resultado parcial e três cards, mas o modelo gratuito retornou **timeout**: job interrompida, `synthesis_llm=false`. B/WEG, C/Chibata, D/notícia local, E/escassez pública e F/multifonte terminaram parciais, sem evidências lidas retidas suficientes. Nenhuma síntese completa aprovada. Duas mensagens de assistente por cenário representam início e resultado, com IDs/texto estáveis após reload; não duplicação do resultado.

Tabela obrigatória DISCOVERY/READ/EVIDENCE/MODEL/JDUI/OVERALL por cenário: [REAL_MODEL_E2E](docs/v5.9.9.7/REAL_MODEL_E2E.md). Dados, etapas e budgets: [e2e-summary.json](qa-artifacts/v5997/e2e-summary.json). Tempos observados 10,737–27,217 s; sem comparação de latência causal. Fluxo encerrado, HTTP 200 ou fallback extrativo não significam pesquisa fundamentada aprovada.

## JDUI e segurança

Chrome real: tabela somente leitura, ordenação por teclado, CSV, links MDN reais, persistência SQLite → sync → IndexedDB → reload; cancelamento real, galeria com cinco miniaturas de 960 px e imagem completa, setas/Esc/foco. Fonte MDN semeada usada na QA visual é declarada separadamente. Nenhuma mídia foi alegada como analisada pelo modelo.

Cards inspecionados em 320/390/1280 px, reduced motion e zoom CSS 200% com scroll interno. Em 390 px, card [20,370] e root 390; corte anterior era captura durante animação, não overflow estável. Console teve 401 pré-login esperado, aviso existente de senha fora de form e erro offline provocado; zero pageerrors nos cenários instrumentados. Não alegamos testes em smartphone físico ou produção, nem todos os fluxos offline.

Screenshots: [320](qa-artifacts/v5997/coverage-card-320.png), [390](qa-artifacts/v5997/coverage-card-390.png), [1280](qa-artifacts/v5997/coverage-card-1280.png), [zoom esquerda](qa-artifacts/v5997/coverage-zoom-card-left.png), [zoom direita](qa-artifacts/v5997/coverage-zoom-card-right.png), [galeria](qa-artifacts/v5997/gallery-dialog.png). Detalhes: [JDUI_QA](docs/v5.9.9.7/JDUI_QA.md), [ui-summary.json](qa-artifacts/v5997/ui-summary.json).

Owner/chat/leitor/versão/TTL e preservação de parâmetros cobertos por regressões; suíte de segurança existente permaneceu verde. Nenhuma nova credencial foi incorporada. Trace contém referências protegidas e sem texto de página, prompts ou segredos. Raw HTML, respostas integrais e metadados privados de runtime ficam locais e fora dos commits. A suíte não prova ausência universal de vulnerabilidades.

## Testes e recursos

- Suíte completa final: **1.683 passed, 4 skipped, 2 warnings, 154,68 s**. Warnings existentes de MSS e timeout do TestClient; skipped permanecem explicitamente ignorados, não testes aprovados.
- Testes focados finais de trace/contexto/reuso: 81 passed. Onze testes novos cobrem causas acima. Busca 34/34, shopping 59/59, experiência 16/16 são baselines focados, não avaliação científica.
- `git diff --check` e `node --check` dos dois harnesses alterados passaram. Logs completos locais; hashes/resultado em [validation-summary.json](qa-artifacts/v5997/validation-summary.json).
- Replay HTML API: 1,5429 → 0,7715 s; WEG 0,7385 → 0,4650 s; Chibata 0,7965 → 0,6055 s. Uma amostra por par, sem inferência estatística de latência real. Replay textual API 0,5689 → 0,5920 s: economia de leitura não garante menor latência em todos os casos.
- Cache tem custo: API textual 52.913 caracteres; WEG textual 37.371. SQLite total API 2.211.840 → 1.667.072 bytes; WEG 655.360 → 827.392. Variação de banco inteiro inclui evidência/trace, não só cache. Não declarar economia geral de disco.
- RSS amostrado da família do harness antes do shutdown: 111.542.272 bytes. Não é pico nem comparação antes/depois; psutil não estava disponível no Python do replay, cujo RSS é null. **Nenhuma redução de RAM comprovada.**
- Processo QA encerrado normalmente; família, banco e runtime temporários removidos: [qa-shutdown.json](qa-artifacts/v5997/qa-shutdown.json). Produção permaneceu intacta.

## Gates e limites restantes

| Gate | Decisão | Evidência / limite |
|---|---|---|
| A contexto | PARTIAL | chamadas internas e persistência testadas; não prova cortes posteriores em todo provedor |
| B deduplicação | PASS no escopo exato | leituras evitadas, owner/versão/vínculos preservados; sem near-duplicate universal |
| C orçamento | PARTIAL | custos/reuso/falhas observados; não trace universal de todo leitor/transporte |
| D passagens | PARTIAL | quatro facetas retidas em regressão e retorno parcial em texto; ganho no HTML real não demonstrado |
| E replay | PASS operacional | mesmos hashes, menos leituras; pesquisa completa não melhorou consistentemente |
| F externo | FAIL / insuficiente | onze casos reais, dez sem evidência lida persistida |
| G modelo | BLOCKED | timeout, nenhuma síntese fundamentada validada |
| H JDUI | PASS no ambiente local | entrega parcial/semeada, persistência, galeria, cancelamento e responsividade reais |
| I segurança | PASS na regressão executada | controles preservados; sem alegação de auditoria universal |

Limites adicionais: dedup exato da extração limitada, não de toda a página; aliases desconhecidos podem custar slots no primeiro encontro; cache opcional tem limite JSON e TTL; corpus privado necessário para repetir HTML; pool comum não avalia queries; trace JDUI_DELIVERED significa persistência para sync, não ACK do navegador; subconsultas internas dos seis E2Es não foram capturadas integralmente. Modelos/serviços externos indisponíveis são BLOCKED/UNVERIFIED, não sucesso.

## Arquivos e próximo passo

Código: `query_intelligence.py`, `search_orchestrator.py`, `research.py`, `research_agents.py`, `retrieval_trace.py`, `web_extract.py`, `evidence_graph.py`, `pc_agent.py`. Validação: `tests/test_retrieval_efficiency_v5997.py`, dois datasets `benchmarks/retrieval_v5997_*.json`, `tools/replay_retrieval_v5997.py`, `tools/qa_discovery_v5992.cjs`, `tools/qa_evidence_visual_v5994.cjs`; `.gitignore` protege capturas/runtime. Documentação e evidências compactas acompanham em `docs/v5.9.9.7/` e `qa-artifacts/v5997/`. Nenhum código alterado é repetido neste relatório.

**Próximo passo:** examinar separadamente descoberta inadequada, entidade/extração e perda de faceta com uma nova amostra de desenvolvimento e fontes efetivamente lidas. Em paralelo lógico, reproduzir timeout com o mesmo orçamento de síntese e exigir saída real estruturada validada. Não aumentar agentes, slots ou tokens indiscriminadamente. A implementação está salva localmente; a qualidade atual não autoriza promover como pesquisa completa.
