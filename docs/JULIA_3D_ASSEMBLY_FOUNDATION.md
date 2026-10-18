# Júlia 3D — fundações de montagem (V5.6)

Data: 17/10/2026 · Commits locais `7479bad` (interação/fundações) e `9519df6`
(catálogo com peças classificadas) · **Sem push/deploy**

Este documento descreve a base de “montagem inteligente” entregue na V5.6:
como cada peça declara o que é, a que grupo pertence, em que ordem se monta e
com o que se conecta — e como isso vira conversa, botão e etapa na tela.
Complementa [JULIA_3D_INTERACTIONS.md](JULIA_3D_INTERACTIONS.md) (contrato de
interação de V5.4, ainda válido) e
[JULIA_3D_MODEL_GENERATION.md](JULIA_3D_MODEL_GENERATION.md) (de onde vêm as
peças).

## Modelo de dados (por peça)

Campos novos no schema, validados com limites e paridade Python/JavaScript:

| Campo | Valores | Papel |
|---|---|---|
| `role` | `structural`, `functional`, `optional` (padrão `functional`) | o que a peça é na montagem |
| `group` | `''`, `internal`, `external` | mostrada por dentro ou por fora |
| `order` | inteiro 0–32 (padrão 0) | ordem de montagem exibida (“Montagem #N”) |
| `related` | até 8 ids existentes | conexões reais da peça na cena |

Regras duras: `related` não pode citar a própria peça nem id inexistente;
nenhuma peça pode ter `group`/`role`/`order` inválidos; tudo é validado nos
dois lados.

## Etapas e montagem

- Até 8 etapas por cena (`steps`) com `title`, `text`, `selected`, `view` e
  `exploded`.
- Avançar uma etapa aplica a seleção, a vista e o modo separado daquela fase:
  a “montagem” atual é uma **sequência educativa guiada por etapas**, não um
  tutorial com encaixe físico.
- Modo separado (“Separar peças”) afasta as peças do centro por direção
  própria, revelando a composição interna sem prometer posições de manutenção.

## Conversa (comandos reconhecidos na V5.6)

- “Mostre apenas as peças internas” / “… as peças externas”
- “Deixe só X” / “Esconda X” (por rótulo ou id)
- “Mostre como isso se conecta” (exige ou usa peça selecionada)
- “Explique como funciona” / “Explique a peça X”
- Continuam valendo: destaque, isolar, focar, transparência, revelar,
  separar/remontar, vistas, etapas e reprodução automática.

Casos honestos: sem peça selecionada, “mostre como isso se conecta” responde
como selecionar; cena sem grupos desabilita os botões de grupo; peça sem
`related` responde “Nenhuma conexão registrada…”.

## Interface

- **Botões**: “Ver só internas”, “Ver só externas” (desabilitados quando a cena
  não tem grupos) e “Ver conexões” (ativa com peça selecionada) convivem com
  “Isolar”, “Focar”, “Transparência”, “Ocultar” e “Revelar tudo”.
- **Detalhes da peça**: descrição, relações, papel/grupo e “Montagem #N”.
- **Status acessível** (`.m3-status`, `aria-live` no passo): cada grupo
  aplicado informa o que está visível (“Exibindo apenas as peças internas.”).
- **Chips**: “Modelo aproximado/educativo/…” e “Cena educativa” identificam a
  fidelidade antes de explorar.

## Contratos preservados

- Estado da cena restrito ao dono e à conversa; comandos de outro dono não
  capturam ação (coberto por teste e pelo QA em Chrome real).
- Operações continuam validadas pelo schema leve (sem importar o motor para
  validar).
- O estado (seleção, grupos escondidos, separado, etapa, vista, velocidade) é
  salvo por mensagem e restaurado no reload.

## Verificação

- 21 testes V5.6 (papel/grupo/ordem, grupos internos/externos, conexões,
  etapas, isolamento por dono/conversa) + suítes congeladas da V5.4.
- QA Chrome real (`tools/3d/qa-v56.cjs`): alternar grupos e explodir mudam
  pixels de verdade; “Ver conexões” mostra o texto esperado; o chat aplica
  “mostre apenas as peças internas” e o estado sobrevive ao reload.
- Artefatos: `qa-artifacts/3d-v56/` (screenshots + `metrics.json`).

## O que ainda não existe (declarado)

- Tutorial guiado peça-a-peça com instruções de encaixe, ferramentas e ordem
  fixa com travas (“só habilita a próxima quando a anterior estiver no lugar”).
- Verificação geométrica de encaixe (tolerância, colisão, folga) — seria
  promessa de engenharia que o projeto não faz.
- Vínculos físicos entre peças (parafusos, cabos como curvas reais): as
  relações são informativas e desenham destaque, não simulação.

Esses itens ficam como evolução natural sobre esta fundação, sem data
comprometida.
