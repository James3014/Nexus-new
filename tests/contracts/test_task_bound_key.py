"""Contract tests for nexus.contracts.task_bound_key (#2454, law 2)."""

from __future__ import annotations

import pytest

from nexus.contracts import planner_snapshot_binding as psb
from nexus.contracts.task_bound_key import task_bound_key, task_identity

DIGEST = "sha256:" + "a" * 64


def test_key_is_task_and_digest() -> None:
    assert task_bound_key("task-1", DIGEST) == ("task-1", DIGEST)


@pytest.mark.parametrize(
    "task_id", [None, "", "   ", "\n\t", 0, 1, b"task-1", ["task-1"], object()]
)
def test_missing_or_malformed_task_fails_closed(task_id: object) -> None:
    assert task_identity(task_id) is None
    assert task_bound_key(task_id, DIGEST) is None


@pytest.mark.parametrize("digest", [None, "", "  ", 0, b"sha256:x", object()])
def test_missing_or_malformed_digest_fails_closed(digest: object) -> None:
    assert task_bound_key("task-1", digest) is None


def test_task_id_is_never_normalised() -> None:
    # distinct ids stay distinct keys: no strip, no case folding
    keys = {task_bound_key(t, DIGEST) for t in ("task-1", " task-1", "task-1 ", "TASK-1")}
    assert len(keys) == 4
    assert task_bound_key(" task-1 ", DIGEST) == (" task-1 ", DIGEST)


def test_same_digest_different_task_is_a_different_key() -> None:
    assert task_bound_key("task-1", DIGEST) != task_bound_key("task-2", DIGEST)


# --- adopter: planner_snapshot_binding (#2032 / #2050) goes through the helper


@pytest.fixture(autouse=True)
def _clean_bindings():
    psb.clear_planner_bindings()
    yield
    psb.clear_planner_bindings()


SNAPSHOT = {"route": "local_heal", "signals": {"x": 1}}


def test_planner_binding_is_task_bound() -> None:
    psb.register_planner_snapshot(SNAPSHOT, task_id="task-1")
    assert psb.is_planner_bound(SNAPSHOT, task_id="task-1")
    assert not psb.is_planner_bound(SNAPSHOT, task_id="task-2")  # cross-task replay
    assert not psb.is_planner_bound(SNAPSHOT, task_id=" task-1")


@pytest.mark.parametrize("task_id", ["", "  ", None])
def test_planner_binding_with_blank_task_binds_nothing(task_id: object) -> None:
    psb.register_planner_snapshot(SNAPSHOT, task_id=task_id)  # type: ignore[arg-type]
    assert not psb.is_planner_bound(SNAPSHOT, task_id=task_id)
    assert not psb._bound


def test_planner_binding_routes_through_task_bound_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, object]] = []

    def refuse(task_id: object, digest: object) -> None:
        calls.append((task_id, digest))
        return None

    monkeypatch.setattr(psb, "task_bound_key", refuse)
    psb.register_planner_snapshot(SNAPSHOT, task_id="task-1")
    assert not psb._bound  # the helper said no: nothing is bound
    assert not psb.is_planner_bound(SNAPSHOT, task_id="task-1")
    assert [c[0] for c in calls] == ["task-1", "task-1"]
    assert calls[0][1] == psb.planner_snapshot_digest(SNAPSHOT)
