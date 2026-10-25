# VEXX AI V5.9.9.4 — Evidence Intelligence

**Decisão: NO_GO.** Correções locais aplicadas/testadas, mas não existe ganho
externo consistente nem pesquisa autônoma completa fundamentada com modelo.
Não publicar com base no número de testes ou nas métricas sintéticas.

## Estado e commits

- HEAD inicial921f27b; branch codex/v598-autonomous-research; worktree vexx-v598-dev.
- HEAD final de aplicação/testes a91c113. O commit de documentação/artefatos é
  informado na entrega; os freezes contêm hashes exatos do código avaliado.
- e8f9443: corpus/baseline; beab357: calibração/preservação/diagnóstico.
- 13b3013/f5f1561: nova avaliação e correção da direção causal.
- 76e6af3/a91c113: reprodução da corrupção HTML e correção da ordem.
- Nenhum push/deploy, reinício de produção ou escrita em SQLite real.
  Studio, VERY, extensão Júlia e identidade Lucas preservados.

## Bugs e correções

1. Fábrica no nome de uma empresa era confundido com verbo fabrica.
2. Variante III respondia sobre variante II; limites de entidade corrigidos.
3. Relações explícitas com auxiliares e inglês eram descartadas.
4. Pontos de APIs eram normalizados junto com pontuação de frases; agora a
   normalização é específica ao identificador, preservando prototype.
5. Contexto imediatamente adjacente de pronome/assinatura podia desaparecer.
6. Peso sem condição de bateria/cartão era promovido a completo; agora parcial.
7. Deduplicação por passagem perdia associações com vários requisitos.
8. Causa era promovida a consequência; direção/sujeito vinculados explicitamente.
9. Mini-DOM movia nomes, links, negação e parâmetros para depois do texto.
   Ordem inline preservada, parágrafos sem duplicação e densidade de links
   sem contagem dupla. Assinaturas deixam de virar set(, ) key value.
10. Diagnóstico de provedores não distinguia claramente consulta/resultado.
    Observador opt-in redigido, isolado por contexto, sem custo de LLM.

Regressões intermediárias detectadas e corrigidas: índice incorreto do retorno
do downloader, normalização de asyncio.TaskGroup e limites de pontuação final.
Nenhum teste removido ou assert antigo relaxado. Logs com falhas preservados.

## Corpus e medidas

125 exemplos SYNTHETIC:74 DEV,34 VALIDATION,17 inicialmente selados;12 domínios,
nove labels, documentos/variantes agrupados na mesma divisão. Sem dados
privados, sem trechos sintéticos apresentados como publicação externa.
Anotação/revisão pelo próprio agente: não é gold humano independente. Não
cobre suficientemente notícias/localidade/datas completas/republicação ou
todas as relações naturais. Critérios e matrizes nos documentos/JSON.

DEV74:TP 8/FP 2/FN 5/TN 59→TP 13/FP 0/FN 0/TN 61; precisão 0,8→1,0;
recall 0,6154→1,0;F1 0,6957→1,0; FPR 0,0328→0;FNR 0,3846→0.
Recall dos dois parciais1→1, mas promoções indevidas2→0;
precisão de DIRECT0,6→1,0. VALIDATION34 manteve4TP/30TN, sem parciais.
17 selados:TP 5/TN 12 mantidos; uma promoção parcial eliminada.
Esses números não estimam precisão/recall universal ou factual da web.

## Internet e trade-offs

- Doze novos:0→1 leituras elegíveis; a única nova foi julgada como atributo
  incorreto. Não houve ganho de qualidade demonstrado.
- Oito novos após direção:7→3 elegíveis. A revisão encontrou dois parciais
  úteis perdidos e duas candidatas problemáticas removidas; parte dos restantes
  ainda mistura alternativas de exercícios ou assinatura mal extraída.
- Seis novos após DOM:1→1 elegíveis, mesmas26 chamadas/48 fetches/18 abertas.
  Melhor ordem textual não resultou em mais respostas entregues nessa amostra.
- Históricos20, antigos12, antigos15 e V5993vinte executados separadamente
  com beab357. Contagens completas em external-comparison.json.
