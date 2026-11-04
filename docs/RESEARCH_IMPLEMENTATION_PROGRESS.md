# Pesquisa — progresso de implementação (atualizado em 03/11/2026)

## Estado mais recente

Ofertas estruturadas já chegam à resposta e ao JDUI com preço, moeda, estoque
declarado, URL direta e horário da leitura. Seis ofertas reais da KaBuM foram
validadas na interface local e preservadas após reload. A comparação técnica já concluiu os aspectos pedidos; compras continua parcial; não houve push/deploy.

A proteção final de passagens de outros aspectos foi validada na suíte completa:
2.543 aprovados, 4 pulados, 2 avisos (179,98s), antes das melhorias posteriores
de formato/revisão abaixo. Os registros antigos são históricos, não o estado atual.

## Histórico — 01/11/2026

Código aplicado; validação automatizada final concluída. Síntese real não aprovada. Não houve commit/push/deploy.
Relatório: `RELATORIO_IMPLEMENTACAO_PESQUISA.md`.

- Modelo implícito removido do catálogo: resolução limitada a modelo `:free`
  realmente listado, cache de 60s, sem alterar seleção explícita ou usar pagos.
- Causa segura de erro preservada no fallback; fontes continuam disponíveis.
- Citações checadas contra fontes lidas/relevantes; código não vale como referência.
- Prompt do writer/reviewer alinhado com o contrato literal, sem afrouxar validação.
- 30 testes focados finais passaram. Suíte completa final isolada: 2.367 passaram,
  4 pulados, 2 avisos, exit 0, em 259,42s. Log:
  `qa-artifacts/research-implementation-final-suite.log`.

## Verificação operacional

Aplicação completa local com conta/SQLite descartáveis e rede/modelos reais.
A/B aprovados somente para a comparação de TaskGroup/gather: documentação
oficial encontrada sem URL e sete passagens pertinentes lidas. C não aprovado:
modelo Solar produziu revisão inválida, Stepfun truncou a saída no replay.
Card oficial e três mensagens persistiram após reload, sem erros de console.
Capturas de 390px/1280px inspecionadas; resultado é extrativo, com lacunas.
Não declarar pesquisa profunda universalmente aprovada nem leitura de lojas.

Laboratório e browser já encerrados com verificação de PID/role/cwd e IPC.
Produção não foi reiniciada. Credenciais descartáveis continuam apenas no
laboratório privado `~/.julia-mobile/ops-research-completion-20261101`.

## Isolamento do WIP

O workspace tem mudanças paralelas de auth/frontend/PC Agent. Não incluir ou
reverter essas mudanças. O snapshot privado contém HEAD `dd6f5c4` mais somente
os hunks desta etapa. Patch isolado, validado contra índice temporário de HEAD:
`qa-artifacts/research-implementation.patch`.

## Próximos passos exatos

1. Testes e relatório concluídos. Preservar a distinção entre suíte verde e
   síntese real reprovada.
2. Reprovar publicação como conclusão de pesquisa profunda até C passar.
3. Medir geração/revisão com modelo capaz no orçamento autorizado, preservando
   detecção de truncamento, literalidade e revisão independente; depois repetir
   C pela interface, reload e cancelamento, e ampliar cenários de compras/notícias.
4. Conferir propagação da escolha de modelo do chat ao job profundo, que usa
   configuração central. Essa integração não foi alterada nesta etapa.

Não reexecutar `integrate.py`/`grounding.py`: já aplicados. Não imprimir
`current.json` ou dados privados. Não presumir que processos antigos continuam
ativos; validar estado fresco antes de qualquer ação operacional.


## Continuação autorizada — 02/11/2026

Implementado no workspace compartilhado, sem publicação:

- Modelo escolhido no chat segue para o job, é validado/persistido em ajustes
  e usado pelo worker; seleção explícita desativa substituição de modelo.
- API de início também aceita model. Jobs antigos conservam padrão central.
- Reserva de 35% do prazo (máximo 40s) para síntese/revisão. Leituras e
  replanejamento respeitam o prazo reservado, sem aumentar o prazo total.
