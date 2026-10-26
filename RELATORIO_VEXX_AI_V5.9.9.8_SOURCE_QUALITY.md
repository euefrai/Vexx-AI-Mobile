# VEXX AI V5.9.9.8 — Source Quality & Passage Yield Intelligence

**Decisão: NO_GO para publicar.** Correções locais verificadas melhoram preservação de passagens; descoberta externa e síntese ainda não atendem à aceitação. Sem push, deploy ou mudanças em produção.

## Resultado principal

| Verificação independente | Resultado |
|---|---|
| A — Leitura de fonte conhecida | Ganho real no snapshot MDN Object.assign: retorno antes perdido agora parcial; comportamento agora suportado. Falhas de janela, requisitos e entidade persistem em outros domínios. |
| B — Descoberta sem URL | Holdout congelado de 12 consultas: zero evidência retida efetivamente lida. Nove referências de notícias não lidas não contam como sucesso. Uma consulta adicional inédita no chat leu quatro fontes, insuficiente para consistência. |
| C — Síntese com evidência válida | Modelo gratuito real: timeout na revisão em uma tentativa; quantity_mismatch antes da revisão na outra. Resultado parcial persistido, sem aprovação da síntese. |

## Correções e causas

1. Parágrafos curtos de resposta eram descartados; parágrafo literal de 18 caracteres da MDN agora é preservado. Espaços/newlines de seções agora alinham com o texto final sem inventar offsets.
2. Título “Return value” não é mais confundido com frase afirmando retorno. Relação “copies/copia” reconhecida sob guardas de entidade/operação existentes.
3. Limite de 32 vínculos favorecia somente a primeira faceta. Distribuição entre requisitos preserva retorno raro sem ampliar orçamento.
4. Grafo recebia primeiros vínculos brutos, perdendo passagens já selecionadas. Usa seleção final e todos os requisitos associados, mantendo REQUIRES_VERIFICATION.
5. Resultado de calculadora/dicionário genérico podia encerrar fallback de API qualificada. Filtragem continua o fallback existente; documentação pai segue elegível para navegação. Regressão intermediária que excluía índices foi detectada e corrigida antes do holdout.
6. Trace recebe contadores limitados de documentos/passagens/vínculos, sem texto ou URL privada.
7. Ferramenta de diagnóstico da síntese agora hidrata checkpoint terminal, corrigindo leitura enganosa de campos vazios do job compacto.

## Evidência e limites

- Mesmo snapshot acessível nos sete pares de leitura. WEG bloqueado; FGV erro de rede; PDF limite de tamanho. Não houve bypass.
- Replay API congelado: base cc60042 10 leituras/3 evidências; final 3/3, comportamento melhora, retorno permanece parcial. Agendamento/fronteira variam: não atribuir toda economia causalmente ao patch.
- Replay HTML genérico: API 6→0 leituras, mas 0→0 evidências; empresa/história sem ganho. Redução de desperdício não é aumento de qualidade.
- Antiga variação 3→2 não foi validada como deduplicação legítima. Há variante alemã e mudanças de fronteira; final preserva três documentos. Veja [preservação](docs/v5.9.9.8/EVIDENCE_PRESERVATION.md).
- Perda Nikon confirmada: bateria/peso nas posições 11.510/12.128, além do teto 8.000. Apenas diagnóstico leu o snapshot com teto maior; produto permanece limitado.
- Entidades implícitas, requisitos não reconhecidos, linguagem natural, páginas longas e relações lexicais continuam limitando recuperação. Precisão/recall independentes indisponíveis; nenhum benchmark humano inventado.

## Validação executada

