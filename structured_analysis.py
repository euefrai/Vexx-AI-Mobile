"""Bounded, deterministic analysis of caller-supplied tabular data."""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import units


MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
MAX_CELLS = 100_000
MAX_COLUMNS = 5_000
MAX_CELL_BYTES = 64 * 1024


class AnalysisError(ValueError):
    """Invalid data, unsupported operation, or configured resource limit."""


@dataclass(frozen=True)
class Dataset:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    source: str
    metadata: Mapping[str, Any]


def _source(source: str) -> str:
    if not isinstance(source, str) or not source.strip():
        raise AnalysisError("source deve ser uma identificação não vazia")
    return source.strip()


def _validate_cell(value: Any) -> int:
    if value is None or isinstance(value, (str, bool, int)):
        encoded = str(value).encode("utf-8")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise AnalysisError("valores numéricos não finitos não são aceitos")
        encoded = repr(value).encode("ascii")
    else:
        raise AnalysisError("células devem conter apenas valores escalares")
    if len(encoded) > MAX_CELL_BYTES:
        raise AnalysisError(f"célula excede o limite de {MAX_CELL_BYTES} bytes")
    return len(encoded)


def from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str,
    columns: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Dataset:
    """Create a dataset from mappings; column order follows the first row."""
    source = _source(source)
    if metadata is not None and not isinstance(metadata, Mapping):
        raise AnalysisError("metadata deve ser um objeto")
    normalized_metadata = dict(metadata or {})
    try:
        metadata_size = len(json.dumps(
            normalized_metadata, ensure_ascii=False, allow_nan=False
        ).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise AnalysisError("metadata deve conter apenas valores JSON finitos") from exc
    if metadata_size > MAX_INPUT_BYTES:
        raise AnalysisError(f"metadata excede o limite de {MAX_INPUT_BYTES} bytes")
    input_size = metadata_size
    result_rows: list[dict[str, Any]] = []
    names = tuple(columns) if columns is not None else None
    if names is not None and (
        not names or any(not isinstance(name, str) or not name.strip() for name in names)
        or len(set(names)) != len(names)
    ):
        raise AnalysisError("colunas devem ter nomes não vazios e únicos")
    if names is not None and len(names) > MAX_COLUMNS:
        raise AnalysisError(f"limite excedido: máximo de {MAX_COLUMNS} colunas")
    if names is not None:
        try:
            input_size += sum(len(name.encode("utf-8")) for name in names)
        except UnicodeEncodeError as exc:
            raise AnalysisError("nomes de coluna devem ser texto UTF-8 válido") from exc
        if input_size > MAX_INPUT_BYTES:
            raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
    for row in rows:
        if len(result_rows) >= MAX_ROWS:
            raise AnalysisError(f"limite excedido: máximo de {MAX_ROWS} linhas")
        if not isinstance(row, Mapping):
            raise AnalysisError("cada linha deve ser um objeto de colunas")
        if names is None:
            names = tuple(row.keys())
            if not names or any(not isinstance(name, str) or not name.strip() for name in names):
                raise AnalysisError("colunas devem ter nomes não vazios")
            if len(set(names)) != len(names):
                raise AnalysisError("colunas devem ter nomes únicos")
            if len(names) > MAX_COLUMNS:
                raise AnalysisError(f"limite excedido: máximo de {MAX_COLUMNS} colunas")
            try:
                input_size += sum(len(name.encode("utf-8")) for name in names)
            except UnicodeEncodeError as exc:
                raise AnalysisError("nomes de coluna devem ser texto UTF-8 válido") from exc
            if input_size > MAX_INPUT_BYTES:
                raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
        if set(row.keys()) != set(names):
            raise AnalysisError("todas as linhas devem ter exatamente as mesmas colunas")
        if (len(result_rows) + 1) * len(names) > MAX_CELLS:
            raise AnalysisError(f"limite excedido: máximo de {MAX_CELLS} células")
        copied = {name: row[name] for name in names}
        for cell in copied.values():
            input_size += _validate_cell(cell)
            if input_size > MAX_INPUT_BYTES:
                raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
        result_rows.append(copied)
    if names is None:
        raise AnalysisError("dados tabulares vazios exigem a lista columns")
    return Dataset(names, tuple(result_rows), source, normalized_metadata)


def _text_input(data: str | bytes) -> str:
    if isinstance(data, bytes):
        if len(data) > MAX_INPUT_BYTES:
            raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AnalysisError("entrada deve usar UTF-8") from exc
    elif isinstance(data, str):
        try:
            encoded_size = len(data.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise AnalysisError("entrada deve ser texto UTF-8 válido") from exc
        if encoded_size > MAX_INPUT_BYTES:
            raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
        text = data
    else:
        raise AnalysisError("entrada deve ser texto ou bytes UTF-8")
    return text


def load_csv(
    data: str | bytes,
    *,
    source: str,
    metadata: Mapping[str, Any] | None = None,
    delimiter: str = ",",
) -> Dataset:
    text = _text_input(data)
    if len(delimiter) != 1:
        raise AnalysisError("delimiter deve ter um caractere")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        header = next(reader)
        if not header or any(not name.strip() for name in header) or len(set(header)) != len(header):
            raise AnalysisError("CSV deve ter cabeçalhos não vazios e únicos")
        rows = []
        for values in reader:
            if len(values) != len(header):
                raise AnalysisError("linha CSV tem quantidade de campos diferente do cabeçalho")
            rows.append(dict(zip(header, values)))
            if len(rows) > MAX_ROWS:
                raise AnalysisError(f"limite excedido: máximo de {MAX_ROWS} linhas")
    except (csv.Error, StopIteration) as exc:
        raise AnalysisError("CSV inválido ou sem cabeçalho") from exc
    return from_rows(rows, source=source, columns=header, metadata=metadata)


def load_json(
    data: str | bytes | list[Any] | Mapping[str, Any],
    *,
    source: str,
    metadata: Mapping[str, Any] | None = None,
) -> Dataset:
    if isinstance(data, (str, bytes)):
        text = _text_input(data)
        try:
            parsed = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
                AnalysisError(f"constante JSON inválida: {value}")))
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise AnalysisError("JSON inválido") from exc
    else:
        parsed = data
        try:
            encoded = json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise AnalysisError("JSON contém valor não serializável") from exc
        if len(encoded) > MAX_INPUT_BYTES:
            raise AnalysisError(f"entrada excede o limite de {MAX_INPUT_BYTES} bytes")
    if isinstance(parsed, Mapping):
        if set(parsed) != {"columns", "rows"} or not isinstance(parsed["columns"], list):
            raise AnalysisError("JSON tabular deve conter apenas columns e rows")
        columns = parsed["columns"]
        if (
            not columns
            or any(not isinstance(name, str) or not name.strip() for name in columns)
            or len(set(columns)) != len(columns)
        ):
            raise AnalysisError("colunas devem ter nomes não vazios e únicos")
        rows = parsed["rows"]
        if not isinstance(rows, list):
            raise AnalysisError("rows deve ser uma lista")
        if any(not isinstance(row, (list, Mapping)) for row in rows):
            raise AnalysisError("cada linha deve ser matriz ou objeto")
        if any(isinstance(row, list) and len(row) != len(columns) for row in rows):
            raise AnalysisError("linhas em formato matriz devem corresponder a columns")
        if any(isinstance(row, Mapping) and set(row) != set(columns) for row in rows):
            raise AnalysisError("linhas em formato objeto devem corresponder a columns")
        return from_rows(
            (dict(zip(columns, row)) if isinstance(row, list) else row for row in rows),
            source=source,
            columns=columns,
            metadata=metadata,
        )
    if not isinstance(parsed, list):
        raise AnalysisError("JSON deve ser uma lista de objetos ou uma tabela columns/rows")
    return from_rows(parsed, source=source, metadata=metadata)


