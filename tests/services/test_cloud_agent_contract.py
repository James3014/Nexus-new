from __future__ import annotations

import pytest

from nexus.services.cloud_agent_contract import (
    CLOUD_AGENT_REQUEST_SCHEMA,
    CLOUD_AGENT_RESPONSE_SCHEMA,
    CloudAgentRequest,
    InjectedCloudAgentAdapter,
    invoke_cloud_agent,
)


def _request() -> CloudAgentRequest:
    return CloudAgentRequest(
        task_id="m4-a-001",
        workspace_revision="rev-1",
        bounded_context="target.py contains the failing function",
        local_diagnosis="target returns the wrong value",
        semantic_assertions=("target must return 2",),
        target_files=("target.py",),
        allowed_mutation_scope=("target.py",),
        provider="injected",
        model="deterministic-test-provider",
    )


def test_provider_neutral_injected_contract_is_explicitly_non_real() -> None:
    response = invoke_cloud_agent(
        InjectedCloudAgentAdapter(
            lambda request: {
                "candidate_payload": "candidate-patch",
                "response_identity": "injected-response-1",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            }
        ),
        _request(),
    )
    assert response["schema"] == CLOUD_AGENT_RESPONSE_SCHEMA
    assert response["task_id"] == "m4-a-001"
    assert response["candidate_payload"] == "candidate-patch"
    assert response["real_cloud_call"] is False
    assert response["provider_call_confirmed"] is True
    assert response["formal_workspace_mutated"] is False
    assert response["route_truth_source"] == "CapabilityPlanner"


def test_request_schema_validates_bounded_scope() -> None:
    request = _request()
    assert request.schema == CLOUD_AGENT_REQUEST_SCHEMA
    with pytest.raises(ValueError, match="target_outside_allowed_scope"):
        CloudAgentRequest(**{**request.__dict__, "target_files": ("other.py",)})


def test_provider_unavailability_is_explicit_and_not_real_cloud() -> None:
    response = invoke_cloud_agent(
        InjectedCloudAgentAdapter(lambda _: {"error": "provider_unavailable"}),
        _request(),
    )
    assert response["error"] == "provider_unavailable"
    assert response["real_cloud_call"] is False
    assert response["candidate_payload"] == ""


def test_response_task_lineage_mismatch_fails_closed() -> None:
    response = invoke_cloud_agent(
        InjectedCloudAgentAdapter(
            lambda _: {
                "task_id": "wrong-task",
                "workspace_revision": "wrong-revision",
                "candidate_payload": "candidate-patch",
                "response_identity": "wrong-response",
            }
        ),
        _request(),
    )
    assert response["error"] == "cloud_response_lineage_mismatch"
    assert response["candidate_payload"] == ""
    assert response["real_cloud_call"] is False
