# VEXX AI V5.9.9.5 — Search Reliability & Retrieval Ground Truth

**Decisão: NO_GO para publicação.** Há correções verificadas de adaptadores, retenção, extração e contrato do modelo. Ainda não há ganho consistente de pesquisa universal nem uma pesquisa autônoma moderadamente complexa com síntese do modelo validada de ponta a ponta. Os testes verdes não substituem esses critérios.

## Escopo e código

Trabalho local em `vexx-v598-dev`, branch `codex/v598-autonomous-research`, base da aplicação `31b063c`. Sem push/deploy, reinício de produção, modificação de dados reais, extensão Júlia, Fajulto Studio ou VERY. Identidade Lucas, permissões de controle remoto e arquitetura existente preservadas.

Commits locais de implementação: `a95b55b` (adaptadores/candidatos), `0c9ee29` (evidência/HTML), `d8157fd` (contrato/diagnóstico), `3335ab7` (IDs de fonte/regressão acadêmica). Os commits de baseline são `c625763` e `17e5e00`.

## Bugs corrigidos

| Falha real | Correção e limite |
|---|---|
| Marginalia retorna HTTP 200 com página de espera para bots; licença vira resultado | Reconhecer bloqueio, usar parser HTML inerte e excluir navegação/rodapé/licença. Sem seguir token de desafio ou executar scripts. |
| Banco Mundial ignora `q` e devolve indicadores de pobreza para população | Consultar código exato, conferir ID da resposta e marcar catálogo como metadado. Suporte semântico intencionalmente pequeno; não oferece valores populacionais nem substitui consultas desconhecidas. |
| Metadado acadêmico incompleto é eliminado antes de ler | Permitir candidato plausível com vínculo lexical, sem exigir abstract/answer facet. Rejeição de metadados explicitamente alheios preservada após regressão detectada pela suíte. |
| Prefixo de linguagem absorvido na entidade `JavaScript Object.assign` | Resolver operação qualificada no parser existente, sem criar outro sistema de busca. |
| Contexto causal sob heading e alias local útil desaparecem | Reter como parcial quando a vinculação é incompleta; não completar requisito nem esconder restrições. |
| Alternativas de exercícios podem parecer fatos | Marcar papéis literais e separar explicações. Alternativa sem correção demonstrada não sustenta resposta. Não inferir a alternativa correta. |
| Títulos curtos desaparecem do contexto HTML | Preservar headings curtos, mantendo a correção anterior de ordem inline e offsets literais. |
| JSON ambíguo/duplicado e truncamento sem diagnóstico | Parser estrito; uma cerca completa permitida, chaves duplicadas/NaN/controles ocultos/saída incompleta rejeitados. `finish_reason` e uso de tokens preservados; truncamento é falha explícita sem retry adicional. |
| Exemplo fixo E1 conflita com IDs S1 recebidos | Prompt usa IDs efetivamente permitidos. IDs inventados continuam sendo rejeitados; não são remapeados para fazer a resposta passar. |

Arquivos principais: `search_providers.py`, `research.py`, `query_intelligence.py`, `evidence_graph.py`, `web_extract.py`, `hermes_bridge.py`, `research_synthesis.py`, `pc_agent.py`. Testes novos: `tests/test_search_reliability_v5995.py`, `tests/test_evidence_reliability_v5995.py`, `tests/test_llm_contract_v5995.py`. Ferramentas de diagnóstico e QA existentes foram reutilizadas e receberam opções de saída isolada; ferramentas novas somente coletam/avaliam a arquitetura existente.

## Evidência de resultado

| Verificação | Antes → depois | Interpretação |
|---|---|---|
| Corpus público, desenvolvimento, 11 registros | Retenção 3/4 → 4/4 positivos anotados; FP 0 → 0 | Uma recuperação parcial; cobertura direta permanece 3/4. Anotação pelo mesmo agente, sem gold humano independente. |
| Corpus público, validação, 6 registros | 0/2 → 0/2 | Nenhum ganho; um rótulo positivo é ambíguo e foi sinalizado UNVERIFIED, sem editar o conjunto congelado. |
| Corpus público, holdout, 3 registros | 0/1 → 0/1 | Parcial útil ainda perdido. Não ajustar regras usando estes registros. |
| Conjunto externo novo, 16 perguntas | 0 → 3 leituras marcadas elegíveis, em 0 → 1 pergunta | Ganho concentrado em Object.assign; não é precisão/recall global nem resposta final validada. |
| Replay dos mesmos 47 textos retornados pelo baseline | 0 → 2 flags de elegibilidade | Isola reclassificação, sem nova descoberta/rede/modelo. |
| Pesquisas autônomas reais no chat | 2/2 sem evidência utilizável | WebAssembly.Table.grow e Intel: resultados parciais persistidos, sem síntese LLM. **Não é SUCCESS_VERIFIED.** |
| Modelo gratuito, síntese isolada com fonte realmente lida | 2 chamadas; ambas rejeitadas | Primeira: IDs inventados/afirmações extras; segunda: JSON com `]` excedente. Sem reparo semântico ou fallback pago. |

