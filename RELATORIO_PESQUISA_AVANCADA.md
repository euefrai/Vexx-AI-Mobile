# Pesquisa geral e aprofundada — descoberta e cobertura

## Objetivo e escopo

Melhorar perguntas naturais, recuperação depois da leitura e cobertura de perguntas com vários aspectos. Esta etapa preserva as correções anteriores de cache, compras e bloqueios. O critério é evidência pertinente realmente lida, sem declarar uma resposta completa apenas por encontrar links ou aumentar a contagem de testes.

As alterações simultâneas em documentos, servidor, PC Agent e interface foram preservadas e ficam fora da cópia isolada de validação desta entrega.

## Perdas reproduzidas e correções

1. **Assunto interpretado como instrução.** Pedidos naturais viravam entidades extensas ou ficavam sem requisitos. Na rede real, a pergunta sobre RAM/SSD recuperou dicionários sobre “diferença”, e a pergunta de `asyncio.timeout` trouxe páginas sobre “na”. O parser agora identifica a entidade/operação, antepõe o assunto na descoberta e conserva autoridade, números, negações, comparação e perguntas residuais. Aspectos ainda não interpretados permanecem pendentes.
2. **Descoberta bem-sucedida antes de leitura malsucedida.** Três snippets pertinentes encerravam a busca; depois as três páginas eram bloqueadas ou irrelevantes, sem consultar outro provedor disponível. A pesquisa geral agora tem uma recuperação pós-leitura no caminho nativo, compartilhando histórico e orçamento restante, excluindo links já conhecidos antes dos gates de suficiência e sem contornar CAPTCHA. Injeções de teste não iniciam rede implicitamente.
3. **Aspectos repetidos ocupando a pesquisa aprofundada.** As três primeiras páginas podiam repetir apenas fundação de uma empresa, ignorando uma quarta fonte já descoberta sobre seus produtos, mesmo havendo orçamento. O analista continua lendo candidatos existentes quando faltam passagens de um aspecto explícito, preservando as parciais e os limites de páginas, tentativas, tempo e cancelamento. Metadados ordenam leitura; não se tornam suporte factual.
4. **Recuperação científica no artigo errado.** Cada dimensão usava o primeiro DOI global, inclusive quando esse artigo já estava lido e outro continuava só com abstract. O alvo agora depende da dimensão sem suporte e das consultas já tentadas. DOI e sua URL normalizada contam como uma publicação. Identificadores longos não são cortados para inventar outro DOI; sem espaço, a descoberta usa o assunto. Abstract não vira texto integral.

## Baseline com rede real

Pipeline nativo, SQLite em memória, sem modelo ou fixtures, quatro perguntas sem URLs fornecidas. Orçamento por caso: três consultas por rodada (teto legado de seis no total), cinco provedores, sete tentativas, 14 s de descoberta compartilhada e 4 s por página. O tempo completo inclui leitura e não tem deadline rígido de 14 s.

| Caso | Tempo | Fontes lidas | Fontes úteis | Estado |
|---|---:|---:|---:|---|
| `asyncio.timeout` e prazo | 6,188 s | 4 | 0 | sem correspondência |
| RAM versus SSD e desempenho | 5,953 s | 4 | 0 | sem correspondência |
| Estoicismo e controle | 6,078 s | 4 | 0 | sem correspondência |
| Sono, memória e aprendizagem | 9,328 s | 2 | 1 | parcial, abstract científico |

O caso de estoicismo tinha páginas pertinentes, descartadas pelo assunto interpretado como a frase inteira. A falha não foi atribuída genericamente a CAPTCHA. Fontes do caso científico permanecem identificadas pelo escopo de abstract ou metadados. Evidência: `output/general-recovery/baseline.json`.

## Verificações

Testes controlados focados já executados por componente: recuperação geral (147), parser e contratos de cobertura (184), diversidade de aspectos no analista (141). Os conjuntos têm sobreposição e não devem ser somados. A reprodução de leitura e a comparação científica usam dados de teste declarados; não provam acesso externo nem verdade científica.