- Suíte final: **1.692 passed, 4 skipped, 2 warnings, 150,86 s**. Warnings existentes de MSS/TestClient; skips preservados. Nove testes novos focados cobrem perdas, falsos suportes, facetas, fallback e trace.
- Benchmarks existentes: pesquisa **34/34**, shopping **59/59**, experiência **16/16**. São verificações de regressão, não pesquisa autônoma universal.
- `node --check` nos dois scripts QA alterados; `py_compile` nas três ferramentas; `git diff --check` sem falha.
- Chrome autenticado local: SSE, resultado parcial persistido, fonte real aberta, cancelamento, imagens, teclado/foco, downloads MD/CSV, reconexão simulada e IndexedDB. Geometria 320/390/1280 e zoom CSS 200%. [E2E](docs/v5.9.9.8/AUTHENTICATED_E2E.md), [JDUI](docs/v5.9.9.8/JDUI_QA.md).
- Sessão inicial de Chrome desapareceu entre etapas: comandos falharam e foram retomados em nova sessão; não apresentados como passes.
- QA encerrado pelo próprio harness. Supervisor/filho ausentes e arquivos temporários removidos, conforme qa-shutdown.json. Nenhum SQLite de produção escrito.

## Gates

| Gate | Situação |
|---|---|
| A Leitura | Parcial: APIs melhoraram; outros domínios ainda perdem informação |
| B Descoberta | Não aprovado: ganho não consistente |
| C Passage yield | Ganho localizado demonstrado; precisão global não medida |
| D Deduplicação | Facetas preservadas no replay final; variação histórica não inteiramente atribuída |
| E Replay | Ganho no cenário API; nenhum ganho informacional nos outros replays |
| F Externo | Reprovado: 0/12 com evidência retida lida |
| G Síntese | Reprovado: timeout/rejeição numérica |
| H JDUI | Aprovado no escopo de entrega parcial local testada |
| I Segurança | Suíte sem regressão detectada; nenhuma flexibilização; não é auditoria completa de segurança |

## Arquivos e commits locais

Base cc60042 na branch codex/v598-autonomous-research.

- 8a6cfcc: holdout congelado (`benchmarks/source_quality_v5998_holdout.json`).
- 5ffb476: `web_extract.py`, `evidence_graph.py`, `research_agents.py`, `search_orchestrator.py`, `retrieval_trace.py`, `tests/test_source_quality_v5998.py`.
- 12ce7a8: `.gitignore`, dataset de desenvolvimento, `tools/probe_source_quality_v5998.py`, `tools/probe_synthesis_v5998.py`, extensão do replay existente, dois scripts QA existentes habilitados para v5998.
- Documentação e evidências compactas em commit local separado: este relatório, `docs/v5.9.9.8/` e resumos/artefatos selecionados em `qa-artifacts/v5998/`.

Capturas completas, runtime privado e respostas brutas ficam fora do Git. Artefatos exploratórios inválidos são explicitamente excluídos das conclusões; hashes de arquivos locais constam do manifesto. Sem alteração de identidade Lucas, extensão Júlia, Fajulto Studio ou VERY; nenhum novo motor/agente/dependência/modelo pago.

## Pendências prioritárias

1. Recuperar seções relevantes tardias sob orçamento constante e sem inferir fatos a partir do título.
2. Corrigir representação de entidade/requisito em linguagem natural usando desenvolvimento, não ajustar ao holdout já aberto.
3. Capturar diagnóstico privado da resposta numérica rejeitada, distinguir alucinação de falso positivo e investigar revisão gratuita sem elevar timeouts às cegas.
4. Congelar nova avaliação independente e repetir A/B/C antes de recomendar publicação.

Não expandir mais motores para esconder esses bloqueios. Próximo passo operacional em [PROGRESS.md](docs/v5.9.9.8/PROGRESS.md). Evidências separadas em [leitura](docs/v5.9.9.8/PASSAGE_YIELD.md), [descoberta](docs/v5.9.9.8/SOURCE_DISCOVERY.md), [três trilhas](docs/v5.9.9.8/THREE_TRACK_DIAGNOSTICS.md), [replay](docs/v5.9.9.8/CONTROLLED_REPLAY.md), [holdout](docs/v5.9.9.8/EXTERNAL_HOLDOUT.md) e [síntese](docs/v5.9.9.8/LLM_TIMEOUT.md).
