# Júlia — Busca Adaptativa (V5.5)

Data: 17/10/2026 · Refere-se a `search_orchestrator.py`, `search_providers.py`,
`research.py` e `research_agents.py`. Visão geral em
[JULIA_RESEARCH_INTELLIGENCE_3.md](JULIA_RESEARCH_INTELLIGENCE_3.md).

A busca V5.5 é **determinística e conservadora**: cada decisão (classe,
consulta derivada, provedor, lacuna, recuperação) sai de regras explícitas —
nada depende de LLM, nada altera o pedido do usuário.

## 1. Classificação do pedido (`classificar`)

Classes por regex determinística (sem acento, case-insensitive):

| Classe         | Gatilhos (exemplos)                                             |
|----------------|-----------------------------------------------------------------|
| `tecnico`      | python, api, docker, erro, compilar, banco de dados, servidor…  |
| `academico`    | artigo, paper, estudo, tese, doi, revisão sistemática…          |
| `noticias`     | notícia, últimas, hoje, eleição, economia, cotação…             |
| `saude`        | saúde, doença, sintoma, tratamento, vacina, câncer…             |
| `dados`        | estatística, PIB, população, selic, IPCA, desemprego…           |
| `enciclopedia` | "o que é", "quem foi", definição, história de, origem…          |
| `imagens`      | imagem, foto, figura, mapa, bandeira…                           |
| `livros`       | livro, autor, obra, ISBN, editora…                              |
| `geral`        | fallback implícito                                              |

Flags adicionais:

- **`produto`**: preço, comprar, oferta, mais barato, loja, vale a pena…
  **e** `quanto custa` / `quanto custam` / `custa quanto` (V5.5: intenção
  comercial explícita também conta como pedido de produto).
- **`comparacao`**: comparar, vs, diferença, melhor entre…
- **`temporal`**: notícia ou quando/desde/até-ano/data…
- **`tecnica`**: classe técnica ativa (usada para ajustar termos).

### Regra do "até" (orçamento ≠ data)

`quanto custa o notebook gamer até R$ 3000?` — o "até" é **teto de preço**,
não pedido de data. Por isso `RX_PEDE_DATA` só trata `até` como data quando
aponta para ano (`até 2010`, `até o ano de 2020`) ou `até hoje`; `até R$ X`,
`até 3000 reais` ficam de fora. Isso evita a lacuna falsa de "datas/anos
pedidos não aparecem nas fontes" em buscas de produto.

## 2. Consultas derivadas (`variantes`)

Regra dura: **números, orçamento, marcas, modelos e condições nunca mudam**.
Só se acrescentam termos.

1. A consulta original vem sempre primeiro (`vs[0] == consulta`).
2. Até 2 trocas determinísticas de sinônimo (`notebook → laptop`,
   `preço → valor`, ...), 1 termo por vez.
3. Versão sem acento (índices costumam indexar as duas formas).
4. Expansão por classe (`documentação/exemplo` para técnico,
   `estudo/artigo` para acadêmico, `dados oficiais` para dados, ...).
5. **Produto não recebe expansão por classe** — o termo do pedido é a busca.
6. Teto padrão de 3 consultas (`teto=3`), corte em 200 chars.

Exemplo:

```
"notebook gamer até R$ 3000 com 16gb de ram"
→ [ "notebook gamer até R$ 3000 com 16gb de ram",      (original)
    ... sinônimos sem acento ... ]                     (números intactos)
```

## 3. Ajuste por provedor (`termos_para_provedor`)

Para Stack Exchange/HN (quando a consulta é técnica), tradução determinística
pt→inglês por dicionário fixo (`memória→memory`, `erro→error`,
`rede→network`, `instalar→install`, ...). Limite 180 chars. Nenhum outro
provedor recebe alteração.

## 4. Escolha de provedores (`_escolher_provedores`)

Ordem por afinidade, filtrando pelo que está disponível e preservando
duplicatas:

| Contexto             | Ordem inicial                          |
|----------------------|----------------------------------------|
| produto              | bing → marginalia                      |
| notícias             | bing-news → bing → hn                  |
| técnico              | stackexchange → hn → bing              |
| saúde                | pubmed → wikipedia → bing              |
| acadêmico            | pubmed → openlibrary → wikipedia       |
| dados                | worldbank → bcb → bing                 |
| livros               | openlibrary → bing                     |
| imagens              | commons → bing                         |
| enciclopédia         | wikipedia → bing                       |
| fallback (todos)     | bing → marginalia → wikipedia          |

Os limites vêm do orçamento (`max_provedores`) e a busca alterna provedor
quando um falha, é bloqueado ou volta vazio (até 3 tentativas por consulta).

## 5. Dedupe canônico (`canonizar_url`/`deduplicar`)

- Remove parâmetros de rastreio (`utm_*`, `gclid`, `fbclid`, `ref`, ...),
  host minúsculo sem `www.`, sem barra final, query ordenada.
- **URL sem `http(s)` ou sem host → ""** e o resultado é descartado como
  `url inválida` (não pode ser aberto/verificado — não é fonte).
- Duplicata: mantém a versão com trecho mais longo; registro em `descartes`
  com motivo `duplicada de <url canônica>`.

## 6. Ranking (`ranquear`)

Pontuação por achado (resumo):

- +3,0 termo no título · +1,5 no trecho · +1,0 na URL (por termo do pedido);
- + peso do provedor × 0,6 (8.0 para Bing/Bing-News/StackExchange/PubMed/BCB);
- + bônus de tipo quando a classe pede (técnico, acadêmico, notícia, dados,
  enciclopédia, saúde, livro);