def _column(dataset: Dataset, column: str) -> None:
    if column not in dataset.columns:
        raise AnalysisError(f"coluna inexistente: {column}")


def _columns(dataset: Dataset, columns: Sequence[str]) -> None:
    for column in columns:
        _column(dataset, column)


def _result(dataset: Dataset, method: str, data: Any, **extra: Any) -> dict[str, Any]:
    provenance = dict(dataset.metadata)
    provenance["source"] = dataset.source
    provenance["method"] = method
    provenance.setdefault("methodology", method)
    return {"data": data, "provenance": provenance, **extra}


def validate_columns(dataset: Dataset, required: Sequence[str]) -> dict[str, Any]:
    """Validate requested names without silently dropping absent columns."""
    missing = [name for name in required if name not in dataset.columns]
    return _result(dataset, "validate_columns", {"valid": not missing, "missing": missing})


def filter_rows(
    dataset: Dataset, column: str, operator: str, value: Any
) -> dict[str, Any]:
    _column(dataset, column)
    allowed = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"}
    if operator not in allowed:
        raise AnalysisError(f"operador não suportado: {operator}")
    if operator == "in" and not isinstance(value, (list, tuple, set, frozenset)):
        raise AnalysisError("valor do operador in deve ser uma coleção")
    selected = []
    for row in dataset.rows:
        cell = row[column]
        if operator in {"gt", "gte", "lt", "lte"}:
            left, right = _number(cell), _number(value)
            matched = {"gt": left > right, "gte": left >= right,
                       "lt": left < right, "lte": left <= right}[operator]
        elif operator == "contains":
            if not isinstance(cell, str) or not isinstance(value, str):
                raise AnalysisError("contains exige valores de texto")
            matched = value in cell
        elif operator == "in":
            matched = cell in value
        elif operator == "eq":
            matched = cell == value
        else:
            matched = cell != value
        if matched:
            selected.append(dict(row))
    return _result(dataset, "filter_rows", selected, rows=len(selected))


