from __future__ import annotations

import os
from unittest import mock

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)

# #1924 (#2032/#2050): the adapter reads its mode switches only from a CapabilityPlanner
# signal_snapshot that build_execution_plan bound to the request's task_id. As in
# test_abc_local_heal_shadow_seam, the env opt-ins are projected onto a real planner snapshot.
# The model identity comes from the planner (NEXUS_LOCAL_MODEL_EXECUTOR_MODEL).
_ENV_MODE_OPT_INS = {
    "candidate_enabled": "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE",
    "advisory_enabled": "NEXUS_LOCAL_MODEL_ADVISORY_ENABLE",
}


def _bound_route_context(task_id: str) -> dict:
    planner_plan = CapabilityPlanner().plan(
        task_desc="ollama smoke", task_type="repair", route={"local_enabled": True}
    )
    snapshot = dict(planner_plan.signal_snapshot)
    snapshot.update({flag: os.environ.get(env) == "1" for flag, env in _ENV_MODE_OPT_INS.items()})
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


def test_ollama_smoke_advisory_contract() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_ADVISORY_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen3:3b",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen3:3b",
    }):
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "advisory output from qwen"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            request = LocalHealCapabilityRequest(
                task_id="task-smoke-advis",
                problem_statement="dry run advisory test",
                evidence_refs=("ref1",),
                executor_controls={"route_context": _bound_route_context("task-smoke-advis")},
                dry_run=False,
            )
            response = LocalHealCapabilityAdapter.run(request)
            
            hr = response.hybrid_route
            assert response.invoked is True
            assert hr.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY
            assert hr.authority == Authority.ADVISORY_ONLY
            assert hr.local_model_called is True
            assert hr.behavior_changed is False
            assert hr.adapter_output_is_route_truth is False
            assert response.capability_payload["gate_passed"] is False
            assert hr.public_claim_allowed is False
            assert hr.production_ready is False
            
            meta = hr.metadata
            assert meta["provider_invoked"] is True
            assert meta["model_name"] == "qwen3:3b"
            assert meta["advisory_text_preview"] == "advisory output from qwen"


def test_ollama_smoke_candidate_contract() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder:7b",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen2.5-coder:7b",
    }):
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "candidate output from qwen"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            request = LocalHealCapabilityRequest(
                task_id="task-smoke-cand",
                problem_statement="dry run candidate test",
                evidence_refs=("ref1",),
                executor_controls={
                    "route_context": _bound_route_context("task-smoke-cand"),
                    # The candidate lane requires its locked-span controls (missing_required_control otherwise).
                    "source_root": "src",
                    "target_file": "f.py",
                    "target_symbol": "sym",
                    "locked_search": "search",
                    "verifier_command": ["cmd"],
                    "work_dir": "work",
                },
                dry_run=False,
            )
            response = LocalHealCapabilityAdapter.run(request)
            
            hr = response.hybrid_route
            assert response.invoked is True
            assert hr.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
            assert hr.authority == Authority.TRACE_ONLY
            assert hr.local_model_called is True
            
            assert response.capability_payload["gate_passed"] is False
            assert hr.public_claim_allowed is False
            assert hr.production_ready is False
            assert hr.adapter_output_is_route_truth is False
            assert hr.behavior_changed is False
            
            meta = hr.metadata
            assert meta["selected_candidate_hash"] != ""
            assert meta["applied_patch_hash"] == ""
            assert meta["verifier_result"] == "not_run"
            assert hr.selected_candidate_hash == meta["selected_candidate_hash"]
            assert hr.applied_patch_hash == ""
            assert hr.selected_candidate_hash_matches_applied is False
            
            assert "missing_applied_patch_hash" in hr.fallback_block_reason
            assert "selected_reapply_not_proven" in hr.fallback_block_reason
