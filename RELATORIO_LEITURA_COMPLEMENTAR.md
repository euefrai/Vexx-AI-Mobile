# Pesquisa: leitura complementar e preservação de fontes — 04/11/2026

## Resultado

Corrigidas perdas entre descoberta, leitura, seleção de trechos e apresentação.
A Embraer passou a mostrar fundador e data de fundação nas duas perguntas da
matriz. O Python passou a conservar a regra geral sobre retorno e a localizar
`list.pop`, sem atribuir a ele o retorno de outro método.

Isso não aprova a síntese universal. O proxy Hermes recusou autenticação e o
modelo gratuito anterior não estava no catálogo. O DeepSeek selecionado no QA
retornou cota esgotada. Um teste adicional com Mistral terminou parcial, sem
síntese assistida validada. Os resultados recuperados foram preservados.

## Causas e correções

1. Linhas curtas de tabelas perdiam para prosa que apenas mencionava o assunto.
   A seleção agora considera o cabeçalho real e o rótulo inicial do campo.
2. Uma fonte já lida e vinculada à entidade era descartada novamente porque
   título e trecho curto não repetiam seu nome. O filtro final revalida as
   passagens literais e o escopo da tabela. Cabeçalho de outra empresa, hash
   inválido, texto adulterado e restrições não confirmadas continuam rejeitados.
3. Metadados genéricos substituíam títulos que identificavam o assunto. Quando
   necessário, o título literal do documento é preservado, sem inventar nomes.
4. A regra geral de retorno do Python era perdida entre extração e síntese.
   Ela agora acompanha os trechos como contexto, com offsets e hash verificados.
   Não comprova automaticamente o retorno de cada operação.
5. Métodos curtos, como `pop`, eram excluídos do inventário. APIs explicitamente
   qualificadas agora são preservadas; a palavra isolada continua insuficiente.
6. Reformulações removiam pontos e a linguagem da consulta. O nome qualificado
   pode ser recuperado do pedido original quando os seus segmentos continuam
   juntos, e “Python” acompanha as frentes técnicas pertinentes.
7. O leitor procurava “return/returns”, mas a documentação atual de `pop` usa
   “returned”. Essa forma é localizada e conservada como suporte parcial somente
   dentro da definição de API alinhada; título isolado não fornece esse vínculo.
8. Preferências de fontes eram duplicadas e “primárias” podia virar “oficiais”.
   As preferências agora permanecem distintas. Nas lacunas de autoridade, a busca
   ampla ganha prioridade sem descartar o contexto enciclopédico inicial.
9. A versão interna do cache de leitura mudou para invalidar recortes antigos,
   preservando mensagens, histórico e dados do usuário.

## Arquivos

- `web_extract.py`: tabelas, contexto de retorno, títulos e localização de formas verbais.
- `research.py`: conservação das fontes vinculadas, contexto e versão do cache.
- `evidence_graph.py`: retorno passivo somente no escopo verificado da API.
- `query_intelligence.py`: preferências, subconsultas e qualificação técnica.
- `python_docs_discovery.py`: nomes curtos e recuperação de APIs explícitas.
- `research_agents.py`: persistência do contexto e recuperação de fontes oficiais.
- `tests/test_research_complementary_reading.py`: regressões positivas e negativas.

## Verificações independentes

**A — Leitura:** replays de documentos reais da Embraer e Python, com limites de
texto preservados, recuperaram campos e passagens antes descartados. Testes
controlados verificaram offsets, hash, métodos diferentes, outro cabeçalho e
contexto sem prova direta. Esses testes controlados não são testes de produção.

**B — Descoberta:** as consultas pela interface não receberam URLs. A busca
localizou os artigos da Embraer e a página do Python por inventário oficial.
O teste de `pop` confirmou a recuperação do item retornado após corrigir toda
a cadeia, não apenas a consulta direta ao inventário.

**C — Síntese:** não aprovada nesta rodada. A cota/autenticação impediu a
validação com o provedor usado anteriormente. A tentativa Mistral ficou parcial.
A regra geral `None` continuou como contexto, sem virar confirmação automática.

## Interface real

Aplicação local completa, SQLite/conta descartáveis e rede real. Foram sete
cenários: duas perguntas da Embraer, comparação append/extend, retorno de pop,
duas perguntas de Rust e uma pesquisa profunda da Embraer no Mistral.

- Sete de sete preservaram texto, mensagens e cards após reload.
- Zero erros de console capturados e nenhum overflow da página em 390 px.
- Clique real abriu o artigo da Embraer e a documentação em `#list.pop`;
  nenhum dos dois levou à home. Não foram testados todos os links e botões.
- As consultas de Rust ainda precisam de fonte primária para o criador e de
  confirmação de autoridade. Contexto da Wikipédia não foi rotulado como oficial.

Dados e respostas: `qa-artifacts/research-complementary-reading-real.json`.
As primeiras tentativas com o modelo ausente do catálogo foram falhas do harness
antes do envio; não foram contabilizadas como consultas aprovadas. A seleção
DeepSeek/Mistral foi explícita na conta privada de QA, sem alterar a configuração
do usuário nem introduzir fallback entre provedores no aplicativo.

## Testes e limites

As regressões focadas passaram, incluindo os controles contra atribuição do
retorno de outro método e contra aceitação de tabela adulterada. A suíte final
completa é registrada no fechamento abaixo. Não foram eliminados testes.

Suíte completa final: **2.669 aprovados, 4 pulados, 2 avisos; exit 0 em
198,20 s** (`qa-artifacts/complementary-reading-verified-full.log`). Os avisos
são as depreciações conhecidas de mss e timeout no TestClient. O diff-check
dos arquivos desta etapa passou. Uma captura mobile da Embraer foi inspecionada;
isso não constitui auditoria visual de todas as telas.

As alterações de segurança/watchdog existentes no workspace foram preservadas.
O agente de produção não foi reiniciado. Esta rodada valida funcionamento local;
não comprova implantação no Render nem disponibilidade dos provedores.

O código desta etapa foi enviado a `origin/main` no commit `d2fcdb5`, com o hash
remoto conferido. O relatório e a matriz preservam as falhas de cota/autenticação
e o resultado parcial da síntese, em vez de classificar a rodada como sete
pesquisas completas. O push não comprova implantação concluída no Render.

Preparação do push autorizado: o conjunto selecionado foi exportado do índice
Git, sem o WIP de outras frentes. A suíte completa dessa árvore passou:
**2.644 aprovados, 4 pulados, 2 avisos; exit 0 em 304,84 s**
(`qa-artifacts/complementary-reading-publish-isolated.log`). A diferença para
2.669 corresponde ao conjunto de alterações/testes locais que não integra esta
publicação; não foram removidos testes do repositório. O código validado não
recebeu novas alterações após essa execução.

O diagnóstico seguinte e as propostas para reduzir falhas de acesso estão em
`docs/RESEARCH_ACCESS_RECOVERY_PLAN.md`. Três requisições públicas reais estão
registradas em `qa-artifacts/research-access-channel-probe.json`; não são novos
testes de interface, geração de respostas ou validação do ambiente de produção.

## Próximo passo exato

Disponibilizar um modelo com autenticação/cota válida e repetir os mesmos casos
de síntese. No Mistral, capturar a causa específica do fallback de geração/revisão
antes de mudar os validadores. Para Python, conferir a aplicação da regra geral
a cada método. Para Rust, descobrir e ler a fonte primária do criador, mantendo
separadas descoberta, leitura, autoridade e afirmações publicadas.
