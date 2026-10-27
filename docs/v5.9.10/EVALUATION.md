# Evidência e critérios

Sem ajuste de retrieval depois de abrir o novo holdout. Conjunto congelado no commit `e8d8e0c`; avaliação agente, sem gold humano independente. Consultas internas e externas capturadas separadamente; não somar seus resultados como candidatos únicos. Código de retrieval avaliado: `f0977ea`. Mudanças posteriores tratam transporte, foco e lifecycle.

## Comparações controladas

| Verificação | Observação | Limite |
|---|---|---|
| Requisitos | Regressões naturais, negação, números/condições e entidades; 92 testes no grupo de query e 10 no arquivo novo final | Não comprova entendimento universal; follow-ups continuam no resolvedor existente. |
| Corpus/provedores congelados | Bosch: mesmo SHA `37322e0c339015cac0f6d2b34ac856fd4ca9ab4bd5ac9fcaa7d21e208a8eda86`, 16 URLs no pool, 12 registros, 10 tentativas. Antes 0 fontes retidas; depois 1, com três facetas **PARTIALLY_SUPPORTED** | Pool retorna os mesmos primeiros candidatos para cada consulta. Neutraliza qualidade de consulta; demonstra retenção/metadados, não ranking ou descoberta. Registros ausentes falham como `frozen_missing`. |
| Leitor conhecido | Sete snapshots públicos locais; todas as passagens escolhidas são literais. Math.hypot cobre três facetas; Object.assign preserva suporte parcial. Nikon mantém 767 caracteres e duas passagens com `source_span` | Apenas sete snapshots disponíveis; não alegar WEG nessa bateria de leitor. WEG teve leitura autônoma no QA. Tramontina não obteve passagem suficiente nesse corpus. |
| Extração longa | `_document_windows` e teto de 8.000 preservados; suíte de regressão cobre offsets/limites | Não houve aumento automático de janela, tokens, fetches ou slots. |

Dados completos permanecem locais em `qa-artifacts/v5910/raw/`, ignorados pelo Git. Sumários públicos têm hashes, estados e URLs; não contêm páginas integrais, credenciais ou conteúdo de reasoning. Replay local requer esses snapshots, não apenas o clone Git.

A primeira reprodução unitária continha um negativo excessivo: uma frase de fato sustentava fundação. O fixture foi corrigido antes da implementação, preservando o caso realmente negativo; baseline corrigido: cinco falhas e três passes. Logs original/corrigido foram mantidos localmente. Isso não foi uma mudança de critério do holdout.

## Holdout externo novo

16 perguntas, cobrindo tecnologia, ciência, história, notícias, empresas, produtos, geografia, educação, esportes, cultura, documentação, comparação, múltiplas facetas, ambiguidade, restrições e escassez. Sem URL semeada e sem LLM nesta trilha.

**3/16 retiveram entradas; 0/16 retiveram IDs de passagens vinculadas a requisitos.** As três categorias foram geografia, educação e esportes; seus esquemas de requisitos não eram aplicáveis. Portanto, entradas lidas/contextuais não viram cobertura completa por conveniência. Há fontes potencialmente pertinentes, mas não há validação suficiente para chamar essas três pesquisas de respondidas. Todos os demais casos ficaram sem evidência retida. O sumário apresenta seleção, leitura, perdas, consultas, orçamento e latência por pergunta.

Não comparar 3/16 com 2/12 da versão anterior como avanço causal: são perguntas e condições externas diferentes. **Descoberta universal não aprovada.** Não houve afinamento para os nomes do conjunto.

## Modelo real: contraste A/B/C

Modelo único gratuito: `poolside/laguna-s-2.1:free`, sem fallbacks pagos; non-streaming, máximo 1.800 tokens, até 15s para redação e 25s no par com revisão. Uma tentativa por caminho; nenhuma repetição até PASS.

- **B Research Agent:** HTTP 200, conteúdo 456 caracteres, finish `stop`, 175 tokens de saída, 4,371s. A citação não era reprodução literal do trecho recebido: rejeição `quote_mismatch`, antes da revisão.
- **A adaptador direto:** requisição exatamente igual à B, incluindo mensagens; timeout em 15s, sem resposta para validar.
- **C endpoint QA autenticado:** login, CSRF, FastAPI, relay e PC Agent reais, SQLite temporário. Mesmo objetivo, prompt de sistema, verificação, texto e ranges/IDs de passagens; somente ID de evidência e data de acesso diferem conforme o job. Timeout em 15,027s; checkpoint preservou evidência e estado bloqueado/interrompido. **Fonte conhecida explicitamente semeada somente neste contraste**, nunca contabilizada como descoberta.

