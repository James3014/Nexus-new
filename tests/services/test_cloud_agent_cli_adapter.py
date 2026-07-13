from __future__ import annotations

import json
import sys

from nexus.services.cloud_agent_cli_adapter import SubprocessCloudAgentAdapter
from nexus.services.cloud_agent_contract import CloudAgentRequest, invoke_cloud_agent


def _request() -> CloudAgentRequest:
    return CloudAgentRequest(
        task_id="m4-real-test-001",
        workspace_revision="fixture-rev-1",
        bounded_context="one bounded fixture file",
        local_diagnosis="the fixture function returns the wrong value",
        semantic_assertions=("return value must be 2",),
        target_files=("fixture.py",),
        allowed_mutation_scope=("fixture.py",),
        provider="test-cli",
        model="test-model",
    )


def test_subprocess_adapter_parses_strict_response_and_preserves_lineage() -> None:
    payload = json.dumps({
        "response_identity": "cli-response-1",
        "candidate_payload": "fixture-candidate",
        "usage": {"input_tokens": 7, "output_tokens": 3},
    })
    adapter = SubprocessCloudAgentAdapter(
        command_builder=lambda _: ([sys.executable, "-c", f"print({payload!r})"], None),
        provider="test-cli",
        model="test-model",
        is_real_provider=False,
    )
    response = invoke_cloud_agent(adapter, _request())
    assert response["candidate_payload"] == "fixture-candidate"
    assert response["response_identity"] == "cli-response-1"
    assert response["provider_call_confirmed"] is True
    assert response["real_cloud_call"] is False
    assert response["error"] == ""


def test_subprocess_adapter_rejects_invalid_json_without_fake_success() -> None:
    adapter = SubprocessCloudAgentAdapter(
        command_builder=lambda _: ([sys.executable, "-c", "print('not-json')"], None),
        provider="test-cli",
        model="test-model",
        is_real_provider=True,
    )
    response = invoke_cloud_agent(adapter, _request())
    assert response["error"] == "cloud_response_invalid_json"
    assert response["candidate_payload"] == ""
    assert response["real_cloud_call"] is False


def test_subprocess_adapter_timeout_is_explicit() -> None:
    adapter = SubprocessCloudAgentAdapter(
        command_builder=lambda _: ([sys.executable, "-c", "import time; time.sleep(2)"], None),
        provider="test-cli",
        model="test-model",
        timeout_sec=0.01,
        is_real_provider=True,
    )
    response = invoke_cloud_agent(adapter, _request())
    assert response["error"] == "provider_timeout"
    assert response["real_cloud_call"] is False
