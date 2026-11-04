# Pesquisa — implementação e validação de 01/11/2026

## Resultado

Foram corrigidas falhas de seleção do modelo padrão e de apresentação de falhas
de inferência. Foram reforçados os contratos de citação e revisão. A leitura e a
descoberta funcionaram no cenário real de documentação Python; a síntese assistida
completa **não está aprovada**. Testes automatizados verdes não substituem esse
critério. Não houve publicação, reinício do agente de produção nem alteração de
credenciais nesta etapa. SearXNG não foi adicionado.

## Causas observadas e correções

1. O padrão implícito `poolside/laguna-s-2.1:free` estava ausente do catálogo real
   do proxy local. A falha de modelo era apresentada como resultado extrativo de
   pesquisa, dificultando distinguir recuperação de geração. Agora o padrão
   implícito consulta o catálogo por até dois segundos, com cache de 60 segundos,
   e usa somente um modelo gratuito efetivamente listado se o padrão desapareceu.
   Escolhas explícitas permanecem intactas. Não há seleção automática de pago.
   Falha do catálogo mantém o caminho original, sem inventar disponibilidade.
2. A causa da falha de inferência se perdia no fallback. Erros conhecidos agora
   produzem avisos específicos e seguros, preservando as fontes recuperadas.
   Nenhuma mensagem bruta do provedor ou chave é apresentada por essa camada.
3. A resposta real sobre estoicismo apresentou referência ausente e uma frase
   atribuída não sustentada pelo texto lido. A finalização de pesquisa agora
   verifica presença/identidade das referências, parágrafos longos sem citação e
   algumas formas de citação literal atribuída. Referências em código não contam.
   Páginas bloqueadas, não lidas ou irrelevantes não validam citações. Em caso de
   falha, são preservados o resumo determinístico e os links reais.
   Essa verificação é estrutural, **não é um verificador semântico universal**.
4. O revisor real repetiu um requisito no mesmo parágrafo, contrariando o
   validador existente. O prompt passou a explicitar unicidade por parágrafo e
   trecho literal contíguo. O validador não foi flexibilizado: duplicatas e
   paráfrases continuam sendo rejeitadas.

## Arquivos desta etapa

- `inference_status.py`: resolução limitada do padrão, diagnóstico e citações.
- `pc_agent.py`: integração nas respostas completas/stream e fallback.
- `research.py`: instrução de resposta factual concisa, citada por parágrafo.
- `research_synthesis.py`: contrato explícito do revisor.
- `tests/test_inference_availability.py`: disponibilidade, seleção explícita,
  gratuitidade, cancelamento, erros, preservação e validade de referências.
- `tests/test_research_review_contract.py`: unicidade e literalidade do revisor.
- `docs/RESEARCH_IMPLEMENTATION_PROGRESS.md`: retomada e limites da validação.

Patch somente desta etapa: `qa-artifacts/research-implementation.patch`,
validado contra um índice temporário de HEAD, sem alterar o índice compartilhado.

O workspace contém alterações paralelas de autenticação, frontend e PC Agent.
Elas foram preservadas. A validação isolada usa `dd6f5c4` mais somente os arquivos
e trechos desta etapa; não representa aprovação de todo o WIP compartilhado.

## Verificações reais A / B / C

Ambiente: aplicação completa local, conta/banco descartáveis, relay e PC Agent
de desenvolvimento, rede e modelos reais; sem fixture de busca. Produção não
foi usada como se já contivesse este código.

Pergunta: comparar `asyncio.TaskGroup` e `asyncio.gather`, incluindo cancelamento
e exceções, solicitando documentação oficial e sem fornecer URL.

- **A — leitura: aprovada neste cenário.** A página oficial
  `https://docs.python.org/3/library/asyncio-task.html` forneceu sete trechos sobre
  cancelamento, propagação de exceções e agrupamento em ExceptionGroup.
