from __future__ import annotations

from nexus.services.cloud_agent_contract import CloudAgentRequest, InjectedCloudAgentAdapter
from nexus.services.cloud_local_stage_chain import run_cloud_local_stage_chain


def _request() -> CloudAgentRequest:
    return CloudAgentRequest(
        task_id="m4-b-001",
        workspace_revision="rev-1",
        bounded_context="target.py bounded context",
        local_diagnosis="target returns the wrong value",
        semantic_assertions=("target returns 2",),
        target_files=("target.py",),
        allowed_mutation_scope=("target.py",),
        provider="injected",
        model="deterministic-cloud-test",
    )


def _cloud(payload: str = "candidate-patch") -> InjectedCloudAgentAdapter:
    return InjectedCloudAgentAdapter(
        lambda request: {
            "candidate_payload": payload,
            "response_identity": f"response-{request.task_id}",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "latency_sec": 0.01,
        }
    )


def test_five_stage_chain_records_injected_candidate_without_real_cloud_claim() -> None:
    result = run_cloud_local_stage_chain(
        request=_request(),
        cloud_adapter=_cloud(),
        local_diagnosis=lambda _: {"status": "ok", "diagnosis": "bounded"},
        cheap_verifier=lambda _: {"status": "pass", "verifier": "cheap"},
        local_retry=lambda _: {"status": "not_needed"},
        committee_escalation=lambda _: {"status": "not_needed"},
    )
    assert result["status"] == "CANDIDATE_VERIFIED_TEST_ONLY"
    assert [stage["stage"] for stage in result["stages"]] == [1, 2, 3]
    assert result["real_cloud_call"] is False
    assert result["claim_boundary"]["real_cloud_proven"] is False
    assert result["formal_workspace_mutated"] is False
    assert result["task_id"] == "m4-b-001"


def test_cloud_failure_is_visible_and_local_retry_can_succeed() -> None:
    result = run_cloud_local_stage_chain(
        request=_request(),
        cloud_adapter=InjectedCloudAgentAdapter(lambda _: {"error": "provider_unavailable"}),
        local_diagnosis=lambda _: {"status": "ok"},
        cheap_verifier=lambda _: {"status": "pass"},
        local_retry=lambda _: {"status": "pass", "candidate": "local-candidate"},
        committee_escalation=lambda _: {"status": "not_needed"},
    )
    assert result["status"] == "LOCAL_RETRY_SUCCEEDED"
    assert result["cloud_failure"] == "provider_unavailable"
    assert result["stages"][1]["status"] == "FAILED"
    assert result["stages"][2]["stage"] == 4
    assert result["local_fallback_visible"] is True
    assert result["real_cloud_call"] is False


def test_verifier_failure_retries_then_escalates_to_committee() -> None:
    result = run_cloud_local_stage_chain(
        request=_request(),
        cloud_adapter=_cloud(),
        local_diagnosis=lambda _: {"status": "ok"},
        cheap_verifier=lambda _: {"status": "fail", "reason": "assertion_failed"},
        local_retry=lambda _: {"status": "fail", "reason": "retry_failed"},
        committee_escalation=lambda _: {"status": "pass", "winner": "committee"},
    )
    assert result["status"] == "COMMITTEE_ESCALATION_SUCCEEDED_TEST_ONLY"
    assert [stage["stage"] for stage in result["stages"]] == [1, 2, 3, 4, 5]
    assert result["stages"][2]["status"] == "FAILED"
    assert result["stages"][3]["status"] == "FAILED"
    assert result["stages"][4]["status"] == "SUCCEEDED"


def test_shadow_path_skips_cloud_and_records_explicit_skip() -> None:
    calls: list[str] = []
    result = run_cloud_local_stage_chain(
        request=_request(),
        cloud_adapter=InjectedCloudAgentAdapter(lambda _: calls.append("cloud") or {"candidate_payload": "fake"}),
        local_diagnosis=lambda _: {"status": "ok"},
        cheap_verifier=lambda _: {"status": "pass"},
        local_retry=lambda _: {"status": "not_needed"},
        committee_escalation=lambda _: {"status": "not_needed"},
        shadow_mode=True,
    )
    assert result["status"] == "SHADOW_ONLY"
    assert result["stages"][1]["skipped"] is True
    assert result["stages"][1]["reason"] == "shadow_path"
    assert calls == []


def test_all_failures_remain_failed_and_do_not_become_fake_success() -> None:
    result = run_cloud_local_stage_chain(
        request=_request(),
        cloud_adapter=InjectedCloudAgentAdapter(lambda _: {"error": "provider_unavailable"}),
        local_diagnosis=lambda _: {"status": "ok"},
        cheap_verifier=lambda _: {"status": "pass"},
        local_retry=lambda _: {"status": "fail"},
        committee_escalation=lambda _: {"status": "fail"},
    )
    assert result["status"] == "FAILED"
    assert result["cloud_failure"] == "provider_unavailable"
    assert result["fake_success"] is False
    assert result["claim_boundary"]["outcome_contributed"] is False