O candidato de recuperação foi congelado em `d8157fd` antes da abertura do holdout. Depois, o probe real revelou o conflito de IDs e a suíte revelou a regressão acadêmica; `3335ab7` corrige ambos. `post-freeze-changes.json` registra os dois arquivos alterados. Os resultados selados continuam atribuídos ao candidato registrado; não são uma aceitação independente do código final. Os arquivos originais e resultados brutos locais foram preservados.

## Testes executados

- Suíte completa final: **1.626 passaram, 4 skips, 2 avisos**, 345,94 s. Avisos de depreciação existentes de `mss` e timeout do TestClient; skips não foram convertidos em aprovação.
- Primeira suíte: 1 falha real no filtro acadêmico, 1.624 passaram. Corrigida; rodada focal de 38 e suíte final passaram. Testes não foram apagados ou relaxados.
- Rodadas focadas: adaptadores 75; evidência/HTML/contrato/AI 117; ajuste de prompt 50. São recortes sobrepostos, não somar como casos independentes.
- Baselines controlados: pesquisa **34/34**, shopping **59/59**, experiência/JDUI **16/16**. Não são pesquisas externas nem avaliação científica.
- Chrome real autenticado com FastAPI, PC Agent e SQLite temporários: chat comum SSE, duas pesquisas autônomas, cancelamento, persistência de IDs/texto após reload, cards/fontes, abertura real de link, CSV, ordenação por teclado, reduced motion e falha de rede/reconexão HTTP 200.
- Geometria e screenshots inspecionados em 1280/390/320 px e CSS zoom 200%. Sem overflow da página; tabela pode rolar internamente. Emulação de viewport, sem alegar telefone físico.
- Runtime QA encerrado de forma graciosa; árvore de processos e banco/runtime temporários ausentes ao final. Produção e proxy compartilhado não foram reiniciados.

## Recursos e segurança

Mesmos limites de leitura/busca e modelo gratuito configurado; nenhum novo serviço, dependência, classificador paralelo, execução de código do modelo, modo schema presumido ou retry infinito. Na comparação de rede: 87 → 84 chamadas observadas e 173 → 162 fetches observados; mediana 8,358 → 7,061 s, sem atribuir causalidade devido à variação de rede/índice. Chat comum: primeiro delta 3.037 ms, total instrumentado 3.510 ms. Os dois probes não streaming reportaram 4.359 tokens no total; uso do chat comum e inferência externa ao probe não foi contabilizado integralmente.

Snapshot da árvore exclusiva de QA: RSS somado 74,08 MB; páginas compartilhadas podem ser contadas mais de uma vez. Não inclui Chrome/proxy, não é P95 nem comparação de memória antes/depois. Detalhes nos artefatos; não há alegação de economia global.

SSRF, isolamento por owner, permissões e validações de quote/ID/unidade continuam cobertos pela suíte. Nenhuma chave foi adicionada a código/artefatos. Capturas externas brutas permanecem locais, fora do commit, com hashes; corpus contém somente amostras curtas. Não foi feita auditoria independente de segurança.

## Pendências e próximo passo exato

1. Corrigir `research_agents._subconsultas_unicas`/`research.dividir_subconsultas`: o plano real perdeu a entidade em frentes como `qual sintaxe`, `valor retornado`, `que ano` e usou instruções de apresentação como busca. Este é um problema observado **anterior ao provedor**; preservar assunto/restrições nos follow-ups usando Query Intelligence existente, sem aumentar orçamento.
2. Instrumentar a transição candidato → leitura do agente com URLs/causas limitadas. Os jobs consumiram 12 slots de página e terminaram sem evidências; hashes de falhas sozinhos não permitem atribuir toda a perda à extração ou ao classificador.
3. Obter uma síntese gratuita com IDs/quotes corretos e revisão semântica aceita após descoberta autônoma. Não aparar `]` ou inventar campos para aceitar JSON inválido.
4. Revisão humana independente das anotações e expansão pública documentada: o corpus atual não cobre todos os rótulos pedidos; faltam exemplos reais revisados de CONTRADICTORY/IRRELEVANT e cobertura suficiente por domínio. O holdout atual já foi observado e não pode ser reutilizado como novo teste cego após otimizações.
5. Corrigir os FNs de validação/parciais por generalização, com novo conjunto independente antes de otimizar. Preservar precisão em entidade, atributo, direção causal, datas e notícias locais.

Documentação complementar em [docs/v5.9.9.5/PROGRESS.md](docs/v5.9.9.5/PROGRESS.md). Os arquivos exigidos detalham auditoria, corpus, calibração, HTML, contrato, síntese, benchmark, E2E e JDUI. A entrega desta rodada é uma melhoria local testada e um diagnóstico verificável; publicação permanece bloqueada pelos critérios de qualidade solicitados.
