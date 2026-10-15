"""Reproducible, deterministic evaluation primitives for research quality."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from continuous_research import ResearchContextStore
import docs_agent
import pc_agent


CLAIM_LABELS = (
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNVERIFIED",
    "INSUFFICIENT_EVIDENCE",
)
DATASET_CATEGORIES = (
    "factual_qa",
    "multi_hop_research",
    "contradiction_detection",
    "source_attribution",
    "document_research",
    "numerical_reasoning",
    "temporal_research",
    "adversarial_research",
    "long_horizon_research",
)


class QualityLabError(ValueError):
    """Invalid benchmark input or evaluation labels."""


def load_dataset(path: str | Path) -> tuple[dict[str, Any], str]:
    """Load and validate a frozen local dataset, returning its SHA-256 digest."""
    dataset_path = Path(path)
    raw = dataset_path.read_bytes()
    try:
        dataset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualityLabError(f"invalid dataset JSON: {dataset_path}") from exc
    if not isinstance(dataset, dict):
        raise QualityLabError("dataset root must be an object")
    if not isinstance(dataset.get("dataset_id"), str) or not dataset["dataset_id"]:
        raise QualityLabError("dataset_id is required")
    if not isinstance(dataset.get("version"), str) or not dataset["version"]:
        raise QualityLabError("dataset version is required")
    if dataset.get("truth_basis") != "synthetic_local_fixture":
        raise QualityLabError("local fixture truth basis must be stated explicitly")
    documents = dataset.get("documents")
    cases = dataset.get("cases")
    if not isinstance(documents, list) or not isinstance(cases, list):
        raise QualityLabError("documents and cases must be arrays")

    document_ids = [d.get("id") for d in documents if isinstance(d, dict)]
    if len(document_ids) != len(documents) or len(set(document_ids)) != len(document_ids):
        raise QualityLabError("documents must have unique IDs")
    known_documents = set(document_ids)
    case_ids = [c.get("id") for c in cases if isinstance(c, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
        raise QualityLabError("cases must have unique IDs")
    for case in cases:
        if case.get("category") not in DATASET_CATEGORIES:
            raise QualityLabError(f"unsupported category in case {case.get('id')!r}")
        queries = case.get("queries")
        if not isinstance(queries, list) or not queries:
            raise QualityLabError(f"case {case['id']!r} must define retrieval queries")
        for query in queries:
            relevance = query.get("relevance")
            if (not isinstance(query.get("text"), str) or not query["text"].strip()
                    or not isinstance(relevance, dict) or not relevance):
                raise QualityLabError(f"case {case['id']!r} has invalid query labels")
            for doc_id, grade in relevance.items():
                if doc_id not in known_documents:
                    raise QualityLabError(f"unknown relevant document {doc_id!r}")
                if isinstance(grade, bool) or not isinstance(grade, int) or grade < 1:
                    raise QualityLabError("relevance grades must be positive integers")
    for document in documents:
        if not all(isinstance(document.get(k), str) and document[k]
                   for k in ("name", "content")):
            raise QualityLabError(f"document {document['id']!r} needs name and content")
        if Path(document["name"]).name != document["name"]:
            raise QualityLabError("benchmark document names must be basenames")
    scenarios = dataset.get("checkpoint_scenarios", [])
    if not isinstance(scenarios, list):
        raise QualityLabError("checkpoint_scenarios must be an array")
    scenario_ids = [scenario.get("id") for scenario in scenarios
                    if isinstance(scenario, dict)]
    if len(scenario_ids) != len(scenarios) or len(set(scenario_ids)) != len(scenario_ids):
        raise QualityLabError("checkpoint scenarios must have unique IDs")
    for scenario in scenarios:
        steps = scenario.get("step_count")
        if (isinstance(steps, bool) or not isinstance(steps, int) or steps < 1
                or not isinstance(scenario.get("objective"), str)
                or not scenario["objective"].strip()):
            raise QualityLabError(f"checkpoint scenario {scenario['id']!r} is invalid")
    return dataset, hashlib.sha256(raw).hexdigest()


def retrieval_metrics(
    retrieved_ids: list[str],
    relevance: dict[str, int],
    k: int = 5,
) -> dict[str, float | int]:
    """Compute document-level P@K, recall@K, reciprocal rank, NDCG, duplicates.

    Precision divides by K even when fewer than K results are returned.
    Duplicate hits count once for relevance and are reported separately.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise QualityLabError("k must be a positive integer")
    if not relevance or any(
        isinstance(grade, bool) or not isinstance(grade, int) or grade < 1
        for grade in relevance.values()
    ):
        raise QualityLabError("relevance must contain positive integer grades")
    ranked = retrieved_ids[:k]
    relevant_ids = set(relevance)
    unique_ranked = set(ranked)
    hits = unique_ranked & relevant_ids
    first_relevant_rank = next(
        (rank for rank, doc_id in enumerate(ranked, start=1) if doc_id in relevant_ids),
        None,
    )
    seen_for_dcg = set()
    dcg = 0.0
    for rank, doc_id in enumerate(ranked, start=1):
        if doc_id in relevance and doc_id not in seen_for_dcg:
            dcg += (2 ** relevance[doc_id] - 1) / math.log2(rank + 1)
            seen_for_dcg.add(doc_id)
    ideal_grades = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = sum(
        (2 ** grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, start=1)
    )
    return {
        "precision_at_k": round(len(hits) / k, 6),
        "recall_at_k": round(len(hits) / len(relevant_ids), 6),
        "mrr_at_k": round(1 / first_relevant_rank, 6) if first_relevant_rank else 0.0,
        "ndcg_at_k": round(dcg / ideal_dcg, 6) if ideal_dcg else 0.0,
        "duplicate_rate_at_k": (
            round((len(ranked) - len(unique_ranked)) / len(ranked), 6)
            if ranked else 0.0
        ),
        "retrieved_count_at_k": len(ranked),
        "relevant_count": len(relevant_ids),
    }


