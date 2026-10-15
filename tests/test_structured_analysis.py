import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import structured_analysis as sa


def sample(metadata=None):
    return sa.from_rows(
        [
            {"month": "Jan", "team": "A", "amount": 10, "unit": "W", "kind": "x"},
            {"month": "Feb", "team": "A", "amount": 20, "unit": "W", "kind": "y"},
            {"month": "Jan", "team": "B", "amount": 0.03, "unit": "kW", "kind": "x"},
            {"month": "Feb", "team": "B", "amount": 0.04, "unit": "kW", "kind": "x"},
        ],
        source="fixture:quarterly.csv",
        metadata=metadata or {"units": {"amount": "W"}, "period": "2026-Q1",
                              "methodology": "measured readings"},
    )


def test_csv_json_rows_and_provenance_are_retained():
    csv_data = sa.load_csv(
        "name,value\nalpha,2\nbeta,4\n",
        source="upload:sample.csv",
        metadata={"period": "2026", "methodology": "reported", "units": {"value": "W"}},
    )
    result = sa.mean(csv_data, "value")
    assert result["data"]["value"] == 3
    assert result["provenance"] == {
        "period": "2026", "methodology": "reported",
        "units": {"value": "W"}, "source": "upload:sample.csv",
        "method": "mean",
    }
    table = sa.load_json(
        '{"columns":["x","y"],"rows":[["a",2],["b",4]]}',
        source="upload:data.json",
    )
    assert sa.sort_rows(table, "y")["data"] == [
        {"x": "a", "y": 2}, {"x": "b", "y": 4}
    ]
    assert sa.from_rows([{"x": 1}], source="manual", columns=["x"]).rows[0]["x"] == 1


def test_filter_sort_group_mean_and_difference_convert_compatible_units():
    data = sample()
    filtered = sa.filter_rows(data, "amount", "gt", 10)
    assert [row["month"] for row in filtered["data"]] == ["Feb"]
    assert [row["month"] for row in sa.sort_rows(data, "month")["data"]] == [
        "Feb", "Feb", "Jan", "Jan"
    ]
    grouped = sa.group_by(data, "team", "amount", unit_column="unit")["data"]
    assert [row["value"] for row in grouped["groups"]] == [15, 35]
    assert all(row["unit"] == "W" for row in grouped["groups"])
    assert grouped["comparison"]["compatible"]
    diff = sa.differences(data, "team", "amount", "A", unit_column="unit")["data"]
    assert [row["difference"] for row in diff["groups"]] == [0, 20]


def test_incompatible_units_are_flagged_and_not_subtracted():
    data = sa.from_rows(
        [{"group": "power", "value": 10, "unit": "W"},
         {"group": "distance", "value": 10, "unit": "m"}],
        source="fixture:incompatible",
    )
    result = sa.differences(data, "group", "value", "power", unit_column="unit")["data"]
    assert result["groups"][0]["difference"] == 0
    assert result["groups"][1]["difference"] is None
    assert result["groups"][1]["status"] == "incompatible_units"
    groups = sa.group_by(data, "group", "value", unit_column="unit")["data"]
    assert not groups["comparison"]["compatible"]
    assert groups["comparison"]["incompatible_groups"] == [
        {"group": "power"}, {"group": "distance"}
    ]

    unknown = sa.from_rows(
        [{"group": "unknown", "value": 1, "unit": "furlong"}],
        source="fixture:unknown-unit",
    )
    unknown_group = sa.group_by(
        unknown, "group", "value", unit_column="unit"
    )["data"]["groups"][0]
    assert unknown_group["status"] == "incompatible_units"


def test_proportions_outliers_and_chart_are_based_only_on_input_rows():
    data = sa.from_rows(
        [{"date": "d1", "category": "a", "value": 1},
         {"date": "d2", "category": "a", "value": 2},
         {"date": "d3", "category": "b", "value": 2},
         {"date": "d4", "category": "b", "value": 3},
         {"date": "d5", "category": "b", "value": 100}],
        source="fixture:observations",
        metadata={"period": "observed", "methodology": "raw"},
    )
    categories = sa.proportions(data, "category")["data"]["groups"][0]["categories"]
    assert categories == [
        {"value": "a", "count": 2, "proportion": 0.4},
        {"value": "b", "count": 3, "proportion": 0.6},
    ]
    outliers = sa.identify_outliers(data, "value")["data"]
    assert [row["date"] for row in outliers["outliers"]] == ["d5"]
    chart = sa.chart_series(data, "date", "value", series_column="category")
    assert [point for group in chart["data"]["series"] for point in group["points"]] == [
        {"x": "d1", "y": 1.0, "unit": None},
        {"x": "d2", "y": 2.0, "unit": None},
        {"x": "d3", "y": 2.0, "unit": None},
        {"x": "d4", "y": 3.0, "unit": None},
        {"x": "d5", "y": 100.0, "unit": None},
    ]
    assert chart["provenance"]["source"] == "fixture:observations"
    assert chart["provenance"]["period"] == "observed"


def test_validation_and_small_or_empty_numeric_cases():
    data = sa.from_rows([{"x": 1, "label": "one"}], source="fixture:one")
    assert sa.validate_columns(data, ["x", "absent"])["data"] == {
        "valid": False, "missing": ["absent"]
    }
    assert sa.identify_outliers(data, "x")["data"]["status"] == "insufficient_data"
    with pytest.raises(sa.AnalysisError, match="inexistente"):
        sa.mean(data, "absent")
    empty = sa.from_rows([], source="fixture:empty", columns=["x"])
    with pytest.raises(sa.AnalysisError, match="não há valores"):
        sa.mean(empty, "x")


def test_bad_inputs_and_resource_limits_fail_explicitly():
    with pytest.raises(sa.AnalysisError, match="UTF-8|CSV|cabeçalho"):
        sa.load_csv(b"\xff", source="bad")
    with pytest.raises(sa.AnalysisError, match="JSON"):
        sa.load_json('{"x": NaN}', source="bad")
    with pytest.raises(sa.AnalysisError, match="exatamente"):
        sa.from_rows([{"x": 1}, {"y": 2}], source="bad")
    with pytest.raises(sa.AnalysisError, match="não finitos"):
        sa.from_rows([{"x": float("inf")}], source="bad")
    with pytest.raises(sa.AnalysisError, match="máximo de"):
        sa.from_rows(({"x": index} for index in range(sa.MAX_ROWS + 1)), source="too-many")
    columns = [f"c{index}" for index in range(100)]
    with pytest.raises(sa.AnalysisError, match="células"):
        sa.from_rows(
            ({column: 0 for column in columns} for _ in range(1001)),
            source="too-many-cells",
        )
    with pytest.raises(sa.AnalysisError, match="bytes"):
        sa.load_json(" " * (sa.MAX_INPUT_BYTES + 1), source="too-large")


def test_chart_flags_incompatible_unit_dimensions():
    data = sa.from_rows(
        [{"x": "a", "series": "watts", "value": 1, "unit": "W"},
         {"x": "a", "series": "meters", "value": 1, "unit": "m"}],
        source="fixture:chart-units",
    )
    chart = sa.chart_series(data, "x", "value", series_column="series",
                            unit_column="unit")["data"]
    assert not chart["comparison"]["compatible"]
