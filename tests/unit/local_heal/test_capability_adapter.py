from __future__ import annotations

import os
import tempfile
import shutil
from unittest import mock
import pytest

from nexus.contracts.hybrid_route import RouteMode, Authority, VerifierResult
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
    build_local_model_provider,
)
from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    OllamaLocalModelProvider,
)
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

# #2936: with no OS sandbox on the host (Linux CI) model commands are refused; these tests
# exercise verifier/drone logic, so they run them unconfined there (sandbox stays on macOS).
pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")

# The snapshot keys LocalHealCapabilityAdapter reads as grants. They are cleared from the real
# planner snapshot so that each scenario states its grants explicitly.
_ADAPTER_GRANT_KEYS = frozenset({
    "model_call_allowed",
    "candidate_enabled",
    "mutation_allowed",
    "verifier_allowed",
    "isolated_solve_enabled",
    "advisory_enabled",
    "fail_closed_enabled",
    "enable_pipeline",
    "executor_provider",
    "executor_model",
})


def _bound_route_context(task_id: str, **grants: object) -> dict:
    """Build a route_context the current contract accepts (#1924, #2032/#2050).

    Start from a real CapabilityPlanner.plan() snapshot, project the scenario's grants onto it,
    and pass it through build_execution_plan(plan, task_id=...) so it is bound to the task that
    the request names.
    """
    planner_plan = CapabilityPlanner().plan(
        task_desc="fix code", task_type="repair", route={"local_enabled": True}
    )
    snapshot = {k: v for k, v in planner_plan.signal_snapshot.items() if k not in _ADAPTER_GRANT_KEYS}
    snapshot.update(grants)
    plan = CapabilityPlan(
        schema_version="nexus_capability_plan_v1",
        selected_capabilities=["local_heal"],
        required_capabilities=["local_heal"],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=[],
        forbidden_capabilities=[],
        constraints=[],
        decision_trace=[],
        replan_trace=[],
        score=95.0,
        signal_snapshot=snapshot,
    )
    return dict(build_execution_plan(plan, task_id=task_id).executor_controls["route_context"])


@pytest.mark.legacy
def test_build_local_model_provider() -> None:
    snap1 = {"model_call_allowed": False}
    prov1 = build_local_model_provider(snap1, {}, "candidate_generate_fn")
    assert isinstance(prov1, InertLocalModelProvider)
    
    snap2 = {"model_call_allowed": True}
    controls2 = {"candidate_generate_fn": lambda req: "output"}
    prov2 = build_local_model_provider(snap2, controls2, "candidate_generate_fn")
    assert isinstance(prov2, InjectedLocalModelProvider)
    
    snap3 = {
        "model_call_allowed": True,
        "executor_provider": "ollama",
        "executor_model": "qwen",
    }
    prov3 = build_local_model_provider(snap3, {}, "candidate_generate_fn")
    assert isinstance(prov3, OllamaLocalModelProvider)


@pytest.mark.legacy
def test_capability_adapter_disabled() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t1",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": False, 
            "local_heal_mode": "disabled",
            "route_context": _bound_route_context("t1", enable_pipeline=False)
        },
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.task_id == "t1"
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert response.hybrid_route.authority == Authority.TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.verifier_result == VerifierResult.NOT_RUN
    assert response.capability_payload["invoked"] is False
    assert response.capability_payload["adapter_invoked"] is False
    assert response.capability_payload["gate_passed"] is False