- **B — descoberta: aprovada neste cenário.** A documentação foi encontrada
  sem URL fornecida. Isso não comprova cobertura de todos os assuntos/lojas.
- **C — síntese: não aprovada.** Em aproximadamente 26,8 segundos, a UI concluiu
  com resultado extrativo e lacunas explícitas. O modelo Solar produziu revisão
  inválida; um replay controlado com Stepfun terminou por truncamento do modelo.
  Não houve troca para provedores pagos nem retries indefinidos para obter verde.
  Um card, seu link oficial e três mensagens persistiram após reload, sem erro
  de console no roteiro. Persistência aprovada não equivale a síntese aprovada.

Screenshots reais inspecionadas em 390px e 1280px:
`output/inference-completion/deep-reviewed-390.png` e
`output/inference-completion/deep-reviewed-1280.png`.
Registro: `output/inference-completion/deep-reviewed-ui.log`.

Limites dos roteiros: uma execução anterior contou zero cards porque o script
alterou indevidamente os seletores ao trocar nomes de imagens; outra capturou
o índice anterior durante a troca de conversa. Esses resultados não foram
tratados como defeitos do produto nem usados para declarar aprovação.

## Testes automatizados

- Focados finais das duas novas suites: **30 aprovados** (3,35s).
- Suíte isolada anterior ao último ajuste de referências e ao contrato do
  revisor: **2.362 aprovados, 4 pulados, 2 avisos** (461,36s).
- Suíte completa final isolada: **2.367 aprovados, 4 pulados, 2 avisos**,
  exit 0, em 259,42s. Log: `qa-artifacts/research-implementation-final-suite.log`.
  Os avisos preexistentes são de depreciação de mss/TestClient.
- `git diff --check` dos arquivos compartilhados alterados: sem erro de espaço.

## Pendências e próximo passo

1. Usar um modelo capaz de cumprir writer/reviewer com o orçamento atual, ou
   ajustar o formato/orçamento após medir a saída real. Disponibilidade no
   catálogo não garante qualidade. Reprovar afirmações sem suporte continua
   obrigatório. Não há aprovação para chamar custos adicionais silenciosamente.
2. Repetir C na interface e só depois ampliar os cenários independentes de
   compras/notícias. Validar URLs de produtos, preço lido, reload e cancelamento.
   Não foi comprovada nesta etapa uma compra real em KaBuM/Shopee/Mercado Livre.
3. Auditar a propagação da escolha de modelo do chat para o job profundo: o job
   usa configuração central. Esta etapa não altera o contrato de API/UI desse
   fluxo compartilhado com outras mudanças.
4. CAPTCHA e bloqueios externos continuam possíveis. Esta etapa não implementa
   bypass, não promete acesso a qualquer site e não transforma snippets em
   conteúdo supostamente lido. APIs/feeds/fontes alternativas autorizadas ainda
   precisam de validação por cenário quando a fonte original bloqueia leitura.


## Continuação de 02/11/2026

A aprovação seguinte foi implementada parcialmente: modelo do chat propagado
até o worker, reserva de tempo para síntese, trechos complementares preservados,
recuperação por cobertura incompleta, retomada de parciais, classificação
consistente de GPUs e catálogo de IDs literais para o revisor. Detalhes e
retomada em docs/RESEARCH_IMPLEMENTATION_PROGRESS.md.

As chamadas reais de redação/revisão ainda falharam. Não há aprovação nova de
síntese completa, UI, compras ou descoberta externa nesta continuação. Nenhum
push/deploy ou reinício de produção foi executado. Alterações paralelas foram
preservadas; a suíte desta continuação avalia o workspace combinado.


Validação final da continuação: **2.468 aprovados, 4 pulados, 2 avisos**,
exit 0 em 305,55s. Log: qa-artifacts/research-followthrough-final.log.
O teste adicional de reserva de tempo passou no grupo de 6 testes depois da
coleta da suíte completa. A primeira execução encontrou uma regressão de
retomada; a correção preservou o teste original, que voltou a passar.

