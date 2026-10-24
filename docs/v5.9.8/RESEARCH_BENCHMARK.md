# Benchmark V5.9.8

## Comparação controlada reproduzível

Mesmo corpus e leitores artificiais, SQLite temporário, sem rede/modelo: V5.9.7 leu duas fontes, zero replanejamentos; V5.9.8 leu quatro, um replanejamento útil; ambas sem leitura duplicada. Tempos finais observados: 0,843 s e 1,908 s. O ganho é cobertura de dados extraídos, não redução de latência nem precisão externa demonstrada. Três lacunas inicialmente abertas receberam dados adicionais; síntese permanece parcial quando não há suporte suficiente.

Comando: python tools/bench_autonomous_v598.py --root <checkout> --output <arquivo>. Artefatos before-final.json e after-final.json. As etapas históricas fixture-* ficam preservadas. Holdout controlado de três casos está em holdout.json; não é medição de acurácia na internet.

## Recuperação externa

Foram executadas 12 categorias do dataset benchmarks/autonomous_research_v598.json, com SQLite temporário, sem modelo na rodada de recuperação. external-assessment.json aponta à observação mais recente disponível por caso. Rodadas distintas usam rede/provedores mutáveis e algumas precedem ajustes posteriores; não são comparação causal antes/depois nem aprovação universal. Zero fonte lida continua zero, mesmo com job terminal e JDUI válida. Não houve conclusão científica real aprovada.

DDG, Wikipedia e depois Crossref tiveram bloqueios/circuitos registrados; não houve tentativa de contornar bloqueios. Resultados de enciclopédia não foram promovidos a estudos originais. Notícia por feed não vale como artigo integral lido. Ofertas sem leitura/compatibilidade não valem como preço confirmado. Avaliação sem modelo não prova qualidade da síntese.

Uma rodada com seis fontes lidas falhou por resumo duplicado de 66.681 caracteres. Replay offline das sete evidências capturadas produziu as mesmas 12 afirmações e gravou 33.921 caracteres, preservando todos os IDs. storage-replay.json documenta isso. A rodada externa posterior não repetiu a exceção, mas retornou zero fontes lidas sob bloqueio de provedores; a prova do volume é o replay e o teste de regressão, não essa rodada vazia.

## Escopos separados

- FIXTURE/OFFLINE_REPLAY: regressões e antes/depois reproduzíveis.
- LIVE_EXTERNAL: descoberta/leitura real, sem autenticação UI ou aprovação de claims.
- AUTHENTICATED_E2E: seis perguntas e recarga no runtime antigo; um PASS, quatro PARTIAL e uma FAIL geográfica.
- REAL_MODEL: teste único gratuito limitado a 160 tokens, sem conteúdo público; BUDGET_LIMITED, não prova de inferência/síntese válida.
- COMPONENT_UI: Chrome local, componentes reais com replay, sem sessão de produção.

Baseline integral: 1385 passed, 4 skipped. Rodada anterior ao último ajuste de armazenamento: 1408 passed, 4 skipped. Suíte integral final após correção de armazenamento: **1409 passed, 4 skipped, 2 warnings** em 444,30 s; final-storage-pytest.log. Congelados: Search 34/34, Shopping 59/59, Experience 16/16; Quality Lab v1 P@5 0,266667, recall/MRR/nDCG 1 e duplicatas 0. Não se generaliza esse corpus para qualidade externa.