@pytest.mark.legacy
def test_capability_adapter_shadow_only_with_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t2",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True, 
            "local_heal_mode": "shadow_only",
            "route_context": _bound_route_context("t2", model_call_allowed=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert response.hybrid_route.authority == Authority.TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert "shadow_only_no_runtime" in response.hybrid_route.fallback_block_reason
    assert "mutation_not_allowed" in response.hybrid_route.fallback_block_reason
    assert response.hybrid_route.evidence_refs == ("ref1",)
    assert response.capability_payload["invoked"] is False
    assert response.capability_payload["adapter_invoked"] is True
    assert response.capability_payload["gate_passed"] is False


@pytest.mark.legacy
def test_capability_adapter_shadow_only_missing_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t3",
        problem_statement="fix syntax",
        evidence_refs=(),
        executor_controls={
            "enable_local_heal": True, 
            "local_heal_mode": "shadow_only",
            "route_context": _bound_route_context("t3", model_call_allowed=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_evidence_refs" in response.hybrid_route.fallback_block_reason
    assert "shadow_only_no_runtime" in response.hybrid_route.fallback_block_reason
    assert "mutation_not_allowed" in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["gate_passed"] is False


@pytest.mark.legacy
def test_capability_adapter_pipeline_enabled_by_env_but_mutation_blocked() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t4",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True, 
            "local_heal_mode": "disabled",
            "route_context": _bound_route_context("t4", enable_pipeline=True, mutation_allowed=False)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "mutation_not_allowed" in response.hybrid_route.fallback_block_reason
    assert "shadow_only_no_runtime" not in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["gate_passed"] is False


@pytest.mark.legacy
def test_capability_adapter_advisory_enabled_by_env() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t5",
        problem_statement="fix test suite",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": False, 
            "local_heal_mode": "disabled",
            "route_context": _bound_route_context("t5", advisory_enabled=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY
    assert response.hybrid_route.authority == Authority.ADVISORY_ONLY
    assert response.hybrid_route.behavior_changed is False
    assert response.hybrid_route.adapter_output_is_route_truth is False
    assert response.capability_payload["gate_passed"] is False
    assert response.hybrid_route.route_mode != RouteMode.LOCAL_ONLY_EXECUTED


@pytest.mark.legacy
def test_capability_adapter_fail_closed_guard_blocked() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t6",
        problem_statement="fix test suite",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "shadow_only",
            "verifier_result": "fail",
            "route_context": _bound_route_context("t6", fail_closed_enabled=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED
    assert response.hybrid_route.authority == Authority.FAIL_CLOSED
    assert response.capability_payload["gate_passed"] is False
    assert "verifier_fail" in response.hybrid_route.fallback_block_reason
    assert response.hybrid_route.public_claim_allowed is False
    assert response.hybrid_route.production_ready is False


@pytest.mark.legacy
def test_capability_adapter_candidate_enabled_with_call() -> None:
    def mock_gen(req) -> str:
        return "proposed change text"
        
    request = LocalHealCapabilityRequest(
        task_id="t7",
        problem_statement="fix candidate wiring",
        evidence_refs=("ref1",),
        executor_controls={
            "candidate_generate_fn": mock_gen,
            "source_root": "src",
            "target_file": "f.py",
            "target_symbol": "sym",
            "locked_search": "search",
            "verifier_command": ["cmd"],
            "work_dir": "work",
            "route_context": _bound_route_context("t7", candidate_enabled=True, model_call_allowed=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert response.hybrid_route.local_model_called is True
    assert "missing_applied_patch_hash" in response.hybrid_route.fallback_block_reason
    assert "selected_reapply_not_proven" in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["gate_passed"] is False



@pytest.mark.legacy
def test_capability_adapter_isolated_solve_missing_control() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t8",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "route_context": _bound_route_context("t8", candidate_enabled=True, model_call_allowed=True, isolated_solve_enabled=True)
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_required_control" in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["gate_passed"] is False


@pytest.mark.legacy
def test_capability_adapter_isolated_solve_success() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        
        def mock_gen(req) -> str:
            return f"```diff\n{diff}```"
            
        request = LocalHealCapabilityRequest(
            task_id="t9",
            problem_statement="fix code",
            evidence_refs=("ref1",),
            executor_controls={
                "source_root": src_root,
                "target_file": test_file,
                "target_symbol": "print",
                "locked_search": "print('hello')",
                "verifier_command": ["python3", "-c", "import os; assert os.path.exists('f.py')"],
                "work_dir": "",
                "candidate_generate_fn": mock_gen,
                "route_context": _bound_route_context("t9", candidate_enabled=True, model_call_allowed=True, isolated_solve_enabled=True, mutation_allowed=True, verifier_allowed=True)
            },
            dry_run=False,
        )
            
        response = LocalHealCapabilityAdapter.run(request)
        assert response.invoked is True
        assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
        assert response.hybrid_route.local_model_called is True
        assert response.hybrid_route.verifier_result == VerifierResult.PASS
        assert response.capability_payload["gate_passed"] is True
        assert response.hybrid_route.public_claim_allowed is False
        assert response.hybrid_route.production_ready is False
        
        # Telemetry metadata check
        metadata = response.capability_payload["metadata"]
        assert metadata["canonical_span_source"] == "locked_search"
        assert metadata["fallback_used"] is False
        assert metadata["target_symbol"] == "print"
        assert metadata["verifier_status"] == "pass"
        
        if os.path.exists(response.hybrid_route.metadata.get("workspace_path", "")):
            shutil.rmtree(response.hybrid_route.metadata.get("workspace_path", ""))


@pytest.mark.legacy
def test_capability_adapter_dry_run_default() -> None:
    # 預設 dry_run=True
    request = LocalHealCapabilityRequest(
        task_id="t_dry",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "candidate",
            "route_context": _bound_route_context("t_dry")
        },
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.fallback_block_reason == "dry_run"
    assert response.hybrid_route.metadata.get("dry_run") is True


def test_capability_adapter_missing_signal_snapshot_fail_closed() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t_qs1",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "candidate",
        },
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert response.hybrid_route.authority == Authority.FAIL_CLOSED
    assert response.hybrid_route.route_truth_source == "CapabilityPlanner"
    assert response.hybrid_route.adapter_output_is_route_truth is False
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.verifier_result == VerifierResult.NOT_RUN


def test_capability_adapter_route_truth_source_is_frozen() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t_qs2",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "candidate",
            "route_truth_source": "AdversarySource",
            "route_context": {
                "signal_snapshot": {
                    "candidate_enabled": True,
                    "model_call_allowed": True,
                }
            }
        },
        dry_run=False,
    )
    with mock.patch("nexus.services.local_heal.capability_adapter.build_local_heal_runtime_policy") as mock_policy:
        from nexus.services.local_heal.capability_runtime_policy import LocalHealRuntimePolicy
        mock_policy.return_value = LocalHealRuntimePolicy(
            enable_pipeline=True,
            mutation_allowed=True,
            public_claim_allowed=False,
            production_ready=False,
            model_call_allowed=True,
            provider_call_allowed=True,
            network_allowed=False,
            dry_run=False,
        )
        response = LocalHealCapabilityAdapter.run(request)
        assert response.hybrid_route.route_truth_source == "CapabilityPlanner"
        assert response.hybrid_route.adapter_output_is_route_truth is False


def test_capability_adapter_output_is_never_route_truth() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t_qs3",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "candidate",
            "route_context": {
                "signal_snapshot": {
                    "candidate_enabled": True,
                    "model_call_allowed": True,
                }
            }
        },
        dry_run=False,
    )
    with mock.patch("nexus.services.local_heal.capability_adapter.build_local_heal_runtime_policy") as mock_policy:
        from nexus.services.local_heal.capability_runtime_policy import LocalHealRuntimePolicy
        mock_policy.return_value = LocalHealRuntimePolicy(
            enable_pipeline=True,
            mutation_allowed=True,
            public_claim_allowed=False,
            production_ready=False,
            model_call_allowed=True,
            provider_call_allowed=True,
            network_allowed=False,
            dry_run=False,
        )
        response = LocalHealCapabilityAdapter.run(request)
        assert response.hybrid_route.adapter_output_is_route_truth is False
        assert response.hybrid_route.public_claim_allowed is False
        assert response.hybrid_route.production_ready is False
        assert response.hybrid_route.behavior_changed is False


def test_capability_adapter_env_flag_does_not_create_route_authority() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_WITH_LOCAL_MODEL_ADAPTER": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
    }):
        request = LocalHealCapabilityRequest(
            task_id="t_qs4",
            problem_statement="fix code",
            evidence_refs=("ref1",),
            executor_controls={
                "enable_local_heal": True,
                "local_heal_mode": "candidate",
                "route_context": {
                    "signal_snapshot": {
                        "candidate_enabled": True,
                        "model_call_allowed": True,
                    }
                }
            },
            dry_run=False,
        )
        with mock.patch("nexus.services.local_heal.capability_adapter.build_local_heal_runtime_policy") as mock_policy:
            from nexus.services.local_heal.capability_runtime_policy import LocalHealRuntimePolicy
            mock_policy.return_value = LocalHealRuntimePolicy(
                enable_pipeline=True,
                mutation_allowed=True,
                public_claim_allowed=False,
                production_ready=False,
                model_call_allowed=True,
                provider_call_allowed=True,
                network_allowed=False,
                dry_run=False,
            )
            response = LocalHealCapabilityAdapter.run(request)
            assert response.hybrid_route.route_truth_source == "CapabilityPlanner"
            assert response.hybrid_route.adapter_output_is_route_truth is False
            assert response.hybrid_route.public_claim_allowed is False
            assert response.hybrid_route.production_ready is False


def test_capability_adapter_cannot_synthesize_signal_snapshot_from_env() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
    }):
        request = LocalHealCapabilityRequest(
            task_id="t_qs5",
            problem_statement="fix code",
            evidence_refs=("ref1",),
            executor_controls={
                "enable_local_heal": True,
                "local_heal_mode": "candidate",
                "route_context": {}
            },
            dry_run=False,
        )
        response = LocalHealCapabilityAdapter.run(request)
        assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert response.hybrid_route.authority == Authority.FAIL_CLOSED
        assert response.hybrid_route.route_truth_source == "CapabilityPlanner"
        assert response.hybrid_route.adapter_output_is_route_truth is False
