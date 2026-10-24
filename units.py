"""Unidades e dimensões (V4.6.1) — normalização determinística para verificação.

Regras: converter só dentro da mesma dimensão; propriedades distintas NUNCA
se equivalem por unidade (TDP ≠ consumo real); ambíguo/desconhecido rejeita.
Tabela explícita e testada (sem conversão inventada).
"""
import math

# dimensão: (fator_para_base, ...)
_TABELA = {
    "energia_por_massa": {"wh/kg": 1.0, "kwh/kg": 1000.0, "wh/g": 1000.0, "mwh/g": 1.0},
    "energia_por_volume": {"wh/l": 1.0, "wh/cm3": 1000.0, "mwh/cm3": 1.0},
    "capacidade_por_massa": {"mah/g": 1.0, "ah/kg": 1.0, "ah/g": 1000.0},
    "pressao": {"pa": 1.0, "kpa": 1000.0, "mpa": 1000000.0},
    "potencia": {"w": 1.0, "kw": 1000.0, "mw": 0.001},
    "energia": {"j": 1.0, "wh": 3600.0, "kwh": 3600000.0},
    "armazenamento": {"b": 1.0, "kb": 1024.0, "mb": 1024.0 ** 2,
                      "gb": 1024.0 ** 3, "tb": 1024.0 ** 4},
    "frequencia": {"hz": 1.0, "khz": 1000.0, "mhz": 1000000.0, "ghz": 1000000000.0},
    "comprimento": {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
                    "pol": 0.0254, "ft": 0.3048, "mi": 1609.34},
    "volume": {"ml": 0.001, "l": 1.0, "litro": 1.0, "litros": 1.0},
    "massa": {"mg": 1e-06, "g": 0.001, "kg": 1.0, "lb": 0.453592},
    "tempo": {"s": 1.0, "min": 60.0, "h": 3600.0, "dia": 86400.0, "dias": 86400.0},
    "porcentagem": {"%": 1.0, "por cento": 1.0},
    "multiplicador": {"mil": 1000.0, "milhão": 1000000.0, "milhões": 1000000.0,
                      "milhao": 1000000.0, "milhoes": 1000000.0,
                      "bilhão": 1000000000.0, "bilhões": 1000000000.0,
                      "bilhao": 1000000000.0, "bilhoes": 1000000000.0},
}
_ALIAS = {"watts": "w", "watt": "w", "quilowatts": "kw", "bytes": "b",
          "segundos": "s", "segundo": "s", "minutos": "min", "horas": "h",
          "quilos": "kg", "gramas": "g", "metros": "m", "hs": "h",
          "anos": "ano", "ano": "ano", "dias": "dia"}


class UnidadeErro(ValueError):
    def __init__(self, mensagem, codigo="unidade"):
        super().__init__(mensagem)
        self.codigo = codigo


def todas_unidades() -> list:
    """Todas as formas conhecidas, maior primeiro (para alternância regex)."""
    formas = set(_ALIAS) | set(_ALIAS.values())
    for fatores in _TABELA.values():
        formas.update(fatores)
    formas.update(("%", "por cento", "c", "f", "°c", "°f"))
    formas.discard("ano")
    return sorted(formas, key=len, reverse=True)


def pattern_unidades() -> str:
    import re as _re
    return "(?:" + "|".join(_re.escape(u) for u in todas_unidades()) + ")"


def normalizar_unidade(u: str) -> str:
    u = (u or "").strip().lower().rstrip(".")
    if u in _ALIAS:
        u = _ALIAS[u]
    return u


def dimensao_de(unidade: str):
    u = normalizar_unidade(unidade)
    for dim, fatores in _TABELA.items():
        if u in fatores:
            return dim
    if u in ("c", "f", "°c", "°f"):
        return "temperatura"
    return None


def para_base(valor: float, unidade: str) -> tuple:
    """(dimensao, valor_na_base). Temperatura via Celsius. Desconhecida levanta."""
    u = normalizar_unidade(unidade)
    for dim, fatores in _TABELA.items():
        if u in fatores:
            return dim, valor * fatores[u]
    if u in ("c", "°c"):
        return "temperatura", valor
    if u in ("f", "°f"):
        return "temperatura", (valor - 32) * 5 / 9
    raise UnidadeErro(f"Unidade desconhecida ou ambígua: {unidade!r}", "desconhecida")


def compativeis(qa: dict, qb: dict) -> bool:
    """Mesma dimensão e ambas conhecidas. Propriedades NÃO são comparadas aqui
    (isso é papel do contexto léxico, não da unidade)."""
    try:
        return para_base(1.0, qa.get("unidade", ""))[0] == para_base(1.0, qb.get("unidade", ""))[0]
    except UnidadeErro:
        return False


def iguais(qa: dict, qb: dict, tolerancia: float = 1e-6) -> bool:
    """Valores iguais após conversão (ex.: 65 W = 0,065 kW)."""
    try:
        da, va = para_base(float(qa.get("valor", float("nan"))), qa.get("unidade", ""))
        _, vb = para_base(float(qb.get("valor", float("nan"))), qb.get("unidade", ""))
    except (UnidadeErro, TypeError, ValueError):
        return False
    if da != para_base(1.0, qb.get("unidade", ""))[0]:
        return False
    if va == vb:
        return True
    escala = max(1.0, abs(va), abs(vb))
    return abs(va - vb) <= tolerancia * escala
