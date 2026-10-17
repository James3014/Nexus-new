"""Characterization of the workspace inventory cluster of ``SelfHostedTaskService`` (split S2).

Big-file split step S2 moves the inventory methods out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  These tests pin the
behaviour before the move and must pass unchanged after it:

* every inventory method's result and error path (``_submission_task_states`` fail-closed
  blocker text, ``state_root_inventory`` authority classification, the
  ``apply_workspace_convergence`` drift / plan-hash / legacy-root refusals);
* the call order of the state lock and state reads (recording probes on the class).  The
  read surfaces take no lock and write nothing; ``workspace_slot_prepare`` goes through
  ``build_contract`` and ``WorktreeManager.prepare_reusable_slot``, and
  ``apply_workspace_convergence(apply=True)`` only reaches ``cleanup_tasks(dry_run=False)``
  for lifecycle-bound paths;
* that facade-module names the moved code reads (``WorktreeManager``, ``_jsonable``) are
  still resolved through the facade at call time, so patches on the facade keep taking
  effect.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

INVENTORY_MEMBERS = {
    "_workspace_task_states": "function",
    "_submission_task_states": "function",
    "find_tasks_by_repository_issue": "function",
    "workspace_inventory": "function",
    "state_root_inventory": "function",
    "workspace_convergence_plan": "function",
    "workspace_slot_status": "function",
    "workspace_slot_prepare": "function",
    "apply_workspace_convergence": "function",
}

IO_EVENTS = (
    "lock+",
    "lock-",
    "_state_path",
    "_read_state",
    "_read_state_snapshot",
    "_write_state_locked",
    "_mutate_state",
)


# ---------------------------------------------------------------------------
# helpers


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


def _seed(
    service: SelfHostedTaskService, task_id: str, *, status: str = "SUBMITTED", **extra: Any
) -> None:
    state: dict[str, Any] = {"task_id": task_id, "attempt_id": "attempt-1", "status": status}
    state.update(extra)
    service._write_state(task_id, state)


def _text(value: str) -> Any:
    """A str where the signature says int (the method stringifies its arguments)."""
    return value


def _disk_bytes(state_dir: Path) -> dict[str, str]:
    if not state_dir.exists():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(state_dir.glob("*.json"))
    }


class Recorder:
    """Class-level recording probes for the state lock, state I/O and collaborators."""

    FUNCTIONS = (
        "_state_path",
        "_read_state",
        "_read_state_snapshot",
        "_write_state_locked",
        "_mutate_state",
        "_workspace_task_states",
    )

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")
        events = self.events

        @contextmanager
        def state_lock(self: Any) -> Iterator[None]:
            events.append("lock+")
            with lock(self):
                yield
            events.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.FUNCTIONS:
            monkeypatch.setattr(cls, name, self._wrap(name, getattr(cls, name)))

    def _wrap(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(self_: Any, *args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(self_, *args, **kwargs)

        return wrapped

    def io(self) -> list[str]:
        return [event for event in self.events if event in IO_EVENTS]


@dataclass
class FakeInventory:
    controller_head: str = "head-1"
    paths: list[str] = field(default_factory=list)


@dataclass
class FakePlan:
    plan_hash: str = "plan-1"
    releasable_paths: list[str] = field(default_factory=list)
    note: str = "plan"


class FakeManager:
    """Stand-in for the facade's ``WorktreeManager``; records every call."""

    calls: list[tuple[str, Any]] = []
    inventory = FakeInventory()
    plan = FakePlan()

    def __init__(self, **kwargs: Any) -> None:
        type(self).calls.append(("__init__", kwargs))

    def get_workspace_inventory(self, **kwargs: Any) -> FakeInventory:
        type(self).calls.append(("get_workspace_inventory", kwargs))
        return type(self).inventory

    def plan_convergence(self, inventory: Any, **kwargs: Any) -> FakePlan:
        type(self).calls.append(("plan_convergence", (inventory, kwargs)))
        return type(self).plan

    def get_reusable_slot_status(self, **kwargs: Any) -> dict[str, Any]:
        type(self).calls.append(("get_reusable_slot_status", kwargs))
        return {"status": SimpleNamespace(ready=True), "slot": kwargs["slot_index"]}

    def prepare_reusable_slot(self, contract: Any, **kwargs: Any) -> dict[str, Any]:
        type(self).calls.append(("prepare_reusable_slot", (contract, kwargs)))
        return {"prepared": FakeInventory(controller_head="slot")}


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> type[FakeManager]:
    class Manager(FakeManager):
        calls: list[tuple[str, Any]] = []
        inventory = FakeInventory()
        plan = FakePlan()

    monkeypatch.setattr(service_module, "WorktreeManager", Manager)
    return Manager


