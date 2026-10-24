# VEXX AI V5.9.9 — pesquisa universal e JDUI

Entrega local por etapas, 24/10/2026. HEAD inicial **79c63db**, branch `codex/v598-autonomous-research`. Sem push, deploy, restart de produção, promoção de contas ou alteração de permissões remotas. Studio, VERY, extensão, identidade Lucas e motor 3D não foram editados.

## Resultado desta etapa

Corrigidas perdas reproduzidas entre pergunta, descoberta, leitura, filtro final e chat. A galeria agora atravessa o fluxo real, com origem e persistência; documentação específica deixou de perder prioridade para dicionários; notícias não usam mais um caminho de feed isolado do leitor/filtro compartilhado. A qualidade universal **ainda não está aprovada**: a recuperação externa continua desigual e há fontes originais inacessíveis. Não se declara equivalência a Perplexity, cobertura absoluta ou conclusão de todas as capacidades aspiracionais do pedido.

| Causa encontrada | Alteração aplicada |
|---|---|
| Fonte era recriada sem data/metadados no gate final | Registro preservado em `fontes_relevantes`; publicado_em no nível superior também é mantido |
| “Notícias sobre cidade”, hoje/ontem/última semana não eram bem resolvidos | Extração de local, região, tópico e janela; contrato explícito de parâmetros obrigatórios |
| Tópico desaparecia ao formar a consulta só com cidade | Tópico preservado na descoberta; local/região/tópico reaplicados nas variantes/replanos de notícias |
| Notícia sem cidade podia passar sem pertinência temática | Avaliação vertical não substitui a correspondência com o assunto |
| Palavras de instrução favoreciam dicionários | Pontuação usa termos distintivos; verbos/instruções não contam como assunto; API qualificada tolera espaços de HTML sem perder fronteiras de tokens |
| Seis primeiros leads escondiam originais posteriores | Doze candidatos preservados; até seis leituras; feeds/Commons não gastam posições de leitura HTML; metadados incompletos não são eliminados antes da recuperação original |
| Candidatos desapareciam após corte/seleção | Reservoir limitado, IDs estáveis, origem/consulta/data/estado/motivos e referências; cache existente, sem novo motor/banco |
| Mídia não atravessava pesquisa rápida/cache/mensagem | Transporte real por media_evidence → research → research_view → mensagem → SQLite/IndexedDB/reload |
| Prompt negava busca de imagens; chat só avisava sobre um job | Prompt corrigido; busca visual simples devolve galeria na própria mensagem; pesquisa profunda explícita continua disponível |
| “Encontre documentação” não ativava pesquisa | Gatilhos corrigidos; pedidos de achar erros no código/arquivos locais não são transformados em busca pública apenas por esse verbo |
| Galerias irrelevantes/modelo inventando cards | Composição por intenção; media/sources emitidos pelo modelo são substituídos pelos registros recuperados |
| Modelo prometia buscar, emitia tool_call ou negava acesso apesar das fontes | Redação inutilizável substituída por resultados preservados; markup de ferramenta não executada não vira execução |
| Sem leitura, o modelo podia inventar acontecimentos/datas | Encerramento determinístico antes da inferência quando só há descoberta/metadados ou nenhuma fonte; fontes/links e limites preservados; cancelamento mantido |
| Fallback SSE podia reabrir requisição concluída como processing | Checkpoint parcial não sobrescreve estado terminal/conteúdo final; retry explícito por queued continua possível; marcador digest preservado |
| Metadado de página pública podia apontar mídia a serviço local | Rejeitados IPs privados/loopback/link-local, aliases numéricos e hosts locais no validador de mídia recuperada |
| Cards altos e metadados excessivos | Superfícies discretas, metadados recolhíveis/persistidos, crédito/licença acessíveis, navegação de imagens, foco/Escape e redução de movimento |

## Validação

Baseline: **1443 passed, 4 skipped, 2 warnings**. Última suíte final: **1493 passed, 4 skipped, 2 warnings em208,61s**, log `full-suite-delivery.log`, código1181c2e. Benchmarks congelados mantidos: **Search34/34, Shopping59/59, Experience16/16**; gabaritos não foram alterados. Focados cobriram restrições, cidades incompatíveis, datas, API qualificada, seleção após feeds, cache/SQLite, mídia, redação, autorização administrativa e isolamento.