def classification_metrics(
    expected: list[str],
    predicted: list[str],
    labels: tuple[str, ...] = CLAIM_LABELS,
) -> dict[str, Any]:
    """Score supplied human/reference labels; does not classify claims itself."""
    if len(expected) != len(predicted):
        raise QualityLabError("expected and predicted labels must have equal length")
    if any(value not in labels for value in expected + predicted):
        raise QualityLabError("unknown classification label")
    matrix = {label: {pred: 0 for pred in labels} for label in labels}
    for actual, guess in zip(expected, predicted):
        matrix[actual][guess] += 1
    total = len(expected)
    correct = sum(matrix[label][label] for label in labels)
    per_label = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in labels if actual != label)
        fn = sum(matrix[label][guess] for guess in labels if guess != label)
        per_label[label] = {
            "precision": round(tp / (tp + fp), 6) if tp + fp else None,
            "recall": round(tp / (tp + fn), 6) if tp + fn else None,
            "support": sum(matrix[label].values()),
        }
    return {
        "count": total,
        "accuracy": round(correct / total, 6) if total else None,
        "confusion_matrix": matrix,
        "per_label": per_label,
    }


def citation_stage_metrics(records: list[dict[str, bool]]) -> dict[str, Any]:
    """Report each citation validation stage independently, never as one pass."""
    stages = (
        "citation_exists",
        "source_retrieved",
        "passage_found",
        "claim_supported",
    )
    totals = {}
    for stage in stages:
        values = [record.get(stage) for record in records]
        if any(not isinstance(value, bool) for value in values):
            raise QualityLabError(f"each citation record needs boolean {stage}")
        passed = sum(values)
        totals[stage] = {
            "passed": passed,
            "total": len(values),
            "rate": round(passed / len(values), 6) if values else None,
        }
    return {"citation_count": len(records), "stages": totals}


def contradiction_metrics(expected: list[bool], detected: list[bool]) -> dict[str, Any]:
    """Evaluate human-labelled conflict detection separately from resolution."""
    if len(expected) != len(detected):
        raise QualityLabError("expected and detected arrays must have equal length")
    if any(type(value) is not bool for value in expected + detected):
        raise QualityLabError("contradiction labels must be booleans")
    tp = sum(a and p for a, p in zip(expected, detected))
    tn = sum(not a and not p for a, p in zip(expected, detected))
    fp = sum(not a and p for a, p in zip(expected, detected))
    fn = sum(a and not p for a, p in zip(expected, detected))
    return {
        "count": len(expected),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(tp / (tp + fp), 6) if tp + fp else None,
        "recall": round(tp / (tp + fn), 6) if tp + fn else None,
    }