### Retomada e validação em 01/11/2026

Ao retomar, o histórico já continha as melhorias anteriores no commit `a2caf6e`. Outras alterações locais de autenticação, servidor e interface foram preservadas. A finalização desta tarefa acrescenta somente a separação entre pertinência lida e suporte de resposta em `research.py`, a proteção contra recuperação sem histórico de busca e três testes dedicados.

Uma fonte precisa conter o assunto no corpo realmente lido, passando pelos filtros existentes; título ou snippet não bastam. Para perguntas de definição ou comportamento ela pode permanecer `TOPIC_ONLY`, sem passagens de resposta e sem cobertura completa artificial. Pedidos de aspectos específicos, como limitações, continuam exigindo passagens pertinentes. A recuperação não inicia rede quando não houve nenhuma tentativa de descoberta registrada, corrigindo a regressão do benchmark de resultado vazio.

Nova execução pública final, sem modelo, em `output/general-recovery/final-scoped-20261101.json`:

| Caso | Tempo | Fontes úteis | Resultado |
|---|---:|---:|---|
| Python `asyncio.timeout` | 5,781 s | 1 | parcial |
| RAM e SSD | 7,750 s | 1 | parcial |
| Estoicismo | 4,547 s | 3 | fontes pertinentes recuperadas |
| Sono/memória | 7,218 s | 1 | parcial, escopo científico limitado |

Os testes ocorreram em datas diferentes; a comparação não é um benchmark causal de performance. Os replays e regressões controladas demonstram separadamente as causas corrigidas. Encontrar fontes úteis não significa responder integralmente a cada pergunta.

UI real local, conta e SQLite descartáveis, rede pública: o pedido de estoicismo exibiu três cards de fontes lidas e preservou os três após reload. Sem erros JavaScript durante o fluxo e sem overflow em 390/1280 px. Evidência: `output/general-recovery/ui-final-20261101.json`. O provedor configurado não produziu síntese por IA nessa execução; a interface apresentou o fallback explícito com trechos e fontes. Portanto, **síntese completa assistida não foi aprovada por este teste**.

Os 89 testes focados iniciais passaram. A primeira suíte completa revelou um caso de pertinência excessiva, agora restringido por aspecto, e duas falhas preexistentes de frontend: handler inline bloqueado por CSP e teste ainda esperando âncora em vez de botão de citação. O handler foi removido, e o teste continua exigindo o destino real e referência desconhecida sem link. Os 20 testes de frontend/pertinência e 43 de recuperação/limites passaram após os ajustes.

**Suíte final: 2.337 aprovados, quatro pulados, dois avisos de depreciação existentes, exit 0 em 241,40 s.** Log: `qa-artifacts/general-final-full-suite.log`. A cópia isolada usa `a2caf6e` acrescido somente dos quatro arquivos de código/testes desta finalização; o conteúdo preparado no índice confere com essa cópia, normalizadas as quebras de linha. Mudanças paralelas não entram no commit. Os processos descartáveis foram encerrados. A publicação foi autorizada pelo usuário; confirmação de push e runtime será registrada na entrega.

## Google e limites

Não foi adicionado um acesso fictício a “todo o Google”. A API antiga Custom Search JSON está fechada para novos clientes e tem transição anunciada para clientes existentes. O Google documenta busca integrada via Gemini Grounding, com configuração e condições próprias. Esta entrega melhora o mecanismo atual e não provisiona contas, chaves ou serviços pagos.

- [Custom Search JSON API — disponibilidade oficial](https://developers.google.com/custom-search/v1/overview).
- [Gemini Grounding com Google Search](https://ai.google.dev/gemini-api/docs/google-search).

Conteúdo privado, bloqueado, pago ou não indexado pode continuar inacessível. Não há promessa de localizar tudo nem flexibilização dos controles de acesso, entidades, variantes ou evidências. Esta entrega não equivale a uma aprovação universal da síntese: descoberta, leitura e resposta final têm verificações distintas.
