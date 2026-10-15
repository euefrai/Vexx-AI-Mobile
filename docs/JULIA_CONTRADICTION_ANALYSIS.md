# JÚLIA Contradiction Analysis (V4.6)

`investigar_divergencia` classifica a dimensão antes de qualquer conclusão:

- `valor_divergente`: mesma unidade, valores distintos (ex.: 65 W × 95 W) →
  follow-ups de metodologia/data; status `em_aberto`.
- `unidade_ou_metrica`: unidades distintas (ex.: W × horas) → podem não
  falar da mesma coisa.
- `data_divergente`: mesma medida, datas distintas → a recente pode atualizar.
- `contexto_divergente`: comparados distintos → conclusões podem coexistir.
- `inconclusivo`: sem dimensão identificável → leitura humana (declarado).

Gatilhos: assimetria de negação ou mesma-unidade-valores-distintos sobre
tópico compartilhado. Cada investigação registra afirmações, fontes, tipo,
explicação, follow-ups e status; aresta CONTRADICTS no grafo; evento
`contradiction_investigated`. Reconciliação inventada: proibida.
