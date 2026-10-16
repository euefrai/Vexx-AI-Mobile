# JULIA Instruction Following (V5.1)

Controle explícito de restrições do pedido ao LLM até a resposta entregue.

## Tipos

- **Obrigatório**: "apenas X", "somente X", "tem que ter" → `obrigatorias`.
- **Proibido**: "não quero X", "sem X", "nada de X", "não pesquise" →
  `proibidas`. "Não pesquise" (majoração: sem objeto de busca) proíbe o
  **ato** (`podem_pesquisar=False`); com objeto ("não pesquise preços"),
  proíbe o objeto.
- **Preferência**: "prefiro", "melhor se" → sugestão, não regra dura.
- **Formato**: "em N linhas" (dígito ou extenso), "curto", "detalhado",
  "com fotos", "em tabela".
- **Correção posterior**: `correcao=True` ("não, eu quis dizer…",
  "na verdade…") — prevalece sobre restrições anteriores e sobre
  memórias antigas (a memória é sobrescrita pelo explícito; histórico
  preservado em `memory_facts`).

## Efeitos no fluxo (`pc_agent.py`)

1. **Pré-LLM**: `podem_pesquisar=False` pula Research e Shopping;
   `max_linhas` vira diretiva `FORMATO OBRIGATÓRIO` no system.
2. **Pós-LLM**: `intent.validar` checa resposta vazia, item proibido
   (por palavra, ignorando negação próxima), formato longo, ação alegada
   sem ferramenta usada, superlativo inverificável e card sem dados.
   Violações são logadas (`INTENT_VALIDATE`); **sem loops de regeneração**.
3. **Recuperação segura (única)**: usados recomendados com proibição
   explícita são movidos para `excluidos` com motivo antes dos cards.

## Limites

- Validação é literal, não semântica (declarado quando o LLM falta).
- Formato curto depende do modelo obedecer à diretiva; o validador
  detecta, não reescreve (reescrever quebraria fences JDUI).
- Segurança/permissões (SSRF, auth, controle do PC) nunca são
  flexibilizadas por instrução do usuário.
