# Testes reais de pesquisa com perguntas variadas — 03/11/2026

## Veredito

A pesquisa ainda não funciona consistentemente fora dos cenários antes validados.
Oito consultas em seis temas: uma atendeu ao pedido, uma ficou parcial e seis
falharam. Nenhum teste usou resposta/fonte simulada. Aplicação local completa,
conta/SQLite descartáveis, busca externa e Reflection gratuito selecionado pela
interface. Isto não é validação do site em produção nem da disponibilidade de
outros modelos.

## Matriz

| Caso | Resultado observado | Avaliação |
|---|---|---|
| Pesquise quem fundou a Embraer e em que ano ela foi criada. Mostre as fontes. | Não recuperou fonte pertinente; nenhuma resposta factual | Falhou |
| Procure notícias desta semana de Ubatã e região; datas e links | Três matérias lidas, janela 02–03/11, datas nos cards e links específicos | Atendeu à coleta pedida; resumo extrativo |
| SSD Kingston NV3 1 TB, preço no Brasil e link do produto | Seis ofertas com preço, estoque e URL direta; modelo devolveu resposta vazia | Parcial |
| Faça uma pesquisa profunda: quem criou Rust e qual sua finalidade? Fontes oficiais | Retornou fallback comum; nenhum job profundo | Falha de roteamento e ausência de resultado |
| Investigue a fundo diferenças list.append/list.extend; retorno e mutação | Retornou fallback comum; nenhum job profundo | Falha de roteamento e ausência de resultado |
| Pesquisa profunda sobre Pitágoras, enunciado e exemplo | Job profundo criado, 11 páginas contadas, zero evidências; interrompida | Falha de recuperação/seleção |
| Pesquise a história da Embraer: fundação e fundadores. | Segunda formulação também sem fontes | Falha reproduzida |
| Pesquisa profunda sobre Rust: criador e finalidade, fontes oficiais | Agora criou job; 8 buscas/10 páginas, zero evidências; interrompida | Roteamento depende da formulação; coleta continua falhando |

Os oito resultados persistiram integralmente após reload, sem duplicação de
mensagens observada, sem erros de console capturados durante os fluxos e sem
overflow da página em 390 px. Isso comprova persistência/layout nos cenários,
não a qualidade factual de uma pesquisa que não trouxe evidências.

## Links e cards

Houve clique real em Abrir oferta e Abrir fonte, não apenas inspeção de href:
- SSD: seis cards de produto; o primeiro abriu a página específica da KaBuM,
  com título do SSD e caminho /produto/621162/..., sem redirecionamento à home.
- Notícias: três cards de fonte; o primeiro abriu a matéria de feriados do
  Ubatã Notícias, sem redirecionamento à home.
- Não foi testada a navegação de todos os nove links nem todos os botões de ação.
- Capturas de SSD e notícias em 390 px foram inspecionadas. O snippet da matéria
  de feriados enfatiza direitos trabalhistas, mostrando oportunidade de melhorar
  a escolha do trecho principal mesmo quando a matéria correta é encontrada.