- Resultado parcial concluído pode ser retomado explicitamente, preservando
  evidências e liberando nova síntese. Retomada antiga entre conversas do mesmo
  dono foi preservada após regressão detectada pela suíte.
- Pesquisa comum transporta trechos complementares, até 3.600 caracteres por
  fonte, e pode recuperar fontes quando ainda há aspectos sem resposta.
- Progresso por requisito também impede parada prematura por zero novos IDs.
- Classificação de mídia no controlador usa o mesmo helper que exclui GPUs.
- Revisor pode selecionar trechos literais da resposta por IDs locais ao
  parágrafo; IDs desconhecidos/cruzados e requisitos duplicados continuam
  rejeitados. Formato literal anterior permanece validado para compatibilidade.

Novos testes: tests/test_research_followthrough.py e casos adicionais em
 tests/test_research_review_contract.py. Focados: 122, 46, 58 e 33 passaram
 nas respectivas execuções; teste adicional de reserva passou no grupo de 6.
Primeira suíte completa: 2.463 passaram, 1 regressão de retomada, 4 pulados.
A regressão foi corrigida, com 40 focados aprovados; suíte final concluída:
2.468 passaram, 4 pulados, 2 avisos, exit 0 em 305,55s, no log
qa-artifacts/research-followthrough-final.log. O teste adicional da reserva de
tempo também passou no grupo de 6 testes após a coleta da suíte final.

Replays reais, somente evidência pública do laboratório anterior, não testes
novos de descoberta/UI: modelo padrão falhou no schema do revisor; após
ajuste do contrato, ocorreu JSON inválido na redação. Reflection gratuito,
confirmado no catálogo local, truncou com 1.800 tokens. Ensaio com 3.200 tokens
apenas no processo QA permitiu gerar a candidata, mas a revisão ficou indisponível
(semantic_review_unavailable); log research-reflection-3200-model.log.
O limite de produção continua 1.800: não adotar ajuste sem aprovação de C.
Não alterar o padrão do produto por um único sucesso ou afrouxar evidências.

Próximos passos: concluir calibração writer/reviewer, conferir suíte final,
repetir A/B/C na interface e então seguir recuperação por domínio/extração
comercial. O adapter providers.py ainda corta conteúdo de mensagens em 12 mil
caracteres; avaliar empacotamento estrutural antes de usar provedores externos
com payload de pesquisa grande. Não publicar como pesquisa universal aprovada.


Retomada técnica prioritária: examinar metadados seguros da chamada de revisão
(finish_reason, usage, tempo, código) e empacotamento de payload por provedor.
O teste de catálogo de spans reduziu cópia de texto, mas o modelo real ainda
retornou revisão inválida. Preservar rejeição de IDs/trechos sem suporte.
O ensaio com maior saída foi somente monkeypatch no processo QA; não confundir
com alteração do produto. A regressão da retomada foi corrigida sem modificar
nem apagar o teste. Teste integrado adicional confirmou reserva de 10s para
síntese quando a etapa de busca consumiu 20s de um job de 30s.

## Continuação com navegador real — 02/11/2026

Estado: implementado localmente; **aceitação geral ainda parcial**. Sem push,
deploy ou reinício do PC Agent de produção. Conta/SQLite/runtime descartáveis,
relay e agente locais reais, pesquisa externa e modelo real; sem respostas mockadas
nos ensaios de navegador. Não publicar como pesquisa universal concluída.

Correções adicionais:

- `providers.py`: preserva mensagens JSON inteiras, substituindo corte silencioso
  em 12.000 caracteres por rejeição explícita acima de 64.000 por mensagem,
  128.000 por pedido ou 64 mensagens. Catálogo não recomenda padrão removido
  quando existe opção gratuita real na lista. Não migra escolhas explícitas.
- `public/app.js` / `pc_agent.py`: padrão automático não vira escolha persistida
  no navegador nem seleção explícita no job. Escolha fora do catálogo mostra
  indisponibilidade. Modelo escolhido pelo usuário continua respeitado.