def sort_rows(dataset: Dataset, column: str, *, descending: bool = False) -> dict[str, Any]:
    _column(dataset, column)
    values = [row[column] for row in dataset.rows if row[column] is not None]
    if all(_is_numeric(value) for value in values):
        key = lambda row: _number(row[column]) if row[column] is not None else 0.0
    elif all(isinstance(value, str) for value in values):
        key = lambda row: row[column] or ""
    else:
        raise AnalysisError("coluna deve conter valores homogêneos numéricos ou texto")
    present = [row for row in dataset.rows if row[column] is not None]
    missing = [row for row in dataset.rows if row[column] is None]
    present.sort(key=key, reverse=descending)
    return _result(dataset, "sort_rows", [dict(row) for row in present + missing])


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number)


def _number(value: Any) -> float:
    if not _is_numeric(value):
        raise AnalysisError(f"valor não numérico: {value!r}")
    return float(value)


_BASE_UNIT = {
    "potencia": "W", "energia": "J", "armazenamento": "B",
    "frequencia": "Hz", "comprimento": "m", "massa": "kg",
    "tempo": "s", "porcentagem": "%",
    "temperatura": "°C",
}


def _declared_unit(dataset: Dataset, column: str) -> str | None:
    units_meta = dataset.metadata.get("units")
    if isinstance(units_meta, str):
        return units_meta
    if isinstance(units_meta, Mapping):
        value = units_meta.get(column)
        return value if isinstance(value, str) and value else None
    return None


def _convert_value(value: Any, unit: str) -> tuple[str, float, str]:
    try:
        dimension, converted = units.para_base(_number(value), unit)
    except units.UnidadeErro as exc:
        raise AnalysisError(f"unidade desconhecida ou incompatível: {unit!r}") from exc
    return dimension, converted, _BASE_UNIT[dimension]


