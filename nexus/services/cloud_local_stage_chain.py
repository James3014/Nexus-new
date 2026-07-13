"""Five-stage Cloud + Local Assist chain with explicit fail-closed outcomes."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from nexus.services.cloud_agent_contract import CloudAgentAdapter, CloudAgentRequest, invoke_cloud_agent


STAGE_CHAIN_SCHEMA = "nexus.cloud_local_assist.stage_chain.v1"


def _stage(stage: int, status: str, *, skipped: bool = False, reason: str = "", **fields: Any) -> dict[str, Any]:
    return {"stage": stage, "status": status, "skipped": skipped, "reason": reason, **fields}


def _call(fn: Callable[[Mapping[str, Any]], Mapping[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return dict(fn(payload) or {})
    except Exception as exc:
        return {"status": "fail", "error": f"stage_exception:{exc}"}


def _ok(value: Mapping[str, Any]) -> bool:
    return str(value.get("status", "")).lower() in {"ok", "pass", "passed", "succeeded", "success"}


def _result(
    *,
    request: CloudAgentRequest,
    stages: list[dict[str, Any]],
    status: str,
    real_cloud_call: bool,
    cloud_failure: str = "",
) -> dict[str, Any]:
    return {
        "schema": STAGE_CHAIN_SCHEMA,
        "status": status,
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "stages": stages,
        "real_cloud_call": real_cloud_call,
        "cloud_failure": cloud_failure,
        "local_fallback_visible": any(stage["stage"] == 4 for stage in stages),
        "fake_success": ("TEST_ONLY" in status) is False and status == "CLOUD_CANDIDATE_VERIFIED",
        "formal_workspace_mutated": False,
        "route_truth_source": "CapabilityPlanner",
        "claim_boundary": {
            "real_cloud_proven": real_cloud_call and status == "CLOUD_CANDIDATE_VERIFIED",
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }


def run_cloud_local_stage_chain(
    *,
    request: CloudAgentRequest,
    cloud_adapter: CloudAgentAdapter,
    local_diagnosis: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    cheap_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    local_retry: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    committee_escalation: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    shadow_mode: bool = False,
) -> dict[str, Any]:
    request.validate()
    stages: list[dict[str, Any]] = []
    diagnosis = _call(local_diagnosis, {"task_id": request.task_id, "workspace_revision": request.workspace_revision, "request": request})
    if _ok(diagnosis):
        stages.append(_stage(1, "SUCCEEDED", result=diagnosis))
    else:
        stages.append(_stage(1, "FAILED", result=diagnosis))
        for number in range(2, 6):
            stages.append(_stage(number, "SKIPPED", skipped=True, reason="local_diagnosis_failed"))
        return _result(request=request, stages=stages, status="FAILED", real_cloud_call=False, cloud_failure="local_diagnosis_failed")

    if shadow_mode:
        stages.append(_stage(2, "SKIPPED", skipped=True, reason="shadow_path"))
        return _result(request=request, stages=stages, status="SHADOW_ONLY", real_cloud_call=False)

    cloud = invoke_cloud_agent(cloud_adapter, request)
    cloud_ok = not cloud.get("error") and bool(cloud.get("candidate_payload"))
    stages.append(
        _stage(
            2,
            "SUCCEEDED" if cloud_ok else "FAILED",
            result=cloud,
            provider=cloud.get("provider", ""),
            model=cloud.get("model", ""),
            usage=cloud.get("usage", {}),
            latency_sec=cloud.get("latency_sec", 0.0),
        )
    )
    real_cloud_call = bool(cloud.get("real_cloud_call", False))
    if cloud_ok:
        verification = _call(cheap_verifier, {"task_id": request.task_id, "workspace_revision": request.workspace_revision, "cloud": cloud})
        stages.append(_stage(3, "SUCCEEDED" if _ok(verification) else "FAILED", result=verification))
        if _ok(verification):
            status = "CLOUD_CANDIDATE_VERIFIED" if real_cloud_call else "CANDIDATE_VERIFIED_TEST_ONLY"
            return _result(request=request, stages=stages, status=status, real_cloud_call=real_cloud_call)
    else:
        cloud_failure = str(cloud.get("error") or "candidate_missing")

    retry = _call(
        local_retry,
        {
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "cloud": cloud,
            "stages": stages,
        },
    )
    stages.append(_stage(4, "SUCCEEDED" if _ok(retry) else "FAILED", result=retry))
    if _ok(retry):
        return _result(
            request=request,
            stages=stages,
            status="LOCAL_RETRY_SUCCEEDED",
            real_cloud_call=real_cloud_call,
            cloud_failure=str(cloud.get("error", "")),
        )

    committee = _call(
        committee_escalation,
        {
            "task_id": request.task_id,
            "workspace_revision": request.workspace_revision,
            "cloud": cloud,
            "retry": retry,
            "stages": stages,
        },
    )
    stages.append(_stage(5, "SUCCEEDED" if _ok(committee) else "FAILED", result=committee))
    if _ok(committee):
        status = "COMMITTEE_ESCALATION_SUCCEEDED_TEST_ONLY" if not real_cloud_call else "COMMITTEE_ESCALATION_SUCCEEDED"
    else:
        status = "FAILED"
    return _result(
        request=request,
        stages=stages,
        status=status,
        real_cloud_call=real_cloud_call,
        cloud_failure=str(cloud.get("error", "")),
    )