Quatro skips conhecidos: verificação semântica LLM, inferência científica Hermes específica e dois casos externos de shopping sem resultados/bloqueados por 403/bot-wall. A sonda de modelo real desta etapa não transforma esses testes semânticos/científicos em aprovados. Dois warnings existentes: `mss.mss` e timeout do Starlette TestClient.

Falhas intermediárias preservadas: três regressões causadas por reformulação antes da consulta original; ajuste de recuperação de feed que rejeitava metadado incompleto; teste antigo que esperava aviso de job em vez de galeria; marcador digest ausente no novo retorno antecipado. A consulta original foi restaurada, o feed permaneceu recuperável, o marcador foi mantido e o teste de intenção visual passou a exigir resultado recuperado sem alegar geração/verificação. Nenhum teste foi removido. Erros do próprio harness (nome reservado request, caminho de teste inexistente, captura SSE aguardando fechamento e clique em menu oculto no desktop) também estão registrados, separados de bugs do produto.

## Evidência externa e modelo

Dois conjuntos com vinte categorias/perguntas distintas em `benchmarks/universal_search_v599.json`, preservando o benchmark congelado. Foram executados desenvolvimento e avaliação, mais uma rodada de avaliação com revisão registrada **31491a3**. As correções posteriores estão identificadas nos commits/E2E, portanto essa rodada não é apresentada como medição final de todos os patches seguintes.

Nessa avaliação externa: **20 casos,168 candidatos contabilizados por caso,50 fontes abertas,7 fontes lidas elegíveis pelo gate,0 ofertas confirmadas**, mediana **7,364 s**. Estados:3ok,1parcial,14sem_correspondencia,1paginas_ilegiveis e1sem estado padronizado de shopping. Há duplicação possível entre pesquisas; cinquenta leituras não equivalem a cinquenta fontes independentes. Conteúdo aberto não implica resposta correta. Recall absoluto, precisão independente, cobertura semântica e precisão de citações permanecem **não medidos**, não zero nem100%.

Uma sonda REAL_MODEL com modelo marcado `:free` recebeu47chunks públicos ordenados. A reprodução literal com citação falhou: inferência executada, qualidade parcial. A captura upstream de64KB contém somente contagens no artefato, sem raciocínio privado. Não houve modelo pago nem mudança nos limites de inferência do produto; o harness local bloqueia fallbacks para modelos pagos.

## O que apareceu no chat

Chrome com login QA, relay FastAPI, PC Agent/WebSocket e SQLite temporários. Dez cenários A–J executados; rodada com20mensagens,20IDs distintos,dez requisições concluídas e reload preservado. Modelos registrados no ai_requests são rótulos de configuração; não provam inferência quando o caminho foi determinístico. Casos críticos foram repetidos após correções; artefatos distinguem cada rodada.

- Município: uma fonte/manchete pertinente apareceu com janela explícita e estado de leitura. Não equivale a cobertura municipal completa nem leitura de todos os originais.
- Brasil hoje: fontes elegíveis ausentes em parte das rodadas; limitação preservada, sem substituir por notícias velhas.
- IA universal: relevância e redação mostraram fragilidade. Fontes não lidas permanecem descoberta; o gate final evita usá-las para uma síntese que simule leitura.
- Documentação: resposta TaskGroup e card oficial passaram a aparecer após os ajustes de ranking; leitura/citação de cada afirmação não foi auditada individualmente.
- Lenovo16GB/R$3000: nenhuma oferta individual confirmada; bloqueio do varejista reconhecido, sem preço inventado.
- Ponte Estaiada: cinco cards Commons, cinco imagens carregadas na inspeção visual final e persistência após reload.
- Vídeos: nenhum vídeo pertinente recuperado naquele ambiente; sem card/miniatura fictícios ou alegação de transcrição.
- História/comparação: resultados executados, mas síntese/afirmações não receberam aprovação factual independente.
- Escassez: ausência de confirmação não é prova de inexistência do objeto pesquisado; a saída deve permanecer limitada às fontes recuperadas.

