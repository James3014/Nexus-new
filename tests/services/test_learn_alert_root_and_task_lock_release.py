"""Learn alerts land in the workspace root; task completion releases file locks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.app.learn_scheduler_service import LearnSchedulerService
from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.orchestrator.file_lock_registry import (
    FileLockRegistry,
    register_task_lock_file,
    release_task_locks,
)
from scripts.ops.learn_alert_dispatcher import dispatch_alert


def _plan(task_id: str, **constraints: object) -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id=f"p:{task_id}", task_id=task_id, phases=["R"], constraints=dict(constraints)
    )


def test_dispatch_alert_writes_under_given_root(tmp_path: Path, monkeypatch) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    ws = tmp_path / "ws"
    monkeypatch.chdir(cwd)
    path = dispatch_alert("DEGRADED", "low", {"x": 1}, root=ws)
    assert path.parent == (ws / ".nexus" / "reports" / "alerts").resolve()
    assert json.loads(path.read_text())["level"] == "DEGRADED"
    assert not (cwd / ".nexus").exists()


def test_scheduler_alert_goes_to_project_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(cwd)

    class _Res:
        returncode = 1
        stdout = ""
        stderr = "policy failed"

    monkeypatch.setattr("nexus.app.learn_scheduler_service.subprocess.run", lambda *a, **k: _Res())
    LearnSchedulerService(Path(cwd), project_root=project).run_scheduler()
    alerts = list((project / ".nexus" / "reports" / "alerts").glob("learn_*.json"))
    assert alerts, "alert must be written under the project (workspace) root"
    assert not (cwd / ".nexus" / "reports" / "alerts").exists()


def test_release_task_locks_frees_registry_for_next_task(tmp_path: Path) -> None:
    lock = EXECUTOR_REGISTRY["file_lock_security_gate"]
    ctx = {"workspace_root": str(tmp_path), "target_files": ["target.py"]}
    first = lock(_plan("rel-a", **ctx), "lock")
    assert first.gate_passed
    assert lock(_plan("rel-b", **ctx), "lock").gate_passed is False
    released = release_task_locks("rel-a")
    assert released == {first.outcome["lock_file"]: ["target.py"]}
    assert FileLockRegistry(lock_file=first.outcome["lock_file"]).holder("target.py") is None
    assert lock(_plan("rel-b", **ctx), "lock").gate_passed
    assert release_task_locks("rel-a") == {}  # idempotent, nothing remembered
    release_task_locks("rel-b")


def test_release_leaves_other_tasks_locks(tmp_path: Path) -> None:
    lock_file = tmp_path / "locks.json"
    reg = FileLockRegistry(lock_file=str(lock_file))
    reg.acquire("keep", ["a.py"])
    reg.acquire("drop", ["b.py"])
    register_task_lock_file("drop", str(lock_file))
    assert release_task_locks("drop") == {str(lock_file): ["b.py"]}
    assert FileLockRegistry(lock_file=str(lock_file)).locks == {"a.py": "keep"}


def test_run_mainchain_releases_task_locks_on_completion(tmp_path: Path, monkeypatch) -> None:
    from nexus_runtime.kernel.request import UnifiedRuntimeRequest

    from nexus.services import mainchain_entry

    lock = EXECUTOR_REGISTRY["file_lock_security_gate"]
    ctx = {"workspace_root": str(tmp_path), "target_files": ["target.py"]}
    seen: dict[str, object] = {}

    class _Runtime:
        def __init__(self, **_kw) -> None:
            pass

        def run(self, request, **_kw):
            receipt = lock(_plan(request.task_id, **ctx), "lock")
            seen["lock_file"] = receipt.outcome["lock_file"]
            seen["held"] = FileLockRegistry(lock_file=receipt.outcome["lock_file"]).holder(
                "target.py"
            )
            raise RuntimeError("task failed after locking")

    monkeypatch.setattr(mainchain_entry, "UnifiedRuntime", _Runtime)
    request = UnifiedRuntimeRequest(
        task_id="mainchain-lock-task",
        workspace_revision="rev",
        task_statement="lock target.py",
        task_type="code_change",
        route={},
        canonical_planning_bundle=object(),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="task failed after locking"):
        mainchain_entry.run_mainchain(request, online_invoker=lambda payload: {})
    assert seen["held"] == "mainchain-lock-task"
    assert FileLockRegistry(lock_file=str(seen["lock_file"])).holder("target.py") is None
