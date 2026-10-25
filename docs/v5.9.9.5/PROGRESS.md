# V5.9.9.5 — progresso local

Base da aplicação: `31b063c`. Branch: `codex/v598-autonomous-research`, checkout `vexx-v598-dev`. Sem push/deploy e sem alteração de dados reais, extensão, Studio ou VERY.

## Concluído até a calibração local

- Auditoria comparativa real de 14 adaptadores / 22 chamadas, com parâmetros, HTTP observado, ranking, snippets, URLs e latências em `qa-artifacts/v5995/provider-audit.json`.
- Conjunto externo novo de 16 perguntas congelado antes das correções. Baseline capturado sem abrir seus resultados para otimização.
- Corpus público pequeno: 20 amostras curtas com origem, offsets e hashes; 11 desenvolvimento, 6 validação, 3 holdout. Anotações MODEL_PROPOSED, sem revisão humana independente. A revisão `annotation-review.json` marca `real-15` UNVERIFIED; o arquivo original foi preservado.
- Marginalia: detectar página de espera/bloqueio e excluir navegação/licença sem executar ou seguir desafios. Banco Mundial: remover `q` não suportado e validar código do indicador retornado. Consulta populacional é catálogo de indicador, não medição da população.
- Candidatos acadêmicos sem abstract podem chegar à leitura dentro do mesmo orçamento; não são promovidos a evidência.
- Ordem inline HTML preservada; títulos curtos mantidos. Alternativas sem correção comprovada são separadas de explicações literais. Contexto causal sob heading e alias de método documentado ficam parciais quando a vinculação é incompleta.
- JSON: aceitar um valor completo ou uma única cerca; rejeitar duplicação de chaves, valores não finitos, controles ocultos e saída incompleta. Bridge mantém finish_reason/usage limitados; o writer rejeita truncamento sem retry/fallback adicional.
- Testes focados: 75 dos adaptadores/leitura; 117 de evidência, extração, contrato, síntese e AI. A primeira rodada teve 3 regressões novas; foram corrigidas e a rodada completa desses testes passou.

## Resultado exploratório antes do holdout

Desenvolvimento: retenção 3/4 → 4/4; uma passagem recuperada como parcial, cobertura direta continua 3/4; nenhum FP nesses 11 exemplos. Validação: nenhum ganho, 0/2 retidos conforme os rótulos originais; uma das duas anotações positivas é ambígua e não pode sustentar uma alegação de recall parcial. Números pequenos e sem gold humano; não são precisão global.

## Verificação final desta rodada

- Candidato de recuperação congelado em `d8157fd`. Ajustes posteriores por falha real do modelo e regressão da suíte em `3335ab7`; causas e hashes registrados, sem ajuste baseado nos exemplos selados.
- Suíte final: **1626 passed, 4 skipped, 2 warnings**. Pesquisa 34/34, shopping 59/59, experiência/JDUI 16/16. Primeira suíte encontrou uma regressão acadêmica, corrigida sem eliminar testes.
- Holdout público: nenhum ganho. Externo de 16 perguntas: 0 → 3 leituras marcadas elegíveis, concentradas em uma pergunta; replay dos mesmos 47 textos: 0 → 2 flags. Não é precisão/recall global.
- Duas pesquisas autônomas reais no Chrome ficaram sem evidências úteis; os dois probes isolados de síntese gratuita foram rejeitados. **Não houve SUCCESS_VERIFIED.**
- Chat comum SSE, cancelamento, IDs/textos após reload, cards de fonte controlada, links, CSV, teclado, reconexão e viewports 1280/390/320/zoom verificados. Runtime, árvore de processos e SQLite temporários encerrados/removidos; produção preservada.
- Relatório principal e nove documentos complementares concluídos. **NO_GO**, sem push/deploy.

## Próximo passo exato e pendências

Corrigir a perda de entidade em `research_agents._subconsultas_unicas`/`research.dividir_subconsultas`, usando os requisitos existentes: os jobs reais criaram frentes como `qual sintaxe`, `valor retornado` e `que ano`. Preservar assunto/restrições e separar instruções de apresentação, sem aumentar orçamento. Adicionar rastreio limitado entre candidato e leitura para explicar os slots consumidos sem evidência.

Depois, congelar um **novo** conjunto independente antes de otimizar, obter revisão independente do corpus e repetir uma pesquisa moderada até síntese/citações/JDUI/persistência efetivamente validados. O holdout desta rodada já foi observado. Faltam casos públicos revisados de CONTRADICTORY/IRRELEVANT e suporte a relações/idiomas ainda perdidos. Consulte `RELATORIO_VEXX_AI_V5.9.9.5_SEARCH_RELIABILITY.md` para resultados e limites completos.