UI:1280/390/320px sem overflow de página; zoom **CSS**200%; modal anterior/próxima/setas/Escape; foco restaurado; metadados recolhíveis e estado preservado após reload; movimento reduzido; cinco imagens carregadas e zero erros JS na rodada visual. Screenshots foram inspecionados. O primeiro screenshot mobile capturou a transição de fechamento do drawer; o harness final aguarda a posição fechada, sem alterar o produto para ocultar o problema.

Não foram medidos FPS, RAM/CPU de aparelho físico ou contraste por ferramenta especializada. Não houve aprovação visual de cards de vídeo/oferta ausentes, nem captura completa dos bytes SSE do app no navegador. Testes do protocolo, sonda upstream e observação da UI têm escopos diferentes. Não se somam FIXTURE/FROZEN_REPLAY/LIVE_EXTERNAL/REAL_MODEL/AUTHENTICATED_E2E em uma taxa única.

Scan dirigido de229arquivos contra sete valores secretos configurados: nenhuma coincidência; fontes/documentação examinadas passaram em UTF-8 estrito. Não é auditoria de todo o histórico. Logs originais mantêm whitespace de tracebacks; o diff --check de fonte/documentação passou. Nenhum SQLite, cookie ou segredo operacional foi exportado.

## Segurança administrativa

Revisadas as rotas legadas: a camada de reauth/autorização adicionada na etapa anterior já é usada por elas. Acrescentados17casos HTTP com corpos válidos para comprovar que um admin autenticado, mas sem autorização recente, recebe403. CSRF/origem, sessão, papel/status/aprovação, revogação, último admin, isolamento e remote_ok continuam cobertos pela suíte. Sem expansão de administração ou novas promoções reais.

## Arquivos e commits

Código: `query_intelligence.py`, `search_orchestrator.py`, `search_verticals.py`, `research.py`, `research_agents.py`, `research_view.py`, `media_evidence.py`, `conversation_followups.py`, `pc_agent.py`, `public/jdui.js`, `public/interface.css` e `.gitignore`.

Testes: `tests/test_universal_search_v599.py`, `tests/test_admin_route_gate_v599.py` e contrato visual atualizado em `tests/test_autonomous_research_v598.py`. Ferramentas: benchmark universal, coleta sanitizada, chat/visual QA e opção live do harness isolado existente. Documentação em `docs/v5.9.9/`; evidências em `qa-artifacts/v599/`. Metadados privados de runtime, bancos, cookies, chaves e backups não fazem parte da entrega versionada.

Commits de implementação:31491a3,96f0175,37afd55,83664b6,174411c,cb94da8,3fc21a1 e1181c2e. A documentação final registra o estado de validação sem reescrever esses commits. HEAD final da entrega é informado na resposta e conferível no Git local. Sem push.

## Pendências e próximo recorte

No inventário final foram observados dois processos apontando para o mesmo relay/SQLite de produção: wrapper PID13712 e processo legado PID31456, este filho do controle do Studio e iniciado às16:05:09UTC. Isso não é um segundo agente QA. Não se verificou qual conexão estava atendendo ao relay, nem se encerrou/reiniciou esses processos; a restrição desta tarefa proíbe restart de produção e alteração do Studio. Consolidar esse runtime numa etapa autorizada é uma pendência operacional independente da qualidade local. Os processos QA desta execução foram encerrados separadamente.

A missão universal permanece parcial. Priorizar agora descoberta temática de baixa cobertura e recuperação dos artigos originais que ficaram apenas em feed, usando os adaptadores/orçamentos existentes. Medir o ganho em fontes realmente lidas e em uma avaliação julgada, antes de ampliar provedores ou paralelismo. Validar um job profundo universal real completo, inclusive roteamento de pedidos explícitos de notícias profundas, replanejamento, cancelamento/reconexão e resultado no chat.

Também permanecem: desambiguação semântica ampla de homônimos; restrições negativas e preferências ainda não universais; navegação relacionada mais completa; documentos/páginas dinâmicas difíceis; ofertas/vídeos verificáveis; precisão factual/citações do modelo; teste de atualização de PWA já instalada e perfil mobile físico. A arquitetura científica existente foi preservada, sem evolução especializada nesta etapa.

Não publicar como “pesquisa universal concluída”. Esta entrega corrige causas e estabelece regressões/E2E reproduzíveis; não resolve a indisponibilidade legítima de fontes nem certifica a redação de todos os modelos.
