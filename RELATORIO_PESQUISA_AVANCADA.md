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

Pipeline nativo, SQLite em memória, sem modelo ou fixtures, quatro perguntas sem URLs fornecidas. Orçamento por caso: três consultas, cinco provedores, sete tentativas, 14 s de descoberta e 4 s por página.

| Caso | Tempo | Fontes lidas | Fontes úteis | Estado |
|---|---:|---:|---:|---|
| `asyncio.timeout` e prazo | 6,188 s | 4 | 0 | sem correspondência |
| RAM versus SSD e desempenho | 5,953 s | 4 | 0 | sem correspondência |
| Estoicismo e controle | 6,078 s | 4 | 0 | sem correspondência |
| Sono, memória e aprendizagem | 9,328 s | 2 | 1 | parcial, abstract científico |

O caso de estoicismo tinha páginas pertinentes, descartadas pelo assunto interpretado como a frase inteira. A falha não foi atribuída genericamente a CAPTCHA. Fontes do caso científico permanecem identificadas pelo escopo de abstract ou metadados. Evidência: `output/general-recovery/baseline.json`.

## Verificações

Testes controlados focados já executados por componente: recuperação geral (147), parser e contratos de cobertura (184), diversidade de aspectos no analista (141). Os conjuntos têm sobreposição e não devem ser somados. A reprodução de leitura e a comparação científica usam dados de teste declarados; não provam acesso externo nem verdade científica.

Pendente nesta fase: congelar o código, repetir as quatro perguntas com rede real, testar uma conversa pela interface e reload, executar a suíte completa isolada e registrar os resultados finais. Scripts: `tools/probe_general_recovery.py` e `tools/live_general_recovery.cjs`.

## Google e limites

Não foi adicionado um acesso fictício a “todo o Google”. A API antiga Custom Search JSON está fechada para novos clientes e tem transição anunciada para clientes existentes. O Google documenta busca integrada via Gemini Grounding, com configuração e condições próprias. Esta entrega melhora o mecanismo atual e não provisiona contas, chaves ou serviços pagos.

- [Custom Search JSON API — disponibilidade oficial](https://developers.google.com/custom-search/v1/overview).
- [Gemini Grounding com Google Search](https://ai.google.dev/gemini-api/docs/google-search).

Conteúdo privado, bloqueado, pago ou não indexado pode continuar inacessível. Não há promessa de localizar tudo nem flexibilização dos controles de acesso, entidades, variantes ou evidências. Esta entrega não equivale a uma aprovação universal da síntese: descoberta, leitura e resposta final têm verificações distintas.