Limite operacional: replays com modelo real ainda rejeitados por JSON/revisão
inválidos ou truncamento. Aumentar para 3.200 tokens apenas no ensaio permitiu
redação, mas não revisão válida. Não houve novo teste pela interface nesta
continuação. Próximo passo exato: diagnosticar saída e orçamento do revisor
com os metadados seguros, validar C e então repetir o percurso pela interface.

## Resultado da continuação com interface real — 02/11/2026

**Houve avanço operacional comprovado; o escopo completo ainda não está aprovado.**
Detalhes e continuidade em `docs/RESEARCH_IMPLEMENTATION_PROGRESS.md`, seção
"Continuação com navegador real". Nenhum push/deploy foi executado.

| Cenário real local | Antes | Depois | Limitação |
| --- | --- | --- | --- |
| Comportamento padrão de asyncio.gather com exceção, sem URL | Documento encontrado, mas descartado | Resposta citada, cobertura completa, 1 card persistido; 16,36s | Uma pergunta técnica aprovada, não avaliação universal |
| RTX 3050 6 GB à venda no Brasil | Zero evidências/cards | 6 fontes lidas, 6 cards, links diretos de produto; 26,07s | Preço atual não confirmado e síntese por IA expirou |
| TaskGroup versus gather, cancelamento/exceções | Falha de síntese | Documentação e card persistidos | Modelo ainda falha no formato/prazo; resultado parcial |

Nos fluxos acima, o navegador usou conta descartável com relay/agente reais,
busca externa e modelo real. Cards/mensagens foram comparados antes/depois do
reload; nenhum erro de console foi coletado durante os fluxos. Inspeção visual
incluiu captura mobile de 390px do caso completo. Não houve teste de produção
nem alegação de acesso universal a páginas bloqueadas.

Causas corrigidas: padrão removido do catálogo gravado automaticamente como
escolha explícita; JSON cortado no adaptador; falhas de leitura sem expiração;
relações de API não reconhecidas; cobertura contando parágrafos omitidos;
descoberta nativa de loja ausente no caminho profundo; palavras de apresentação
derrubando relevância de produtos. Acrescentada rejeição de modelo/VRAM de GPU
conflitantes. Formato pode ser corrigido uma vez, sem relaxar validação factual.

Arquivos desta etapa: `providers.py`, `public/app.js`, `pc_agent.py`,
`research_agents.py`, `research_synthesis.py`, `query_intelligence.py`,
`evidence_graph.py`, `search_providers.py`, `search_orchestrator.py` e testes
de propagação, contexto, recuperação, cobertura, relações e descoberta comercial.
Alterações de outras frentes no workspace foram preservadas.

Evidências principais: `qa-artifacts/research-recovery-real-summary.json`,
`research-recovery-simple-final-ui.log`, `research-recovery-shopping-final-ui.log`,
`research-recovery-comparison-grouped-ui.log`, `research-recovery-final.log`.
Não confundir a validação de links/fontes com confirmação de preços ou conclusão
da comparação. Próxima etapa: preço estruturado com proveniência até a resposta,
e síntese multiaspecto estável usando um provedor operacional.


## Atualização — 03/11/2026: ofertas lidas até resposta e JDUI

**Resultado comprovado:** a busca profunda por RTX 3050 6 GB no Brasil,
sem URL fornecida, encontrou e leu seis páginas de produto da KaBuM. Preços
extraídos do JSON-LD dessas páginas chegaram à resposta e aos seis cards.
A leitura observou R$ 1.399,99 a R$ 1.754,98 em 03/11; isso não é garantia
permanente de preço, estoque, checkout ou menor preço de todo o mercado.
Não houve solução de CAPTCHA nem tentativa de ignorar bloqueios.

