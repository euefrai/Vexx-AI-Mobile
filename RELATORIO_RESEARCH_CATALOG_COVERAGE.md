# Pesquisa profunda — catálogo de citações consistente com o contexto

Base `a0ba29e`, branch `main`. Alterações locais, sem push/deploy, reinício de agente ou acesso a bancos reais.

## Falhas corrigidas

- O escritor de produção usa `literal_quote_ids=True`, mas o catálogo podia consumir as 12 opções nas primeiras frases de uma fonte e omitir a passagem complementar. Agora distribui vagas entre as passagens antes de preencher as restantes. Mantidos até 12 opções, 24–450 caracteres por opção e até 1.800 caracteres de citações por fonte; sem aumento de tokens, fontes, tentativas ou chamadas.
- Os estados dos requisitos eram calculados sobre o excerpt completo, embora o modelo recebesse somente o catálogo. Agora refletem os trechos realmente enviados. Uma informação fora do catálogo permanece pendente; não é considerada respondível apenas por existir no texto interno.
- O modo de catálogo aceitava referências com `quote` em texto livre, inclusive trechos não oferecidos, apesar de instruir o uso exclusivo de `quote_id`. Agora exige o formato do catálogo e resolve apenas IDs existentes, mantendo as conferências de fonte, literalidade, números, unidades e revisão separada. Respostas que descumprem esse formato caem no fallback existente; não há retry automático.
- Catálogos sem nenhum trecho citável não fazem uma chamada inútil ao modelo.

A avaliação do catálogo conserva a atribuição real de tabelas e os offsets/hash dos fragmentos. Frases selecionadas que eram adjacentes dentro da mesma passagem conservam o contexto literal, incluindo pronomes. Nunca se unem por cima de uma oração omitida ou entre passagens distintas. Essa reconstrução serve à avaliação de cobertura; o escritor continua recebendo citações com IDs separados.

A revisão recebe o contexto completo já previsto para conferir ressalvas e contradições. A nova avaliação de cobertura usa apenas o conteúdo citável efetivamente oferecido ao escritor. Campos internos usados para rastrear posições não são enviados no JSON do catálogo.

## Comparação controlada com a base

Mesmas entradas sintéticas, sem provedor real. Artefato: `qa-artifacts/catalog-coverage-assessment.json`.

| Cenário | Antes | Depois |
| --- | --- | --- |
| Fonte com passagem complementar no final | 12 citações/680 caracteres, informação de produtos omitida | 12 citações/665 caracteres, informação de produtos incluída |
| Fato tardio ainda fora do limite dentro de uma única passagem | Produtos marcados SUPPORTED sem serem enviados | Produtos permanecem DISCOVERED |
| Catálogo vazio | Uma chamada ao escritor | Nenhuma chamada |
| Texto livre contornando `quote_id` | Aceito | Rejeitado |

O segundo cenário é uma limitação real preservada: a distribuição de vagas não garante recuperar toda informação tardia dentro de um único parágrafo extenso. O estado agora mostra essa falta corretamente.

## Verificação

- Baseline dos dez primeiros casos novos: **8 falhas e 2 aprovações**, reproduzindo perda de passagem, cobertura incorreta, chamada vazia, contorno de IDs e falha no wrapper de produção controlado.
- A primeira implementação separava frases adjacentes demais na avaliação de cobertura. Um teste adicional reproduziu a perda do referente de um pronome. Corrigido preservando apenas contiguidade literal verificada; o negativo com uma oração intermediária omitida continua pendente.
- Focados finais: **173 passed, 1 warning**, 13,61 s. Incluem 13 casos novos, catálogo anterior, tabelas, offsets/hash após cortes por palavra, cobertura semântica, seleção de fontes, persistência, revisão e agentes.
- Integração controlada pelo próprio `pc_agent._research_writer`, com ambos os flags usados em produção: duas fases (escrita/revisão), resposta com três aspectos confirmados, citações, proveniência, checkpoint/reload, conteúdo JDUI e exports MD/CSV/JSON. A função do provedor foi substituída por respostas controladas; isso não é inferência real.
- Suíte completa: **1.894 passed, 4 skipped, 2 warnings**, 167,99 s, exit 0. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. `py_compile` e `git diff --check` aprovados.

Logs locais: `qa-artifacts/catalog-coverage-before.log`, `catalog-coverage-context.log`, `catalog-coverage-focused-final.log`, `catalog-coverage-full.log`, além dos `.exit` finais.

## Arquivos e limites

`research_synthesis.py`, `tests/test_quote_catalog_coverage.py`, artefato comparativo e este relatório. Sem alterações de UI, identidade, extensão Júlia, Fajulto, permissões remotas, dependências ou schema do banco.

Não houve descoberta web nova, avaliação com modelo real, teste visual ou teste autenticado em produção. A seleção dentro de um parágrafo longo e a validação ao vivo de descoberta/síntese permanecem trabalhos futuros. Nenhum resultado deste conjunto controlado comprova pesquisa universal completa.
