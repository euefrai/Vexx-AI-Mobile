import sqlite3

import pytest

from continuous_research import ResearchContextStore


@pytest.fixture
def store():
    connection = sqlite3.connect(":memory:")
    result = ResearchContextStore(connection)
    result.initialize()
    yield result
    connection.close()


def test_context_checkpoints_restore_latest_state_without_losing_evidence_references(store):
    first = store.save(
        "owner-a",
        "job-1",
        {
            "objective": "Compare the two policies.",
            "evidence": [{"id": "e1", "source_id": "s1"}],
            "pending_steps": ["check publication date"],
            "next_action": "verify current policy version",
            "untrusted_extra": "not persisted",
        },
    )
    second = store.save(
        "owner-a",
        "job-1",
        {
            "objective": "Compare the two policies.",
            "evidence": [
                {"id": "e1", "source_id": "s1"},
                {"id": "e2", "source_id": "s2"},
            ],
            "pending_steps": [],
            "next_action": "synthesize sourced differences",
        },
    )

    restored = store.restore_latest("owner-a", "job-1")
    assert first == 1
    assert second == 2
    assert restored == {
        "sequence": 2,
        "state": {
            "objective": "Compare the two policies.",
            "evidence": [
                {"id": "e1", "source_id": "s1"},
                {"id": "e2", "source_id": "s2"},
            ],
            "pending_steps": [],
            "next_action": "synthesize sourced differences",
        },
        "semantic_compaction": "unavailable_without_llm",
    }


def test_context_checkpoints_are_owner_and_job_scoped(store):
    store.save("owner-a", "job-1", {"objective": "First investigation"})
    assert store.restore_latest("owner-b", "job-1") is None
    assert store.restore_latest("owner-a", "job-2") is None
    assert store.delete_for_job("owner-a", "job-1") == 1
    assert store.restore_latest("owner-a", "job-1") is None


def test_context_checkpoint_rejects_missing_objective_and_oversized_state(store):
    with pytest.raises(ValueError, match="objective"):
        store.save("owner", "job", {"evidence": []})
    with pytest.raises(ValueError, match="size limit"):
        store.save("owner", "job", {"objective": "Question", "evidence": ["x" * 1_050_000]})