def _aggregate(
    dataset: Dataset,
    rows: Sequence[Mapping[str, Any]],
    column: str,
    unit_column: str | None,
) -> tuple[float, int, str | None, str | None]:
    values = [_number(row[column]) for row in rows]
    if not values:
        raise AnalysisError("não há valores para agregar")
    declared = _declared_unit(dataset, column)
    row_units = [row[unit_column] for row in rows] if unit_column else []
    unit_names: list[str] = []
    if row_units:
        if any(not isinstance(unit_name, str) or not unit_name for unit_name in row_units):
            return 0.0, len(values), None, "incompatible_units"
        unit_names = list(dict.fromkeys(row_units))
    elif declared:
        unit_names = [declared]
    if not unit_names:
        return sum(values) / len(values), len(values), None, None
    converted: list[float] = []
    dimensions: set[str] = set()
    base_units: set[str] = set()
    for value, unit_name in zip(values, row_units or [unit_names[0]] * len(values)):
        try:
            dimension, base_value, base_unit = _convert_value(value, unit_name)
        except AnalysisError:
            return 0.0, len(values), None, "incompatible_units"
        dimensions.add(dimension)
        base_units.add(base_unit)
        converted.append(base_value)
    if len(dimensions) != 1:
        return 0.0, len(values), None, "incompatible_units"
    return sum(converted) / len(converted), len(values), next(iter(base_units)), None


def mean(
    dataset: Dataset, column: str, *, unit_column: str | None = None
) -> dict[str, Any]:
    _columns(dataset, [column] + ([unit_column] if unit_column else []))
    value, count, unit, status = _aggregate(dataset, dataset.rows, column, unit_column)
    data = {"value": None if status else value, "count": count, "unit": unit,
            "status": status or "ok"}
    return _result(dataset, "mean", data)


def group_by(
    dataset: Dataset,
    by: str | Sequence[str],
    value_column: str,
    *,
    unit_column: str | None = None,
) -> dict[str, Any]:
    keys = [by] if isinstance(by, str) else list(by)
    _columns(dataset, keys + [value_column] + ([unit_column] if unit_column else []))
    buckets: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in dataset.rows:
        key = tuple(row[name] for name in keys)
        buckets.setdefault(key, []).append(row)
    groups = []
    for key, rows in buckets.items():
        value, count, unit, status = _aggregate(dataset, rows, value_column, unit_column)
        groups.append({"group": dict(zip(keys, key)),
                       "value": None if status else value,
                       "count": count, "unit": unit,
                       "status": status or "ok"})
    dimensions = {units.dimensao_de(group["unit"]) for group in groups if group["unit"]}
    unknown_units = any(group["status"] == "incompatible_units" for group in groups)
    comparable = not unknown_units and (len(dimensions) <= 1)
    incompatible_groups = [
        item["group"] for item in groups if item["status"] != "ok"
    ]
    if len(dimensions) > 1:
        incompatible_groups.extend(
            item["group"] for item in groups if item["group"] not in incompatible_groups
        )
    return _result(
        dataset, "group_by",
        {"groups": groups,
         "comparison": {"compatible": comparable,
                        "incompatible_groups": incompatible_groups,
                        "reason": None if comparable else "incompatible_units"}},
    )


def differences(
    dataset: Dataset,
    group_column: str,
    value_column: str,
    baseline: Any,
    *,
    unit_column: str | None = None,
) -> dict[str, Any]:
    grouped = group_by(dataset, group_column, value_column, unit_column=unit_column)["data"]["groups"]
    reference = next((item for item in grouped if item["group"][group_column] == baseline), None)
    if reference is None:
        raise AnalysisError(f"grupo de referência inexistente: {baseline!r}")
    results = []
    for item in grouped:
        compatible = item["status"] == reference["status"] == "ok"
        if compatible and item["unit"] != reference["unit"]:
            compatible = bool(item["unit"] and reference["unit"] and units.compativeis(
                {"unidade": item["unit"]}, {"unidade": reference["unit"]}))
        results.append({
            "group": item["group"], "value": item["value"], "unit": item["unit"],
            "difference": item["value"] - reference["value"] if compatible else None,
            "status": "ok" if compatible else "incompatible_units",
        })
    return _result(dataset, "differences",
                   {"baseline": reference["group"], "groups": results})


