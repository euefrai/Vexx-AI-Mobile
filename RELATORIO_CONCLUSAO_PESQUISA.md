# Continuação: síntese e conclusão da pesquisa — 29/10/2026

Esta etapa retoma a pendência identificada em `RELATORIO_TESTES_REAIS_UI.md`.
O usuário autorizou publicar na `main` os ajustes desta etapa e da interface.

## Causas corrigidas

- **Prazos da revisão:** a redação podia consumir o tempo necessário à revisão
  separada. A pesquisa passa a ter um par de chamadas limitado a 50 segundos:
  até 25 para escrever e até 25 para revisar, respeitando o prazo restante do
  job e cancelamento. A função genérica mantém seu padrão anterior de 25/12 s.
  Não foram adicionados retries automáticos nem varredura de outros modelos.
- **Trechos técnicos perdidos:** assinaturas isoladas disputavam espaço com o
  texto explicativo; métodos aninhados podiam manter o escopo indevido após seu
  término. O leitor usa a árvore real de definições e a assinatura única da
  mesma seção. Se houver ambiguidade, não presume a identidade da API.
  O catálogo enviado ao modelo também mantém a assinatura literal verificada
  separada do quote: o sujeito não se perde entre extração e redação.
- **Casos especiais substituindo a regra geral:** a seleção prioriza o padrão
  documentado e permite passagens complementares por aspecto, mantendo os
  limites de oito passagens e 1.800 caracteres por fonte no contexto do modelo.
- **Autoridade sempre pendente:** para as APIs Python reconhecidas, a identidade
  da página lida é confrontada com o inventário Sphinx oficial, incluindo
  projeto, nomes, caminho e hash do inventário. Domínio, título ou booleano
  fornecido pelo modelo continuam insuficientes. Outros assuntos/publicadores
  não recebem automaticamente essa comprovação.
- **Proveniência perdida no caminho:** a comprovação agora acompanha tanto a
  evidência em memória quanto sua versão persistida e o contexto da síntese.
  A validação de autoridade permanece separada do texto produzido pelo modelo.
- **Falha real de persistência:** um registro com sete passagens chegava a
  20.153 caracteres e excedia o limite de 12 mil. A representação agora fatora
  atributos repetidos de documento, seções e offsets; o mesmo registro ficou
  com 10.342 caracteres e foi restaurado exatamente, sem truncamento, descarte
  de passagens ou aumento do limite SQLite/JSON.
- **Formato do modelo:** identificadores técnicos em código inline podem ser
  convertidos em texto simples; HTML e código arbitrário continuam rejeitados.
  `answers: []` em um parecer que não publica conteúdo é normalizado, mas
  afirmações de cobertura nesse parecer continuam inválidas. Uma lista de
  pontos vazia tem diagnóstico próprio, separado de erro do provedor.
- **Falsas lacunas após uma resposta validada:** a resolução de sujeitos
  implícitos limita-se a APIs primárias verificadas, exigindo simultaneamente
  nome exato na resposta, trecho literal, assinatura real da API, proveniência
  compatível e revisão separada aprovada com um trecho da própria resposta.
  Restrições numéricas/de versão, tabelas genéricas e contexto sem comprovação
  continuam parciais. Lacunas lexicais preliminares só deixam de impedir a
  conclusão quando todos os requisitos da resposta final passam nessas regras.
- **Falso positivo reproduzido na interface:** uma resposta com dois parágrafos
  de cancelamento foi considerada pelo revisor como resposta também às exceções.
  A validação agora exige uma relação explícita de propagação, agrupamento,
  lançamento ou tratamento de exceções tanto na resposta quanto no trecho
  citado. A simples menção a `CancelledError` não preenche esse aspecto. O caso
  foi incorporado às regressões negativas, sem aceitar a avaliação indevida.

O cache de extração foi versionado para não reutilizar a representação anterior.
Nenhum conteúdo externo ou código do modelo é executado por esse fluxo.

