# Evidências V5.9.9.1

Implementação final:7011908; baseline:71e978e. Tudo é QA local ou consulta HTTP pública, salvo snapshots operacionais explícitos em leitura. Metadados privados, cookies, chaves, SQLite e gatilho qa-stop ficam fora do Git. Bancos QA foram removidos após parada graciosa.

- baseline/ e baseline-tests.log:20casos e suíte antes das mudanças.
- selection/:medição isolada da seleção,sem aumento de elegibilidade agregada.
- delivery-evaluation/ e delivery-holdout/:rodadas finais20/12,com revisão e SHA do dataset em cada caso.
- *-losses.json e retrieval-comparison-metrics.json:análise offline e escopos de contagem.
- source-reading-gain.json:uma URL antes/depois; leitura não é certificação de data/local.
- judged-sample.json:revisão estreita por agente,não gabarito humano ou precisão universal.
- e2e-case-*.log:primeira iteração; documento e espera de jobs revelaram falhas.
- e2e-final-case-*.log:repetições com polling correto,cancelamento/reload; o caso13ainda revelou trecho técnico errado.
- e2e-entity-accepted.log e e2e-entity-final-db.json:última repetição,fonte Python correta,mensagem final única e cinco IDs/linhas.
- e2e-extra-accepted.log:IndexedDB,MD/CSV,falha de imagem injetada e recuperação. O logextraanterior tem seletor de painel incorreto e não é aprovação.
- visual-final.log e screenshots:Chrome real,inspecionado,incluindo foto carregada no modal.
- real-model-stream.json:inferência gratuita real,PARTIAL,sem literalidade aprovada e sem raciocínio privado exportado.
- runtime-observation-final.json/runtime-control-status.json:produção em leitura,sem stop ou inferência de competição só por TCP.
- full-suite-final.log:1536passed/4skipped/2warnings; frozen-final-*:34/34,59/59,16/16.

Logs intermediários,erros de harness e resultados desfavoráveis foram preservados. Não somar FIXTURE,FROZEN_REPLAY,LIVE_EXTERNAL,REAL_MODEL,AUTHENTICATED_E2E ou falha injetada numa taxa única. Holdout final0/12elegíveis:pesquisa universal não aprovada.
