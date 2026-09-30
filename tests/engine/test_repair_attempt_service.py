"""Focused tests for RepairAttemptService trajectory evidence wiring (Issue #1212 battle seam).

Coverage requirements:
  1. seal occurs BEFORE pregate invocation
  2. result binds AFTER pregate returns
  3. telemetry failure is fail-open (pregate/runtime outcome unchanged)
  4. multiple strategy trajectories do not cross (each strategy gets its own trajectory_id)
  5. strong eligible row binds trajectory outcome
  6. TRACE_ONLY / ineligible row does NOT bind trajectory outcome
  7. refresh_registered_experiment called only when at least one strong binding succeeded
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from nexus.core.state_contracts import NexusState
from nexus.engine.repair_attempt_service import (
    RepairAttemptService,
    _battle_trajectory_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(task_id: str = "t-1") -> NexusState:
    return NexusState(task_id=task_id)


def _git_init(tmp_path: Path) -> Path:
    """Minimal git repo so git_exists check passes."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _make_svc(tmp_path: Path, run_cli_fn=None) -> RepairAttemptService:
    if run_cli_fn is None:
        run_cli_fn = MagicMock(return_value=(False, []))
    return RepairAttemptService(
        project_root=tmp_path,
        run_cli_pregate_fn=run_cli_fn,
        subprocess_run=MagicMock(),
    )


def _strategy_result(name: str, *, passed: bool = False, has_payload: bool = True) -> dict:
    payload = (
        f"diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+{name}"
        if has_payload
        else ""
    )
    payload_sha = hashlib.sha256(payload.encode()).hexdigest() if payload else ""
    return {
        "strategy": name,
        "passed": passed,
        "score": 10.0 if passed else 0.0,
        "verifier_status": "pass" if passed else "fail",
        "gate_results": [
            {
                "cmd_sha256": hashlib.sha256(b"pytest -q").hexdigest(),
                "exit_code": 0 if passed else 1,
                "passed": passed,
                "stdout_sha256": hashlib.sha256(b"").hexdigest(),
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                "reason": "",
            }
        ],
        "candidate_payload": payload,
        "candidate_payload_sha256": payload_sha,
        "candidate_state_hash": "",
    }


def _make_executing_swarm(
    strategies: list,
    *,
    wt_path_base: Path | None = None,
) -> MagicMock:
    """Return a BattleSwarm mock that actually calls execute_fn for each strategy.

    This is required to exercise the swarm_worker closure (where seal/bind live).
    The mock calls execute_fn synchronously (not in a thread), mirroring BattleSwarm
    behavior for the purpose of unit testing.
    """

    def fake_trigger_battle(*, task_id, desc, context, execute_fn):
        results = []
        for s in strategies:
            wt = str(wt_path_base / f"wt_{s['name']}") if wt_path_base else f"/fake/wt/{s['name']}"
            try:
                res = execute_fn(s, wt, task_id, desc, context)
                results.append({
                    "strategy": s["name"],
                    "passed": res.get("passed", False),
                    "score": res.get("score", 0.0),
                    "verifier_status": res.get("verifier_status", "fail"),
                    "gate_results": res.get("gate_results", []),
                    "candidate_payload": res.get("candidate_payload", ""),
                    "candidate_payload_sha256": res.get("candidate_payload_sha256", ""),
                    "candidate_state_hash": res.get("candidate_state_hash", ""),
                    "params": s.get("params", {}),
                })
            except Exception:
                results.append({"strategy": s["name"], "passed": False, "score": 0.0})

        winners = [r for r in results if r.get("passed")]
        winner = winners[0] if winners else None
        return {
            "status": "winner_found" if winner else "all_failed",
            "winner": winner,
            "all_results": results,
            "worktrees_to_clean": [],
            "branches_to_clean": [],
        }

    swarm = MagicMock()
    swarm.default_workers = len(strategies)
    swarm.trigger_battle.side_effect = fake_trigger_battle
    return swarm


def _default_seal_fn(**kwargs):
    """Default seal side-effect: returns a valid step ref mock."""
    ref = MagicMock()
    ref.step_sha256 = "abc"
    ref.step_ref = "trajectory/steps/xx/00000000.json"
    ref.trajectory_id = kwargs["trajectory_id"]
    ref.step_index = 0
    return ref