## Validação

- **166 testes focados passaram**, incluindo casos negativos de autoridade,
  assinatura, versão, resposta omitida, HTML/código e limites de tempo.
- A mudança intencional do prazo foi acompanhada de verificação de limites por
  etapa e soma máxima de 50 segundos. Os casos semânticos congelados conservam
  as mesmas decisões de suporte, contradição e insuficiência.
- O teste de metadados compara a estrutura original e restaurada, incluindo
  todas as passagens, IDs e offsets, sob o limite de persistência existente.
- A validação real usa a aplicação local completa, rede pública e o modelo
  gratuito configurado, por meio do roteiro `tools/live_research_completion.cjs`.
  Os resultados finais da interface e da suíte completa são registrados abaixo.

## Resultado final e limitação real do provedor

- **Suíte completa: 2.104 passaram, 4 puladas, 2 avisos, 175,79 s, exit 0.**
  Os avisos são as depreciações já existentes de `mss.mss` e TestClient.
- **A — leitura:** página oficial aberta e passagens sobre as duas APIs, padrões,
  cancelamento e exceções recuperadas. O contexto final continua limitado a
  1.800 caracteres por fonte; a distribuição por frases evita que o primeiro
  parágrafo longo esconda os aspectos seguintes. Tabelas mantêm seu caminho
  anterior para preservar rótulos e condições das linhas.
- **B — descoberta:** o pedido enviado pela interface não continha a URL. O
  sistema encontrou a página oficial e comprovou sua identidade pelo inventário.
- **C — síntese:** houve resposta real assistida em português com quatro
  parágrafos citados, preservada após reload. A reavaliação dos mesmos textos e
  pareceres reais aprovou os quatro aspectos após a correção de nomes curtos
  inequívocos (`TaskGroup`/`gather`); esse replay não é uma nova chamada ao modelo.
- O último teste independente pela interface preservou três mensagens e um
  card após reload, sem erros de console, mas recorreu aos extratos porque a
  revisão do provedor foi rejeitada. Uma chamada posterior recebeu **HTTP 429**
  do modelo gratuito. Por isso, **C ainda não está comprovada de forma estável
  com esse provedor**, e o resultado não é apresentado como aprovação universal.

Não foram feitas novas tentativas após confirmar o limite 429, nem foi trocado
o modelo ou utilizado um provedor pago. O próximo passo operacional é repetir
o mesmo roteiro com quota disponível ou um modelo já configurado e estável.
Os problemas de persistência, escopo e falsa conclusão foram corrigidos e
receberam regressões; não foi reduzida a exigência de suporte para contornar
uma limitação externa.

Evidências: `output/synthesis-completion/acceptance.json`, `ui-final.json`,
`review-replay.json` e capturas `research-390.png`/`research-1280.png`.
Logs locais: `qa-artifacts/synthesis-completion-focused.log` e
`qa-artifacts/synthesis-completion-full.log`.

## Arquivos principais desta continuação

`research_agents.py`, `research_synthesis.py`, `web_extract.py`, `evidence_graph.py`,
`python_docs_discovery.py`, `research.py`, `research_view.py`,
`tests/test_research_completion.py`, `tests/test_quote_catalog_coverage.py`,
`tests/test_live_ui_recovery.py` e `tools/live_research_completion.cjs`.

As alterações de UI, compras, notícias, contexto e os demais testes da rodada
anterior também integram a publicação conjunta. Logs privados, credenciais e
capturas de histórico pessoal não integram os arquivos para publicação.

## Limites da conclusão

Uma resposta aprovada neste cenário não certifica buscas universais, todos os
modelos ou qualquer marketplace. Provedores gratuitos continuam sujeitos a
limites e falhas. Quando faltar conteúdo, revisão ou uma condição obrigatória,
o sistema mantém a resposta parcial e as evidências disponíveis, sem simular
uma pesquisa completa.