def checkpoint_metrics(expected: dict[str, list[str]], actual: dict[str, list[str]]) -> dict[str, Any]:
    """Measure persisted state coverage and repeated operation IDs by category."""
    categories = ("objectives", "constraints", "decisions", "evidence_ids", "pending")
    coverage = {}
    for category in categories:
        wanted = set(expected.get(category, []))
        found = set(actual.get(category, []))
        coverage[category] = {
            "expected": len(wanted),
            "preserved": len(wanted & found),
            "recall": round(len(wanted & found) / len(wanted), 6) if wanted else None,
            "missing": sorted(wanted - found),
        }
    operation_ids = actual.get("operation_ids")
    duplicates = (
        len(operation_ids) - len(set(operation_ids))
        if operation_ids is not None else None
    )
    return {
        "state": coverage,
        "operation_count": len(operation_ids) if operation_ids is not None else None,
        "duplicate_operation_ids": duplicates,
    }


def retrieval_recommendations(metrics: dict[str, float | int]) -> list[dict[str, str]]:
    """Return bounded review suggestions from measured retrieval metrics only."""
    recommendations = []
    recall = float(metrics["recall_at_k"])
    precision = float(metrics["precision_at_k"])
    duplicates = float(metrics["duplicate_rate_at_k"])
    ndcg = float(metrics["ndcg_at_k"])
    if recall < 0.8:
        recommendations.append({
            "signal": "low_recall",
            "recommendation": (
                "Inspect missing annotated documents and query coverage before "
                "changing retrieval."
            ),
        })
    if precision < 0.4 and recall >= 0.8:
        recommendations.append({
            "signal": "low_precision_with_recall",
            "recommendation": (
                "Review ranking specificity and irrelevant top-K results without "
                "reducing coverage."
            ),
        })
    if duplicates > 0:
        recommendations.append({
            "signal": "duplicate_results",
            "recommendation": "Review document/chunk de-duplication in top-K.",
        })
    if ndcg < 0.8:
        recommendations.append({
            "signal": "weak_rank_order",
            "recommendation": "Review ordering against the graded relevance labels.",
        })
    return recommendations


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def run_document_retrieval_benchmark(
    dataset_path: str | Path,
    work_dir: str | Path,
    *,
    k: int = 5,
    owner: str = "quality-lab-v1",
) -> dict[str, Any]:
    """Measure the real document extractor and FTS5/lexical retrieval locally.

    All indexed originals and SQLite state are confined to `work_dir`.
    """
    dataset, digest = load_dataset(dataset_path)
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    documents_dir = root / "documents"
    database_path = root / "benchmark.sqlite3"
    if database_path.exists():
        raise QualityLabError("benchmark database path must be fresh")
    if documents_dir.exists() and any(documents_dir.iterdir()):
        raise QualityLabError("benchmark originals directory must be empty")
    documents_dir.mkdir(exist_ok=True)
    old_docs_path = os.environ.get("JULIA_DOCS_PATH")
    os.environ["JULIA_DOCS_PATH"] = str(documents_dir)
    db = None
    try:
        db = pc_agent.open_db(database_path)
        started = time.perf_counter()
        document_ids = {}
        extraction_times = {}
        for document in dataset["documents"]:
            raw = document["content"].encode("utf-8")
            before = time.perf_counter()
            saved = docs_agent.salvar_documento(
                db, document["name"], raw, "quality-lab", owner=owner
            )
            extraction_times[document["id"]] = (
                time.perf_counter() - before
            ) * 1000
            document_ids[document["id"]] = saved["doc_id"]

        case_results = []
        query_times = []
        source_checks = []
        for case in dataset["cases"]:
            query_results = []
            case_retrieved = []
            for query in case["queries"]:
                before = time.perf_counter()
                hits = docs_agent.trechos_relevantes(
                    db, query["text"], k=k, owner=owner
                )
                elapsed_ms = (time.perf_counter() - before) * 1000
                query_times.append(elapsed_ms)
                retrieved = [hit["doc"] for hit in hits]
                id_by_name = {
                    doc["name"]: doc["id"] for doc in dataset["documents"]
                }
                retrieved_ids = [
                    id_by_name[name] for name in retrieved if name in id_by_name
                ]
                case_retrieved.extend(retrieved_ids)
                query_results.append({
                    "query": query["text"],
                    "metrics": retrieval_metrics(retrieved_ids, query["relevance"], k),
                    "retrieved_document_ids": retrieved_ids,
                    "retrieved_chunk_ids": [hit["chunk_id"] for hit in hits],
                    "elapsed_ms": round(elapsed_ms, 3),
                })
            case_results.append({
                "case_id": case["id"],
                "category": case["category"],
                "queries": query_results,
            })
            retrieved_for_case = set(case_retrieved)
            checks = {"case_id": case["id"], "category": case["category"]}
            if case.get("primary_source"):
                checks["primary_source_id"] = case["primary_source"]
                checks["primary_source_retrieved"] = (
                    case["primary_source"] in retrieved_for_case
                )
                checks["republication_only"] = (
                    case.get("republication") in retrieved_for_case
                    and case["primary_source"] not in retrieved_for_case
                )
            if case.get("latest_source"):
                checks["latest_source_id"] = case["latest_source"]
                checks["latest_source_retrieved"] = (
                    case["latest_source"] in retrieved_for_case
                )
            if case.get("expected_conflict"):
                expected_pair = set(case.get("expected_passages", []))
                checks["conflict_evidence_complete"] = (
                    bool(expected_pair) and expected_pair <= retrieved_for_case
                )
            if len(checks) > 2:
                source_checks.append(checks)

        by_category = {}
        for category in sorted({case["category"] for case in case_results}):
            metrics = [
                query["metrics"]
                for case in case_results if case["category"] == category
                for query in case["queries"]
            ]
            by_category[category] = {
                key: _mean([float(row[key]) for row in metrics])
                for key in (
                    "precision_at_k", "recall_at_k", "mrr_at_k",
                    "ndcg_at_k", "duplicate_rate_at_k",
                )
            }
            by_category[category]["case_count"] = sum(
                case["category"] == category for case in case_results
            )
            by_category[category]["query_count"] = len(metrics)

        results = [
            query["metrics"]
            for case in case_results for query in case["queries"]
        ]
        summary = {
            key: _mean([float(row[key]) for row in results])
            for key in (
                "precision_at_k", "recall_at_k", "mrr_at_k",
                "ndcg_at_k", "duplicate_rate_at_k",
            )
        }
        attribution_cases = [
            row for row in source_checks if "primary_source_retrieved" in row
        ]
        temporal_cases = [
            row for row in source_checks if "latest_source_retrieved" in row
        ]
        conflict_cases = [
            row for row in source_checks if "conflict_evidence_complete" in row
        ]
        source_quality = {
            "primary_source": {
                "cases": len(attribution_cases),
                "retrieved": sum(row["primary_source_retrieved"]
                                 for row in attribution_cases),
                "recall": _mean([
                    float(row["primary_source_retrieved"])
                    for row in attribution_cases
                ]),
                "republication_only": sum(
                    row["republication_only"] for row in attribution_cases
                ),
            },
            "latest_temporal_source": {
                "cases": len(temporal_cases),
                "retrieved": sum(row["latest_source_retrieved"]
                                 for row in temporal_cases),
                "recall": _mean([
                    float(row["latest_source_retrieved"])
                    for row in temporal_cases
                ]),
            },
            "contradiction_evidence_pair": {
                "cases": len(conflict_cases),
                "complete": sum(row["conflict_evidence_complete"]
                                for row in conflict_cases),
                "recall": _mean([
                    float(row["conflict_evidence_complete"])
                    for row in conflict_cases
                ]),
            },
            "independence": (
                "not scored: domain or URL difference is not evidence of "
                "independent origin"
            ),
        }
        report = {
            "report_schema": "julia-research-quality-report/1",
            "dataset": {
                "dataset_id": dataset["dataset_id"],
                "version": dataset["version"],
                "sha256": digest,
                "truth_basis": dataset["truth_basis"],
            },
            "execution": {
                "kind": "local_frozen_document_retrieval",
                "retriever": "docs_agent.trechos_relevantes",
                "database": "temporary SQLite; owner-scoped fixture data only",
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
                "k": k,
            },
            "counts": {
                "documents": len(document_ids),
                "cases": len(case_results),
                "queries": len(query_times),
            },
            "timing_ms": {
                "total": round((time.perf_counter() - started) * 1000, 3),
                "extraction_mean": round(
                    sum(extraction_times.values()) / len(extraction_times), 3
                ) if extraction_times else None,
                "retrieval_mean": round(sum(query_times) / len(query_times), 3)
                if query_times else None,
                "retrieval_max": round(max(query_times), 3) if query_times else None,
            },
            "retrieval_metrics": summary,
            "by_category": by_category,
            "source_checks": source_checks,
            "source_quality_metrics": source_quality,
            "optimization_recommendations": retrieval_recommendations(summary),
            "cases": case_results,
            "not_measured": [
                "semantic claim correctness",
                "web search quality",
                "source independence beyond curated fixture labels",
                "LLM generation quality",
                "CPU and process-wide RAM",
                "token consumption",
                "real-world factual accuracy",
            ],
        }
        return report
    finally:
        if db is not None:
            db.close()
        if old_docs_path is None:
            os.environ.pop("JULIA_DOCS_PATH", None)
        else:
            os.environ["JULIA_DOCS_PATH"] = old_docs_path