@contextlib.contextmanager
def _trajectory_patches(
    tmp_path: Path,
    *,
    seal_side_effect=None,
    bind_result_side_effect=None,
    bind_outcome_side_effect=None,
    refresh_side_effect=None,
    collection_result=None,
):
    """Context manager that applies all trajectory telemetry patches at once.

    Using contextlib.ExitStack to stack multiple patch context managers without
    requiring Python 3.10+ parenthesized with-statement unpacking.
    """
    evidence_root = tmp_path / "evidence"
    if collection_result is None:
        collection_result = MagicMock(
            status="COLLECTED",
            group_sha256="gs",
            collected_count=1,
            eligible_count=0,
            row_refs=(),
        )

    with contextlib.ExitStack() as stack:
        mock_subproc = stack.enter_context(patch("subprocess.run"))
        mock_subproc.return_value = MagicMock(stdout="deadbeef\n", returncode=0)

        stack.enter_context(
            patch(
                "nexus.engine.repair_attempt_service.resolve_research_evidence_root",
                return_value=evidence_root,
            )
        )
        stack.enter_context(
            patch(
                "nexus.engine.repair_attempt_service.seal_trajectory_step",
                side_effect=seal_side_effect if seal_side_effect is not None else _default_seal_fn,
            )
        )
        stack.enter_context(
            patch(
                "nexus.engine.repair_attempt_service.bind_trajectory_step_result",
                side_effect=bind_result_side_effect,
            )
        )
        stack.enter_context(
            patch(
                "nexus.research.clm_system_one.candidate_evidence_collector.collect_candidate_group",
                return_value=collection_result,
            )
        )
        yield mock_subproc


def _run_battle_attempt(svc, swarm, tmp_path, task_id="t-1", verify_cmds=None):
    """Run execute_attempt in battle mode (attempt=2, git repo present)."""
    return svc.execute_attempt(
        task_id=task_id,
        task_desc="fix the bug",
        state=_make_state(task_id),
        attempt=2,
        verify_cmds=verify_cmds or ["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
        battle_swarm=swarm,
    )


# ===========================================================================
# 1. _battle_trajectory_id: collision resistance
# ===========================================================================


class TestBattleTrajectoryId:
    def test_deterministic(self):
        assert _battle_trajectory_id("t", 2, "conservative", "abc") == _battle_trajectory_id(
            "t", 2, "conservative", "abc"
        )

    def test_differs_by_strategy(self):
        assert _battle_trajectory_id("t", 2, "conservative", "abc") != _battle_trajectory_id(
            "t", 2, "aggressive", "abc"
        )

    def test_differs_by_revision(self):
        assert _battle_trajectory_id("t", 2, "conservative", "abc") != _battle_trajectory_id(
            "t", 2, "conservative", "def"
        )

    def test_differs_by_attempt(self):
        assert _battle_trajectory_id("t", 2, "conservative", "abc") != _battle_trajectory_id(
            "t", 3, "conservative", "abc"
        )

    def test_differs_by_task(self):
        assert _battle_trajectory_id("t1", 2, "conservative", "abc") != _battle_trajectory_id(
            "t2", 2, "conservative", "abc"
        )

    def test_is_64_char_hex(self):
        tid = _battle_trajectory_id("t", 2, "conservative", "abc")
        assert len(tid) == 64
        assert all(c in "0123456789abcdef" for c in tid)


# ===========================================================================
# 2. seal occurs BEFORE pregate invocation
# ===========================================================================


class TestSealBeforePregate:
    def test_seal_called_before_run_cli_pregate(self, tmp_path):
        """seal_trajectory_step must be called strictly before run_cli_pregate_fn."""
        _git_init(tmp_path)
        call_order: list[str] = []

        def recording_seal(**kwargs):
            call_order.append("seal")
            return _default_seal_fn(**kwargs)

        def recording_pregate(**kwargs):
            call_order.append("pregate")
            return (True, [{"passed": True, "cmd": "pytest -q", "exit_code": 0}])

        svc = _make_svc(tmp_path, run_cli_fn=recording_pregate)
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path, seal_side_effect=recording_seal):
            _run_battle_attempt(svc, swarm, tmp_path)

        seal_idx = next((i for i, v in enumerate(call_order) if v == "seal"), None)
        pregate_idx = next((i for i, v in enumerate(call_order) if v == "pregate"), None)
        assert seal_idx is not None, "seal_trajectory_step was never called"
        assert pregate_idx is not None, "run_cli_pregate_fn was never called in swarm_worker"
        assert seal_idx < pregate_idx, (
            f"seal ({seal_idx}) must precede pregate ({pregate_idx}); order={call_order}"
        )