- + atualidade quando a consulta é temporal (ano no título/trecho);
- −1,5 para páginas dos próprios provedores (bing.com, google.com, ddg.org…);
- −1,0 sem trecho.

`correspondencia` = fração dos termos do pedido presentes nos 8 melhores;
≤ 0,15 → estado `sem_correspondencia` (resultados existem, mas não
respondem ao pedido — nunca "ok" falso).

## 7. Lacunas (`detectar_lacunas`)

Cada lacuna é texto explícito do que o pedido exige e as fontes não cobrem:

| Condição                                                  | Lacuna |
|-----------------------------------------------------------|--------|
| pedido de número/preço e nenhum dígito nas fontes          | números/valores pedidos não aparecem nas fontes |
| pedido de data e nenhum ano (19xx/20xx) nas fontes         | datas/anos pedidos não aparecem nas fontes |
| pedido de definição e nenhuma fonte enciclopédica          | sem fonte enciclopédica direta para a definição |
| comparação pedida e fontes de um único domínio             | comparação pedida exige mais de uma fonte independente |
| produto sem fonte de dados/preço em R$                     | preço/valor comercial não confirmado por fonte de dados |
| classe notícia e nenhum achado `noticia`                   | sem fonte de notícia recente |
| classe acadêmica e nenhum achado acadêmico/saúde           | sem fonte acadêmica/científica direta |
| nenhum achado                                              | nenhuma fonte utilizável |

## 8. Recuperação por lacuna

`_consultas_recuperacao` mapeia lacuna → consulta complementar **sem mexer no
pedido** (máx. 2, deduplicadas):

- números/preço → `"<pedido> valor preço número"`
- datas/notícia → `"<pedido> 2026"`
- enciclopédica → `"<pedido> definição"`
- independência → `"<pedido> comparativo"`
- acadêmica → `"<pedido> estudo artigo"`

`pesquisar_com_recuperacao` roda **uma única** rodada extra quando há
recuperação pendente; `limite_primeira` (8 s no fluxo rápido) adia quando a
primeira rodada já consumiu o tempo — com motivo declarado
(`recuperacao_adiada`), nunca silencioso.

No fluxo de agentes, as consultas de recuperação viram **novas frentes** no
replanejamento (busca + leitura + análise), uma rodada extra, orçamento
original.

## 9. Estados honestos

Nível busca (`search_orchestrator.CODIGO_TEXTO`):

| Estado               | Significado                                                |
|----------------------|------------------------------------------------------------|
| `ok`                 | ≥ 2 fontes utilizáveis e correspondentes                   |
| `parcial`            | 1 fonte utilizável                                         |
| `sem_resultados`     | provedores responderam, sem resultados                     |
| `sem_correspondencia`| houve resultados, nenhum responde ao pedido               |
| `bloqueado`          | provedores recusaram (bot-wall/CAPTCHA) — sem bypass       |
| `rede`               | falha de rede/DNS/timeout                                  |
| `indisponivel`       | provedores indisponíveis no momento                        |

Nível pesquisa (`research.ESTADO_TEXTO`, agrega busca + leitura de páginas):
`ok`, `parcial`, `paginas_ilegiveis`, `sem_resultados`,
`sem_correspondencia`, `bloqueado`, `rede`, `indisponivel` (prioridade
`bloqueado > rede > indisponivel > sem_correspondencia > sem_resultados >
paginas_ilegiveis > parcial > ok`).

## 10. Orçamentos

| Orçamento            | consultas | provedores | tempo   | mín. resultados |
|----------------------|-----------|------------|---------|-----------------|
| `ORCAMENTO_PADRAO`   | 4         | 6          | 28 s    | 3               |
| `ORCAMENTO_RAPIDA`   | 2         | 3          | 10 s    | 3               |
| `ORCAMENTO_SUB`      | 1         | 2          | 8 s     | 2               |

Agentes (`MODOS`): `rapida` 2 buscas, `pro` 4, `profunda` 8,
`investigativa` 12 (timeouts 30/60/120/300 s). O loop para cedo quando já
tem `min_resultados` e uma consulta bastou.

## 11. Exemplo de fluxo real

`"quanto custa o notebook gamer até R$ 3000?"`

1. `classificar` → `produto=True`, classes `[geral]`; o "até R$" **não**
   dispara lacuna de data.
2. Provedores: `bing → marginalia → wikipedia` (produto primeiro).
3. Sem resultados com R$ nas fontes → lacunas: "números/valores pedidos não
   aparecem nas fontes" + "preço/valor comercial não confirmado por fonte de
   dados".
4. Recuperação (se a 1ª rodada foi rápida): `"... valor preço número"` —
   o `R$ 3000` do pedido permanece intacto na consulta.
5. Estado final: `ok`/`parcial` com `lacunas` e `recuperacao` explícitas;
   nada é preenchido por suposição.

## 12. O que a busca adaptativa NUNCA faz

- Não remove/acrescenta números, orçamento, marcas, modelos ou condições.
- Não contorna bloqueio/CAPTCHA (provedor bloqueado é registrado como tal).
- Não transforma vazio em resultado nem resultado irrelevante em "ok".
- Não roda mais de uma rodada de recuperação/replanejamento por pesquisa.
- Não usa LLM em nenhuma etapa (tudo determinístico e testável).
