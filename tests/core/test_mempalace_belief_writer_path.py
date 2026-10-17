"""Failed-outcome-pattern producer -> nexus_soul_palace -> MemPalace -> evaluate_constraints.

Outcomes flow through the real CrystallizationService.persist_outcome path.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

lancedb = pytest.importorskip("lancedb")

from nexus.core.capability_constraints import CapabilityConstraints  # noqa: E402
from nexus.engine.crystallization_service import CrystallizationService  # noqa: E402
from nexus.services.belief_constraint_producer import BeliefConstraintProducer  # noqa: E402
from nexus.services.mem_palace import MemPalace  # noqa: E402

SKILL = "skill_flaky"


class _StubModel:
    def __init__(self, *_args, **_kwargs):
        pass

    def encode(self, _text):
        return SimpleNamespace(tolist=lambda: [0.0] * 4)


@pytest.fixture(autouse=True)
def stub_embedder(monkeypatch):
    """Keep the legacy artifact archive (SoulPalaceEngine) off the real embedding model."""
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _StubModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)


def _service(root) -> CrystallizationService:
    return CrystallizationService(project_root=root, reporter=MagicMock())


def _outcome(passed: bool, skill: str = SKILL, n: int = 0) -> dict:
    return {
        "task_id": f"T-{n}",
        "decision_id": f"T-{n}",
        "skill_id": skill,
        "passed": passed,
        "metadata": {"task_type": "bugfix"},
    }


def _verdict(root) -> dict:
    palace = MemPalace(str(root))
    return CapabilityConstraints(str(root), mem_palace=palace).evaluate_constraints(
        SimpleNamespace(task_desc="regular coding task")
    )


def _rows(root) -> list:
    return (
        lancedb
        .connect(str(root / ".nexus" / "vector_db"))
        .open_table("nexus_soul_palace")
        .to_pandas()
        .to_dict("records")
    )


def test_n_consecutive_failures_forbid_skill_end_to_end(tmp_path):
    service = _service(tmp_path)
    for i in range(3):
        service.persist_outcome(_outcome(False, n=i))

    verdict = _verdict(tmp_path)
    assert verdict["constraints_source"] == "ok"
    assert len(verdict["forbidden_skills_rules"]) == 1
    assert SKILL in verdict["forbidden_skills_rules"][0]
    assert "bugfix" in verdict["forbidden_skills_rules"][0]
    assert service.last_constraint_write_status == "ok"


def test_fewer_than_n_failures_yield_no_constraint(tmp_path):
    service = _service(tmp_path)
    for i in range(2):
        service.persist_outcome(_outcome(False, n=i))

    verdict = _verdict(tmp_path)
    assert verdict["constraints_source"] == "ok"
    assert verdict["forbidden_skills_rules"] == []


def test_success_resets_streak_before_threshold(tmp_path):
    service = _service(tmp_path)
    for i, passed in enumerate([False, False, True, False, False]):
        service.persist_outcome(_outcome(passed, n=i))

    assert _verdict(tmp_path)["forbidden_skills_rules"] == []


def test_repeat_failures_do_not_duplicate_and_refresh_updated_at(tmp_path):
    clock = {"t": datetime(2026, 10, 1, tzinfo=timezone.utc)}
    producer = BeliefConstraintProducer(tmp_path, threshold=2, now=lambda: clock["t"])
    for i in range(2):
        producer.record_outcome(_outcome(False, n=i))
    first = [r for r in _rows(tmp_path) if r["type"] == "belief"]
    assert len(first) == 1

    clock["t"] += timedelta(days=3)
    producer.record_outcome(_outcome(False, n=9))
    beliefs = [r for r in _rows(tmp_path) if r["type"] == "belief"]
    assert len(beliefs) == 1
    assert beliefs[0]["id"] == first[0]["id"]
    assert beliefs[0]["updated_at"] == clock["t"].isoformat()
    assert beliefs[0]["updated_at"] != first[0]["updated_at"]


def test_success_lifts_constraint(tmp_path):
    service = _service(tmp_path)
    for i in range(3):
        service.persist_outcome(_outcome(False, n=i))
    assert len(_verdict(tmp_path)["forbidden_skills_rules"]) == 1

    service.persist_outcome(_outcome(True, n=10))
    verdict = _verdict(tmp_path)
    assert verdict["constraints_source"] == "ok"
    assert verdict["forbidden_skills_rules"] == []

    for i in range(3):
        service.persist_outcome(_outcome(False, n=20 + i))
    assert len(_verdict(tmp_path)["forbidden_skills_rules"]) == 1
    assert len([r for r in _rows(tmp_path) if r["type"] == "belief"]) == 1


def test_artifact_rows_are_not_read_as_beliefs(tmp_path):
    # Failed outcomes archive artifact rows even below the threshold.
    _service(tmp_path).persist_outcome(_outcome(False))
    assert any(r["type"] == "artifact" for r in _rows(tmp_path))

    palace = MemPalace(str(tmp_path))
    assert palace.list_beliefs(status="ALL") == []
    assert _verdict(tmp_path)["forbidden_skills_rules"] == []


def test_missing_embedding_dependency_still_writes_belief(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import -> ImportError
    service = _service(tmp_path)
    for i in range(3):
        service.persist_outcome(_outcome(False, n=i))

    assert service.last_constraint_write_status == "ok"
    assert len(_verdict(tmp_path)["forbidden_skills_rules"]) == 1


def test_write_failure_is_observable_and_never_raises(tmp_path, monkeypatch):
    store = MemPalace(str(tmp_path)).belief_store

    def _boom(_row):
        raise RuntimeError("disk full")

    producer = BeliefConstraintProducer(tmp_path, threshold=1, belief_store=store)
    monkeypatch.setattr(lancedb, "connect", lambda _p: _boom(None))
    producer.record_outcome(_outcome(False))

    assert producer.last_write_status == "unavailable"
    assert "disk full" in producer.last_write_error


def test_unreadable_store_reports_unavailable_not_silent_empty(tmp_path, monkeypatch):
    (tmp_path / ".nexus" / "vector_db").mkdir(parents=True)

    def _boom(_path):
        raise RuntimeError("db corrupted")

    monkeypatch.setattr(lancedb, "connect", _boom)
    verdict = _verdict(tmp_path)

    assert verdict["constraints_source"] == "unavailable"
    assert "db corrupted" in verdict["constraints_unavailable_reason"]
    assert verdict["forbidden_skills_rules"] == []


def test_single_task_retries_count_as_one_failure(tmp_path):
    """#2375: one task failing all 3 retries is streak 1, not a forbid belief."""
    producer = BeliefConstraintProducer(tmp_path)
    for _ in range(3):
        producer.record_outcome(_outcome(False, n=0))

    state = producer._load_state()
    assert [e["streak"] for e in state.values()] == [1]
    assert not any(e["active"] for e in state.values())
    assert not (tmp_path / ".nexus" / "vector_db").exists() or not [
        r for r in _rows(tmp_path) if r["type"] == "belief"
    ]


