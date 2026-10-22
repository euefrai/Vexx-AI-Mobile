# V5.9.2 — benchmark universal

Execução em 22/10/2026. Evidências originais em `qa-artifacts/v592/`. Snapshots de rede variam; diferenças de tempo não são benchmark controlado de latência. Resumo reproduzível: `python tools/compare_universal_v592.py`.

## Sete sondas externas obrigatórias

| Pedido | Antes → depois (s) | Resultado comprovado |
|---|---:|---|
| Salvador → São Paulo, +30 dias, um adulto | 12,865 → 8,251 | Data 21/11/2026 e rota preservadas; zero tarifas/inventário confirmados |
| Salvador → Feira de Santana, +7 dias | 10,585 → 8,030 | Data 29/10/2026 e modo ônibus preservados; zero passagens confirmadas |
| 100 USD → BRL agora | 10,638 → 0,314 | Referência diária: 5,0233 BRL/USD em 21/10/2026; 100 USD = 502,33 BRL |
| USD/BRL últimos 30 dias | 8,408 → 0,327 | 22 observações existentes; nenhum dia fictício |
| Salvador, notícias últimos sete dias | 8,318 → 5,102 | Sem fonte útil suficiente |
| Recife, eventos próximas duas semanas | 12,595 → 2,264 | Uma página de contexto; nenhuma agenda/data de evento/ingresso confirmado |
| Comparar fontes de acontecimento recente | 4,382 → 4,051 | Sem correspondência suficiente; comparação factual não demonstrada |

Baseline de moedas usou pesquisa web; final usa adaptador estruturado de dados atuais. A redução observada não mede aceleração geral de buscas. Taxas são referências diárias ECB via Frankfurter, não cotação intradiária negociável; horário de consulta separado da data da taxa, horário da taxa desconhecido. Sem spread, impostos ou transações. Fonte e parâmetros em `external-fx.json`.

`final-universal-validated.json` preserva erro `JSONLimitError` de eventos. `events-cache-repair.json` registra somente a repetição desse caso após reparo do cache opcional. `universal-comparison.json` mantém proveniência/erro anterior. Página turística de Recife não comprova eventos na janela. Textos capturados antes do último ajuste de formatação permanecem snapshots originais.

## Categorias A–L

| Grupo | Cobertura exercitada | Nível / limite |
|---|---|---|
| A Produtos | Notebook, celular, tênis, fones, eletrodoméstico, livro, ferramenta, componente, autopeça, móvel e esporte | FIXTURE de preservação; shopping congelado 59/59; nenhuma nova oferta comercial confirmada |
| B Voos | Rota, data e adulto | EXTERNAL_E2E de pesquisa; inventário não verificado |
| C Ônibus | Rota, modo e data | EXTERNAL_E2E de pesquisa; inventário não verificado |
| D Moedas | Conversão, histórico e sentido do par | EXTERNAL_E2E USD/BRL e CHROME_E2E; outros pares somente contrato/fixture |
| E Notícias | Localidade e janela de publicação | EXTERNAL_E2E insuficiente; publicação não prova ocorrência |
| F Eventos | Cidade e janela futura | EXTERNAL_E2E parcial, contexto apenas |
| G Ciência | Baterias e semicondutores | Três abstracts/DOIs reais para baterias; semicondutores em FIXTURE; nenhum full text comprovado |
| H Tecnologia | CPUs e Transformer | FIXTURE de preservação, sem comparação externa nova |
| I Documentação/geral | FastAPI, Django, asyncio, cursos, serviço público e história | FIXTURE de contrato, não prova resposta factual |
| J Documentos | PDF e planilha | FIXTURE; experiência congelada cobre documentos locais, sem novo PDF externo |
| K Multimídia | Imagens e vídeos com origem | CHROME_E2E de imagem local/zoom; vídeo não assistido/analisado |
| L Contradições | Valores divergentes e replanejamento | LOCAL_E2E de pipeline com fixture; divergência aberta exige verificação |

`tools/bench_universal_v592.py`: **32/32 contratos preservados**, relógio fixo 22/10/2026. `retrieval_quality=not_measured`. Isso não equivale a 32 pesquisas úteis ou respostas corretas.

## Profundidade e qualidade

- Baseline reproduziu verificação/síntese/auditoria feitas após nova busca e consultas genéricas sem assunto. Teste atual executa recuperação, lê nova evidência e exige seus dados na síntese e no checkpoint público.
- Baseline de snippet produzia PARTIALLY_SUPPORTED com zero fontes lidas. Teste atual impede suporte por evidência explicitamente não lida.
- Sonda científica real `deep-real.json`: 4,13 s, três abstracts Crossref/DOIs, sem LLM/full text. Capturada antes do reparo da falsa lacuna de notícias para ciência; o estado parcial antigo não é anunciado como resultado final atual. Regressão posterior passou em testes focados e suíte completa.
- Quality Lab v2 inalterado: precision@k **0,275**, recall@k **0,916667**, MRR **1**, nDCG **0,925589**. Nenhuma melhoria demonstrada nesses escores; dataset preservado.
- Último snapshot comercial externo V5.9.1: **0/3 ofertas confirmadas**, evidência histórica, não nova medição V5.9.2. Shopping 59/59 é determinístico.

Reprodução sem rede: benchmarks convencionais e `python tools/bench_universal_v592.py`. Com rede: `python tools/retrieval_recovery_v592.py --output <arquivo-novo.json>`, preservando snapshots anteriores. Chrome: `python tools/chrome_e2e_v592.py`, com Chrome/dependências locais. Fixtures usam banco temporário, sem dados de produção.