- `research_synthesis.py`: uma correção de formato por fase, dentro do prazo
  original; contratos de fonte, citação, quantidade e revisão permanecem.
  Resposta vazia não gera retry. Truncamento/filtro do revisor mantém causa segura.
- `research_agents.py`: falhas de leitura expiram (rede 60s; bloqueio 600s).
  Reload comum respeita espera; retomada explícita libera tentativas sem zerar
  páginas/tempo. Cobertura associa parágrafos publicados às revisões originais
  via proveniência; parágrafos rejeitados permanecem na auditoria.
- `query_intelligence.py` / `evidence_graph.py`: exceção no singular e relações
  de execução/espera/propagação passam a ser reconhecidas. Testes negativos
  preservam vínculo com a API nomeada; não admitem a função errada.
- `search_providers.py` / `search_orchestrator.py` / `research_agents.py`:
  pesquisa profunda reutiliza descoberta pública KaBuM já existente e prioriza
  caminho especializado em compras. Descoberta não vira preço/oferta verificada.
  Instruções como "preço atual e link direto do produto" não contam como palavras
  que a página precisa repetir. Modelo de GPU e VRAM explicitamente conflitantes
  são rejeitados; comparações mantêm tratamento separado.

Evidência real, não somente contagem de testes:

1. **Antes:** default antigo `poolside/laguna-s-2.1:free` era gravado automaticamente
   pelo frontend e enviado como explícito ao job; modelo não encontrado.
2. **Leitura:** pergunta sobre comportamento/exceção de `asyncio.gather` descartava
   documentação já lida. Replay da extração real passou de zero para quatro
   passagens pertinentes após correção de relações linguísticas.
3. **Descoberta + síntese + persistência:** pergunta sem URL sobre exceção padrão
   de `asyncio.gather`, documentação oficial, passou pela UI em 16,36s: resposta
   assistida citada, cobertura final `complete`, 1 card/3 mensagens antes e após
   reload, zero erros de console coletados durante o fluxo. Capturas 390/1280.
4. **Comparação mais complexa:** TaskGroup versus gather encontra/lê documentação,
   mas as tentativas reais ainda terminaram em formato inválido ou timeout.
   Resultado extrativo e card persistem. C não aprovado nesse cenário.
5. **Compras:** RTX 3050 6 GB no Brasil passou de zero para seis fontes lidas/cards,
   com links `kabum.com.br/produto/...` preservados após reload (26,07s; zero erros
   de console). **Preço atual e síntese completa não aprovados**: redação atingiu
   timeout. Esse resultado melhora A/B, não aprova C/compras integralmente.

Artefatos: `qa-artifacts/research-recovery-real-summary.json`, logs
`research-recovery-simple-final-ui.log`, `research-recovery-shopping-final-ui.log`,
`research-recovery-comparison-grouped-ui.log`, capturas em
`qa-artifacts/research-recovery-browser/` e `output/synthesis-completion/shopping-live-*.png`.
Um ensaio intermediário `single-ui` sofreu conversão de encoding no script QA e
não representa o cenário menor; usar `simple-final-ui` como evidência válida.

Provedores configurados, diagnóstico pontual (não promessa de disponibilidade):
Upstage gratuito respondeu no cenário menor; maior cenário apresentou formato/
prazo instáveis. StepFun truncou saída a 1.800 tokens; Gemini teve erros de modelo/
provedor; Mistral limite de uso; DeepSeek sem cota. Não houve troca automática
para modelos pagos nem exposição das chaves. Limite de produção segue 1.800.

Testes novos: `test_research_format_recovery.py`, `test_research_operation_relations.py`,
`test_research_published_coverage.py`, `test_research_store_adapter.py`; ampliados
providers, failed_reads e followthrough. A primeira suíte encontrou retry indevido
para `{}`; corrigido preservando o teste original. Focados recentes: 49 cobertura,
58 propagação de modelo, 46 relações, 27 compras/orquestrador aprovados.
Suítes intermediárias: 2.498, 2.510, 2.517 e 2.520 aprovados; cada uma antecede
mudanças posteriores. Resultado final deve ser lido em `research-recovery-final.log`.

