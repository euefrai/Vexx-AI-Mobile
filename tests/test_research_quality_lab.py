import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_quality_lab as lab


DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "research_quality_v1.json"


def test_frozen_dataset_is_versioned_and_fixture_scoped():
    dataset, digest = lab.load_dataset(DATASET)
    assert dataset["version"] == "1.0.0"
    assert dataset["truth_basis"] == "synthetic_local_fixture"
    assert digest == (
        "e29379d7b805d25a3a5bea69ab3f9ea11f101cec13cc86c30fa44c221a4d489b"
    )
    assert len(dataset["documents"]) >= 8
    assert {case["category"] for case in dataset["cases"]} >= {
        "factual_qa", "multi_hop_research", "contradiction_detection",
        "source_attribution", "document_research", "numerical_reasoning",
        "temporal_research", "adversarial_research",
    }
    assert {scenario["step_count"] for scenario in dataset["checkpoint_scenarios"]} == {
        10, 25, 50,
    }


def test_dataset_rejects_unknown_reference_and_non_fixture_truth(tmp_path):
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    raw["truth_basis"] = "model_answer"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(lab.QualityLabError, match="truth basis"):
        lab.load_dataset(bad)

    raw["truth_basis"] = "synthetic_local_fixture"
    raw["cases"][0]["queries"][0]["relevance"]["invented-doc"] = 3
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(lab.QualityLabError, match="unknown relevant document"):
        lab.load_dataset(bad)


def test_retrieval_metrics_are_exact_and_report_duplicates():
    result = lab.retrieval_metrics(
        ["doc-a", "doc-b", "doc-a", "irrelevant"],
        {"doc-a": 3, "doc-b": 1},
        k=4,
    )
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == 1.0
    assert result["mrr_at_k"] == 1.0
    assert result["duplicate_rate_at_k"] == 0.25
    assert 0 < result["ndcg_at_k"] <= 1


def test_retrieval_metrics_reject_bad_k_and_empty_reference():
    with pytest.raises(lab.QualityLabError, match="positive integer"):
        lab.retrieval_metrics([], {"doc": 1}, k=0)
    with pytest.raises(lab.QualityLabError, match="positive integer grades"):
        lab.retrieval_metrics([], {}, k=5)


def test_claim_label_metrics_do_not_infer_semantics():
    result = lab.classification_metrics(
        ["SUPPORTED", "CONTRADICTED", "UNVERIFIED"],
        ["SUPPORTED", "UNVERIFIED", "UNVERIFIED"],
    )
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["confusion_matrix"]["CONTRADICTED"]["UNVERIFIED"] == 1
    assert result["per_label"]["CONTRADICTED"]["recall"] == 0.0


def test_citation_validation_stages_remain_separate():
    result = lab.citation_stage_metrics([
        {
            "citation_exists": True,
            "source_retrieved": True,
            "passage_found": False,
            "claim_supported": False,
        },
        {
            "citation_exists": True,
            "source_retrieved": False,
            "passage_found": False,
            "claim_supported": False,
        },
    ])
    stages = result["stages"]
    assert stages["citation_exists"]["rate"] == 1.0
    assert stages["source_retrieved"]["rate"] == 0.5
    assert stages["passage_found"]["rate"] == 0.0
    assert stages["claim_supported"]["rate"] == 0.0


def test_contradiction_metric_reports_false_positives_and_negatives():
    result = lab.contradiction_metrics(
        [True, True, False, False],
        [True, False, True, False],
    )
    assert result == {
        "count": 4,
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "precision": 0.5,
        "recall": 0.5,
    }


def test_checkpoint_metric_covers_state_and_duplicate_operations():
    result = lab.checkpoint_metrics(
        {
            "objectives": ["objective"],
            "constraints": ["owner-only", "no-llm"],
            "decisions": ["do-not-research-online"],
            "evidence_ids": ["e-1", "e-2"],
            "pending": ["verify-source"],
        },
        {
            "objectives": ["objective"],
            "constraints": ["owner-only"],
            "decisions": ["do-not-research-online"],
            "evidence_ids": ["e-1", "e-2"],
            "pending": ["verify-source"],
            "operation_ids": ["step-1", "step-2", "step-2"],
        },
    )
    assert result["state"]["constraints"]["recall"] == 0.5
    assert result["state"]["constraints"]["missing"] == ["no-llm"]
    assert result["duplicate_operation_ids"] == 1


def test_optimization_recommendations_are_tied_to_measured_signals():
    recommendations = lab.retrieval_recommendations({
        "precision_at_k": 0.2,
        "recall_at_k": 0.95,
        "ndcg_at_k": 0.99,
        "duplicate_rate_at_k": 0.0,
    })
    assert [item["signal"] for item in recommendations] == [
        "low_precision_with_recall",
    ]


def test_runner_measures_real_local_document_retriever_in_isolated_store(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JULIA_DOCS_PATH", str(tmp_path / "original-user-docs"))
    old_path = str(tmp_path / "original-user-docs")
    work_dir = tmp_path / "isolated-run"
    report = lab.run_document_retrieval_benchmark(DATASET, work_dir, k=5)

    assert report["dataset"]["truth_basis"] == "synthetic_local_fixture"
    assert report["dataset"]["sha256"]
    assert report["execution"]["retriever"] == "docs_agent.trechos_relevantes"
    assert report["counts"] == {"documents": 11, "cases": 8, "queries": 9}
    assert report["timing_ms"]["retrieval_mean"] >= 0
    assert report["retrieval_metrics"]["recall_at_k"] is not None
    assert report["source_quality_metrics"]["primary_source"]["recall"] == 1.0
    assert report["source_quality_metrics"]["contradiction_evidence_pair"]["recall"] == 1.0
    assert report["optimization_recommendations"][0]["signal"] == (
        "low_precision_with_recall"
    )
    assert (work_dir / "documents").is_dir()
    assert not (Path(old_path) / "protocol-gh-a.txt").exists()
    assert any(
        "semantic claim correctness" in item
        for item in report["not_measured"]
    )


def test_runner_measures_persisted_checkpoint_restore_after_reopen(tmp_path):
    report = lab.run_checkpoint_benchmark(
        DATASET, tmp_path / "checkpoints.sqlite3"
    )

    assert report["counts"] == {
        "scenarios": 3,
        "checkpoints_saved": 85,
        "steps_in_scenarios": 85,
    }
    for scenario in report["scenarios"]:
        assert scenario["checkpoint_sequence"] == scenario["step_count"]
        assert scenario["restored_sequence"] == scenario["step_count"]
        assert scenario["metrics"]["duplicate_operation_ids"] is None
        assert all(
            value["recall"] == 1.0
            for value in scenario["metrics"]["state"].values()
        )
