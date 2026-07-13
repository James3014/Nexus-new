"""Online auth/error stdout must not be classified as successful delivery."""

from __future__ import annotations

from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    build_online_route,
    normalize_online_invoker_payload,
    online_payload_indicates_non_delivery,
)


def test_ineligible_tier_error_marks_online_stage_failed() -> None:
    def invoker(context):
        return normalize_online_invoker_payload(
            provider="gemini",
            task_id=str(context.get("task_id")),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "FAIL"},
            raw_response="Error authenticating: IneligibleTierError: migrate",
            usage={},
            error="",
            evidence_refs=[f"online:{context.get('task_id')}:gateway"],
        )

    def verifier(context):
        online = context.get("online") or {}
        return {
            "task_id": context.get("task_id"),
            "status": "pass" if online.get("gate_passed") else "fail",
            "gate_passed": bool(online.get("gate_passed")),
            "invoked": True,
            "evidence_refs": ["v"],
        }

    route = dict(build_online_route(recommended_flow="direct", gateway_provider="gemini"))
    route["online_policy"] = "auto"
    route["injected_transport"] = False
    route["provider"] = "gemini"
    route["online_execution_decision"] = {
        "online_policy": "auto",
        "online_execution_requested": True,
        "online_execution_authorized": True,
        "online_authorization_source": "cli_task_policy",
        "approved_online_providers": ["gemini"],
        "preflight_status": "ONLINE_READY",
        "physical_invocation_allowed": True,
        "reason": "online_execution_authorized",
    }

    receipt = UnifiedRuntime().run(
        UnifiedRuntimeRequest(
            task_id="auth-fail-1",
            workspace_revision="rev-1",
            task_statement="advisory only",
            task_type="advisory",
            route=route,
            online_prompt="hi",
            online_payload="json",
        ),
        online_invoker=invoker,
        verifier=verifier,
    )
    online = receipt.get("online") or {}
    assert online.get("status") == "FAILED"
    assert online.get("invoked") is True
    assert online.get("gate_passed") is False
    resp = online.get("response") or {}
    assert resp.get("output_delivered") is False
    assert online_payload_indicates_non_delivery(resp) is True
