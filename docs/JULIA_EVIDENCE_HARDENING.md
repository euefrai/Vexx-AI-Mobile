# JÚLIA Evidence Hardening (V4.6.1)

## Números sozinhos não sustentam nada

`verificar_claim` agora exige, para SUPPORTED: quantidade exata **com
unidade compatível** (`units.compativeis`) **e** valor igual após conversão
(`units.iguais`, ex.: 65 W = 0,065 kW) **e** entidade/propriedade em comum
(≥2 tokens de conteúdo) **e** datas/base compatíveis quando citadas.
TDP ≠ consumo máximo; 30% sem data sustenta o número com ressalva registrada
(`condicoes_ausentes`), nunca carta branca.

## Unidades (`units.py`)

Dimensões: potência, energia, armazenamento (1024), frequência, comprimento,
massa, tempo, porcentagem, temperatura (com offset). Desconhecida/ambígua
(`léguas`, vazia) → rejeitada. Dimensões distintas (W × Wh) → incompatíveis.
Propriedades distintas com mesma unidade continuam distintas (decide o
contexto, não a tabela).

Testes: `tests/test_units.py` (conversões, precisão, incompatibilidades,
TDP, datas, base de comparação).
