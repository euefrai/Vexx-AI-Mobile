# JÚLIA Source Independence (V4.6)

Domínio distinto **não** prova independência; mesma conclusão **não** prova
dependência. Laudo estrutural por par (`analisar_independencia`):

- URL canônica (host minúsculo, sem tracking, `utm_*`/`fbclid`/`gclid` fora).
- Hash do conteúdo normalizado (idêntico → DUPLICATES).
- Jaccard de shingles ≥0,6 ou citação literal ≥60 chars → DERIVED_FROM.
- Mesmo domínio sem cópia → MENTIONS (relação desconhecida).
- Caso geral → MENTIONS com motivo explícito: "independência NÃO presumida".

Três sites repetindo o mesmo texto geram DERIVED_FROM, e o verificador os
trata como uma origem — nunca como três confirmações.
