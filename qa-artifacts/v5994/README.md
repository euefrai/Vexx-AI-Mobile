# Evidências locais V5.9.9.4

Decisão NO_GO. Este pacote contém resultados positivos e negativos; não é
certificado de precisão universal ou pesquisa profunda completa.

- code-freeze*.json: revisions/hashes dos candidatos antes de abrir cada onda.
- baseline-dev/validation e after-*.json: corpus sintético, anotação pelo agente.
- baseline-sealed/after-sealed: 17 exemplos operacionalmente selados, sem gold humano.
- external-comparison/provider-fidelity: doze novas perguntas e67 diagnósticas
  anteriores, candidato beab357. A única nova elegível era falso positivo de
  atribuição causal; causal-direction-replay registra correção no mesmo texto.
- direction-comparison: oito novas perguntas antes/depois de f5f1561.
- order-comparison: seis novas perguntas antes/depois de a91c113.
- post-*-guard: hashes verificados no momento da respectiva avaliação. O guard
  inicial foi supersedido pelas correções posteriores, não alterado retroativamente.
- full-suite*.log: tentativas e falhas preservadas. Final1595 passed/4 skipped.
- benchmark-*-order-final.log: Search34/34,Shopping59/59,Experience16/16.
- e2e-*.json/log: Chrome autenticado, SSE e persistência; completed_flow do
  harness significa encerramento mecânico, não SUCCESS_VERIFIED.
- isolated-real-model*: duas respostas reais gratuitas, ambas rejeitadas;
  a final falhou por JSON inválido. Não são testes de descoberta/chat completos.
- direct-delivery.json: última leitura pública com discovery semeada em fixture,
  store/pipeline reais. Sem modelo; não inferir busca autônoma bem-sucedida.
- visual-order-final e source-interactions-order-final: Chrome no candidato final.
- coverage-card-*.png e coverage-zoom-card-*.png: capturas dos cards efetivamente
  inspecionadas. Capturas antigas da mensagem inteira não mostram a tabela.
- local-job-diagnostics*: apenas jobs/contas de QA, sem sessão/cookie/credencial.
- extraction-performance: microbenchmark sintético, incluindo custo de memória.
- cleanup-*-runtime: relay/agent/SQLite temporários removidos, produção intacta.
- secret-scan: busca de valores exatos atuais, sem variantes codificadas/OCR.

Documentos lidos são URLs públicas reais; origens example.org pertencem apenas
às fixtures declaradas SYNTHETIC. Não há execução de conteúdo externo/modelo.
Textos brutos de leitura são diagnóstico local, não redistribuição de datasets
nem licença adicional sobre publicações. Não publicar este pacote automaticamente.

Metadados privados de processos/SQLite e trigger qa-stop são ignorados pelo Git.
Artefatos de versões anteriores e snapshots não rastreados não fazem parte da entrega.
