from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n26", task_id="n26", phases=["R"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    assert r.telemetries["wall_time_ms"] > 0, f"{name}: wall_time_ms=0"


def _assert_fail_closed(
    name: str,
    error: str,
    *,
    status: str | None = "BLOCKED",
    invoked: bool = True,
) -> None:
    # Stub success was removed on purpose (99c8295ba, 13df4578d, 7ae787b81; #1850 archive):
    # the executor now fails closed and reports the specific reason below.
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked is invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed is False, f"{name}: gate_passed={r.gate_passed}"
    assert r.outcome.get("semantic_status") == status, f"{name}: {r.outcome}"
    assert r.outcome.get("error") == error, f"{name}: {r.outcome}"


def _assert_retired(name: str) -> None:
    # Executor-only key with no planner node, archived 2026-10-13 (ARCHIVED_2026-10-13.md, #1906):
    # the historical node id is kept and now asserts the key is unreachable.
    assert name not in EXECUTOR_REGISTRY, f"{name} must not be registered"


def test_exec_nightshift_runs() -> None:
    _assert_fail_closed("nightshift", "BLOCKED_EXTERNAL_AUTH:nightshift_model")


def test_exec_battle_swarm_runs() -> None:
    _assert_retired("battle_swarm")


def test_exec_sandbox_runner_runs() -> None:
    _assert_fail_closed("sandbox_runner", "SANDBOX_COMMAND_CONTEXT_REQUIRED")


def test_exec_dual_loop_runs() -> None:
    _assert_retired("dual_loop")


def test_exec_ultra_review_runs(tmp_path) -> None:
    # ultra_review reviews a real diff (2026-10-13): a git workspace with one benign change.
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    (tmp_path / "target.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_target.py").write_text(
        "from target import f\n\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
    )
    git("init", "-q")
    git("add", "target.py", "tests/test_target.py")
    git("commit", "-q", "-m", "base")
    (tmp_path / "target.py").write_text(
        "def f():\n    return 1\n\n\ndef g():\n    return f() + 1\n", encoding="utf-8"
    )
    fn = EXECUTOR_REGISTRY["ultra_review"]
    plan = CapabilityExecutionPlan(
        plan_id="test-n26",
        task_id="n26",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path)},
    )
    r = fn(plan, "test task")
    assert r.invoked
    assert r.telemetries["wall_time_ms"] > 0
    assert {"bandit", "ruff-security", "py_compile"} <= set(r.outcome["executed_checks"])
    from nexus.engine.ultra_review_service import os_sandbox_available

    if os_sandbox_available():
        assert r.gate_passed, r.outcome
        assert "tests/test_target.py" in r.outcome["executed_checks"]
    else:
        # PR tests run only behind an OS barrier; elsewhere they cannot run. Since #2738 (Refs #2732) the
        # review is record-only (advisory, never a completion gate): the missing barrier is
        # recorded as BLOCKED + review_error, and the receipt itself does not block.
        assert r.gate_passed is True
        assert r.outcome["advisory_only"] is True
        assert r.outcome["review_status"] == "BLOCKED"
        assert r.outcome["review_error"] == "ghost_regression_not_executed:no_os_barrier"


def test_exec_learning_closure_runs() -> None:
    _assert_fail_closed(
        "learning_closure", "archived_hollow_learning_closure_2026-10-12", invoked=False
    )


def test_exec_metabolism_resume_runs() -> None:
    _assert_fail_closed("metabolism_resume", "TOKEN_THRESHOLD_NOT_REACHED", status="SKIPPED")


def test_exec_promotion_engine_runs() -> None:
    _assert_retired("promotion_engine")


def test_exec_subagent_outcome_service_runs() -> None:
    _assert_retired("subagent_outcome_service")


def test_exec_attempt_settlement_service_runs() -> None:
    _assert_retired("attempt_settlement_service")