# ---------------------------------------------------------------------------
# surface


def test_inventory_members_kinds_and_signatures() -> None:
    cls = SelfHostedTaskService
    kinds = {name: type(inspect.getattr_static(cls, name)).__name__ for name in INVENTORY_MEMBERS}
    assert kinds == INVENTORY_MEMBERS
    assert str(inspect.signature(cls.apply_workspace_convergence)) == (
        "(self, *, controller_root: 'Optional[str | Path]' = None, "
        "expected_controller_revision: 'str', expected_plan_hash: 'str', apply: 'bool' = False) "
        "-> 'dict[str, Any]'"
    )
    assert str(inspect.signature(cls.workspace_slot_prepare)) == (
        "(self, request: 'Mapping[str, Any]', *, campaign_id: 'str' = 'default', "
        "slot_index: 'int' = 0) -> 'dict[str, Any]'"
    )


# ---------------------------------------------------------------------------
# _workspace_task_states / _submission_task_states / find_tasks_by_repository_issue


def test_workspace_task_states_without_state_dir(tmp_path: Path) -> None:
    service = SelfHostedTaskService(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    if service.state_dir.exists():
        for path in service.state_dir.iterdir():
            if path.is_file():
                path.unlink()
        service.state_dir.rmdir()
    assert service._workspace_task_states() == {}
    assert service._submission_task_states() == {}
    assert service.find_tasks_by_repository_issue("r", 1) == []


def test_workspace_task_states_reads_snapshots_sorted_without_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    _seed(service, "b")
    _seed(service, "a", status="FINAL_BLOCK")
    (state_dir / "c.json").write_text("{bad", encoding="utf-8")
    (state_dir / "notes.txt").write_text("x", encoding="utf-8")
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    states = service._workspace_task_states()
    assert list(states) == ["a", "b", "c"]
    assert states["a"] == service._read_state_snapshot("a")
    assert states["c"]["state_valid"] is False
    assert recorder.io()[:3] == ["_read_state_snapshot"] * 3
    assert "lock+" not in recorder.events
    assert _disk_bytes(state_dir) == before


def test_workspace_task_states_skips_vanished_snapshots(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "a")
    _seed(service, "b")
    original = SelfHostedTaskService._read_state_snapshot
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_read_state_snapshot",
        lambda self, task_id: None if task_id == "a" else original(self, task_id),
    )
    assert list(service._workspace_task_states()) == ["b"]


def test_submission_task_states_returns_valid_states(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "a")
    _seed(service, "b", status="FINAL_BLOCK")
    recorder = Recorder(monkeypatch)
    states = service._submission_task_states()
    assert states == service._workspace_task_states()
    assert recorder.events[0] == "_workspace_task_states"
    assert "lock+" not in recorder.events


def test_submission_task_states_fails_closed_on_invalid_state(
    service: SelfHostedTaskService, state_dir: Path
) -> None:
    _seed(service, "a")
    (state_dir / "b.json").write_text("{bad", encoding="utf-8")
    (state_dir / "c.json").write_text("[]", encoding="utf-8")
    before = _disk_bytes(state_dir)
    with pytest.raises(RuntimeError) as caught:
        service._submission_task_states()
    assert str(caught.value) == (
        "INVALID_DURABLE_STATE_BLOCKS_SUBMISSION:b:STATE_JSON_INVALID,c:"
        + (service._read_state_snapshot("c") or {})["blocker"]["code"]
    )
    assert _disk_bytes(state_dir) == before