Causas e correções:
- O leitor conservava a descrição, mas descartava a oferta estruturada.
  `research_product_evidence.py` reaproveita o HTML já baixado, sem nova chamada
  de rede, e exige produto compatível, URL do mesmo item, moeda explícita,
  preço positivo e uma oferta individual válida. Agregados, intervalo de
  ofertas, validade vencida, moeda ausente e páginas com challenge são rejeitados.
- Os campos declarados, hash, caminho `Product.offers`, URL e instante da leitura
  acompanham a evidência no SQLite e no contexto da síntese. O hash verifica
  integridade do registro, não certifica a veracidade comercial da loja.
- Falha do modelo deixava a resposta extrativa sem preço e escondia a oferta
  nos detalhes. Agora preço, disponibilidade declarada e horário aparecem
  diretamente na resposta e nos cards, sem duplicar o título nem expor JSON cru.
  Proveniência técnica permanece nos detalhes; normalização não é citação do DOM.
- Identidade, preço, estoque e data eram separados em quatro citações, acima
  do limite de três referências do parágrafo. O catálogo mantém uma oferta
  curta como unidade citável. Passagens de outros aspectos da mesma página
  continuam separadas, com offsets de origem preservados e limite de 1.800
  caracteres por fonte. Os gates numéricos, citações e revisão não foram removidos.

Validação operacional local:
- Busca pela interface: seis fontes/cards e três mensagens antes/depois do
  reload, sem erros de console; rodada final de compras em 36,46 segundos.
- Verificação adicional: os seis preços e links `/produto/...` permaneceram
  idênticos após reload; expansão dos detalhes também persistiu.
- Mobile 390 px: largura do documento 390 px e nenhum card com overflow;
  captura `output/playwright/research-product-card-390.png` inspecionada.
- Não houve teste de produção, push/deploy ou reinício do agente de produção.

**Limitação ainda aberta:** a redação do modelo gratuito continuou falhando
em formato, referências ou prazo. Replays controlados com evidências reais
reproduziram essas falhas. Ofertas lidas são utilizáveis sem essa redação, mas
isso não aprova a síntese autônoma universal nem a comparação multiaspecto.
Não declarar a pesquisa profunda integralmente concluída.

Arquivos desta etapa: `research_product_evidence.py`, `research_agents.py`,
`research_synthesis.py`, `research_view.py`, `public/jdui.js`,
`tests/test_research_product_evidence.py`, `tests/test_jdui_fontes_v57.py`.
WIP de outras frentes preservado. Evidências compactas:
`qa-artifacts/research-product-real-summary.json`; logs `research-price-*-ui.log`
e `research-price-contract-*.log`. Testes focados finais: 77 aprovados,
incluindo timeout do modelo, persistência, tampering, CAPTCHA, preço negativo,
moeda ausente, oferta vencida e conservação de outras passagens.


## Continuação — contrato de síntese e revisão (03/11/2026)

O replay de uma saída real mostrou seis parágrafos válidos rejeitados pelo teto
de cinco. Agora até oito candidatos podem ser agrupados em no máximo cinco
parágrafos: somente adjacentes com fonte em comum, até três referências e
650 caracteres. Cada candidato passa primeiro pelos gates individuais de
citação/número/unidade. A união não pode usar o trecho vizinho para justificar
um número antes sem suporte; nenhuma afirmação é apagada ou aprovada pelo
agrupamento. Depois, a revisão avalia o parágrafo inteiro; uma rejeição remove
todo o grupo. Casos não agrupáveis continuam exigindo reparo limitado do modelo.

A revisão real revelou requisitos repetidos apontando para trechos distintos.
O pedido de saída agora usa mapa requisito -> ID de trecho; o formato antigo
permanece compatível. IDs estrangeiros, duplicados e trechos de outro parágrafo
continuam rejeitados. Quando não há requisito explícito, não enviamos catálogo
de respostas vazio nem exigimos um campo sem finalidade. Esse ajuste reduz o
contrato, mas **não basta para garantir obediência do modelo**: o replay posterior
ainda devolveu JSON inválido. Isso permanece falha, sem aprovação automática.

