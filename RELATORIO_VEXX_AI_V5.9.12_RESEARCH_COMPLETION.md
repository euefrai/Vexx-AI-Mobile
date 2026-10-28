# VEXX AI V5.9.12 — conclusão real da pesquisa

## Resultado desta etapa

**Gerdau e WEG concluíram pesquisas reais de ponta a ponta**: descoberta sem URL fornecida, leitura, resposta LLM, citações literais, revisão semântica, cobertura dos três requisitos, publicação no chat e persistência após reload. Não houve marcação artificial de sucesso nem retirada dos validadores numéricos.

**A meta geral continua em andamento.** Há aprovação localizada do fluxo completo em empresas; não há comprovação de confiabilidade universal do Research Ultra. Na rodada final de quatro casos, dois completaram, um teve revisão inválida e um sofreu rate limit. Outras categorias continuam com recuperação insuficiente.

Base `40f9531`, branch `codex/v598-autonomous-research`, árvore rastreada inicialmente limpa. Commits locais: `4b9441b` congela avaliação; `ef97dfc` corrige atribuição/leitura; `53d4154` corrige encerramento e busca por título; `1fee389` preserva campos curtos citáveis; `3938bee` vincula cobertura semântica aos requisitos. HEAD de lógica validada: `3938bee`; documentação/ferramentas fecham em commit posterior, consultável com `git log -1 --oneline`.

Sem push/deploy, dados de produção, reinício de PC Agent de produção ou alterações em outras aplicações. Identidade Lucas e permissões de controle remoto preservadas. Todos os serviços/browser usados eram QA descartável; modelo exclusivo `poolside/laguna-s-2.1:free`, sem fallback pago.

## Causas corrigidas

| Causa reproduzida | Correção |
|---|---|
| “Atlas Fundadores” virava nome próprio inteiro e rejeitava fonte pertinente | Rótulos internos de consulta em minúsculas, preservando entidade/constraints. |
| Fallback parava no primeiro provedor mesmo com exclusão explícita de entidade | Rejeita incompatibilidades antes de encerrar fallback. DOI é excluído do detector de modelos de produto; não confunde `result-1` de um DOI com equipamento. |
| Pergunta histórica com causas/consequências em cláusulas separadas perdia o evento | Extensão do parser existente; sem segundo parser ou nomes de benchmarks na lógica. |
| Ano/produtos de infobox lidos sem atribuição da empresa | Preserva header real da mesma tabela DOM, offsets e SHA da extração. Só aceita campos com escopo compatível; título isolado não comprova fato. |
| Um parágrafo com contexto atravessava tabela e excluía linhas úteis na seleção | Heading só é anexado ao bloco adjacente. Passagens conservam offsets literais. |
| Linhas curtas, como “Fundação 1969”, sumiam do catálogo de citações | Junta somente linhas selecionadas contíguas da mesma tabela/header/SHA, sem texto omitido, até 450 caracteres. Preserva limites de cada campo; mínimo de quote e validação numérica mantidos. |
| Relação de produtos em inglês e contexto pronominal curto eram perdidos | Reconhece manufacturers/producers of e uma ponte neutra após sujeito explícito. Novo sujeito, aquisição ambígua, negação e fala reportada não herdam atribuição. |
| Catálogo/redator perdia atribuição e limites das passagens | Metadados estruturais acompanham os ranges até o redator/revisor; não concatena passagens distantes em quote falso. |
| Pergunta original extraída como claim UNVERIFIED impedia qualquer conclusão | Mantém os vereditos preliminares, mas avalia a resposta final pelas próprias citações, revisão e cobertura. Contradições, lacunas reais e auditoria inválida continuam impedindo conclusão. |
| “Entre os produtos fabricados pela Gerdau...” não era reconhecido como resposta | Na mesma chamada de revisão, o modelo indica requisito e trecho literal da resposta. Só aceita IDs conhecidos, span existente, parágrafo SUPPORTED e fonte citada vinculada ao requisito. Ano/data requer ano literal; peso requer valor/unidade. Objetivo não decomposto e restrição oficial não são resolvidos por esse mecanismo. |
| JSON válido seguido por um único delimitador extra descartava todo o texto | Normalização opt-in na redação, registrada em `format_normalization`. Não aceita payload extra, instruções, chaves duplicadas, truncamento ou bidi; revisão permanece estrita. |
| OpenSearch recebia facetas como se fossem parte do título | Usa entidade única reconhecida para localizar artigo, preservando pedido original na elegibilidade/proveniência. |