def proportions(
    dataset: Dataset, column: str, *, by: str | None = None
) -> dict[str, Any]:
    _columns(dataset, [column] + ([by] if by else []))
    buckets: dict[Any, list[Any]] = {}
    for row in dataset.rows:
        key = row[by] if by else None
        buckets.setdefault(key, []).append(row[column])
    groups = []
    for group, values in buckets.items():
        counts: dict[Any, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        categories = [
            {"value": value, "count": count, "proportion": count / len(values)}
            for value, count in counts.items()
        ]
        groups.append({"group": {by: group} if by else {}, "count": len(values),
                       "categories": categories})
    return _result(dataset, "proportions", {"groups": groups})


def _quantile(sorted_values: Sequence[float], fraction: float) -> float:
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def identify_outliers(
    dataset: Dataset, column: str, *, factor: float = 1.5
) -> dict[str, Any]:
    _column(dataset, column)
    if not _is_numeric(factor) or float(factor) < 0:
        raise AnalysisError("factor deve ser um número finito não negativo")
    factor = float(factor)
    numeric_rows = [(row, _number(row[column])) for row in dataset.rows]
    values = sorted(value for _, value in numeric_rows)
    if len(values) < 4:
        return _result(dataset, "identify_outliers", {
            "method": "iqr", "count": len(values), "outliers": [],
            "bounds": None, "status": "insufficient_data",
        })
    q1, q3 = _quantile(values, 0.25), _quantile(values, 0.75)
    spread = q3 - q1
    lower, upper = q1 - factor * spread, q3 + factor * spread
    outliers = [dict(row) for row, value in numeric_rows if value < lower or value > upper]
    return _result(dataset, "identify_outliers", {
        "method": "iqr", "count": len(values), "outliers": outliers,
        "bounds": {"lower": lower, "upper": upper}, "status": "ok",
    })


def chart_series(
    dataset: Dataset,
    x_column: str,
    y_column: str,
    *,
    series_column: str | None = None,
    unit_column: str | None = None,
) -> dict[str, Any]:
    _columns(dataset, [x_column, y_column] +
             ([series_column] if series_column else []) +
             ([unit_column] if unit_column else []))
    series: dict[Any, list[Mapping[str, Any]]] = {}
    for row in dataset.rows:
        key = row[series_column] if series_column else "series"
        series.setdefault(key, []).append(row)
    result_series = []
    dimensions: set[str] = set()
    incompatible: list[Any] = []
    declared = _declared_unit(dataset, y_column)
    for key, rows in series.items():
        unit_names = [row[unit_column] for row in rows] if unit_column else []
        if not unit_names and declared:
            unit_names = [declared] * len(rows)
        points = []
        group_dimensions = set()
        units_seen = list(dict.fromkeys(unit_names))
        group_is_compatible = True
        for index, row in enumerate(rows):
            y = _number(row[y_column])
            unit_name = unit_names[index] if unit_names else None
            if unit_name:
                try:
                    dimension, y, base_unit = _convert_value(y, unit_name)
                    group_dimensions.add(dimension)
                    dimensions.add(dimension)
                    unit_name = base_unit
                except AnalysisError:
                    group_is_compatible = False
            elif unit_column:
                group_is_compatible = False
            points.append({"x": row[x_column], "y": y, "unit": unit_name})
        is_compatible = len(group_dimensions) <= 1 and len(units_seen) == 0 or (
            len(group_dimensions) <= 1 and all(
                units.compativeis({"unidade": a}, {"unidade": b})
                for a in units_seen for b in units_seen
            )
        )
        is_compatible = is_compatible and group_is_compatible
        if not is_compatible:
            incompatible.append(key)
        result_series.append({"name": key, "points": points,
                              "unit": points[0]["unit"] if points else None,
                              "status": "ok" if is_compatible else "incompatible_units"})
    if len(dimensions) > 1:
        for item in result_series:
            if item["name"] not in incompatible:
                incompatible.append(item["name"])
            item["status"] = "incompatible_units"
    comparable = not incompatible and len(dimensions) <= 1
    return _result(dataset, "chart_series", {
        "x": x_column, "y": y_column, "series": result_series,
        "comparison": {"compatible": comparable,
                       "incompatible_groups": incompatible,
                       "reason": None if comparable else "incompatible_units"},
    })
