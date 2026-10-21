"""Serialize bounded persistent JSON without ever cutting its syntax."""
import json


class JSONLimitError(ValueError):
    """The new state cannot be persisted safely within its storage budget."""


def encode(value, limit):
    result = json.dumps(value, ensure_ascii=False)
    if len(result) > limit:
        raise JSONLimitError(f"Estado JSON excede o limite de {limit} caracteres; registro anterior preservado")
    return result
