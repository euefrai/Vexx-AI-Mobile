"""Lossless, owner-scoped research context checkpoints."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping


CONTEXT_VERSION = 1
MAX_CHECKPOINT_BYTES = 1_048_576
STATE_FIELDS = (
    "objective",
    "restrictions",
    "plan",
    "sources",
    "document_chunks",
    "evidence",
    "contradictions",
    "hypotheses",
    "decisions",
    "results",
    "pending_steps",
    "next_action",
)


class ResearchContextStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_context_checkpoints (
                owner_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                context_version INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, job_id, sequence)
            )
            """
        )
        self._connection.commit()

    def save(self, owner_id: str, job_id: str, state: Mapping[str, Any]) -> int:
        if not owner_id.strip() or not job_id.strip():
            raise ValueError("Owner and research job identifiers are required")
        if not isinstance(state.get("objective"), str) or not state["objective"].strip():
            raise ValueError("A research objective is required to checkpoint context")

        preserved = {field: state.get(field) for field in STATE_FIELDS if field in state}
        preserved["objective"] = state["objective"].strip()
        encoded = json.dumps(
            {"version": CONTEXT_VERSION, "state": preserved},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        encoded_bytes = encoded.encode("utf-8")
        if len(encoded_bytes) > MAX_CHECKPOINT_BYTES:
            raise ValueError("Research context exceeds the checkpoint size limit")

        cursor = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM research_context_checkpoints "
            "WHERE owner_id=? AND job_id=?",
            (owner_id, job_id),
        )
        sequence = int(cursor.fetchone()[0])
        self._connection.execute(
            """
            INSERT INTO research_context_checkpoints (
                owner_id, job_id, sequence, context_version, state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                job_id,
                sequence,
                CONTEXT_VERSION,
                encoded,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._connection.commit()
        return sequence

    def restore_latest(self, owner_id: str, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT context_version, state_json, sequence
            FROM research_context_checkpoints
            WHERE owner_id=? AND job_id=?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            (owner_id, job_id),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[1])
        if payload.get("version") != row[0] or row[0] != CONTEXT_VERSION:
            raise ValueError("Unsupported research context checkpoint version")
        return {
            "sequence": row[2],
            "state": payload["state"],
            "semantic_compaction": "unavailable_without_llm",
        }

    def delete_for_job(self, owner_id: str, job_id: str) -> int:
        cursor = self._connection.execute(
            "DELETE FROM research_context_checkpoints WHERE owner_id=? AND job_id=?",
            (owner_id, job_id),
        )
        self._connection.commit()
        return cursor.rowcount
