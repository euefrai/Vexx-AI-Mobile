import sqlite3

import pytest

from hypothesis_engine import Hypothesis, HypothesisStore


@pytest.fixture
def store():
    connection = sqlite3.connect(":memory:")
    result = HypothesisStore(connection)
    result.initialize()
    yield result
    connection.close()


def test_hypotheses_persist_updates_and_remain_owner_scoped(store):
    item = Hypothesis(
        hypothesis_id="thermal",
        owner_id="owner-a",
        job_id="job-1",
        statement="Thermal throttling may explain the slowdown.",
        evidence_ids=("ev-1",),
        missing_evidence=("CPU temperature under load",),
        next_steps=("Measure temperature during a repeatable workload",),
    )
    store.save(item)
    store.save(
        Hypothesis(
            **{
                **item.__dict__,
                "status": "weakened",
                "evidence_ids": ("ev-1", "ev-2"),
                "result_summary": "One measured observation weakens this explanation.",
            }
        )
    )

    assert store.list_for_job("owner-a", "job-1") == [
        Hypothesis(
            **{
                **item.__dict__,
                "status": "weakened",
                "evidence_ids": ("ev-1", "ev-2"),
                "result_summary": "One measured observation weakens this explanation.",
            }
        )
    ]
    assert store.list_for_job("owner-b", "job-1") == []
    assert store.list_for_job("owner-a", "job-2") == []


def test_hypothesis_deletion_is_limited_to_owner_and_job(store):
    store.save(Hypothesis("h1", "owner-a", "job-1", "Possibility one"))
    store.save(Hypothesis("h2", "owner-a", "job-2", "Possibility two"))
    store.save(Hypothesis("h3", "owner-b", "job-1", "Other owner's possibility"))

    assert store.delete_for_job("owner-a", "job-1") == 1
    assert store.list_for_job("owner-a", "job-1") == []
    assert len(store.list_for_job("owner-a", "job-2")) == 1
    assert len(store.list_for_job("owner-b", "job-1")) == 1


@pytest.mark.parametrize(
    "hypothesis",
    [
        Hypothesis("h", "owner", "job", "Claim", status="confirmed"),
        Hypothesis("h", "owner", "job", " "),
        Hypothesis("h", "owner", "job", "Claim", evidence_ids=("",)),
        Hypothesis("h", "owner", "job", "Claim", next_steps=("x" * 1_201,)),
    ],
)
def test_hypothesis_validation_rejects_invalid_state(store, hypothesis):
    with pytest.raises(ValueError):
        store.save(hypothesis)