O primeiro probe C usou grafia errada dos estados finais e fez polling por 210s; isso é erro do instrumento, não latência do modelo. Grafia corrigida. Captura de transporte mede a chamada real e não reporta esses 210s como tempo de geração.

O HTTP 200 vazio histórico não se repetiu. Sem corpo original não é possível determinar retrospectivamente sua causa. Parsing de text parts e perda de metadados foram reproduzidos com HTTP controlado e corrigidos; os resultados reais acima não autorizam dizer que a falha histórica foi resolvida.

## Nove cenários no chat real

Chrome real, origem QA local nova, conta de teste, nenhuma URL fornecida, FastAPI + PC Agent de desenvolvimento + SQLite descartável. Configuração/modelos registrados: somente o gratuito acima.

| Cenário | Resultado observado |
|---|---|
| Saudação | 2,665s, sem job profundo, resposta determinística, reload preservado. Não demonstra inferência LLM. |
| Web factual | 12,822s; Vidas Secas sem fontes pertinentes; limitação explícita. Falha de pesquisa, não PASS factual. |
| Empresa multifaceta | WEG, 27,208s: uma fonte lida autonomamente, fundador/data sustentados, produtos pendentes. Modelo respondeu HTTP 200 em 8,922s, mas candidato rejeitado por validação numérica; também há citação fora do excerpt entregue. Resultado extrativo parcial persistido. |
| Comparação | Entidade contaminada por “compare ... quanto ao”; nenhuma evidência retida; parcial persistido. |
| Notícias | Janela 20–27/10/2026/localidade mantidas; nenhuma fonte utilizável. Falha de recuperação, sem inventar notícia. |
| Escassez | Nenhum contador público recuperado; não inventou visitas; parcial persistido. |
| Deep novo | Revolução dos Cravos, 19,819s: sem evidências; entidade inclui instruções; parcial persistido. Não aprovou cadeia completa. |
| Mídia | Cinco imagens reais do Commons com origem/crédito/limites; não tratadas como evidência. |
| Cancelamento | Job cancelado em 2,902s, sem resultado final fabricado. |

WEG: `40,000` na fonte e `40.000` na resposta entram na proteção conservadora contra separadores de milhares ambíguos. Não classificamos automaticamente como alucinação numérica. A segunda conclusão ainda cita trecho que não foi entregue ao modelo; portanto não bastaria flexibilizar números. Validador e limite de passagens permaneceram intactos. Revisão semântica não executada quando redação falhou na validação.

Mensagens: SQLite 22/22 IDs únicos; IndexedDB 22/22, cinco respostas estruturadas e quatro resultados de job; reload preservou IDs/texto nos nove cenários. MD/CSV do job real baixados. Isso comprova entrega/persistência dos resultados observados, não correção factual de respostas ausentes.

Uma primeira tentativa de UI reutilizou cookie de outro QA com mesmo segredo fixo e SQLite novo: 403/503 e espera sem conclusão. Interrompida e guardada como falha de instrumento. Nova origem de navegador usou login novo; o harness agora gera segredo de sessão único por instância. Não confundir isso com teste de produção.

## JDUI, segurança e recursos

Chrome: fontes e galeria sem overflow em 1280/390/320, zoom CSS 200%, teclado/Escape/foco, reduced motion, estado de metadados após reload, link real aberto, exportações e fetch rejeitado offline seguido de health 200. Capturas inspecionadas. Viewports emulados, sem celular físico. O screenshot do modal após avançar mostra carregamento da segunda imagem; a primeira foi carregada de fato. Não alegar todas as imagens carregadas.

Primeira espera de estabilidade do instrumento perdeu o node durante remount periódico. Corrigido o instrumento para scroll atômico e espera do drawer, sem suprimir sync nem repetir modelo. Remount/foco possui reprodução controlada separada antes/depois. Limitação visual observada: título genérico “company” e data de criação do artigo no card WEG; placeholder estreito no composer de 320px. Pendentes, sem redesenho nesta versão.

Auth/RBAC/CSRF/SSRF/isolamento, revogação de sessão, named pipe, WAL, citações, quantidades e sanitização permanecem na suíte. Nenhuma mudança de permissão remota; QA usa controle remoto desativado. Não houve produção, push ou deploy. Limites originais mantidos; timings de etapas não incluem necessariamente a redação final fora da etapa do plano, por isso captura HTTP é a medida da chamada.