Não foram criados outro motor, Evidence Graph, banco ou agentes. Não aumentaram slots, páginas, tokens, timeout ou número de chamadas LLM por pesquisa. A cobertura semântica usa a revisão já existente, sem uma chamada adicional. Nenhum código do modelo foi executado.

## Evidência controlada e externa

Reextração do **mesmo HTML capturado** no desenvolvimento, sem rede/modelo:

- Gerdau: cobertura incompleta → três requisitos cobertos; 3 → 13 vínculos.
- Sega: incompleta → três requisitos cobertos; 2 → 6 vínculos.
- Guerra do Contestado: zero vínculos antes/depois nesse replay. Falha preservada.
- Todos os spans aceitos são literais, teto de 8.000 caracteres mantido. Vínculos não são contagem de fatos independentes. Hashes iguais dos snapshots no antes/depois; isto prova leitura/associação, não ranking melhor na internet.

Desenvolvimento live em seis perguntas: WEG/Gerdau/Sega cobriram dados de fundador, fundação e produtos; história, Math.trunc e rio Tocantins não obtiveram suporte suficiente naquela rodada. Execuções de rede distintas não são comparação causal de ranking.

Holdout de 16 perguntas congelado antes da implementação em `4b9441b`, sem URLs fornecidas, sem modelo e sem gold humano. Avaliado em `53d4154`, antes das mudanças finais de citação/cobertura semântica: três casos retiveram entrada marcada como lida; dois tiveram passagem vinculada; somente Toyota cobriu todos os requisitos de recuperação. Isso **não é uma resposta final LLM aprovada**. Esporte reteve contexto sem vínculo; rio Jequitinhonha teve suporte parcial. Mediana 48,78 s; intervalo 8,382–138,148 s. Não houve nova rodada live do holdout no HEAD final, nem ajuste aos seus resultados.

Diagnóstico adicional de desenvolvimento: duas consultas Bing RSS, com e sem aspas no evento, retornaram os mesmos títulos genéricos. A URL preserva a consulta; isso não determina por que o provedor respondeu assim. A API Wikipedia retornou artigo para o evento. O gargalo seguinte foi localizado no leitor: em nova execução Contestado, encontrou/abriu a página, mas selecionou 1.727 caracteres de confrontos, sem vínculo de causa/consequência, embora existam headings reais “Antecedentes” e “Consequências”. Não se deve resolver isso apenas aumentando texto ou promovendo conteúdo temático a prova.

## QA autenticado final — `3938bee`

| Pergunta | Resultado | Evidência |
|---|---|---|
| Gerdau: fundador, fundação, produtos | **COMPLETE / LLM** | Cinco parágrafos revisados, três requisitos ligados a spans da resposta e fontes citadas. 57,209 s; reload preservado. |
| Natura: mesmos requisitos | PARTIAL | Redação/revisão não aprovada: `semantic_review_invalid`. Não contada como conclusão bem-sucedida. 52,179 s. |
| WEG: mesmos requisitos | **COMPLETE / LLM** | Dois parágrafos revisados; nomes, data e produtos vinculados a spans e evidência real. 45,267 s; reload preservado. |
| Nvidia: mesmos requisitos, caso adicional | BLOCKED | `rate_limit`; evidências preservadas, sem fabricar resposta completa. 41,930 s. |

