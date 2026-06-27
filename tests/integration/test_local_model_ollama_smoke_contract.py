from __future__ import annotations

import os
from unittest import mock

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)


def test_ollama_smoke_advisory_contract() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_ADVISORY_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen3:3b",
    }):
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "advisory output from qwen"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            request = LocalHealCapabilityRequest(
                task_id="task-smoke-advis",
                problem_statement="dry run advisory test",
                evidence_refs=("ref1",),
                executor_controls={},
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
    }):
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "candidate output from qwen"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            request = LocalHealCapabilityRequest(
                task_id="task-smoke-cand",
                problem_statement="dry run candidate test",
                evidence_refs=("ref1",),
                executor_controls={},
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
