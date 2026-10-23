# Vexx AI — revisão de suporte por parágrafo

> Histórico desta etapa. A exigência posterior de contraevidência literal para contradições e suas novas medições estão em `RELATORIO_SUPPORT_CALIBRATION.md`.

Entrega local sobre `b5cd857`, em 22/10/2026. Sem push/deploy/reinício de produção. Modelo, provedores, chaves, contas, identidade, memória, 3D, extensão e permissões preservados.

## Comportamento

- A redação agora precisa passar por uma **segunda chamada**, separada da geração, usando o modelo já configurado. O revisor recebe os parágrafos, citações e o contexto disponível das fontes citadas; não recebe histórico ou memória. Fontes e texto são tratados como dados não confiáveis, sem ferramentas ou execução de código.
- Estados: `SUPPORTED`, `PARTIAL`, `CONTRADICTED`, `INCONCLUSIVE`. As instruções diferenciam ausência de informação de contradição e pedem atenção a negação, entidades/modelos, datas, condições, unidades, causalidade e abstracts.
- Apenas parágrafos `SUPPORTED` permanecem na síntese. Os demais são removidos por inteiro; o revisor não tem autorização para reescrever conclusões. Se não restar nenhum parágrafo, é exibido o fallback com os trechos originais e aviso de omissão. Isso não transforma as próprias fontes em fatos comprovados.
- Revisão ausente, inválida, duplicada, incompleta, com índices/estados desconhecidos, erro do provedor, falta de tempo ou cancelamento impede a publicação da candidata gerada. A saída tardia da revisão também é descartada.
- Validações anteriores de IDs, trechos literais, números, unidades, links e tamanho continuam obrigatórias **antes** da revisão. O revisor não pode aprovar conteúdo que falhou nessas validações.
- Proveniência dos parágrafos mantidos é reindexada, preservando o índice original. Classificações e motivos de vocabulário fechado ficam no checkpoint; relatórios e exportação JSON incluem a contagem por estado, sem inserir a conclusão removida na redação ou nos achados gerados.

## Recursos e retomada

No máximo um par geração/revisão por job, depois das rodadas adaptativas. O orçamento de até 25 s é compartilhado: a geração recebe até 15 s/60% do restante; a revisão recebe até 12 s, limitada pelo restante. Não há retry ou troca automática de modelo. O cliente continua com teto de 1.800 tokens por chamada; a revisão pede somente JSON curto. `VEXX_RESEARCH_SYNTHESIS=0` mantém o modo extrativo.

O timeout é passado ao cliente HTTP; cancelamento/limites são conferidos antes e depois das chamadas e não interrompem imediatamente um socket já em curso. Se o processo cair após registrar a tentativa, a retomada não repete automaticamente as inferências. Pesquisas já concluídas não são reprocessadas ou alteradas.

## Testes executados

- Baseline: **51 passed**.
- Focados finais: **84 passed**, incluindo 33 novos casos parametrizados/testes. Cobrem os quatro estados, os 12 cenários adversariais controlados, remoção seletiva, reindexação, revisão faltante/malformada/duplicada, deadline compartilhado, resposta tardia, cancelamento, checkpoint, isolamento, relatório, exports e ausência de credenciais em erros/eventos.
- Os testes determinísticos usam revisores explicitamente simulados para conferir o comportamento do sistema. **Não medem capacidade semântica do modelo**. As fixtures antigas foram adaptadas ao segundo estágio, conservando suas assertions de segurança, conteúdo e retomada; nenhuma foi removida.
- Suíte completa final: **1.220 passed, 4 skipped, 2 warnings em 142,60 s**. `git diff --check` e verificação dos arquivos de entrega contra as credenciais locais executados ao concluir.

## Avaliação com modelo real

Modelo preservado: `poolside/laguna-s-2.1:free`. Corpus congelado: `benchmarks/semantic_support_v1.json`, com **12 casos sintéticos**, rubrica humana, três sustentados e nove sem suporte completo. Inclui quote que omite uma negação presente no contexto, produto semelhante, anos/valores trocados, causalidade, afirmação parcialmente sustentada e dado ausente. Não usa produtos reais ou busca web.

1. Primeira rodada: concordância exata **6/12**, com um erro de disponibilidade. Os nove casos sem suporte completo não receberam `SUPPORTED`. Houve confusão entre falta de informação e contradição.
2. Após explicitar a distinção e acrescentar um exemplo geral de classificação, mantidos casos/gabaritos: concordância **7/12**, com uma revisão inválida e uma indisponível. Dos retornos válidos, houve três classificações incorretas. Novamente, nenhum dos nove casos sem suporte completo recebeu `SUPPORTED`; os três controles sustentados foram aceitos.
3. Smoke completo de **geração + revisão reais**: candidata sustentada aceita, em **5,033 s**, com fonte fictícia identificada, banco descartável e duas chamadas. Sem leitura web ou interface de produção.

A concordância mede somente o estado, não a categoria de motivo. As duas rodadas usam o mesmo conjunto e são diagnóstico, não um teste independente de generalização. Zero liberações indevidas nessa amostra pequena **não garante ausência de falsos positivos**. O modelo ainda confunde `PARTIAL`/`INCONCLUSIVE` com `CONTRADICTED`; portanto, esses rótulos são avaliações automáticas sujeitas a erro, não provas de que uma fonte refutou um fato. A barreira conservadora funciona nesses exemplos, mas a classificação não atingiu qualidade suficiente para ser usada como selo de veracidade.

Foram 24 chamadas isoladas de avaliação e duas no smoke, sem retries automáticos, novo provedor, assinatura ou mudança de plano. Custos seguem a configuração existente. Ferramenta opt-in: `tools/evaluate_semantic_support.py --live`; `--output` permite preservar rodadas anteriores.

## Arquivos, evidências e limites

Produção: `research_synthesis.py`, `research_agents.py`, `research_exports.py`, `pc_agent.py` (documentação da chamada) e `.env.example`. Testes: `tests/test_semantic_support.py`, `tests/test_research_synthesis.py`. Corpus, ferramenta e este relatório completam a entrega.

Evidências em `qa-artifacts/semantic-support-*`: baseline/focados/suíte, resultados das duas rodadas reais e smoke completo. O relatório anterior de síntese permanece como histórico da primeira entrega.

Limites: o mesmo modelo faz a redação e a revisão em chamadas separadas, podendo repetir vieses/erros. A revisão usa somente o contexto recuperado e não estabelece verdade, causalidade ou precisão universal. Conteúdo externo pode conter instruções maliciosas; não é executado, mas não se afirma imunidade a influência sobre o julgamento do modelo. Não houve teste visual, telefone físico ou publicação nesta etapa.

Próximo trabalho de qualidade: conjunto independente mais diversificado e melhor calibração das classes de ausência/contradição, antes de ampliar escopo ou apresentar selos de confiança ao usuário.
