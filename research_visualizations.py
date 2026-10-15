"""Build validated JDUI blocks from deterministic structured-analysis results."""

from __future__ import annotations

import math
from typing import Any, Mapping

import jdui


def chart_message(
    result: Mapping[str, Any],
    *,
    title: str,
    source_title: str,
    source_url: str = "",
    locator: str = "",
    chart_type: str = "bar",
) -> dict:
    data, provenance, source = _analysis_parts(result, source_title, source_url, locator)
    comparison = data.get("comparison")
    if isinstance(comparison, Mapping) and comparison.get("compatible") is False:
        raise ValueError("Cannot chart groups with incompatible units")
    series_data = data.get("series")
    if not isinstance(series_data, list) or not 1 <= len(series_data) <= 6:
        raise ValueError("Analysis result must contain 1 to 6 chart series")
    labels = [str(point.get("x", "")) for point in _points(series_data[0])]
    if not labels or len(labels) > 24:
        raise ValueError("JDUI charts require 1 to 24 data points")

    units: set[str] = set()
    series = []
    for item in series_data:
        points = _points(item)
        if [str(point.get("x", "")) for point in points] != labels:
            raise ValueError("Chart series must use the same ordered x values")
        unit = item.get("unit")
        if unit:
            units.add(str(unit))
        values = []
        for point in points:
            value = point.get("y")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Chart series contains a non-finite numeric value")
            values.append(value)
        if item.get("status") != "ok":
            raise ValueError("Chart series is not marked as compatible")
        series.append({"label": str(item.get("name", "")), "values": values})
    if len(units) > 1:
        raise ValueError("Cannot plot series with different units on the same axis")

    props = {
        "type": chart_type,
        "title": title,
        "labels": labels,
        "series": series,
        "source": source,
        "x_label": str(data.get("x", "")),
        "y_label": next(iter(units), str(data.get("y", ""))),
        "sources": [source],
    }
    _add_provenance_metadata(source, provenance)
    return _validated_message("chart", props)


def compare_message(
    result: Mapping[str, Any],
    *,
    title: str,
    baseline_label: str,
    source_title: str,
    source_url: str = "",
    locator: str = "",
) -> dict:
    data, provenance, source = _analysis_parts(result, source_title, source_url, locator)
    baseline = data.get("baseline")
    groups = data.get("groups")
    if not isinstance(baseline, Mapping) or not isinstance(groups, list):
        raise ValueError("Analysis result must contain a baseline and comparison groups")
    baseline_group = _group_label(baseline)
    baseline_item = next((item for item in groups if _same_group(item, baseline)), None)
    if baseline_item is None or baseline_item.get("status") != "ok":
        raise ValueError("Baseline group is missing or incompatible")
    baseline_value = _finite_value(baseline_item.get("value"))
    baseline_unit = str(baseline_item.get("unit") or "")
    rows = []
    for item in groups:
        if not isinstance(item, Mapping):
            raise ValueError("Comparison contains an invalid group")
        if _same_group(item, baseline):
            continue
        if item.get("status") != "ok" or str(item.get("unit") or "") != baseline_unit:
            raise ValueError("Cannot compare groups with incompatible units or status")
        rows.append(
            {
                "label": _group_label(item.get("group")),
                "a": _format_measurement(baseline_value, baseline_unit),
                "b": _format_measurement(_finite_value(item.get("value")), baseline_unit),
                "melhor": "",
            }
        )
    if not 1 <= len(rows) <= 12:
        raise ValueError("JDUI comparison requires 1 to 12 non-baseline groups")
    props = {
        "title": title,
        "columns": [baseline_label or baseline_group, "Grupo comparado"],
        "rows": rows,
        "sources": [source],
    }
    _add_provenance_metadata(source, provenance)
    return _validated_message("compare", props)


def _analysis_parts(
    result: Mapping[str, Any],
    source_title: str,
    source_url: str,
    locator: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, str]]:
    if not isinstance(result, Mapping):
        raise ValueError("Expected a structured-analysis result")
    data, provenance = result.get("data"), result.get("provenance")
    if not isinstance(data, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("Analysis result is missing data or provenance")
    source_id = provenance.get("source")
    if not isinstance(source_id, str) or not source_id.strip() or not source_title.strip():
        raise ValueError("Source id and title are required for visual provenance")
    return data, provenance, {
        "id": source_id.strip(),
        "title": source_title.strip(),
        "url": source_url,
        "locator": locator,
    }


def _add_provenance_metadata(source: dict[str, str], provenance: Mapping[str, Any]) -> None:
    for key in ("period", "methodology"):
        value = provenance.get(key)
        if isinstance(value, str) and value.strip():
            source[key] = value.strip()
    method = provenance.get("method")
    if isinstance(method, str) and method.strip():
        source["analysis_method"] = method.strip()


def _points(series: Any) -> list[Mapping[str, Any]]:
    if not isinstance(series, Mapping) or series.get("status") != "ok":
        raise ValueError("Chart series is missing or incompatible")
    points = series.get("points")
    if not isinstance(points, list) or not points or any(not isinstance(point, Mapping) for point in points):
        raise ValueError("Chart series has no points")
    return points


def _same_group(item: Any, baseline: Mapping[str, Any]) -> bool:
    return isinstance(item, Mapping) and item.get("group") == baseline


def _group_label(value: Any) -> str:
    if not isinstance(value, Mapping) or not value or any(not isinstance(key, str) for key in value):
        raise ValueError("Comparison group label is missing")
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def _finite_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Comparison value must be finite and numeric")
    return float(value)


def _format_measurement(value: float, unit: str) -> str:
    return f"{value:.12g} {unit}".strip()


def _validated_message(component: str, props: dict) -> dict:
    message = {
        "version": jdui.VERSION,
        "blocks": [{"type": "ui", "component": component, "props": props}],
    }
    ok, normalized, errors = jdui.validar_mensagem(message)
    if not ok or normalized is None:
        raise ValueError(f"Generated JDUI block failed validation: {errors}")
    return normalized