def test_distinct_tasks_still_forbid_and_streak_survives_restart(tmp_path):
    for i in range(3):
        # fresh producer each time: dedupe state must persist
        BeliefConstraintProducer(tmp_path).record_outcome(_outcome(False, n=i))
        BeliefConstraintProducer(tmp_path).record_outcome(_outcome(False, n=i))  # retry
    beliefs = [r for r in _rows(tmp_path) if r["type"] == "belief"]
    assert len(beliefs) == 1
    assert beliefs[0]["status"] == "active"


def test_retries_through_persist_outcome_do_not_forbid(tmp_path):
    service = _service(tmp_path)
    for _ in range(3):
        service.persist_outcome(_outcome(False, n=0))
    assert _verdict(tmp_path)["forbidden_skills_rules"] == []

    for i in (1, 2):
        service.persist_outcome(_outcome(False, n=i))
    assert len(_verdict(tmp_path)["forbidden_skills_rules"]) == 1


def test_missing_task_id_keeps_legacy_counting(tmp_path):
    producer = BeliefConstraintProducer(tmp_path)
    for _ in range(3):
        payload = _outcome(False, n=0)
        payload.pop("task_id")
        producer.record_outcome(payload)
    assert [e["streak"] for e in producer._load_state().values()] == [3]


def test_tracked_task_ids_are_bounded(tmp_path):
    producer = BeliefConstraintProducer(tmp_path, threshold=10**6)
    for i in range(80):
        producer.record_outcome(_outcome(False, n=i))
    entry = next(iter(producer._load_state().values()))
    assert entry["streak"] == 80
    assert len(entry["tasks"]) == 50
