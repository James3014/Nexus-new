"""Paired Local Advisor experiment harness (Arm A disabled vs Arm B advisor).

Offline-injectable. Never treats missing usage as zero.
Does not claim savings without MEASURED paired evidence.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


MEASURED = "MEASURED"
UNAVAILABLE = "UNAVAILABLE"
ESTIMATED = "ESTIMATED"
NOT_APPLICABLE = "NOT_APPLICABLE"

ARM_A = "A_online_only"
ARM_B = "B_local_advisor_online"


@dataclass
class MetricValue:
    value: float | int | None
    quality: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "quality": self.quality}


@dataclass
class ArmResult:
    arm: str
    task_id: str
    workspace_revision: str
    local_assist_policy: str
    local_invoked: bool = False
    online_invoked: bool = False
    local_output_delivered: bool = False
    online_output_delivered: bool = False
    local_provider_call_count: int = 0
    online_provider_call_count: int = 0
    input_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    output_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    total_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    online_latency_ms: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    end_to_end_latency_ms: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    retry_count: int = 0
    context_bytes: int = 0
    error: str = ""
    task_success: bool = False
    verified_success: bool = False
    local_contribution_observed: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_tokens"] = self.input_tokens.to_dict()
        payload["output_tokens"] = self.output_tokens.to_dict()
        payload["total_tokens"] = self.total_tokens.to_dict()
        payload["online_latency_ms"] = self.online_latency_ms.to_dict()
        payload["end_to_end_latency_ms"] = self.end_to_end_latency_ms.to_dict()
        return payload


def _metric_from_usage(usage: Mapping[str, Any] | None, key: str) -> MetricValue:
    if not isinstance(usage, Mapping):
        return MetricValue(None, UNAVAILABLE)
    if key not in usage or usage.get(key) is None:
        return MetricValue(None, UNAVAILABLE)
    try:
        return MetricValue(int(usage[key]), MEASURED)
    except (TypeError, ValueError):
        return MetricValue(None, UNAVAILABLE)


def _delta(a: MetricValue, b: MetricValue) -> dict[str, Any]:
    """B - A when both MEASURED; else unavailable."""
    if a.quality != MEASURED or b.quality != MEASURED or a.value is None or b.value is None:
        return {"value": None, "quality": UNAVAILABLE}
    return {"value": float(b.value) - float(a.value), "quality": MEASURED}


def load_task_defs(tasks_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(tasks_dir)
    tasks: list[dict[str, Any]] = []
    if not root.is_dir():
        return tasks
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, Mapping) and data.get("task_id"):
            tasks.append(dict(data))
    return tasks


def run_arm_injected(
    *,
    arm: str,
    task: Mapping[str, Any],
    local_assist_policy: str,
    online_invoker: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    local_service: Any | None = None,
    project_root: str | Path = ".",
) -> ArmResult:
    """Run one arm through UnifiedRuntime with injected transports."""
    from nexus.services.local_assist_service import LocalAssistRequest, REQUEST_SCHEMA
    from nexus.services.unified_runtime import (
        UnifiedRuntime,
        UnifiedRuntimeRequest,
        build_online_route,
        extract_online_stage_payload,
    )

    task_id = str(task.get("task_id") or "paired-task")
    revision = str(task.get("workspace_revision") or "fixture-rev")
    allowed = tuple(str(x) for x in (task.get("allowed_files") or []) if str(x).strip())
    statement = str(task.get("task_statement") or task_id)
    t0 = time.perf_counter()

    result = ArmResult(
        arm=arm,
        task_id=task_id,
        workspace_revision=revision,
        local_assist_policy=local_assist_policy,
        context_bytes=len(statement.encode("utf-8")),
    )

    local_request = None
    local_enabled = local_assist_policy == "advisor" and bool(allowed) and local_service is not None
    if local_enabled:
        snapshot = dict(task.get("planner_snapshot") or {})
        if not snapshot:
            snapshot = {
                "route_truth_source": "CapabilityPlanner",
                "execution_topology": "single_local_model",
                "protocol_mode": "unified_diff",
                "model_call_allowed": True,
                "executor_provider": "ollama",
                "executor_model": str(task.get("local_model") or "fixture-model"),
            }
        local_request = LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(Path(project_root).resolve()),
            workspace_revision=revision,
            task_statement=statement,
            action="advisor",
            allowed_files=allowed,
            target_file=allowed[0],
            target_symbol="",
            evidence_refs=(f"paired:{task_id}:request",),
            requested_role="advisor",
            mutation_policy="isolated_only",
            planner_snapshot=snapshot,
        )

    def verifier(context: Mapping[str, Any]) -> dict[str, Any]:
        online = context.get("online", {}) if isinstance(context, Mapping) else {}
        domain, _raw, payload = extract_online_stage_payload(online if isinstance(online, Mapping) else {})
        ok = bool(domain) or bool(payload.get("output_delivered"))
        return {
            "task_id": task_id,
            "status": "pass" if ok else "fail",
            "gate_passed": ok,
            "invoked": True,
            "evidence_refs": [f"verifier:{task_id}:paired"],
        }

    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=revision,
        task_statement=statement,
        task_type=str(task.get("task_type") or "repair"),
        route=build_online_route(
            recommended_flow="hybrid" if local_enabled else "direct",
            local_enabled=local_enabled,
        ),
        online_prompt=statement,
        online_payload=str(task.get("online_payload") or "Return advisory JSON only."),
        online_phase="R",
        local_enabled=local_enabled,
        local_request=local_request,
        evidence_refs=(f"paired:{task_id}:{arm}",),
    )

    try:
        receipt = UnifiedRuntime(local_service=local_service if local_enabled else None).run(
            request,
            online_invoker=online_invoker,
            verifier=verifier,
            receipt_path=None,
        )
    except Exception as exc:  # noqa: BLE001
        result.error = f"{exc.__class__.__name__}:{exc}"
        result.end_to_end_latency_ms = MetricValue(int((time.perf_counter() - t0) * 1000), MEASURED)
        return result

    elapsed = int((time.perf_counter() - t0) * 1000)
    result.receipt = dict(receipt)
    result.end_to_end_latency_ms = MetricValue(elapsed, MEASURED)
    local = receipt.get("local", {}) if isinstance(receipt.get("local"), Mapping) else {}
    online = receipt.get("online", {}) if isinstance(receipt.get("online"), Mapping) else {}
    domain, _raw, online_payload = extract_online_stage_payload(online if isinstance(online, Mapping) else {})
    local_resp = local.get("response", {}) if isinstance(local.get("response"), Mapping) else {}

    result.local_invoked = bool(local.get("invoked"))
    result.online_invoked = bool(online.get("invoked") or online_payload.get("invoked"))
    result.local_output_delivered = bool(local.get("gate_passed") or local_resp.get("output_delivered"))
    result.online_output_delivered = bool(online_payload.get("output_delivered") or domain)
    result.local_provider_call_count = int(local_resp.get("provider_call_count") or (1 if result.local_invoked else 0))
    result.online_provider_call_count = int(online_payload.get("provider_call_count") or 0)
    usage = online_payload.get("usage") if isinstance(online_payload.get("usage"), Mapping) else {}
    result.input_tokens = _metric_from_usage(usage, "input_tokens")
    result.output_tokens = _metric_from_usage(usage, "output_tokens")
    result.total_tokens = _metric_from_usage(usage, "total_tokens")
    if result.total_tokens.quality == UNAVAILABLE and "tokens_used" in (usage or {}):
        result.total_tokens = _metric_from_usage(usage, "tokens_used")
    result.online_latency_ms = MetricValue(elapsed, MEASURED)
    refs = list(online.get("evidence_refs") or []) + list(online_payload.get("evidence_refs") or [])
    result.evidence_refs = [str(r) for r in refs]
    result.local_contribution_observed = any("local_context_forwarded" in r for r in result.evidence_refs)
    result.task_success = bool(result.online_output_delivered)
    result.verified_success = bool(receipt.get("verifier", {}).get("gate_passed")) if isinstance(receipt.get("verifier"), Mapping) else False
    result.error = str(online_payload.get("error") or local.get("reason") or "")
    return result


def compare_arms(arm_a: ArmResult, arm_b: ArmResult) -> dict[str, Any]:
    claim_eligible = (
        arm_a.total_tokens.quality == MEASURED
        and arm_b.total_tokens.quality == MEASURED
        and arm_a.online_invoked
        and arm_b.online_invoked
    )
    return {
        "task_id": arm_a.task_id,
        "workspace_revision": arm_a.workspace_revision,
        "arm_a": arm_a.to_dict(),
        "arm_b": arm_b.to_dict(),
        "deltas": {
            "online_token_delta": _delta(arm_a.total_tokens, arm_b.total_tokens),
            "total_token_delta": _delta(arm_a.total_tokens, arm_b.total_tokens),
            "online_latency_delta": _delta(arm_a.online_latency_ms, arm_b.online_latency_ms),
            "end_to_end_latency_delta": _delta(arm_a.end_to_end_latency_ms, arm_b.end_to_end_latency_ms),
            "retry_delta": {
                "value": arm_b.retry_count - arm_a.retry_count,
                "quality": MEASURED,
            },
            "success_delta": {
                "value": int(arm_b.task_success) - int(arm_a.task_success),
                "quality": MEASURED,
            },
        },
        "measurement_quality": {
            "arm_a_tokens": arm_a.total_tokens.quality,
            "arm_b_tokens": arm_b.total_tokens.quality,
        },
        "claim_eligibility": {
            "token_savings_claim_allowed": False,
            "time_savings_claim_allowed": False,
            "paired_measured": claim_eligible,
            "reason": (
                "injected_or_unmeasured_usage"
                if not claim_eligible
                else "measured_but_public_claim_still_false_without_campaign_gate"
            ),
        },
        "claim_boundary": {
            "public_claim_allowed": False,
            "proven_token_savings": False,
            "proven_time_savings": False,
            "proven_cost_reduction": False,
        },
    }


def run_paired_task_injected(
    task: Mapping[str, Any],
    *,
    online_invoker_a: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    online_invoker_b: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    local_service_b: Any | None,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    arm_a = run_arm_injected(
        arm=ARM_A,
        task=task,
        local_assist_policy="disabled",
        online_invoker=online_invoker_a,
        local_service=None,
        project_root=project_root,
    )
    arm_b = run_arm_injected(
        arm=ARM_B,
        task=task,
        local_assist_policy="advisor",
        online_invoker=online_invoker_b,
        local_service=local_service_b,
        project_root=project_root,
    )
    return compare_arms(arm_a, arm_b)


def write_experiment_summary(path: str | Path, rows: list[Mapping[str, Any]], *, status: str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "nexus.local_assist.paired_experiment_summary.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment_status": status,
        "task_count": len(rows),
        "claim_boundary": {
            "public_claim_allowed": False,
            "proven_token_savings": False,
            "proven_time_savings": False,
            "proven_cost_reduction": False,
            "proven_quality_improvement": False,
        },
        "rows": list(rows),
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