Validação focada: 91 testes aprovados, incluindo junção sem perda, bloqueio de
empréstimo de números entre parágrafos, revisão negativa, IDs de outro parágrafo,
chaves JSON duplicadas e limite de referências/tamanho. Suíte completa anterior
a esta última revisão: 2.550 aprovados, 4 pulados, 2 avisos (204,63s).

Próximo passo exato: verificar suporte real a saída estruturada no transporte do
provedor/modelo gratuito e medir conformidade antes de ativá-la; ou qualificar
outro modelo gratuito já disponível. Não ampliar busca, aumentar retries sem
limite, usar modelo pago silenciosamente ou flexibilizar evidências para esconder
a falha do escritor/revisor. Também permanece revisar a exclusão de requisitos
por "video" em consultas de GPU (`query_intelligence.answer_requirements`).


### Fechamento da validação desta etapa — 03/11/2026

- Suíte completa do código final: **2.556 aprovados, 4 pulados, 2 avisos**,
  exit 0 em 251,40s (`qa-artifacts/research-recovery-1103-final-suite.log`).
  Avisos preexistentes: depreciações de mss e timeout no TestClient.
- `node --check` em app.js/JDUI e `git diff --check` nos arquivos desta etapa
  passaram. O WIP preexistente em app.js não foi normalizado nem revertido.
- Aplicação local nova, conta e SQLite descartáveis, rede/modelo reais:
  compras em 31,26s, seis fontes/cards; comparação em 20,92s, uma fonte;
  pergunta simples em 31,31s, uma fonte. Todos mantiveram três mensagens e a
  contagem de cards após reload, sem erros de console durante os fluxos.
- Compras e comparação ficaram **parciais**: formato da redação ainda falhou.
  O caso simples foi marcado completo pelo pipeline, com citações/persistência,
  mas a inspeção humana encontrou redação confusa no primeiro parágrafo.
  **Não aprovar qualidade geral de C só pelo estado complete ou pela suíte.**
- Resumo auditável: `qa-artifacts/research-1103-final-real-summary.json`.
  O laboratório novo foi encerrado verificando PID, cwd, role development,
  SQLite isolado e zero operações ativas; somente seus dois processos e sua
  sessão de browser foram fechados. Nenhuma ação no agente de produção.
- Sem commit, push ou deploy. Próxima etapa permanece a conformidade/qualidade
  do modelo usado para redação e revisão, com aceitação por respostas reais.


## Saída estruturada e orçamento do modelo — 03/11/2026

Implementado o próximo passo no transporte e na revisão. O cliente antes enviava
somente model/messages/max_tokens. Agora a pesquisa envia JSON Schema estrito
apenas quando o catálogo público do proxy declara response_format e
structured_outputs. Modelos sem essa informação continuam no protocolo anterior.
A descoberta tem timeout de um segundo, cache limitado e entra no prazo da chamada.
O modelo escolhido é preservado; não há seleção silenciosa de modelo pago.

`research_output.py` constrói schemas limitados a seis fontes: IDs de citações
são vinculados aos IDs de trechos de sua própria fonte; revisão exige enums,
parágrafos e estrutura conhecidos. null em um requisito significa ausência de
resposta, sem cobertura. Gates locais de número/unidade, literalidade, identidade,
revisão negativa e persistência continuam aplicados depois do JSON.
Para raciocínio obrigatório, usa low somente se o próprio catálogo declara
suporte; o limite permanece 1.800 tokens. Chat comum mantém sua configuração.

A carga do revisor foi compactada: hashes e árvores de offsets permanecem na
proveniência, enquanto o modelo recebe a ligação validada entre assinatura de
seção e trecho. Cabeçalhos de tabela também são mantidos. Hash divergente ou
assinatura posterior ao trecho não gera contexto de API. Nos ensaios, o contexto
da revisão caiu de cerca de 7.741 para 3.960 tokens; não é benchmark universal.