def run_checkpoint_benchmark(
    dataset_path: str | Path,
    database_path: str | Path,
) -> dict[str, Any]:
    """Exercise persisted checkpoint save/restore with frozen 10/25/50-step cases."""
    dataset, digest = load_dataset(dataset_path)
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise QualityLabError("checkpoint database path must be fresh")
    scenarios = []
    total_checkpoints = 0
    for scenario in dataset.get("checkpoint_scenarios", []):
        started = time.perf_counter()
        owner = "quality-lab-checkpoint"
        job_id = scenario["id"]
        connection = sqlite3.connect(path)
        store = ResearchContextStore(connection)
        store.initialize()
        results = []
        for step in range(1, scenario["step_count"] + 1):
            results.append({
                "operation_id": f"{job_id}-step-{step}",
                "step": step,
            })
            state = {
                "objective": scenario["objective"],
                "restrictions": scenario.get("restrictions", []),
                "decisions": scenario.get("decisions", []),
                "evidence": scenario.get("evidence", []),
                "pending_steps": scenario.get("pending_steps", []),
                "results": results,
                "next_action": scenario.get("pending_steps", [""])[0],
            }
            sequence = store.save(owner, job_id, state)
        connection.close()

        reopened = sqlite3.connect(path)
        try:
            restored = ResearchContextStore(reopened).restore_latest(owner, job_id)
        finally:
            reopened.close()
        if restored is None:
            raise QualityLabError(f"checkpoint restore failed for {job_id}")
        state = restored["state"]
        expected = {
            "objectives": [scenario["objective"]],
            "constraints": scenario.get("restrictions", []),
            "decisions": scenario.get("decisions", []),
            "evidence_ids": scenario.get("evidence", []),
            "pending": scenario.get("pending_steps", []),
        }
        actual = {
            "objectives": [state.get("objective", "")],
            "constraints": state.get("restrictions", []),
            "decisions": state.get("decisions", []),
            "evidence_ids": state.get("evidence", []),
            "pending": state.get("pending_steps", []),
        }
        scenarios.append({
            "scenario_id": job_id,
            "step_count": scenario["step_count"],
            "checkpoint_sequence": sequence,
            "restored_sequence": restored["sequence"],
            "semantic_compaction": restored["semantic_compaction"],
            "metrics": checkpoint_metrics(expected, actual),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        })
        total_checkpoints += sequence
    return {
        "dataset": {
            "dataset_id": dataset["dataset_id"],
            "version": dataset["version"],
            "sha256": digest,
            "truth_basis": dataset["truth_basis"],
        },
        "execution": {
            "kind": "local_sqlite_checkpoint_save_close_reopen_restore",
            "store": "continuous_research.ResearchContextStore",
            "semantic_compaction": "not tested; unavailable without LLM",
        },
        "counts": {
            "scenarios": len(scenarios),
            "checkpoints_saved": total_checkpoints,
            "steps_in_scenarios": sum(item["step_count"] for item in scenarios),
        },
        "scenarios": scenarios,
    }
