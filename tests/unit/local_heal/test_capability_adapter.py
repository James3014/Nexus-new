from __future__ import annotations

import os
import tempfile
import shutil
from unittest import mock

from nexus.contracts.hybrid_route import RouteMode, Authority, VerifierResult
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
    build_local_model_provider_from_env,
)
from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    OllamaLocalModelProvider,
)


def test_capability_adapter_disabled() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t1",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={"enable_local_heal": False, "local_heal_mode": "disabled"},
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


def test_capability_adapter_shadow_only_with_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t2",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={"enable_local_heal": True, "local_heal_mode": "shadow_only"},
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


def test_capability_adapter_shadow_only_missing_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t3",
        problem_statement="fix syntax",
        evidence_refs=(),
        executor_controls={"enable_local_heal": True, "local_heal_mode": "shadow_only"},
        dry_run=False,
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_evidence_refs" in response.hybrid_route.fallback_block_reason
    assert "shadow_only_no_runtime" in response.hybrid_route.fallback_block_reason
    assert "mutation_not_allowed" in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["gate_passed"] is False


def test_capability_adapter_pipeline_enabled_by_env_but_mutation_blocked() -> None:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_HEAL_CAPABILITY_ADAPTER_ENABLE_PIPELINE": "1"}):
        request = LocalHealCapabilityRequest(
            task_id="t4",
            problem_statement="fix syntax",
            evidence_refs=("ref1",),
            executor_controls={"enable_local_heal": True, "local_heal_mode": "disabled"},
            dry_run=False,
        )
        response = LocalHealCapabilityAdapter.run(request)
        assert response.invoked is True
        assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "mutation_not_allowed" in response.hybrid_route.fallback_block_reason
        assert "shadow_only_no_runtime" not in response.hybrid_route.fallback_block_reason
        assert response.capability_payload["gate_passed"] is False


def test_capability_adapter_advisory_enabled_by_env() -> None:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_MODEL_ADVISORY_ENABLE": "1"}):
        request = LocalHealCapabilityRequest(
            task_id="t5",
            problem_statement="fix test suite",
            evidence_refs=("ref1",),
            executor_controls={"enable_local_heal": False, "local_heal_mode": "disabled"},
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


def test_capability_adapter_fail_closed_guard_blocked() -> None:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE": "1"}):
        request = LocalHealCapabilityRequest(
            task_id="t6",
            problem_statement="fix test suite",
            evidence_refs=("ref1",),
            executor_controls={
                "enable_local_heal": True,
                "local_heal_mode": "shadow_only",
                "verifier_result": "fail",
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


def test_capability_adapter_candidate_enabled_with_call() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
    }):
        def mock_gen(req) -> str:
            return "proposed change text"
            
        request = LocalHealCapabilityRequest(
            task_id="t7",
            problem_statement="fix candidate wiring",
            evidence_refs=("ref1",),
            executor_controls={
                "candidate_generate_fn": mock_gen,
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


def test_build_local_model_provider_from_env() -> None:
    env1 = {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "0"}
    prov1 = build_local_model_provider_from_env(env1, {}, "candidate_generate_fn")
    assert isinstance(prov1, InertLocalModelProvider)
    
    env2 = {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1"}
    controls2 = {"candidate_generate_fn": lambda req: "output"}
    prov2 = build_local_model_provider_from_env(env2, controls2, "candidate_generate_fn")
    assert isinstance(prov2, InjectedLocalModelProvider)
    
    env3 = {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen",
    }
    prov3 = build_local_model_provider_from_env(env3, {}, "candidate_generate_fn")
    assert isinstance(prov3, OllamaLocalModelProvider)


def test_capability_adapter_isolated_solve_missing_control() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
    }):
        request = LocalHealCapabilityRequest(
            task_id="t8",
            problem_statement="fix code",
            evidence_refs=("ref1",),
            executor_controls={},
            dry_run=False,
        )
        response = LocalHealCapabilityAdapter.run(request)
        assert response.invoked is False
        assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "missing_required_control" in response.hybrid_route.fallback_block_reason
        assert response.capability_payload["gate_passed"] is False


def test_capability_adapter_isolated_solve_success() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
    }):
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


def test_capability_adapter_dry_run_default() -> None:
    # 預設 dry_run=True
    request = LocalHealCapabilityRequest(
        task_id="t_dry",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        executor_controls={
            "enable_local_heal": True,
            "local_heal_mode": "candidate",
        },
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.fallback_block_reason == "dry_run"
    assert response.hybrid_route.metadata.get("dry_run") is True