Verificação real local com Reflection gratuito escolhido explicitamente pela
interface: comparação TaskGroup/gather gerou síntese citada em 26,39s; compras
RTX 3050 6 GB gerou síntese com seis ofertas em 23,14s. As três mensagens e a
contagem de cards persistiram em ambos, sem erros de console. Os preços foram
conferidos contra os campos JSON-LD salvos, incluindo mudanças de preço da loja
entre rodadas. URLs continuam sendo páginas /produto/. Verificação adicional
conferiu preço/link após reload, detalhes expandidos e largura mobile de 390 px.
Capturas de comparação e card mobile foram inspecionadas.

**Limites:** ambos os trabalhos ainda foram marcados partial pela cobertura.
Há avanço real na redação, mas não aprovação universal da pesquisa profunda.
Solar gratuito também passou o formato com schema; rejeitou suporte nos ensaios.
Reflection foi qualificado nestes cenários, sem alterar o padrão global do usuário.
Redação ainda tem detalhes editoriais a refinar (por exemplo, "relevantada").

Arquivos desta etapa: `research_output.py`, `hermes_bridge.py`, `pc_agent.py`,
`research_synthesis.py`, `tests/test_research_structured_output.py`.
Artefatos: `research-structured-real-summary.json`, logs `research-structured-*.log`
em qa-artifacts. Referência de protocolo:
[documentação oficial do OpenRouter](https://github.com/OpenRouterTeam/docs/blob/main/guides/features/structured-outputs.mdx)

Próximo passo: separar falhas reais de cobertura de perdas na vinculação dos
aspectos à resposta já revisada, com negativos de entidade/variante e leitura
manual; revisar também a exclusão indevida de requisitos por "video" em GPUs.
Não aprovar complete pela mera presença de texto ou cards.


Validação final desta etapa: **2.569 testes aprovados, 4 pulados, 2 avisos**,
exit 0 em 279,31s (`qa-artifacts/research-structured-final-suite.log`). Os avisos
continuam sendo as depreciações de mss e timeout no TestClient. Compilação dos
quatro módulos alterados e diff-check dos hunks rastreados passaram.
O laboratório foi encerrado por IPC após verificar role development, PID, cwd,
SQLite descartável e zero operações ativas; somente seu relay e browser foram
fechados. Sem commit/push/deploy ou reinício do agente de produção.


## Correção de cobertura por aspecto — 03/11/2026

Causa reproduzida em resposta/revisão reais persistidas: o parágrafo sobre
ExceptionGroup começava com "Após todas as tarefas terminarem", sem repetir
TaskGroup. Mesmo revisado como SUPPORTED, perdia a ligação com a entidade.
A resolução de sujeito implícito agora exige que TODAS as citações do parágrafo
pertençam inequivocamente à mesma assinatura de API, em fonte primária lida,
com hash e limites de seção coerentes. Outra API, escopo ambíguo, nome de API
inventado, restrição numérica ou ausência de autoridade mantém a lacuna.
Comportamento de exceção/cancelamento precisa continuar presente no texto.
A rotina é usada somente depois da revisão do parágrafo; títulos isolados
não aprovam afirmações e não se aproveita o parágrafo vizinho.

Também corrigida a exclusão de requisitos por "placa de vídeo": agora usa a
mesma distinção entre hardware e mídia já existente no roteamento. O pedido de
preço volta a ter requisito explícito; fotos/vídeos reais continuam sendo galeria.
Isso não confirma automaticamente preço, variante, país ou URL de produto.

Replay causal do mesmo texto/citações/revisão: cobertura completa False -> True,
com quatro aspectos técnicos e autoridade suportados. Esse replay NÃO é uma
nova chamada ao modelo. Evidência: `qa-artifacts/research-coverage-real-replay.json`.
Focados: 84 aprovados, incluindo negativos de entidade, ambiguidade, hash,
restrição numérica, autoridade, atributo diferente e galeria. Arquivos desta
etapa: `research_synthesis.py`, `query_intelligence.py`,
`tests/test_research_coverage_binding.py`.


Validação nova pela interface local (rede/modelo reais, conta descartável):
- Comparação TaskGroup/gather: 36,50s, resposta revisada, quatro aspectos técnicos
  e autoridade da documentação suportados, resultado complete. Uma fonte/card e
  três mensagens idênticos após reload; zero erros de console. Texto e captura
  mobile de 390 px inspecionados.
- Compras RTX 3050 6 GB: 36,07s, resposta assistida e seis ofertas, mantendo cards,
  preços e links diretos após reload, zero erros de console. Resultado continua
  partial: o parser ainda conserva toda a frase como entidade do requisito de
  preço. Essa lacuna não foi promovida artificialmente a suporte.
- A verificação adicional preservou detalhes expandidos e ausência de overflow.
Resumo: `qa-artifacts/research-coverage-real-summary.json`.

Próximo passo exato: decompor a identidade do produto e as restrições comerciais
sem apagar variante, VRAM, país, atualidade ou necessidade de link direto; testar
negativos antes de permitir cobertura comercial completa. A melhora comprovada
nesta etapa é a atribuição de sujeito implícito em API e o reconhecimento do
requisito de preço para hardware, não a solução universal de compras.
Laboratório encerrado com validação de PID/role/cwd/SQLite e zero operações
ativas. Sem commit/push/deploy ou ações no agente de produção.


Fechamento desta correção: **2.592 testes aprovados, 4 pulados, 2 avisos**,
exit 0 em 277,83s (`qa-artifacts/research-coverage-final-suite.log`). Os avisos
são as depreciações já conhecidas de mss e timeout no TestClient. Compilação de
query_intelligence/research_synthesis e diff-check dos arquivos alterados passaram.
Nenhum teste foi eliminado; WIP de outras frentes preservado.


## Testes variados — 03/11/2026

Oito consultas reais em seis temas: uma atendida, uma parcial, seis falhas.
Problemas de roteamento, descoberta/seleção e síntese comum continuam.
Ver `RELATORIO_TESTES_REAIS_PESQUISA_VARIADA.md` e
`qa-artifacts/research-varied-real-summary.json`.
Nenhuma alteração de código/publicação nesta rodada; não generalizar os
cenários positivos anteriores para a pesquisa em geral.

## Correção das falhas variadas — 04/11/2026

Foram implementadas e testadas as correções de roteamento, entidades/aspectos,
contexto das subconsultas, seleção do documento completo, aliases de APIs no DOM,
leitura de links internos, capacidade em TB, ofertas factuais e isolamento dos
cards por conversa. O transporte de síntese ganhou uma recuperação única para
conteúdo nulo com JSON Schema anunciado, preservando modelo, limites e validação.

Arquivos centrais: `pc_agent.py`, `query_intelligence.py`, `web_extract.py`,
`evidence_graph.py`, `research.py`, `research_agents.py`, `python_docs_discovery.py`,
`shopping.py`, `hermes_bridge.py` e `tests/test_varied_research_repairs.py`.
As dependências de pesquisa pendentes desta sequência incluem `inference_status.py`,
`research_output.py`, `research_product_evidence.py`, síntese/proveniência, seleção
de modelos e apresentação dos resultados. A publicação exclui o WIP de outras
frentes; o conjunto completo de caminhos consta no commit.

O relatório `RELATORIO_TESTES_REAIS_PESQUISA_VARIADA.md` registra causas,
regressões corrigidas, testes reais, suítes, arquivos, limitações e pendências.
Não houve declaração de sucesso universal: continuam lacunas de fonte primária,
atribuição de fundador, retorno de operações e cobertura integral da síntese.
