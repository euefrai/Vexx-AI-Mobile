import pytest

import structured_analysis as analysis
from research_visualizations import chart_message, compare_message


@pytest.fixture
def dataset():
    return analysis.load_csv(
        "month,team,amount,unit\nJan,A,10,W\nFeb,A,20,W\nJan,B,20,W\nFeb,B,30,W\n",
        source="upload:energy.csv",
        metadata={"period": "2026-Q1", "methodology": "meter readings"},
    )


def test_chart_and_comparison_use_actual_analysis_and_keep_source(dataset):
    chart_result = analysis.chart_series(
        dataset, "month", "amount", series_column="team", unit_column="unit"
    )
    message = chart_message(
        chart_result,
        title="Power by month",
        source_title="energy.csv",
        locator="rows 1-4",
        chart_type="line",
    )
    props = message["blocks"][0]["props"]
    assert props["labels"] == ["Jan", "Feb"]
    assert props["series"] == [
        {"label": "A", "values": [10.0, 20.0]},
        {"label": "B", "values": [20.0, 30.0]},
    ]
    assert props["y_label"] == "W"
    assert props["sources"][0]["id"] == "upload:energy.csv"
    assert props["sources"][0]["locator"] == "rows 1-4"
    assert props["sources"][0]["period"] == "2026-Q1"
    assert props["sources"][0]["methodology"] == "meter readings"
    assert props["sources"][0]["analysis_method"] == "chart_series"

    difference_result = analysis.differences(
        dataset, "team", "amount", "A", unit_column="unit"
    )
    comparison = compare_message(
        difference_result,
        title="Mean power by team",
        baseline_label="Team A",
        source_title="energy.csv",
    )
    row = comparison["blocks"][0]["props"]["rows"][0]
    assert row == {
        "label": "team=B",
        "a": "15 W",
        "b": "25 W",
        "melhor": "",
    }
    assert comparison["blocks"][0]["props"]["sources"][0]["id"] == "upload:energy.csv"


def test_chart_rejects_incompatible_units_and_missing_provenance(dataset):
    result = analysis.chart_series(
        dataset, "month", "amount", series_column="team", unit_column="unit"
    )
    incompatible = {
        "data": {
            **result["data"],
            "comparison": {"compatible": False, "incompatible_groups": ["B"]},
        },
        "provenance": result["provenance"],
    }
    with pytest.raises(ValueError, match="incompatible units"):
        chart_message(incompatible, title="Chart", source_title="energy.csv")

    with pytest.raises(ValueError, match="Source id and title"):
        chart_message(
            {"data": result["data"], "provenance": {}},
            title="Chart",
            source_title="energy.csv",
        )


def test_chart_rejects_unaligned_series(dataset):
    result = analysis.chart_series(
        dataset, "month", "amount", series_column="team", unit_column="unit"
    )
    result["data"]["series"][1]["points"].pop()
    with pytest.raises(ValueError, match="same ordered x values"):
        chart_message(result, title="Chart", source_title="energy.csv")
