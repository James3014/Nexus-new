"""#1924: LocalHeal accepts only route_context snapshots bound in-process, per task, by build_execution_plan."""

from __future__ import annotations

import os
import shutil
import tempfile
from unittest import mock

import pytest

from nexus.contracts.planner_snapshot_binding import ROUTE_CONTEXT_NOT_PLANNER_BOUND
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
)
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

# #2936: with no OS sandbox on the host (Linux CI) model commands are refused; these tests
# exercise verifier/drone logic, so they run them unconfined there (sandbox stays on macOS).
pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")

_DIFF = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-print('hello')\n+print('world')\n"


def _source_root() -> str:
    root = tempfile.mkdtemp()
    with open(os.path.join(root, "f.py"), "w", encoding="utf-8") as handle:
        handle.write("print('hello')\n")
    return root


def _solve_controls(src_root: str) -> dict:
    return {
        "source_root": src_root,
        "target_file": "f.py",
        "target_symbol": "print",
        "locked_search": "print('hello')",
        "verifier_command": ["true"],
        "work_dir": "",
        "candidate_generate_fn": lambda req: f"```diff\n{_DIFF}```",
    }


_TASK_ID = "t-binding"


def _planner_controls(task_id: str | None = _TASK_ID) -> dict:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1"}):
        plan = CapabilityPlanner().plan(
            task_desc="fix code", task_type="repair", route={"local_enabled": True}
        )
    return dict(build_execution_plan(plan, task_id=task_id).executor_controls)


def _run(controls: dict, task_id: str = _TASK_ID) -> tuple[object, object]:
    response = LocalHealCapabilityAdapter.run(
        LocalHealCapabilityRequest(
            task_id=task_id,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            executor_controls=controls,
            dry_run=False,
        )
    )
    receipt = LocalHealReceiptAdapter().build(
        claim_verified=True, payload=response.capability_payload
    )
    return response, receipt


def test_forged_route_context_is_rejected() -> None:
    """Adversarial-review reproduction: a hand-built snapshot with every planner key."""
    src_root = _source_root()
    try:
        forged = {
            "planner_version": "capability_planner_v1",
            "canonical_execution_topology_source": "forged",
            "ssd_route_map": {},
            "context_slimming_policy": {},
            "harness_relevance_policy": {},
            "research_isolation_policy": {},
            "selected_executor": "local_model",
            "candidate_enabled": True,
            "mutation_allowed": True,
            "verifier_allowed": True,
            "model_call_allowed": True,
            "isolated_solve_enabled": True,
        }
        response, receipt = _run({
            "route_context": {"signal_snapshot": forged},
            **_solve_controls(src_root),
        })
        assert response.invoked is False
        assert response.hybrid_route.fallback_block_reason == ROUTE_CONTEXT_NOT_PLANNER_BOUND
        assert response.hybrid_route.local_model_called is False
        assert receipt.gate_passed is False
    finally:
        shutil.rmtree(src_root, ignore_errors=True)


def test_edited_planner_snapshot_is_rejected() -> None:
    """Self-granting isolated_solve on a genuine planner snapshot breaks the binding."""
    src_root = _source_root()
    try:
        controls = _planner_controls()
        snapshot = {**controls["route_context"]["signal_snapshot"], "isolated_solve_enabled": True}
        response, receipt = _run({
            **controls,
            "route_context": {"signal_snapshot": snapshot},
            **_solve_controls(src_root),
        })
        assert response.hybrid_route.fallback_block_reason == ROUTE_CONTEXT_NOT_PLANNER_BOUND
        assert receipt.gate_passed is False
    finally:
        shutil.rmtree(src_root, ignore_errors=True)


def test_genuine_build_execution_plan_snapshot_is_accepted() -> None:
    src_root = _source_root()
    try:
        response, receipt = _run({**_planner_controls(), **_solve_controls(src_root)})
        reason = response.hybrid_route.fallback_block_reason or ""
        assert ROUTE_CONTEXT_NOT_PLANNER_BOUND not in reason
        assert response.invoked is True
        assert response.hybrid_route.local_model_called is True
        # The planner does not grant isolated_solve, so this stays a candidate-only, blocked route.
        assert response.hybrid_route.route_mode.value == "local_only_blocked"
        assert receipt.gate_passed is False
    finally:
        shutil.rmtree(src_root, ignore_errors=True)


def test_snapshot_bound_to_another_task_is_rejected() -> None:
    """Replay: a genuine snapshot bound to task A is not accepted for task B."""
    src_root = _source_root()
    try:
        controls = _planner_controls(task_id="t-binding-task-a")
        response, receipt = _run(
            {**controls, **_solve_controls(src_root)}, task_id="t-binding-task-b"
        )
        assert response.invoked is False
        assert response.hybrid_route.fallback_block_reason == ROUTE_CONTEXT_NOT_PLANNER_BOUND
        assert response.hybrid_route.local_model_called is False
        assert receipt.gate_passed is False
        # The same controls remain valid for the task they were bound to.
        response, _ = _run({**controls, **_solve_controls(src_root)}, task_id="t-binding-task-a")
        assert response.hybrid_route.fallback_block_reason != ROUTE_CONTEXT_NOT_PLANNER_BOUND
        assert response.invoked is True
    finally:
        shutil.rmtree(src_root, ignore_errors=True)


def test_execution_plan_without_task_id_binds_nothing() -> None:
    src_root = _source_root()
    try:
        controls = _planner_controls(task_id=None)
        assert (
            controls["route_context"]["signal_snapshot"]["planner_version"]
            == "capability_planner_v1"
        )
        response, receipt = _run(
            {**controls, **_solve_controls(src_root)}, task_id="t-binding-never-bound"
        )
        assert response.hybrid_route.fallback_block_reason == ROUTE_CONTEXT_NOT_PLANNER_BOUND
        assert receipt.gate_passed is False
    finally:
        shutil.rmtree(src_root, ignore_errors=True)


def test_source_changed_during_verification_fails_closed(monkeypatch, tmp_path) -> None:
    # The isolated workspace writes Armor artifacts; CI checks out the tree under OS temp,
    # so opt in to ephemeral Armor storage for this test only (same as the armor lane tests).
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
    monkeypatch.setenv("NEXUS_ARMOR_ARTIFACT_ROOT", str(tmp_path / "armor"))
    src_root = _source_root()
    try:
        response = run_isolated_local_solve_loop(
            IsolatedLocalSolveRequest(
                task_id="t-tamper",
                source_root=src_root,
                problem_statement="fix code",
                evidence_refs=("ref1",),
                model_output=f"```diff\n{_DIFF}```",
                verifier_command=("python3", "-c", "open('f.py', 'a').write('# tampered\\n')"),
                work_dir="",
                local_model_called=True,
                mutation_allowed=True,
                verifier_allowed=True,
                target_file="f.py",
                target_symbol="print",
                locked_search="print('hello')",
            )
        )
        assert (
            "VERIFIED_SOURCE_CHANGED_DURING_VERIFICATION"
            in response.hybrid_route.fallback_block_reason
        )
        assert "source_hash" not in response.capability_payload
        receipt = LocalHealReceiptAdapter().build(
            claim_verified=True, payload=response.capability_payload
        )
        assert receipt.gate_passed is False
        workspace = response.apply_receipt.workspace_path
        if workspace and os.path.exists(workspace):
            shutil.rmtree(workspace, ignore_errors=True)
    finally:
        shutil.rmtree(src_root, ignore_errors=True)