@pytest.mark.parametrize(
    ("invalid", "expected"),
    [
        ({"task_id": "x", "state_valid": False, "blocker": {"code": "C"}}, "x:C"),
        ({"task_id": "x", "state_valid": False}, "x:STATE_INVALID"),
        ({"task_id": "x", "state_valid": False, "blocker": None}, "x:STATE_INVALID"),
        ({"task_id": "x", "state_valid": False, "blocker": {}}, "x:STATE_INVALID"),
        ({"state_valid": False, "blocker": {"code": "C"}}, "unknown:C"),
        ({"task_id": "", "state_valid": False}, "unknown:STATE_INVALID"),
    ],
)
def test_submission_task_states_blocker_text(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, invalid: dict, expected: str
) -> None:
    states = {
        "ok": {"task_id": "ok"},
        "falsy": {"task_id": "f", "state_valid": None},
        "bad": invalid,
    }
    monkeypatch.setattr(SelfHostedTaskService, "_workspace_task_states", lambda self: states)
    with pytest.raises(RuntimeError) as caught:
        service._submission_task_states()
    assert str(caught.value) == f"INVALID_DURABLE_STATE_BLOCKS_SUBMISSION:{expected}"


def test_find_tasks_by_repository_issue(service: SelfHostedTaskService) -> None:
    _seed(service, "req", request={"repository": " James3014/Nexus-new ", "issue": " 7 "})
    _seed(service, "req-alias", request={"repository": "James3014/Nexus-new", "issue_number": 7})
    _seed(service, "state-level", repository="James3014/Nexus-new", issue="7")
    _seed(service, "other-issue", request={"repository": "James3014/Nexus-new", "issue": "8"})
    _seed(service, "other-repo", request={"repository": "x/y", "issue": "7"})
    _seed(service, "mixed", request={"repository": "James3014/Nexus-new"}, issue="7")
    matches = service.find_tasks_by_repository_issue(" James3014/Nexus-new ", 7)
    # sorted by state file name: "req-alias.json" < "req.json"
    assert [state["task_id"] for state in matches] == ["req-alias", "req", "state-level"]
    assert matches[1] == service._read_state_snapshot("req")
    assert (
        service.find_tasks_by_repository_issue("James3014/Nexus-new", _text("8"))[0]["task_id"]
        == "other-issue"
    )
    assert service.find_tasks_by_repository_issue("nope", 7) == []


