# Pesquisa: seis casos reais e correção de integridade dos trechos

## Resultado principal

A recuperação está mais estável, mas **a qualidade das respostas ainda é insuficiente neste conjunto pequeno**. Foram avaliadas duas rodadas reais dos seis casos, usando SQLite temporário e os componentes existentes de pesquisa, compras e continuação. Nenhum chat ou banco do usuário foi utilizado. Não foi um teste autenticado da interface nem um benchmark cego de acurácia.

O laboratório local existente também foi executado (`run_research_quality_lab.py`). Recall@5, MRR@5 e nDCG@5 foram 1,0 no corpus congelado; precision@5 foi 0,266667. Essas métricas de recuperação local não representam qualidade de respostas na web. O avaliador ao vivo reutiliza as métricas mecânicas de citação do laboratório, sem atribuir suporte semântico automaticamente.

## Casos observados

| Caso | Tempo antes / depois | Resultado na segunda rodada |
|---|---:|---|
| Preço Galaxy A56 256 GB no Brasil | 14,164 / 19,465 s | Não atendido: zero ofertas confirmadas do modelo; uma TV apareceu indevidamente como alternativa próxima de celular. |
| Outro modelo parecido e seu preço | 0,014 / 0,025 s | Bloqueado pelo pré-requisito: nenhum produto confirmado apareceu na resposta anterior. O componente retornou `None`; o fallback do chat completo não foi avaliado. |
| Galaxy A56 versus A36: bateria, proteção, atualizações | 11,420 / 6,011 s | Parcial: duas fontes secundárias lidas, mas resposta extrativa sem conclusão verificada nas três dimensões pedidas. |
| Notícias de IA no Brasil nas últimas 24 horas | 5,308 / 6,134 s | Não atendido: página geral sem data; não demonstrou o período solicitado. |
| Estudos com placebo sobre creatina e força em adultos | 3,594 / 14,026 s | Não atendido: nenhum estudo recuperado, nenhuma chamada de redação. |
| Comparar condições das recomendações FDA/EFSA sobre cafeína | 17,298 / 20,365 s | Parcial: três fontes secundárias; documentos originais das duas entidades não foram recuperados, portanto divergência não demonstrada. |

Na segunda rodada houve seis links de citação em respostas de pesquisa; todos correspondiam a fontes recuperadas. **Isso não prova suporte das afirmações nem validade factual das fontes.** Nenhuma das três tentativas de redação assistida da segunda rodada foi aceita; os motivos incluíram resposta vazia/inválida e indisponibilidade do provedor. Os fallbacks permaneceram ativos; validadores não foram afrouxados. As variações de tempo e de fontes ao vivo não podem ser atribuídas à correção.

Contadores lógicos da segunda rodada: compras registraram seis tentativas de provedor e seis páginas consultadas; cada um dos quatro jobs de pesquisa debitou uma busca e três páginas. Houve uma tentativa de redação em comparação, notícia e divergência; zero em ciência e nas duas rotas comerciais. Contadores de páginas incluem tentativas sem evidência útil; não equivalem ao número de requisições HTTP (redirects e operações internas não foram contados individualmente). A continuação não fez nova consulta.

## Causa corrigida

O seletor de trechos usava posições fixas em caracteres. No caso real de divergência, começava no último dígito de um número: o trecho exibia `0` onde o texto original continha `200`. Foi reproduzido no texto da mesma página, no deslocamento 800; o início íntegro era 798. Isso afetava a integridade da evidência exibida mesmo quando o modelo era rejeitado pelos validadores.

- `web_extract.melhor_trecho`: janelas começam e terminam em limites de tokens separados por espaço, preservando sinais, datas, números e decimais. Mantém trecho literal, limite de tamanho e custo limitado de varredura; um token maior que a janela é omitido, não truncado.
- `research_agents.agente_sintetizador`: o corte de 300 caracteres da resposta extrativa usa a mesma proteção, para não reintroduzir o erro na exibição.
- Replay congelado: início corrigido de 800 para 798, trecho literal de 395 caracteres, número completo preservado. Esta comparação isolada comprova a correção; não mede acurácia geral.
- Não garante fronteiras de frase nem preservação de toda ressalva semântica em um trecho curto. Não foi estabelecida a veracidade da recomendação clínica citada; o teste verifica integridade textual.

## Implementação e evidências

- `tools/evaluate_live_research.py`: avaliador opt-in (`--live --output <diretório novo>`), subprocessos limitados a 65 s por caso, workspace temporário, sem chats reais ou troca automática para modelo pago. A redação usa apenas o modelo configurado terminado em `:free`, sem fallback de modelos.
- `tests/test_excerpt_boundaries.py`: dez regressões para início/fim de números, sinais, decimais, datas, tokens longos e renderização extrativa.
- `qa-artifacts/live-research-six-assessment.json`: avaliação consolidada, com limites explícitos.
- `qa-artifacts/live-research-boundary-result.json`: resultado do replay da falha real.
- Capturas completas locais em `qa-artifacts/live-research-six-baseline/` e `qa-artifacts/live-research-six-after/`; texto público do replay em `qa-artifacts/live-research-boundary-replay.json`.

## Testes

- Baseline novo: nove falhas antes da correção; a décima regressão cobre o corte adicional na renderização.
- **131 testes focados passaram**. Uma primeira invocação apontou um nome de arquivo inexistente e não executou testes; foi corrigida para os arquivos reais. A execução válida está em `qa-artifacts/live-research-focused.log`.
- Suíte completa: **1.308 passaram, 4 ignorados, 2 avisos em 324,41 s**. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. Log local: `qa-artifacts/live-research-full.log`.
- `git diff --check`: sem erros.

## Pendências priorizadas

1. Bloquear alternativas comerciais de categoria incompatível e melhorar descoberta do modelo exato. Não oferecer TV como alternativa de celular.
2. Exigir documento e data compatíveis com o período nas notícias; um índice geral não prova notícia recente.
3. Melhorar fontes acadêmicas e priorizar documentos originais quando o usuário pedir comparação entre entidades específicas.
4. Avaliar a continuação novamente após uma pesquisa que realmente confirme produto visível, sem fabricar esse pré-requisito.
5. Investigar falhas de geração separadamente da recuperação; citações e quantidades continuam passando pelos validadores existentes.

Este relatório registra avaliação e código local. Não houve push, deploy ou recarga do PC Agent nesta etapa.