Próximo passo exato: transportar preço/oferta realmente extraídos da página de
produto para evidência estruturada e para a síntese/JDUI, preservando moeda,
variante, disponibilidade, URL direta, origem do campo e momento da leitura.
Depois reduzir perdas de formato/latência na comparação multiaspecto com o
provedor real, repetir UI de compras/comparação e exigir C aprovado. Não resolver
com preço de snippet, suposição, relaxamento de evidência ou simples aumento de testes.


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

## Recuperação das consultas variadas — 04/11/2026

Implementados: reconhecimento de comandos profundos, separação de entidade e
aspectos, contexto nas subconsultas, varredura do contêiner principal antes do
recorte, aliases reais do DOM em APIs, prioridade para links internos de história,
exclusão de navegação editorial da Wikipédia, armazenamento em TB e resposta
factual de ofertas verificadas. Cards históricos agora respeitam o chat e não
contaminam uma nova busca.

Diagnosticado com chamadas reais: JSON Schema anunciado pelo gateway pode
retornar conteúdo nulo. Há recuperação única no mesmo modelo, dentro do prazo,
mantendo esforço de raciocínio anunciado e todas as verificações locais. Recusa,
filtro, truncamento e limites do provedor não disparam recuperação. Redação e
revisão reais passaram nesse caminho; cobertura incompleta continua explícita.

Relatório detalhado: `RELATORIO_TESTES_REAIS_PESQUISA_VARIADA.md`.
Matriz real: `qa-artifacts/research-varied-repair-release.json`.
Workspace e conteúdo publicável foram testados separadamente, pois existem
alterações pendentes de outras frentes. Não reiniciar o agente de produção como
parte do QA; somente os processos descartáveis deste laboratório são gerenciados.

Próximo passo exato: resolver as lacunas restantes da matriz sem enfraquecer os
validadores: localizar a fonte do fundador da Embraer; descobrir fonte primária
para criador/finalidade de Rust; selecionar a passagem que documenta o retorno
dos métodos de lista no Python; confirmar a síntese completa em outra pergunta
de matemática. Repetir leitura, descoberta e
síntese separadamente e novamente pela interface, preservando reload e links.
Não classificar esta etapa como pesquisa universal completa.

Fechamento real desta rodada: matemática completou enunciado + fórmula + exemplo
numérico, com cinco fontes lidas, revisão e persistência. A matriz consolidada
tem três pedidos atendidos e cinco parciais; oito preservados após reload,
zero erros de console capturados e zero overflow em 390 px. As pendências de
Embraer, Rust e Python continuam; para matemática, o próximo teste deve usar
outra pergunta/fonte, sem reapresentar o cenário aprovado como avanço novo.
IDs do histórico de compras ganharam 128 bits após colisão revelada pela suíte.

Integração final com o main remoto (PC Companion preservado): 2.633 aprovados,
4 pulados e 2 avisos; exit 0 em 220,63 s. Log em
`qa-artifacts/research-merged-release-suite.log`. Árvore combinada testada em
exportação isolada. WIP local preservado; laboratório encerrado com validação
de identidade e zero operações ativas. Não houve reinício do agente de produção.

## Leitura complementar — 04/11/2026

Corrigidas perdas de campos de tabelas no ranking e no filtro final de fontes,
títulos genéricos, descarte de regra geral de retorno na síntese, APIs curtas,
remoção de pontos/linguagem das subconsultas e localização do retorno passivo.
Preferências oficiais/primárias preservadas sem duplicação; a busca de autoridade
é priorizada nas lacunas sem substituir o contexto inicial. Cache interno de
leitura: `5.9.9.9-complementary-reading-1`; históricos preservados.

Sete testes reais pela interface, sete persistidos após reload, zero erros de
console capturados e zero overflow em 390 px. Cliques reais abriram o artigo da
Embraer e a referência `list.pop`, sem redirecionar para a home. Os casos da
Embraer passaram a mostrar fundador/data; Python preserva contexto e recupera
o item retornado por pop. Não promover a regra geral None a prova de cada API.

