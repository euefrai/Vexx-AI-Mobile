# Júlia 3D — geração de modelos (V5.6)

Data: 17/10/2026 · Commits locais `9519df6` (catálogo) e `41173a9` (pesquisa) ·
**Sem push/deploy**

Como a Júlia decide **o que** desenhar quando o usuário pede um objeto em 3D,
como cada modelo é rotulado e o que o sistema se recusa a fazer. Complementa
[JULIA_3D_EDUCATION.md](JULIA_3D_EDUCATION.md) (cenas clássicas),
[JULIA_3D_ASSEMBLY_FOUNDATION.md](JULIA_3D_ASSEMBLY_FOUNDATION.md) (peças,
grupos e etapas) e [JULIA_3D_VISUAL_POLISH.md](JULIA_3D_VISUAL_POLISH.md)

## Pipeline

1. **Intenção** (`model3d.request`): verbos 3D + forma. Primitivas (`cubo`,
   `esfera`, `cilindro`, `pirâmide`), cenas educativas (`computador`,
   `geometria`, `solar`), modelo GLB local e, na V5.6, **dispositivos**.
2. **Catálogo local** (`model3d_catalog.py`): 14 cenas procedurais originais
   para pedidos reconhecidos (consoles, celular, controle, placa-mãe, notebook,
   gabinete, monitor, teclado, headset, mesa, suporte de celular, motor V8).
3. **Templates paramétricos** (`model3d_research.py`): cinco famílias de forma
   (disco, drone, ferramenta, cilindro, caixa) usadas quando o assunto não
   está no catálogo mas admite uma forma defensável.
4. **Pesquisa pública + composição**: com a família escolhida, uma única
   consulta de dimensões é feita; medidas citadas viram proporção da cena.

Nada disso baixa ou copia arquivo de terceiro: a pesquisa lê **texto público**
(título/trecho) e infere proporção. Nenhum asset externo entra no pacote.

## Rótulos de fidelidade (`precision`)

| Rótulo | Quando aparece | O que significa |
|---|---|---|
| `exato` | primitivas e GLB local | geometria determinística do próprio produto |
| `educativo` | cenas clássicas (computador, geometria, solar) | modelo didático, medidas ilustrativas |
| `aproximado` | catálogo local e pesquisa com medidas | forma inspirada em referências; proporção a partir de medidas citadas |
| `conceitual` | pesquisa com fontes, mas sem medidas confiáveis | forma genérica e educativa |

O rótulo aparece na interface (chip “Modelo …”) e a fonte aparece nos detalhes
da mensagem. Toda cena carrega `source` com prefixo editorial fixo, validado
nos dois lados (Python e JavaScript):

- `Catálogo local V5.6 — …`
- `Aproximado por referências públicas — …`
- `Modelo conceitual educativo — …`

## Catálogo local (devices)

- **Roteamento**: pedido de dispositivo exige verbo 3D + palavra 3D; kinds e
  modelo têm prioridade; frases congeladas da V5.4.1 continuam valendo
  (“quero ver um notebook em 3D” → `education: computer`, resolvido pelo
  catálogo dentro da família computador). Sem verbo, nada é capturado.
- **Regras de fabricação**: cena validada pelo schema (≤ 32 peças, ≤ 8 etapas,
  ≤ 20 KB, ≤ 7.139 bytes por cena), peças com `role`/`group`/`order`,
  ≥ 3 etapas educativas e descrição que declara a aproximação.
- Exemplo de descrição: “Reconstrução educativa por primitivas, inspirada em
  referências públicas do Xbox Series S. Não é modelo oficial nem CAD; cores e
  medidas são aproximadas.”

## Templates paramétricos (pesquisa)

Famílias e gatilhos (assunto normalizado):

| Família | Exemplos de gatilho | Forma |
|---|---|---|
| `disco` | aspirador (robô), caixa de som, smart speaker | corpo em disco achatado com aro, sensor e base |
| `drone` | drone, quadricóptero | corpo central + 4 braços em X + rotores + câmera |
| `ferramenta` | furadeira, parafusadeira, martelete | corpo, mandril, punho, gatilho |
| `cilindro` | liquidificador, lata, bomba, luminária, vaso | corpo cilíndrico, tampa, base, controle |
| `caixa` | geladeira, forno, armário, sofá, impressora, TV | volume em caixa com frente, puxador e apoio |

**Sem template não há busca**: “dragão em 3D” não vira caixa genérica — o
sistema responde com a limitação honesta e não faz scraping inútil.

## Leitura de medidas

- Triplos em `mm`, `cm`, `m`, `pol`/`polegadas`/`"`, com vírgula ou ponto.
- Sanidade: cada valor entre 1 e 500 cm e sem razão maior que 100 entre o
  maior e o menor.
- Ordem lida como largura × altura × profundidade (L×A×P das listagens);
  em `disco` e `drone` a **menor medida vira altura** (listagens de aspirador
  vêm como L×P×A — sem essa regra o robô virava um cilindro alto).
- Escala final: maior dimensão 2,4 unidades de cena; posições/dimensões
  limitadas pelo schema; a cena é validada antes de sair do gerador.
- Sem triplo confiável → `conceitual` (forma genérica, sem medida);
  sem resultado algum ou rede fora → `None` e limitação honesta no chat.

## Orçamento, cache e segurança

- **Uma consulta** (`<assunto> dimensões medidas`), até 3 provedores, timeout
  total ~7 s, até 8 resultados — via `research._buscar_orquestrado`
  (provedores públicos sem chave da V5.5).
- **Cache em memória**: positivo 6 h, negativo 30 min, até 32 assuntos. Nada
  é gravado em disco; reinício limpa tudo.
- **Injeção para testes**: `gerar(assunto, buscar=fake)` — a suíte prova
  parsing, rótulos, cache e falha de rede sem tocar a internet.
- **Gancho único**: `pc_agent.cmd_model3d(..., pesquisa_web=...)`, acionado só
  para pedidos de criação fora do catálogo. O canal `ai_completa` e o worker
  SSE passam `cfg['pesquisa_web']` (ambiente `JULIA_WEB_SEARCH`, padrão `1`);
  o comando direto/testes usam o padrão desligado.

## Exemplo de fluxo

> “me mostre um aspirador de robô em 3D”

1. Não há verbo/forma no catálogo → família `disco` + consulta de dimensões.
2. Fontes citam “32,5 × 32,5 × 9,7 cm” → escala 2,4 e 0,716; rótulo
   **aproximado**; fonte “Aproximado por referências públicas — exemplo.com”.
3. Chat responde com a ressalva (“não é CAD nem modelo oficial”) e abre a cena
   com partes, etapas e modo separado.

## Verificação

- 5 testes V5.6 dedicados (medidas, conceitual, limitação, cache/unidades,
  fluxo no `pc_agent` sem LLM nem rede).
- QA em Chrome real monta uma cena de pesquisa gerada com busca falsa
  determinística e confere rótulo e fonte visíveis (`qa-artifacts/3d-v56/`).
- Suíte completa: 671 passed, 3 skipped
  (`qa-artifacts/3d-research-tests.txt`).

## Limitações declaradas

- Não é CAD: sem tolerâncias, encaixes dimensionais ou engenharia reversa.
- A ordem L×A×P é uma convenção de leitura; listagens fora do padrão podem
  produzir proporção trocada — o rótulo “aproximado” e a fonte visível cobrem
  essa incerteza.
- A pesquisa depende de provedores públicos no momento da consulta; sem rede
  a resposta é a limitação honesta, nunca geometria inventada.
- Nenhum arquivo/imagem de terceiro é baixado; somente texto público é lido.