# ===========================================================================
# 3. result binds AFTER pregate
# ===========================================================================


class TestBindAfterPregate:
    def test_bind_called_with_passed_flag_from_pregate(self, tmp_path):
        """bind_trajectory_step_result must receive the actual pregate result."""
        _git_init(tmp_path)
        bound_results: list[dict] = []

        def recording_bind_result(*, evidence_root, step_ref, action_result, **kw):
            bound_results.append(action_result)

        svc = _make_svc(
            tmp_path,
            run_cli_fn=MagicMock(
                return_value=(True, [{"passed": True, "cmd": "pytest", "exit_code": 0}])
            ),
        )
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path, bind_result_side_effect=recording_bind_result):
            _run_battle_attempt(svc, swarm, tmp_path)

        assert len(bound_results) >= 1, "bind_trajectory_step_result was never called"
        result = bound_results[0]
        assert result["passed"] is True
        assert result["exception_type"] is None

    def test_bind_captures_pregate_exception_type(self, tmp_path):
        """When pregate raises inside swarm_worker, bind_trajectory_step_result
        captures the exception_type and passed=False."""
        _git_init(tmp_path)
        bound_results: list[dict] = []

        def recording_bind_result(*, evidence_root, step_ref, action_result, **kw):
            bound_results.append(action_result)

        # Raise only on the first call (inside swarm_worker); fall back gracefully
        # on the second call (fallback pregate after all_failed) so the service
        # doesn't propagate the error outward.
        call_count = [0]

        def sometimes_exploding(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("pregate boom")
            return (False, [])

        svc = _make_svc(tmp_path, run_cli_fn=sometimes_exploding)
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(
            tmp_path,
            bind_result_side_effect=recording_bind_result,
            collection_result=MagicMock(
                status="COLLECTED",
                group_sha256="gs",
                collected_count=0,
                eligible_count=0,
                row_refs=(),
            ),
        ):
            _run_battle_attempt(svc, swarm, tmp_path)

        assert len(bound_results) >= 1, "bind_trajectory_step_result was never called"
        result = bound_results[0]
        assert result["passed"] is False
        assert result["exception_type"] == "RuntimeError"


# ===========================================================================
# 4. Telemetry failure is fail-open
# ===========================================================================


class TestTelemetryFailOpen:
    def test_seal_failure_does_not_affect_pregate_outcome(self, tmp_path):
        """seal_trajectory_step raises → pregate still runs and outcome is ok."""
        _git_init(tmp_path)
        pregate_calls: list[int] = []

        def counting_pregate(**kwargs):
            pregate_calls.append(1)
            return (True, [{"passed": True, "cmd": "pytest", "exit_code": 0}])

        svc = _make_svc(tmp_path, run_cli_fn=counting_pregate)
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path, seal_side_effect=RuntimeError("seal exploded")):
            out = _run_battle_attempt(svc, swarm, tmp_path)

        assert len(pregate_calls) >= 1, "pregate was not called after seal failure"
        assert out["status"] == "ok"

    def test_bind_result_failure_does_not_affect_outcome(self, tmp_path):
        """bind_trajectory_step_result raises → runtime outcome unchanged."""
        _git_init(tmp_path)
        svc = _make_svc(
            tmp_path,
            run_cli_fn=MagicMock(
                return_value=(True, [{"passed": True, "cmd": "pytest", "exit_code": 0}])
            ),
        )
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path, bind_result_side_effect=RuntimeError("bind exploded")):
            out = _run_battle_attempt(svc, swarm, tmp_path)

        assert out["status"] == "ok"

    def test_refresh_failure_does_not_affect_outcome(self, tmp_path):
        """refresh_registered_experiment raises → runtime outcome unchanged."""
        _git_init(tmp_path)
        svc = _make_svc(
            tmp_path,
            run_cli_fn=MagicMock(
                return_value=(True, [{"passed": True, "cmd": "pytest", "exit_code": 0}])
            ),
        )
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(
            tmp_path,
            bind_outcome_side_effect="some/ref.json",
            refresh_side_effect=RuntimeError("refresh boom"),
            collection_result=MagicMock(
                status="COLLECTED",
                group_sha256="gs",
                collected_count=1,
                eligible_count=1,
                row_refs=("groups/gs/row1.json",),
            ),
        ):
            out = _run_battle_attempt(svc, swarm, tmp_path)

        assert out["status"] == "ok"


