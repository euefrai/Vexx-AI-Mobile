# Pesquisa profunda — preservar cobertura até a resposta

Base: `5accdda`, branch `main`. Trabalho local, sem push, deploy ou reinício do PC Agent. Bancos de teste descartáveis; dados reais preservados.

## Correções

1. A seleção das seis evidências de maior pontuação podia excluir a única fonte que respondia a outro aspecto. Agora a preparação prioriza suporte complementar aos requisitos, recalculado sobre o texto efetivamente oferecido à síntese. Suporte direto tem prioridade sobre parcial; empates mantêm a pontuação e a ordem estável. Sem aspectos reconhecidos, a ordenação por relevância permanece.
2. Dentro de uma fonte, passagens repetindo o mesmo assunto podiam consumir os 1.800 caracteres e excluir outra seção útil. As passagens agora priorizam aspectos diferentes antes de preencher o espaço restante. Preservados os limites de seis fontes, 1.800 caracteres por fonte e a separação de trechos não contíguos. Nenhum teto de chamada, tokens, tamanho de resposta ou tentativas foi aumentado.
3. Metadados de passagens cujos offsets não correspondiam ao texto disponível podiam entrar na redação e gerar cobertura incorreta. São rejeitados quando existe texto completo da extração para conferir as posições. Registros antigos sem esse texto continuam sujeitos à leitura e aos validadores existentes; não há alegação de verificação retroativa integral.
4. Fontes explicitamente irrelevantes ou inelegíveis para o pedido não entram na síntese. Fontes não lidas continuam excluídas. Abstracts conservam seu escopo e não recebem prioridade como texto completo. Campos armazenados como `DIRECT_ANSWER` e IDs de requisitos não substituem a conferência do texto.

Os IDs de citação continuam ligados às evidências originais: uma fonte E7 pode ser selecionada em segundo lugar sem virar E2. Citações, revisão separada, números/unidades e estados de resposta incompleta mantêm suas validações. Nenhum rótulo de recuperação vira automaticamente aprovação semântica da resposta.

## Comparação controlada com a base

Dados sintéticos de teste, usando as mesmas entradas nas duas versões e os componentes reais de preparação. A função de escrita apenas captura o contexto; não chama um modelo.

| Caso | Antes | Depois |
| --- | --- | --- |
| Sete fontes, seis repetindo fundação e uma trazendo produtos | A fonte de produtos era omitida | A fonte complementar entra nas mesmas seis vagas |
| Dois trechos de fundação antes de uma passagem de produtos | 1.609 caracteres, produtos ausentes | 1.117 caracteres, os três aspectos disponíveis |
| Passagem incompatível com os offsets do texto | Texto incompatível enviado e marcado como suporte | Passagem rejeitada; produtos continuam pendentes |

Em observação local de CPU com 80 registros e 12 preparações, a mediana foi 10,260 ms e o máximo 11,923 ms; seis fontes foram selecionadas. Isso não mede inferência, rede ou latência total, nem representa benchmark universal de qualidade. O processamento considera no máximo 80 candidatos, compatível com a avaliação de evidências existente, sem novas chamadas externas.

Artefato: `qa-artifacts/synthesis-selection-assessment.json`.

## Validação

- Regressões novas na base: **8 falhas e 2 aprovações**, reproduzindo perdas de fonte, passagem, contexto desatualizado e falha de redação controlada por ausência de dados.
- Testes focados finais: **111 passed, 1 skipped, 1 warning**, 13,49 s. Incluem 13 casos novos, revisão semântica, identidades de fonte, negativos de texto não lido/abstract/ineligibilidade, limites, parciais, reload, checkpoint, auditor e exportações Markdown/CSV/JSON.
- Síntese com escritor e revisor controlados: resposta completa apenas quando os três aspectos são explicitamente revisados; sem revisão do aspecto de produtos, permanece incompleta. A resposta citada e sua proveniência sobrevivem ao salvamento/reload e chegam ao payload JDUI.
- O teste negativo de contexto parcial foi fortalecido durante a implementação: a primeira fixture curta não produzia uma passagem parcial real. Foi substituída por extração de tabela em documento longo, com asserção explícita do estado parcial, sem relaxar a produção para ajustar o teste.
- Suíte completa: **1.881 passed, 4 skipped, 2 warnings**, 191,17 s, exit 0. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. `py_compile` e `git diff --check` aprovados.

Logs: `qa-artifacts/synthesis-selection-before.log`, `synthesis-selection-focused-final.log` e `synthesis-selection-full.log`, com arquivos `.exit` para as execuções finais.

## Arquivos e limites

`research_agents.py`, `research_synthesis.py`, `tests/test_synthesis_context_selection.py`, artefato comparativo e este relatório. A avaliação de cobertura do contexto foi centralizada para usar a mesma lógica na preparação e na escrita.

Esta etapa comprova correções locais de seleção e integração controlada. Não houve nova descoberta web ao vivo, inferência real, teste visual ou smoke autenticado em produção. A melhoria não resolve escassez de fontes, bloqueios de provedores ou todos os tipos de pergunta. O próximo passo permanece avaliar descoberta e síntese reais em perguntas novas, sem substituir essas verificações pelo total de testes.
