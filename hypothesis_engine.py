"""Owner-scoped persistence for hypotheses and their investigation state."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


HYPOTHESIS_STATUSES = frozenset({"open", "supported", "weakened", "inconclusive"})
MAX_TEXT_LENGTH = 12_000
MAX_ITEM_LENGTH = 1_200
MAX_ITEMS = 100


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    owner_id: str
    job_id: str
    statement: str
    status: str = "open"
    evidence_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    result_summary: str = ""


class HypothesisStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_hypotheses (
                hypothesis_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                statement TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open', 'supported', 'weakened', 'inconclusive')),
                evidence_ids TEXT NOT NULL,
                missing_evidence TEXT NOT NULL,
                next_steps TEXT NOT NULL,
                result_summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, job_id, hypothesis_id)
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_hypotheses_job "
            "ON research_hypotheses(owner_id, job_id, updated_at)"
        )
        self._connection.commit()

    def save(self, hypothesis: Hypothesis) -> None:
        self._validate(hypothesis)
        now = datetime.now(timezone.utc).isoformat()
        self._connection.execute(
            """
            INSERT INTO research_hypotheses (
                hypothesis_id, owner_id, job_id, statement, status,
                evidence_ids, missing_evidence, next_steps, result_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, job_id, hypothesis_id) DO UPDATE SET
                statement=excluded.statement,
                status=excluded.status,
                evidence_ids=excluded.evidence_ids,
                missing_evidence=excluded.missing_evidence,
                next_steps=excluded.next_steps,
                result_summary=excluded.result_summary,
                updated_at=excluded.updated_at
            """,
            (
                hypothesis.hypothesis_id,
                hypothesis.owner_id,
                hypothesis.job_id,
                hypothesis.statement.strip(),
                hypothesis.status,
                json.dumps(hypothesis.evidence_ids, ensure_ascii=False),
                json.dumps(hypothesis.missing_evidence, ensure_ascii=False),
                json.dumps(hypothesis.next_steps, ensure_ascii=False),
                hypothesis.result_summary.strip(),
                now,
                now,
            ),
        )
        self._connection.commit()

    def list_for_job(self, owner_id: str, job_id: str) -> list[Hypothesis]:
        rows = self._connection.execute(
            """
            SELECT hypothesis_id, owner_id, job_id, statement, status,
                   evidence_ids, missing_evidence, next_steps
                   , result_summary
            FROM research_hypotheses
            WHERE owner_id=? AND job_id=?
            ORDER BY created_at, hypothesis_id
            """,
            (owner_id, job_id),
        ).fetchall()
        return [
            Hypothesis(
                hypothesis_id=row[0],
                owner_id=row[1],
                job_id=row[2],
                statement=row[3],
                status=row[4],
                evidence_ids=tuple(json.loads(row[5])),
                missing_evidence=tuple(json.loads(row[6])),
                next_steps=tuple(json.loads(row[7])),
                result_summary=row[8],
            )
            for row in rows
        ]

    def delete_for_job(self, owner_id: str, job_id: str) -> int:
        cursor = self._connection.execute(
            "DELETE FROM research_hypotheses WHERE owner_id=? AND job_id=?",
            (owner_id, job_id),
        )
        self._connection.commit()
        return cursor.rowcount

    @staticmethod
    def _validate(hypothesis: Hypothesis) -> None:
        if not hypothesis.owner_id.strip() or not hypothesis.job_id.strip() or not hypothesis.hypothesis_id.strip():
            raise ValueError("Hypothesis, owner, and job identifiers are required")
        if not hypothesis.statement.strip() or len(hypothesis.statement) > MAX_TEXT_LENGTH:
            raise ValueError("Hypothesis statement is empty or too long")
        if hypothesis.status not in HYPOTHESIS_STATUSES:
            raise ValueError("Unsupported hypothesis status")
        if len(hypothesis.result_summary) > MAX_TEXT_LENGTH:
            raise ValueError("Hypothesis result is too long")
        values_to_validate = (
            hypothesis.evidence_ids,
            hypothesis.missing_evidence,
            hypothesis.next_steps,
        )
        if sum(len(values) for values in values_to_validate) > MAX_ITEMS:
            raise ValueError("Hypothesis lists exceed the combined item limit")
        for values in values_to_validate:
            _validate_items(values)


def _validate_items(values: Sequence[str]) -> None:
    if len(values) > MAX_ITEMS:
        raise ValueError("Hypothesis list exceeds the item limit")
    if any(not item.strip() or len(item) > MAX_ITEM_LENGTH for item in values):
        raise ValueError("Hypothesis list contains an empty or oversized value")