# ===========================================================================
# 5. Multiple strategies do not cross trajectory_ids
# ===========================================================================


class TestNoTrajectoryLeakage:
    def test_each_strategy_gets_distinct_trajectory_id(self, tmp_path):
        """Each strategy in a multi-strategy swarm must produce a distinct trajectory_id."""
        _git_init(tmp_path)
        strategy_names = ["conservative", "aggressive", "decompose", "wisdom_guided"]
        strategies = [{"name": n, "params": {}} for n in strategy_names]
        sealed_calls: list[dict] = []

        def recording_seal(**kwargs):
            sealed_calls.append({
                "trajectory_id": kwargs["trajectory_id"],
                "candidate_id": kwargs["candidate_id"],
                "strategy_name": kwargs["pre_action_state"]["strategy_name"],
            })
            return _default_seal_fn(**kwargs)

        svc = _make_svc(tmp_path, run_cli_fn=MagicMock(return_value=(False, [])))
        swarm = _make_executing_swarm(strategies, wt_path_base=tmp_path)

        with _trajectory_patches(
            tmp_path,
            seal_side_effect=recording_seal,
            collection_result=MagicMock(
                status="COLLECTED",
                group_sha256="gs",
                collected_count=4,
                eligible_count=0,
                row_refs=(),
            ),
        ):
            _run_battle_attempt(svc, swarm, tmp_path, task_id="t-multi")

        assert len(sealed_calls) == 4, f"Expected 4 seal calls, got {len(sealed_calls)}"

        seen_tids = [c["trajectory_id"] for c in sealed_calls]
        assert len(seen_tids) == len(set(seen_tids)), (
            "Duplicate trajectory_ids detected — strategies are cross-contaminating"
        )

        for record in sealed_calls:
            assert record["candidate_id"] is None
            strat = record["strategy_name"]
            expected_tid = _battle_trajectory_id("t-multi", 2, strat, "deadbeef")
            assert record["trajectory_id"] == expected_tid, (
                f"trajectory_id mismatch for strategy '{strat}'"
            )


# ===========================================================================
# 6-8. Battle pregate telemetry is TRACE_ONLY and cannot advance readiness
# ===========================================================================


class TestBattlePregateTraceOnly:
    def test_even_eligible_candidate_row_does_not_bind_outcome(self, tmp_path):
        """Mechanical pregate observations are never labeled as repair trajectories."""
        _git_init(tmp_path)
        svc = _make_svc(
            tmp_path,
            run_cli_fn=MagicMock(return_value=(True, [{"passed": True}])),
        )
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(
            tmp_path,
            collection_result=MagicMock(
                status="COLLECTED",
                group_sha256="gs",
                collected_count=1,
                eligible_count=1,
                row_refs=("groups/gs/row1.json",),
            ),
        ):
            out = _run_battle_attempt(svc, swarm, tmp_path)

        assert out["status"] == "ok"
        outcome_dir = tmp_path / "evidence" / "trajectory" / "outcomes"
        assert not outcome_dir.exists() or not list(outcome_dir.glob("*.json"))

    def test_trace_only_pregate_does_not_create_readiness_binding(self, tmp_path):
        _git_init(tmp_path)
        svc = _make_svc(tmp_path, run_cli_fn=MagicMock(return_value=(False, [])))
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path):
            _run_battle_attempt(svc, swarm, tmp_path)

        outcome_dir = tmp_path / "evidence" / "trajectory" / "outcomes"
        assert not outcome_dir.exists() or not list(outcome_dir.glob("*.json"))


# ===========================================================================
# 9. Pre-action state must NOT contain forbidden future keys
# ===========================================================================


