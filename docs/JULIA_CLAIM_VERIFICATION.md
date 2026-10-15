# JÚLIA Claim Verification 2.0 (V4.6)

## Extração (`extrair_afirmacoes_v2`)

Divide em afirmações verificáveis (número ou nome próprio, 40–400 chars;
caudas curtas reagrupadas) + condições: `comparado_a`, `metrica`,
`quantidades[{valor, unidade}]`, `datas`. Condição ausente é registrada
(`condicoes_ausentes`), nunca presumida. Sem LLM: só regras justificáveis.

## Estados e regras

- SUPPORTED: mesma quantidade+unidade no trecho (`quantidade-exata`) —
  ainda com ressalvas registradas.
- PARTIALLY_SUPPORTED: cobertura léxica ≥0,25 (`lexico-provisorio`).
- CONTRADICTED: evidência marcada `contradiz`.
- INSUFFICIENT_EVIDENCE / UNVERIFIED: resto, com condições ausentes listadas.
- Termos nos trechos ≠ sustentação: cobertura é léxica, declarada como tal.
- Verificação semântica LLM: BLOQUEADA (sem provedor); `metodo` sempre
  registrado em cada veredito.

## Auditoria (`auditar_resposta`)

Fantamas `[E9]/[S9]`, superlativos sem SUPPORTED, afirmações sem evidência,
`etapa_semantica: BLOQUEADA`. `ok` só sem problemas. Teste estrutural nunca
apresentado como prova semântica.