def test_find_tasks_by_repository_issue_non_mapping_request(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = {
        "a": {"task_id": "a", "request": "r#1", "repository": "r", "issue": 1},
        "b": {"task_id": "b", "request": ["r", "1"]},
        "c": {"task_id": "c", "request": None, "repository": " r ", "issue": " 1 "},
    }
    monkeypatch.setattr(SelfHostedTaskService, "_workspace_task_states", lambda self: states)
    assert [s["task_id"] for s in service.find_tasks_by_repository_issue("r", 1)] == ["a", "c"]


def test_find_tasks_by_repository_issue_request_issue_wins_over_alias(
    service: SelfHostedTaskService,
) -> None:
    _seed(service, "t", request={"repository": "r", "issue": "1", "issue_number": "2"})
    assert [s["task_id"] for s in service.find_tasks_by_repository_issue("r", 1)] == ["t"]
    assert service.find_tasks_by_repository_issue("r", 2) == []


def test_find_tasks_reads_through_workspace_task_states(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "t", request={"repository": "r", "issue": "1"})
    recorder = Recorder(monkeypatch)
    service.find_tasks_by_repository_issue("r", 1)
    assert recorder.events[0] == "_workspace_task_states"
    assert "lock+" not in recorder.events


# ---------------------------------------------------------------------------
# workspace_inventory / workspace_convergence_plan / workspace_slot_status


def test_workspace_inventory_uses_facade_manager(
    service: SelfHostedTaskService, manager: type[FakeManager], tmp_path: Path
) -> None:
    _seed(service, "t")
    root = tmp_path / "controller"
    root.mkdir()
    result = service.workspace_inventory(controller_root=str(root))
    assert result == {"controller_head": "head-1", "paths": []}
    resolved = root.resolve()
    assert manager.calls == [
        (
            "__init__",
            {"root_dir": str(resolved.parent / "nexus-runtime-targets"), "create_root": False},
        ),
        (
            "get_workspace_inventory",
            {"controller_root": resolved, "task_states": service._workspace_task_states()},
        ),
    ]


def test_workspace_inventory_defaults_to_cwd(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    service.workspace_inventory()
    assert manager.calls[1][1]["controller_root"] == cwd.resolve()
    assert manager.calls[0][1]["root_dir"] == str(cwd.resolve().parent / "nexus-runtime-targets")


def test_workspace_inventory_reads_jsonable_through_the_facade(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module, "_jsonable", lambda value: seen.append(value) or {"patched": True}
    )
    assert service.workspace_inventory(controller_root=tmp_path) == {"patched": True}
    assert seen == [manager.inventory]
    assert service.workspace_convergence_plan(controller_root=tmp_path) == {"patched": True}
    assert service.workspace_slot_status(controller_root=tmp_path) == {"patched": True}


def test_workspace_inventory_is_read_only(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    state_dir: Path,
    tmp_path: Path,
) -> None:
    _seed(service, "t")
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    service.workspace_inventory(controller_root=tmp_path)
    service.workspace_convergence_plan(controller_root=tmp_path)
    service.workspace_slot_status(controller_root=tmp_path)
    assert recorder.events == [
        "_workspace_task_states",
        "_read_state_snapshot",
        "_workspace_task_states",
        "_read_state_snapshot",
        "_workspace_task_states",
        "_read_state_snapshot",
    ]
    assert _disk_bytes(state_dir) == before


def test_workspace_convergence_plan_defaults_expected_to_inventory_head(
    service: SelfHostedTaskService, manager: type[FakeManager], tmp_path: Path
) -> None:
    result = service.workspace_convergence_plan(controller_root=tmp_path)
    assert result == {"plan_hash": "plan-1", "releasable_paths": [], "note": "plan"}
    names = [name for name, _ in manager.calls]
    assert names == ["__init__", "get_workspace_inventory", "plan_convergence"]
    assert manager.calls[2][1] == (manager.inventory, {"expected_controller_revision": "head-1"})
    manager.calls.clear()
    service.workspace_convergence_plan(
        controller_root=tmp_path, expected_controller_revision="pinned"
    )
    assert manager.calls[2][1] == (manager.inventory, {"expected_controller_revision": "pinned"})
    manager.calls.clear()
    service.workspace_convergence_plan(controller_root=tmp_path, expected_controller_revision="")
    assert manager.calls[2][1] == (manager.inventory, {"expected_controller_revision": "head-1"})


def test_workspace_slot_status(
    service: SelfHostedTaskService, manager: type[FakeManager], tmp_path: Path
) -> None:
    _seed(service, "t")
    result = service.workspace_slot_status(controller_root=tmp_path)
    assert result == {"status": {"ready": True}, "slot": 0}
    resolved = tmp_path.resolve()
    assert manager.calls == [
        (
            "__init__",
            {"root_dir": str(resolved.parent / "nexus-runtime-targets"), "create_root": False},
        ),
        (
            "get_reusable_slot_status",
            {
                "campaign_id": "default",
                "slot_index": 0,
                "controller_root": resolved,
                "task_states": service._workspace_task_states(),
            },
        ),
    ]
    manager.calls.clear()
    service.workspace_slot_status(campaign_id="c", slot_index=3, controller_root=tmp_path)
    assert manager.calls[1][1]["campaign_id"] == "c"
    assert manager.calls[1][1]["slot_index"] == 3


# ---------------------------------------------------------------------------
# workspace_slot_prepare


def test_workspace_slot_prepare_builds_contract_then_prepares(
    service: SelfHostedTaskService, manager: type[FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "t")
    order: list[str] = []
    contract = SimpleNamespace(target_worktree_root="/targets")

    def build_contract(self: Any, request: Any) -> Any:
        order.append("build_contract")
        assert request == {"task_id": "new"}
        return contract

    monkeypatch.setattr(SelfHostedTaskService, "build_contract", build_contract)
    recorder = Recorder(monkeypatch)
    result = service.workspace_slot_prepare({"task_id": "new"}, campaign_id="camp", slot_index=2)
    assert result == {"prepared": {"controller_head": "slot", "paths": []}}
    assert order == ["build_contract"]
    assert recorder.events == ["_workspace_task_states", "_read_state_snapshot"]
    states = service._workspace_task_states()
    assert manager.calls == [
        ("__init__", {"root_dir": "/targets"}),
        (
            "prepare_reusable_slot",
            (contract, {"campaign_id": "camp", "slot_index": 2, "task_states": states}),
        ),
    ]


def test_workspace_slot_prepare_contract_failure_stops_before_manager(
    service: SelfHostedTaskService, manager: type[FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    def build_contract(self: Any, request: Any) -> Any:
        raise ValueError("bad contract")

    monkeypatch.setattr(SelfHostedTaskService, "build_contract", build_contract)
    recorder = Recorder(monkeypatch)
    with pytest.raises(ValueError, match="bad contract"):
        service.workspace_slot_prepare({})
    assert manager.calls == []
    assert recorder.events == []


# ---------------------------------------------------------------------------
# apply_workspace_convergence


def test_apply_convergence_controller_drift(
    service: SelfHostedTaskService, manager: type[FakeManager], tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError) as caught:
        service.apply_workspace_convergence(
            controller_root=tmp_path,
            expected_controller_revision="other",
            expected_plan_hash="plan-1",
        )
    assert str(caught.value) == (
        "CONTROLLER_REVISION_DRIFT: current controller head-1 does not match expected other"
    )
    assert [name for name, _ in manager.calls] == ["__init__", "get_workspace_inventory"]
    resolved = tmp_path.resolve()
    assert manager.calls[0][1] == {
        "root_dir": str(resolved.parent / "nexus-runtime-targets"),
        "create_root": False,
    }
    assert manager.calls[1][1] == {"controller_root": resolved, "task_states": {}}


def test_apply_convergence_plan_hash_mismatch(
    service: SelfHostedTaskService, manager: type[FakeManager], tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError) as caught:
        service.apply_workspace_convergence(
            controller_root=tmp_path,
            expected_controller_revision="head-1",
            expected_plan_hash="stale",
        )
    assert (
        str(caught.value) == "PLAN_HASH_MISMATCH: current plan plan-1 does not match expected stale"
    )
    assert manager.calls[2][1] == (manager.inventory, {"expected_controller_revision": "head-1"})


def test_apply_convergence_dry_run_never_cleans(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    state_dir: Path,
) -> None:
    _seed(service, "t", lease={"target_worktree": str(tmp_path / "w")})
    manager.plan = FakePlan(releasable_paths=[str(tmp_path / "w")])
    monkeypatch.setattr(
        SelfHostedTaskService,
        "cleanup_tasks",
        lambda *a, **k: pytest.fail("dry run must not clean"),
    )
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    result = service.apply_workspace_convergence(
        controller_root=tmp_path, expected_controller_revision="head-1", expected_plan_hash="plan-1"
    )
    assert result == {
        "plan_hash": "plan-1",
        "releasable_paths": [str(tmp_path / "w")],
        "note": "plan",
        "applied": False,
        "next_gate": "EXPLICIT_APPLY",
    }
    assert recorder.events == ["_workspace_task_states", "_read_state_snapshot"]
    assert _disk_bytes(state_dir) == before


def test_apply_convergence_apply_cleans_only_bound_paths(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bound = tmp_path / "bound"
    bound.mkdir()
    _seed(service, "owner", lease={"target_worktree": str(bound)})
    _seed(service, "no-lease")
    _seed(service, "empty-lease", lease={"target_worktree": ""})
    manager.plan = FakePlan(releasable_paths=[str(tmp_path / "unbound"), str(bound / ".")])
    cleanups: list[dict[str, Any]] = []

    def cleanup_tasks(self: Any, **kwargs: Any) -> dict[str, Any]:
        cleanups.append(kwargs)
        return {"decisions": [{"task_id": kwargs["task_id"], "cleanup_performed": True}]}

    monkeypatch.setattr(SelfHostedTaskService, "cleanup_tasks", cleanup_tasks)
    result = service.apply_workspace_convergence(
        controller_root=tmp_path,
        expected_controller_revision="head-1",
        expected_plan_hash="plan-1",
        apply=True,
    )
    assert cleanups == [{"task_id": "owner", "dry_run": False}]
    assert result == {
        "plan_hash": "plan-1",
        "releasable_paths": [str(tmp_path / "unbound"), str(bound / ".")],
        "note": "plan",
        "applied": True,
        "decisions": [
            {
                "path": str(tmp_path / "unbound"),
                "cleanup_decision": "BLOCKED_UNBOUND_WORKSPACE",
                "cleanup_blocker": "no lifecycle task contract owns this worktree",
                "cleanup_performed": False,
            },
            {"task_id": "owner", "cleanup_performed": True},
        ],
        "next_gate": "OWNER_REVIEW",
    }


def test_apply_convergence_cleanup_without_decisions(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(service, "owner", lease={"target_worktree": str(tmp_path / "b")})
    manager.plan = FakePlan(releasable_paths=[str(tmp_path / "b")])
    monkeypatch.setattr(SelfHostedTaskService, "cleanup_tasks", lambda self, **kwargs: {})
    result = service.apply_workspace_convergence(
        controller_root=tmp_path,
        expected_controller_revision="head-1",
        expected_plan_hash="plan-1",
        apply=True,
    )
    assert result["decisions"] == []


def test_apply_convergence_refuses_legacy_root_before_cleanup(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(service, "owner", lease={"target_worktree": str(tmp_path / "b")})
    manager.plan = FakePlan(
        releasable_paths=[str(tmp_path / "b"), "/Users/jameschen/Workspace/nexus"]
    )
    cleanups: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService, "cleanup_tasks", lambda self, **kwargs: cleanups.append(kwargs) or {}
    )
    with pytest.raises(RuntimeError) as caught:
        service.apply_workspace_convergence(
            controller_root=tmp_path,
            expected_controller_revision="head-1",
            expected_plan_hash="plan-1",
            apply=True,
        )
    assert str(caught.value) == "LEGACY_ROOT_APPLY_FORBIDDEN: legacy root cannot be released"
    assert cleanups == [{"task_id": "owner", "dry_run": False}]


def test_apply_convergence_reads_jsonable_through_the_facade(
    service: SelfHostedTaskService,
    manager: type[FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        service_module, "_jsonable", lambda value: {"patched": type(value).__name__}
    )
    dry = service.apply_workspace_convergence(
        controller_root=tmp_path, expected_controller_revision="head-1", expected_plan_hash="plan-1"
    )
    assert dry == {"patched": "FakePlan", "applied": False, "next_gate": "EXPLICIT_APPLY"}


# ---------------------------------------------------------------------------
# state_root_inventory


def _write(path: Path, payload: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_state_root_inventory_missing_root(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = tmp_path / "no-root"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    empty_sha = hashlib.sha256(b"[]").hexdigest()
    assert service.state_root_inventory() == {
        "schema": "nexus.lifecycle_state_root_inventory.v1",
        "canonical_state_root": str(canonical.resolve()),
        "entry_count": 0,
        "task_count": 0,
        "conflict_task_ids": [],
        "authority_conflict": False,
        "evidence_duplicate_task_ids": [],
        "entries": [],
        "inventory_sha256": empty_sha,
    }


def test_state_root_inventory_classifies_and_hashes(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = (tmp_path / "canon").resolve()
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    full = {
        "task_id": "a",
        "attempt_id": "at",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "candidate_commit_sha": "c",
        "candidate_ref": "r",
        "updated_at": "u",
        "extra": "ignored",
    }
    raw_a = _write(canonical / "a.json", full)
    raw_arch = _write(canonical / "nexus-state-archive" / "2026" / "a.json", {"task_id": "a"})
    raw_reh = _write(canonical / "rehearsal" / "b.json", {"task_id": "b"})
    raw_dup1 = _write(canonical / "d.json", {"task_id": "dup"})
    raw_dup2 = _write(canonical / "e.json", {"task_id": "dup"})
    _write(canonical / "manifest-1.json", {"task_id": "m"})
    _write(canonical / "list.json", ["task_id"])
    _write(canonical / "no-id.json", {"status": "x"})
    _write(canonical / "empty-id.json", {"task_id": ""})
    (canonical / "bad.json").write_text("{bad", encoding="utf-8")
    result = service.state_root_inventory()
    entries = result["entries"]
    assert [
        (Path(e["path"]).relative_to(canonical).as_posix(), e["authority"]) for e in entries
    ] == [
        ("a.json", "CANONICAL_AUTHORITY"),
        ("d.json", "CANONICAL_AUTHORITY"),
        ("e.json", "CANONICAL_AUTHORITY"),
        ("nexus-state-archive/2026/a.json", "ARCHIVE_EVIDENCE"),
        ("rehearsal/b.json", "REHEARSAL_EVIDENCE"),
    ]
    assert entries[0] == {
        "path": str(canonical / "a.json"),
        "authority": "CANONICAL_AUTHORITY",
        "task_id": "a",
        "attempt_id": "at",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "candidate_commit_sha": "c",
        "candidate_ref": "r",
        "state_sha256": hashlib.sha256(raw_a).hexdigest(),
        "updated_at": "u",
    }
    assert [e["state_sha256"] for e in entries[1:]] == [
        hashlib.sha256(raw).hexdigest() for raw in (raw_dup1, raw_dup2, raw_arch, raw_reh)
    ]
    assert result["entry_count"] == 5
    assert result["task_count"] == 3
    assert result["conflict_task_ids"] == ["dup"]
    assert result["authority_conflict"] is True
    assert result["evidence_duplicate_task_ids"] == ["a"]
    assert result["canonical_state_root"] == str(canonical)
    assert (
        result["inventory_sha256"]
        == hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    assert list(result) == [
        "schema",
        "canonical_state_root",
        "entry_count",
        "task_count",
        "conflict_task_ids",
        "authority_conflict",
        "evidence_duplicate_task_ids",
        "entries",
        "inventory_sha256",
    ]


def test_state_root_inventory_unreadable_file_is_skipped(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = (tmp_path / "canon").resolve()
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    _write(canonical / "a.json", {"task_id": "a"})
    _write(canonical / "b.json", {"task_id": "b"})
    real = Path.read_bytes

    def read_bytes(self: Path) -> bytes:
        if self.name == "a.json":
            raise OSError("gone")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    result = service.state_root_inventory()
    assert [e["task_id"] for e in result["entries"]] == ["b"]
    assert result["authority_conflict"] is False


def test_state_root_inventory_is_read_only_and_uses_canonical_state_dir(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = (tmp_path / "canon").resolve()
    _write(canonical / "a.json", {"task_id": "a"})
    calls: list[str] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "canonical_state_dir",
        staticmethod(lambda: calls.append("canonical_state_dir") or canonical),
    )
    before = {p.name: p.read_bytes() for p in canonical.rglob("*.json")}
    recorder = Recorder(monkeypatch)
    result = service.state_root_inventory()
    assert calls == ["canonical_state_dir"]
    assert result["entry_count"] == 1
    assert recorder.events == []
    assert {p.name: p.read_bytes() for p in canonical.rglob("*.json")} == before