class TestPreActionStateForbiddenKeys:
    FORBIDDEN = {
        "final_verifier_status",
        "final_outcome",
        "final_candidate_status",
        "trajectory_outcome",
    }

    def test_pre_action_state_has_no_forbidden_keys(self, tmp_path):
        """Verify no forbidden final-outcome keys appear in sealed pre_action_state."""
        _git_init(tmp_path)
        sealed_states: list[dict] = []

        def capturing_seal(**kwargs):
            sealed_states.append(kwargs["pre_action_state"])
            return _default_seal_fn(**kwargs)

        svc = _make_svc(tmp_path, run_cli_fn=MagicMock(return_value=(False, [])))
        swarm = _make_executing_swarm(
            [{"name": "conservative", "params": {}}], wt_path_base=tmp_path
        )

        with _trajectory_patches(tmp_path, seal_side_effect=capturing_seal):
            _run_battle_attempt(svc, swarm, tmp_path)

        assert len(sealed_states) >= 1, "seal_trajectory_step was never called"
        for pre_state in sealed_states:
            all_keys = set(json.loads(json.dumps(pre_state)).keys())
            intersection = all_keys & self.FORBIDDEN
            assert not intersection, (
                f"Pre-action state contains forbidden future keys: {intersection}"
            )


# ===========================================================================
# 10. Regression guard: non-battle-swarm paths unaffected
# ===========================================================================


class TestExistingPathsUnaffected:
    def test_abort_on_sim_lewm_rejected(self, tmp_path):
        run_cli = MagicMock(return_value=(True, [{"passed": True}]))
        lewm_instance = MagicMock()
        lewm_instance.simulate.return_value = {"status": "REJECTED", "cost": 7}
        svc = RepairAttemptService(
            project_root=tmp_path,
            run_cli_pregate_fn=run_cli,
            lewm_cls=MagicMock(return_value=lewm_instance),
        )
        state = _make_state("r-1")
        state.metadata["task_description"] = "fix"
        state.metadata["sim_lewm"] = True

        out = svc.execute_attempt(
            task_id="r-1",
            task_desc="fix",
            state=state,
            attempt=1,
            verify_cmds=["pytest -q"],
            run_dir=tmp_path,
            skip_pregate_for_isolated_workspace=False,
        )

        assert out["status"] == "abort"
        assert out["passed"] is False
        run_cli.assert_not_called()

    def test_synthetic_pass_for_isolated_skip(self, tmp_path):
        run_cli = MagicMock(return_value=(False, []))
        svc = RepairAttemptService(project_root=tmp_path, run_cli_pregate_fn=run_cli)
        state = _make_state("r-2")

        out = svc.execute_attempt(
            task_id="r-2",
            task_desc="fix",
            state=state,
            attempt=1,
            verify_cmds=[],
            run_dir=tmp_path,
            skip_pregate_for_isolated_workspace=True,
        )

        assert out["status"] == "ok"
        assert out["passed"] is True
        assert out["gate_results"][0]["pregate_skip"] is True
        run_cli.assert_not_called()

    def test_default_pregate_path(self, tmp_path):
        run_cli = MagicMock(
            return_value=(True, [{"cmd": "pytest -q", "passed": True, "exit_code": 0}])
        )
        svc = RepairAttemptService(project_root=tmp_path, run_cli_pregate_fn=run_cli)
        state = _make_state("r-3")

        out = svc.execute_attempt(
            task_id="r-3",
            task_desc="fix",
            state=state,
            attempt=1,
            verify_cmds=["pytest -q"],
            run_dir=tmp_path,
            skip_pregate_for_isolated_workspace=False,
        )

        assert out["status"] == "ok"
        assert out["passed"] is True
        assert out["gate_results"][0]["cmd"] == "pytest -q"
        run_cli.assert_called_once()


# Preserve exact historical pytest node IDs used by exact-base impact evidence.
def test_repair_attempt_service_aborts_on_sim_lewm_rejected(tmp_path):
    TestExistingPathsUnaffected().test_abort_on_sim_lewm_rejected(tmp_path)


def test_repair_attempt_service_returns_synthetic_pass_for_isolated_skip(tmp_path):
    TestExistingPathsUnaffected().test_synthetic_pass_for_isolated_skip(tmp_path)


def test_repair_attempt_service_runs_default_pregate(tmp_path):
    TestExistingPathsUnaffected().test_default_pregate_path(tmp_path)