Limite atual: Hermes com erro de autenticação, modelo gratuito antigo ausente
do catálogo e DeepSeek com cota esgotada. A tentativa Mistral ficou parcial.
Leitura/descoberta avançaram; síntese assistida não foi aprovada nesta rodada.
Relatório: `RELATORIO_LEITURA_COMPLEMENTAR.md`; dados:
`qa-artifacts/research-complementary-reading-real.json`.

Próximo passo: repetir a síntese com modelo/cota válidos; registrar a causa
precisa da geração/revisão Mistral; comprovar aplicação da regra de retorno aos
métodos; recuperar fonte primária para o criador de Rust. Preservar os testes
negativos e os critérios de autoridade. Não reiniciar o agente de produção.

Suíte final desta etapa: 2.669 aprovados, 4 pulados e 2 avisos; exit 0 em
198,20 s, em `qa-artifacts/complementary-reading-verified-full.log`.
Diff-check passou. Código enviado a `origin/main` em `d2fcdb5`, com hash remoto
conferido; implantação no Render não foi verificada. Antes do envio, a árvore
selecionada foi exportada do índice sem o WIP alheio e aprovada em suíte completa:
2.644 aprovados, 4 pulados e 2 avisos, exit 0 em 304,84 s
(`qa-artifacts/complementary-reading-publish-isolated.log`). Os 2.669 anteriores
referem-se ao workspace com outras alterações locais, preservadas sem envio.

Diagnóstico de acesso: REST pública do Ubatã entregou conteúdo de um post;
uma página exata KaBuM foi lida; API Mercado Livre sem token retornou 403,
sem comprovação de CAPTCHA. Plano em `docs/RESEARCH_ACCESS_RECOVERY_PLAN.md`:
primeiro separar erros e coordenar requisições por origem; depois aproveitar
o canal WordPress. Firecrawl anônimo atual não atende ao contrato de autenticação
documentado. Nenhuma nova integração paga foi ativada; o PC Agent não foi
reiniciado. Próxima implementação de acesso e nova validação da síntese pendentes.

## Coordenação por origem e leitura de notícias — 04/11/2026

Implementados localmente `read_access.py` e `publisher_reader.py`: limites por
origem, junção de downloads simultâneos, motivo HTTP específico, Retry-After,
cancelamento em fila e REST pública de Ubatã. Redirects coordenados no destino;
SSRF/isolamento preservados. Corrigidos achados reais: crédito “Ubatã Notícias”
tratado como local e “mostre as fontes” absorvido pelo nome da cidade.

Interface comum: pergunta antes sem fontes agora tem artigo regional lido,
card persistido e clique abrindo o artigo exato. Profunda: seis fontes lidas,
nove evidências, mas redação bloqueada por cota DeepSeek; fallback sem cards
de fonte nesta resposta. Não marcar a síntese/experiência profunda como aprovada.
Reload, console após login e overflow 390 px verificados nos dois casos.
Laboratório privado encerrado com validação de identidade e operações zeradas;
produção preservada. Dados/limitações em `RELATORIO_ACESSO_PESQUISA.md`.

Fechamento: suíte completa isolada sem WIP alheio, 2.697 aprovados, 4 pulados,
2 avisos; exit 0 em 452,02 s. Log: `qa-artifacts/origin-access-final-isolated-suite.log`.
Uma execução isolada intermediária foi interrompida para incluir a regressão
final de preservação de parágrafos; não conta como aprovação. O workspace havia
passado com 2.720 testes antes dos dois ajustes finais. Não somar os conjuntos.
Hashes do código/testes conferidos com a exportação final; diff-check passou.

Próximo passo exato: implementar cache público com revalidação e testar síntese
com modelo operacional; conferir os cards do fallback profundo antes de aprovar C.
Somente uma linha nova em `tests/conftest.py` pertence a esta etapa; preservar
as demais alterações preexistentes nesse arquivo. Ainda sem novo push desta rodada.