- Amostra manual de 24 títulos/URLs Bing:6pertinentes ao tema(25%). Não mede
  texto lido ou respostas corretas, nem precisão populacional do provedor.
- Consultas com entidades corretas retornaram hotéis/dicionários. Não houve
  novo provedor, aumento de chamadas ou relaxamento de filtros para obter PASS.

Cada nova correção semântica teve novas perguntas congeladas antes. Resultados
abertos tornaram-se diagnósticos; não reutilizados como aprovação independente.
As medianas de rede variaram; não há atribuição causal de ganho de latência.

## Modelo e entrega

Quatro tentativas autenticadas de pesquisa, entre beab357/a91c113: fontes
insuficientes, respostas parciais persistidas, nenhuma síntese LLM executada.
Cancelamento real sem resultado final. Duas tentativas **isoladas** de síntese
gratuita leram MDN e receberam respostas; ambas rejeitadas. A final teve JSON
inválido(691 caracteres/4,765 s), sem revisão/retry. Não são E2E completos.
Modelo poolside/laguna-s-2.1:free; sem fallback pago ou chamadas por passagem.

Um teste com URL semeada explicitamente leu páginas públicas e percorreu
extração/classificação/SQLite/JDUI/IndexedDB. É discovery fixture com leitura
real, não descoberta autônoma. Não promoveu cobertura parcial a resposta completa.

## Interface, segurança e recursos

Chrome real:1280/390/320, zoom CSS200% com scroll local, teclado/CSV/readonly,
reduced-motion, reload, IndexedDB, fontes abrindo MDN, offline/reconexão.
Capturas dos cards inspecionadas. Page errors dos fluxos[]. Não certifica
telefone físico, todos os modais, comparação no chat ou WCAG completa.

Auth/RBAC/CSRF/owner isolation/SSRF/DNS/redirect/rate limits/tool grants,
checkpoint/cancelamento/WAL/sanitização mantidos e cobertos pela suíte existente.
Proteção de artefatos privados por gitignore; varredura de segredos registrada
no pacote de QA. Não executar HTML/JS externo ou código do modelo.

Microbenchmark1000 parágrafos:62,77→68,10 ms, pico Python1,94→2,68 MB. A ordem
correta tem custo medido; não alegar redução de RAM. Limites de bytes/HTML/texto,
fontes, paralelismo e profundidade mantidos. Amostra idle do primeiro QA:
relay 35,7 MB/agent 3,76 MB, CPU 0% em0,2 s; não é pico ou medida de produção.

## Testes e arquivos

Final: **1595 passed,4 skipped,2 warnings,258,73 s**.
Skips: duas inferências bloqueadas, DDG sem resultados e shopping HTTP403.
Warnings existentes de mss e TestClient. Search 34/34,Shopping 59/59,Experience 16/16.
Node syntax/py_compile/diff-check executados; não mascaram as falhas externas.

Aplicação: evidence_graph.py,query_intelligence.py,research.py,research_agents.py,
research_view.py,search_providers.py,web_extract.py e .gitignore.
Regressões:tests/test_evidence_calibration_v5994.py e test_ordered_extraction_v5994.py.
Avaliação: novos corpus/holdouts em benchmarks/; ferramentas de avaliação,
síntese/entrega/Chrome em tools/; documentação em docs/v5.9.9.4/ e evidências
em qa-artifacts/v5994/. Artefatos antigos não rastreados foram preservados.

## Pendências prioritárias

1. Exercícios/alternativas versus gabaritos, cabeçalhos+listas causais e
   perda de passagens técnicas nos filtros de contexto/seleção.
2. Anotar HTML/passage/span públicos com revisão independente suficiente.
3. Descoberta ainda pouco fiel; corrigir com evidência de ganho, sem mais
   chamadas ou aceitação temática como resposta.
4. Contrato JSON do modelo gratuito e pesquisa autônoma completa permanecem
   não aprovados. Não enfraquecer validação para produzir texto final.

Próximo procedimento exato em docs/v5.9.9.4/PROGRESS.md.