A coleta de notícias foi conferida independentemente na página do
[Ubatã Notícias](https://ubatanoticias.com.br/): as matérias e datas de publicação
existem. Para Embraer, há informação oficial disponível em
[About Embraer](https://embraer.com/about) e no
[perfil de Ozires Silva](https://embraer.com/ozires-silva/pt/).
Logo, o fallback não representa ausência de informação na web.

## Diagnóstico limitado ao que foi observado

1. Formulações equivalentes de pesquisa profunda não chegam sempre ao job.
2. Em Rust, a descoberta retornou páginas de linguagem genérica e Google Chrome,
   rejeitadas por relevância. Isso não foi publicado como evidência válida.
3. Em Pitágoras, houve rejeições COVERAGE, inclusive de URLs sobre o tema, e
   falhas de rede em páginas da Wikipédia. É necessário replay dos documentos
   para separar rejeição indevida de conteúdo que não responde ao pedido.
4. Compras recupera ofertas, mas a redação comum ainda pode falhar/vazia.
5. Não há evidência para atribuir todas essas falhas a CAPTCHA. Os dois links
   clicados abriram no navegador sem challenge detectado.

## Evidências e limites

`qa-artifacts/research-varied-real-summary.json` guarda perguntas, respostas,
links, resultados antes/depois de reload, estados dos jobs e rejeições.
Logs: `qa-artifacts/varied-*-ui.log` e `varied-link-clicks.log`.
Capturas: `output/playwright/varied-*-390.png`.
O contador cards dos logs originais mede apenas .jdui-srccard; para SSD, usar
productLinks e o clique adicional, que confirmou seis .jdui-pcard.
O tempo de 140,55s do primeiro Rust inclui espera do harness por um resultado
profundo inexistente; não é uma medida válida da latência real da resposta.

Não houve mudança no código do aplicativo, commit, push ou deploy nesta rodada.
Não foi repetida a suíte unitária: a solicitação foi validar fluxos reais, e a
execução se concentrou nos oito fluxos e nos dois cliques de navegação.

## Próxima prioridade

Corrigir roteamento de modo explícito e preservação/decomposição do assunto
antes de ampliar a busca. Usar esta matriz como regressão, conservando controles
de entidade, variante, data e leitura; depois estabilizar a síntese comum de compras.

Laboratório encerrado após verificar PID, cwd, role development, SQLite privado
e zero operações ativas. Somente os processos/browser deste QA foram encerrados.

## Correções e repetição — 04/11/2026

Esta seção atualiza o diagnóstico anterior; os resultados de 03/11 acima são
o baseline, não o estado final desta etapa.

### Causas corrigidas

- Comandos profundos com dois-pontos e “investigue a fundo” não iniciavam jobs.
- Cláusulas sobre ano, finalidade e instruções da comparação viravam partes
  da entidade. O parser agora separa os aspectos sem retirar restrições de
  lugar, preço, variante ou negação. A representação anterior de “linguagem Lua”
  permanece compatível; a leitura reconhece o nome dentro desse contexto.
- Subconsultas perdiam a categoria linguagem ou o escopo Python. O inventário
  oficial agora recebe o contexto original também nas frentes de investigação.
- O extrator podia escolher bibliografia, seção isolada ou lista de cards em
  vez do documento. A seleção agora examina o contêiner principal pertinente
  antes de reter janelas literais, com os mesmos limites de tamanho.
- A documentação atual do Python mostra sequence.append/extend e mantém
  list.append/extend como âncoras reais do DOM. Esses aliases são associados
  somente à definição que os contém, com alinhamento de spans e mesmo método;
  o retorno de reverse não é atribuído a append.
- Navegação prioriza links internos de identidade/história realmente extraídos;
  páginas editoriais e traduções da Wikipédia deixam de consumir os slots de
  leitura. Artigos têm preferência sobre portais de vagas em perguntas históricas.
  Hrefs com &amp; são decodificados como atributos HTML antes da análise do URL;
  isso evita interpretar uma ação editorial como se fosse um novo artigo.
- “1 TB” não era reconhecido como armazenamento, criando pendência falsa nas
  ofertas. Pedidos simples de preço/link usam os dados já verificados; pedidos
  de comparação/análise continuam precisando de síntese.
  A suíte também revelou colisão no identificador do histórico de compras: o
  sufixo tinha só 16 bits. Passou para 128 bits, com teste determinístico que
  preserva dois registros mesmo quando os primeiros bytes aleatórios coincidem.
- “Mostre as fontes” podia anexar cards do último job de outro chat. A seleção
  agora respeita a conversa e não reaproveita essa lista durante uma nova busca.

### Recuperação da síntese: diagnóstico real e correção

O gateway anunciou suporte a JSON Schema, mas devolveu content=null,
finish_reason=stop e uso de tokens não nulo em chamadas reais. Isso não era
ausência de fontes. Sem o formato estruturado, houve texto, porém uma revisão
consumiu 1.800 tokens de raciocínio sem resposta final.

Agora há uma única recuperação de compatibilidade, somente na pesquisa: mesmo
modelo e prompt, sem JSON Schema no transporte, mantendo esforço baixo quando
anunciado pelo provedor, limite de tokens e prazo original. O JSON e as evidências
continuam passando pelas mesmas validações. Não há troca para outro modelo ou
provedor. Recusas, filtros, truncamento, cota, rate limit e falta de tempo não
disparam essa recuperação.

A execução real posterior conseguiu produzir texto e revisão válidos usando
essa recuperação. O indicador de cobertura permaneceu falso quando a resposta
não cobriu todos os aspectos: conseguir redigir não transforma uma resposta
parcial em completa. Evidências: repair-release-real-synthesis-shape.log,
repair-release-real-synthesis-plain.log e repair-release-real-synthesis-recovery.log.

### Verificação pela interface

Oito consultas foram repetidas na aplicação local completa, com busca externa
real, modelo Reflection gratuito selecionado e conta/SQLite descartáveis.
Os quatro casos profundos foram repetidos novamente depois da correção de
compatibilidade. O resumo consolidado está em
`qa-artifacts/research-varied-repair-release.json`.

SSDs: seis cards de oferta, preços e estoque recuperados. Houve clique real no
primeiro “Abrir oferta”, que abriu /produto/621162/... e não a home da KaBuM.
Notícias: três cards de matérias da janela 02–04/11; clique real na primeira
matéria do Ubatã Notícias, sem redirecionamento à home. Não foram clicados todos
os links nem exercitadas todas as ações dos cards.

Na repetição inicial, os oito resultados preservaram texto, quantidade de
mensagens e cards após reload; zero erros de console capturados e nenhum overflow
da página em 390 px. O harness de notícias passou a esperar conteúdo real e
rolar a mensagem antes de ler innerText, pois a renderização fora da área visível
podia fornecer apenas o placeholder. Isso foi corrigido no teste, sem modificar
dados ou injetar estado no aplicativo. Capturas mobile de SSD e matemática foram
inspecionadas; isso não equivale a auditoria visual completa de todas as telas.

### Limites e pendências

- Embraer passou a recuperar a fundação em fonte oficial, mas não confirmou
  o fundador nas fontes selecionadas.
- Rust recupera criador e finalidade, mas a Wikipédia não atende, sozinha,
  ao pedido de fontes oficiais.
- Python recupera a diferença entre as operações e confirma a identidade
  da documentação; o retorno ainda não foi sustentado por um trecho selecionado.
- Matemática recupera enunciado/exemplos, mas completar a redação e a cobertura
  depende de selecionar e publicar ambos os aspectos, além da revisão.
- O provedor ainda pode falhar. A recuperação é limitada e não garante resposta
  de qualquer modelo. Não houve bypass de CAPTCHA, fonte inventada ou relaxamento
  da exigência de evidências para aumentar os resultados positivos.
- Estes testes não validam a produção. O agente PC de produção não foi reiniciado.

### Regressões e escopo da publicação

A primeira suíte completa revelou quatro regressões em representação da entidade,
escopo de API e alinhamento de títulos do extrator opcional. Todas foram corrigidas
preservando os testes existentes. Depois, a suíte do workspace passou: 2.647
aprovados, 4 pulados, 2 avisos. Uma exportação do índice, sem o WIP de contas,
watchdog e companion, passou com 2.575 aprovados, 4 pulados e 2 avisos antes
da última recuperação de compatibilidade. Os 75 testes focados dessa recuperação
também passaram; a suíte final do índice é registrada no fechamento abaixo.

O commit reúne correções de pesquisa desta sequência e suas dependências de
modelo, proveniência, síntese e apresentação. Alterações pendentes de contas,
PC Companion, watchdog, controle remoto e workflow permanecem fora do commit.

Durante o fechamento surgiram dois commits do PC Companion no main remoto.
A integração conserva esses commits e os separa das alterações de pesquisa;
o código combinado também será validado antes do envio, sem limpar o WIP local.