São duas perguntas distintas na mesma categoria, não consistência universal nem fontes independentes. Gerdau reteve dois registros de evidência que apontam para a mesma URL: não equivalem a duas publicações independentes. As citações das respostas completas foram conferidas contra o catálogo e os spans retornados; a revisão automática não comprova a verdade do mundo por si só.

As tentativas anteriores também foram guardadas: rate limit, vazio, JSON inválido, omissão de requisito e falsa pendência por claim preliminar. Cada versão teve alterações reproduzidas antes da nova tentativa; não houve loop de retry até PASS. HTTP 200 com content vazio e `reasoning_present=true` foi observado; reasoning não foi publicado nem usado como resposta. Isso não esclarece todas as falhas históricas.

## Testes, UI e segurança

- **Suíte final: 1.804 passed, 4 skipped, 2 warnings**, 459,36 s, exit 0, em `3938bee`.
- Intermediária: três falhas/1.785 passes. Corrigidos range sem ID e DOI confundido com modelo. A expectativa literal de maiúsculas do teste de query passou a comparar sem distinção de caso, preservando a verificação de faceta/constraints; nenhum teste removido.
- Suíte posterior intermediária: 1.790 passes. Outra execução foi interrompida somente no processo pytest próprio quando a nova falha semântica já havia sido reproduzida; não foi contada como PASS. A suíte final acima inclui todas as correções.
- Focados: 165 passes após catálogo; 142 após cobertura semântica. Execuções sobrepostas não somadas como cobertura independente. Novos negativos cobrem tabela de outra entidade, aquisição/negação, ID/aspecto inventado, ano ausente, span inexistente, fonte não vinculada e objetivo não decomposto.
- Benchmarks finais: Search 34/34, Shopping 59/59, Experience 16/16. São regressão, não avaliação inédita de pesquisa universal.
- Chrome real: links de fonte abertos, cards sem overflow em 1280/390/320 px; inspeção visual em desktop e 320 px. Emulação, não celular físico. Não se alegou novo teste de galeria/streaming de produção.
- Exportações MD/CSV reais. IndexedDB: 12 mensagens, 12 IDs únicos, quatro mensagens estruturadas/resultados; reload preservado nos quatro casos finais. SQLite QA verificado pelo coletor.
- Quatro sessões QA encerradas; bancos/runtime temporários removidos, zero processos associados, zero operações ativas antes do último stop. Nenhum processo de produção encerrado.
- `py_compile`, `node --check`, diff e scan de artefatos públicos foram executados na entrega. Capturas integrais, prompts, logs e runtime privados ficam ignorados; sumários não publicam credenciais nem reasoning.

## Limites e próximo passo exato

**Integração completa comprovada em empresas; Research Ultra universal continua NO_GO.** Descoberta/seleção de trechos em outras categorias e obediência do modelo gratuito ainda precisam melhorar. Cards de fonte podem repetir a mesma URL para registros distintos; alguns títulos JSON-LD são descrições. Esses detalhes continuam pendentes, sem alegação de polimento visual completo.

Próxima fase já autorizada: usar o HTML de desenvolvimento Contestado capturado para testar seleção por headings reais “Antecedentes”/“Consequências”, mantendo H1/ancestralidade e offsets; distinguir contexto parcial de suporte factual. Validar com negativos de outra entidade e de associação/causalidade antes de permitir qualquer revisão semântica encerrar a lacuna. Não ajustar ao holdout, não aumentar limites e não trocar ausência de evidência por estado completo.

Produção alterada: `query_intelligence.py`, `evidence_graph.py`, `research_agents.py`, `research_synthesis.py`, `research.py`, `search_orchestrator.py`, `web_extract.py`, `pc_agent.py`. Testes e ferramentas constam do diff desde `40f9531`. Artefatos compactos em `qa-artifacts/v5912/`; progresso e reprodução em `docs/v5.9.12/`.
