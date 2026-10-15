# JÚLIA Evidence Store (V4.5)

Tabela `evidence`: `id` (ev-*), `job_id`, `owner_id`, `fonte_id`, `url`,
`título`, `domínio`, `acessado_em`, `publicado_em` (quando conhecida),
`trecho`, `localizacao`, `afirmacao`, `relacao`, `status`, `original` (fonte
crua, auditoria).

## Status (transições só para frente na confiança)

- `encontrada`: só na busca, ainda não aberta.
- `recuperada`: lida com texto extraído.
- `inacessivel`: falhou (código registrado no evento, não some).
- `parcial`: sustenta parte da afirmação.
- `nao_sustenta`: lida e não sustenta.
- `contradiz`: nega a afirmação.

Link ≠ confirmação: existir na busca nunca vira `recuperada`, e
`recuperada` nunca vira "verdadeira" — só os estados acima.

## Verificação por afirmação

`extrair_afirmacoes` (frases longas com número/nome próprio) × `cobertura`
léxica contra trechos → SUPPORTED (≥0,5) / PARTIALLY (≥0,25) / UNVERIFIED /
INSUFFICIENT (sem evidências) / CONTRADICTED (evidência `contradiz`).
Etapa LLM de interpretação: BLOQUEADA (sem provedor); registrada como tal,
nunca como validada. Exagero do resumo vs fonte: auditor aponta; correção de
redação é dever do texto final (extrativo hoje).
