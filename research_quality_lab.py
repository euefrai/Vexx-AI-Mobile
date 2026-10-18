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
    "academic_research",
    "document_format",
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
    # Digest canônico: CRLF→LF antes do hash. O mesmo conteúdo congelado
    # no git produz o mesmo digest no Windows (core.autocrlf=true, working
    # tree CRLF) e no Linux/CI (LF) — sem depender do checkout local.
    return dataset, hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


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
        import tracemalloc
        tracemalloc.start()
        try:
            _probe = [docs_agent.trechos_relevantes(
                db, case["queries"][0]["text"], k=k, owner=owner)
                for case in dataset["cases"][:3]]
        finally:
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
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
                "peak_python_kb": round(peak_bytes / 1024, 1),
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
                "CPU time and process-wide RSS (peak Python KB is measured)",
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


def store_report(db, owner: str, report: dict[str, Any]) -> str:
    """Persist a benchmark report for the admin dashboard (real data only)."""
    import secrets

    if not isinstance(report, dict) or not report:
        raise QualityLabError("report must be a non-empty object")
    dataset = report.get("dataset", {}) if isinstance(report.get("dataset"), dict) else {}
    run_id = "qr-" + secrets.token_hex(6)
    db.execute(
        """CREATE TABLE IF NOT EXISTS quality_runs (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
            dataset_id TEXT NOT NULL DEFAULT '', dataset_version TEXT NOT NULL DEFAULT '',
            dataset_sha256 TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL)"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_quality_owner ON quality_runs(owner_id, created_at)"
    )
    with db:
        db.execute(
            "INSERT INTO quality_runs (id, owner_id, dataset_id, dataset_version,"
            " dataset_sha256, summary, created_at) VALUES (?,?,?,?,?,?,?)",
            (run_id, owner, str(dataset.get("dataset_id", ""))[:120],
             str(dataset.get("version", ""))[:40], str(dataset.get("sha256", ""))[:64],
             json.dumps(report, ensure_ascii=False)[:200000],
             time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())),
        )
    return run_id


def list_reports(db, owner: str, limite: int = 20) -> list[dict[str, Any]]:
    """Latest stored reports (owner-scoped; summaries only, never recomputed)."""
    try:
        rows = db.execute(
            "SELECT id, dataset_id, dataset_version, dataset_sha256, summary, created_at"
            " FROM quality_runs WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
            (owner, max(1, min(int(limite or 20), 100))),
        ).fetchall()
    except Exception:
        return []
    out = []
    for run_id, ds_id, ds_ver, digest, summary, ts in rows:
        try:
            full = json.loads(summary or "{}")
        except ValueError:
            continue
        out.append({
            "id": run_id, "dataset_id": ds_id, "dataset_version": ds_ver,
            "dataset_sha256": digest, "created_at": ts,
            "summary": full.get("summary", {}) if isinstance(full, dict) else {},
            "counts": full.get("counts", {}) if isinstance(full, dict) else {},
        })
    return out


def run_memory_retrieval_benchmark(
    dataset_path: str | Path,
    work_dir: str | Path,
    *,
    k: int = 5,
    owner: str = "quality-lab-memory",
) -> dict[str, Any]:
    """Seed memory facts, then score memorias_relevantes against graded keys."""
    dataset, digest = load_dataset(dataset_path)
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "benchmark.sqlite3"
    if database_path.exists():
        raise QualityLabError("benchmark database path must be fresh")
    db = None
    try:
        db = pc_agent.open_db(database_path)
        started = time.perf_counter()
        for fact in dataset.get("memory_facts", []):
            pc_agent.guardar_fato(db, str(fact.get("key", "")), str(fact.get("value", "")),
                                  owner=owner)
        query_results = []
        query_times = []
        for case in dataset.get("memory_cases", []):
            before = time.perf_counter()
            hits = pc_agent.memorias_relevantes(db, case["query"], k=k, owner=owner)
            elapsed_ms = (time.perf_counter() - before) * 1000
            query_times.append(elapsed_ms)
            retrieved_ids = [hit["key"] for hit in hits
                             if isinstance(hit, dict) and hit.get("key")]
            expected = case.get("expected_keys", [])
            relevance = {key: 3 for key in expected}
            query_results.append({
                "query": case["query"],
                "metrics": retrieval_metrics(retrieved_ids, relevance, k),
                "retrieved_key_ids": retrieved_ids,
                "elapsed_ms": round(elapsed_ms, 3),
            })
        results = [row["metrics"] for row in query_results]
        summary = {key: _mean([float(row[key]) for row in results]) for key in (
            "precision_at_k", "recall_at_k", "mrr_at_k",
            "ndcg_at_k", "duplicate_rate_at_k")}
        summary["query_count"] = len(query_results)
        summary["mean_query_ms"] = round(sum(query_times) / len(query_times), 3
                                         ) if query_times else None
        summary["total_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return {
            "dataset": {"dataset_id": dataset["dataset_id"], "version": dataset["version"],
                        "sha256": digest, "truth_basis": dataset["truth_basis"]},
            "summary": summary, "queries": query_results,
        }
    finally:
        if db is not None:
            db.close()


def run_graph_retrieval_benchmark(
    dataset_path: str | Path,
    work_dir: str | Path,
    *,
    k: int = 5,
    owner: str = "quality-lab-graph",
) -> dict[str, Any]:
    """Seed evidence rows, then score the lexical graph ranker."""
    import evidence_graph
    dataset, digest = load_dataset(dataset_path)
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "benchmark.sqlite3"
    if database_path.exists():
        raise QualityLabError("benchmark database path must be fresh")
    db = pc_agent.open_db(database_path)
    try:
        job_id = "bench-graph"
        started = time.perf_counter()
        with db:
            for ev in dataset.get("graph_evidence", []):
                db.execute(
                    "INSERT INTO evidence (id, job_id, owner_id, url, titulo, trecho)"
                    " VALUES (?,?,?,?,?,?)",
                    (ev["id"], job_id, owner, ev.get("url", ""), ev.get("titulo", ""),
                     ev.get("trecho", "")))
        query_results = []
        query_times = []
        for case in dataset.get("graph_cases", []):
            before = time.perf_counter()
            ranked = evidence_graph.rank_evidencias(db, owner, job_id, case["query"], k)
            elapsed_ms = (time.perf_counter() - before) * 1000
            query_times.append(elapsed_ms)
            retrieved_ids = [row["id"] for row in ranked]
            relevance = {doc: 3 for doc in case.get("expected_ids", [])}
            query_results.append({
                "query": case["query"],
                "metrics": retrieval_metrics(retrieved_ids, relevance, k),
                "retrieved_evidence_ids": retrieved_ids,
                "elapsed_ms": round(elapsed_ms, 3),
            })
        results = [row["metrics"] for row in query_results]
        summary = {key: _mean([float(row[key]) for row in results]) for key in (
            "precision_at_k", "recall_at_k", "mrr_at_k",
            "ndcg_at_k", "duplicate_rate_at_k")}
        summary["query_count"] = len(query_results)
        summary["mean_query_ms"] = round(sum(query_times) / len(query_times), 3
                                         ) if query_times else None
        summary["total_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return {
            "dataset": {"dataset_id": dataset["dataset_id"], "version": dataset["version"],
                        "sha256": digest, "truth_basis": dataset["truth_basis"]},
            "summary": summary, "queries": query_results,
        }
    finally:
        db.close()


def run_factual_verification_benchmark(
    dataset_path: str | Path,
) -> dict[str, Any]:
    """Score verificar_claim on frozen labeled pairs (deterministic only)."""
    import evidence_graph
    dataset, digest = load_dataset(dataset_path)
    pairs = dataset.get("factual_pairs", [])
    if not pairs:
        raise QualityLabError("dataset has no factual_pairs")
    expected, predicted, rows = [], [], []
    started = time.perf_counter()
    for pair in pairs:
        claim = {"texto": pair.get("claim_text", ""),
                 "condicoes": {"comparado_a": "", "metrica": "",
                               "quantidades": evidence_graph.extrair_quantidades(
                                   pair.get("claim_text", "")),
                               "datas": []}}
        trecho = pair.get("trecho", "")
        if trecho:
            result = evidence_graph.verificar_claim(
                claim, [{"id": "frozen", "trecho": trecho}])
            label = result["estado"]
        else:
            label = "INSUFFICIENT_EVIDENCE"
        expected.append(pair["expected_label"])
        predicted.append(label)
        rows.append({"id": pair.get("id", ""), "expected": pair["expected_label"],
                     "predicted": label,
                     "match": pair["expected_label"] == label})
    classification = classification_metrics(expected, predicted)
    return {
        "dataset": {"dataset_id": dataset["dataset_id"], "version": dataset["version"],
                    "sha256": digest, "truth_basis": dataset["truth_basis"]},
        "classification": classification, "pairs": rows,
        "total_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _pdf_minimo(texto: str) -> bytes:
    """PDF mínimo válido com uma página de texto (fixture local, sem libs)."""
    corpo = f"BT /F1 12 Tf 50 750 Td ({texto}) Tj ET".encode("latin-1", "ignore")
    partes, offsets, base = [], [], 0
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(corpo) + corpo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = [b"%PDF-1.4\n"]
    for i, obj in enumerate(objs, start=1):
        offsets.append(sum(len(p) for p in out))
        out.append(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_pos = sum(len(p) for p in out)
    out.append(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.append(f"{off:010d} 00000 n \n".encode())
    out.append(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref_pos}\n%%EOF\n".encode())
    return b"".join(out)


def run_format_benchmark(
    work_dir: str | Path,
    *,
    owner: str = "quality-lab-format",
) -> dict[str, Any]:
    """Gera fixtures PDF/DOCX/XLSX/HTML/JSON/CSV/MD/TXT e mede extração+busca."""
    import io
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "benchmark.sqlite3"
    if database_path.exists():
        raise QualityLabError("benchmark database path must be fresh")
    marca = "ZIRCONIO-42"
    arquivos = {
        "relatorio.pdf": _pdf_minimo(f"Relatorio {marca} com conclusoes."),
        "contrato.json": ('{"title": "Contrato", "parte": "%s Ltda", '
                          '"valor": 1000}' % marca).encode("utf-8"),
        "tabela.csv": f"item,valor\ncaneta,{marca}-5\n".encode("utf-8"),
        "pagina.html": (f"<html><head><title>T</title></head><body><h1>{marca}</h1>"
                        f"<p>Texto com a marca.</p></body></html>").encode("utf-8"),
        "nota.md": f"# {marca}\n\nAnotacao simples.\n".encode("utf-8"),
        "texto.txt": f"Texto puro com {marca} embutido.\n".encode("utf-8"),
    }
    try:
        from docx import Document as _Docx

        buf = io.BytesIO()
        doc = _Docx()
        doc.add_paragraph(f"Contrato {marca} assinado.")
        doc.save(buf)
        arquivos["contrato.docx"] = buf.getvalue()
        docx_ok = True
    except ImportError:
        docx_ok = False
    try:
        from openpyxl import Workbook as _Wb

        buf = io.BytesIO()
        wb = _Wb()
        ws = wb.active
        ws.append(["item", "valor"])
        ws.append(["caneta", f"{marca}-5"])
        wb.save(buf)
        arquivos["planilha.xlsx"] = buf.getvalue()
        xlsx_ok = True
    except ImportError:
        xlsx_ok = False
    db = None
    try:
        db = pc_agent.open_db(database_path)
        started = time.perf_counter()
        resultados = []
        for nome, raw in arquivos.items():
            before = time.perf_counter()
            saved = docs_agent.salvar_documento(db, nome, raw, "quality-lab", owner=owner)
            texto = docs_agent.obter_texto(db, saved["doc_id"], owner=owner)
            hits = docs_agent.trechos_relevantes(db, marca.lower(), saved["doc_id"], owner=owner)
            resultados.append({
                "arquivo": nome, "doc_id": saved["doc_id"],
                "marca_encontrada": marca in texto,
                "hits": len(hits),
                "elapsed_ms": round((time.perf_counter() - before) * 1000, 3),
            })
        total_ms = round((time.perf_counter() - started) * 1000, 3)
        return {"formatos": sorted(arquivos),
                "docx_gerado": docx_ok, "xlsx_gerado": xlsx_ok,
                "resultados": resultados,
                "total_ms": total_ms,
                "todos_extraidos": all(r["marca_encontrada"] for r in resultados),
                "todos_buscaveis": all(r["hits"] >= 1 for r in resultados)}
    finally:
        if db is not None:
            db.close()


class FrozenProvider:
    """Deterministic synthetic provider for mode comparison (documented)."""

    nome = "frozen"

    def __init__(self, documentos):
        self._docs = documentos

    def buscar(self, consulta: str, limite: int = 6):
        return [dict(titulo=d["titulo"], url=d["url"], trecho=d["trecho"])
                for d in self._docs[:limite]]


def run_mode_comparison_benchmark(
    work_dir: str | Path,
    *,
    owner: str = "quality-lab-modes",
) -> dict[str, Any]:
    """Same frozen corpus across rapida/pro/profunda/investigativa.

    Measures evidences, searches, pages and latency per mode. Synthetic
    provider; compares budgets, not real-world quality.
    """
    import research_agents
    docs = [
        {"titulo": f"Doc {i}", "url": f"http://exemplo.com/{i}",
         "trecho": f"Estudo {i} sobre cafe e rendimento de 5 por cento em 2024.",
         "texto": f"Estudo {i} sobre cafe e rendimento. " * 20}
        for i in range(8)
    ]

    def recuperar(url: str):
        doc = next(d for d in docs if d["url"] == url)
        return {"titulo": doc["titulo"], "texto": doc["texto"], "final": url}

    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    modos = {}
    for modo in ("rapida", "pro", "profunda", "investigativa"):
        db = None
        try:
            db = pc_agent.open_db(root / f"modes-{modo}.sqlite3")
            job = research_agents.criar_job(db, owner, "cafe faz bem?", manual=modo)
            started = time.perf_counter()
            resumo = research_agents.executar(db, job["id"], owner, [FrozenProvider(docs)],
                                             recuperar)
            modos[modo] = {
                "status": resumo["status"],
                "evidencias": resumo["evidencias"],
                "buscas": resumo["usados"].get("buscas", 0),
                "paginas": resumo["usados"].get("paginas", 0),
                "total_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        finally:
            if db is not None:
                db.close()
    return {"modos": modos, "provider": "frozen-synthetic"}
