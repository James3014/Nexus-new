"""Paired Local Advisor experiment harness (Arm A disabled vs Arm B advisor).

Offline-injectable. Never treats missing usage as zero.
Does not claim savings without live paired evidence with explicit provenance.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


# Measurement provenance (replaces ambiguous generic MEASURED).
FIXTURE_MEASURED = "FIXTURE_MEASURED"
PROVIDER_REPORTED = "PROVIDER_REPORTED"
LOCALLY_MEASURED = "LOCALLY_MEASURED"
ESTIMATED = "ESTIMATED"
UNAVAILABLE = "UNAVAILABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
# Backward-compat alias: treat as FIXTURE_MEASURED for injected harness paths.
MEASURED = FIXTURE_MEASURED

COMPARABLE_QUALITIES = frozenset(
    {FIXTURE_MEASURED, PROVIDER_REPORTED, LOCALLY_MEASURED, ESTIMATED, MEASURED}
)

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
    local_context_forwarded: bool = False
    local_provider_call_count: int = 0
    online_provider_call_count: int = 0
    online_provider: str = ""
    online_model: str = ""
    local_provider: str = ""
    local_model: str = ""
    input_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    output_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    total_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    local_total_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    combined_total_tokens: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    online_latency_ms: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    end_to_end_latency_ms: MetricValue = field(default_factory=lambda: MetricValue(None, UNAVAILABLE))
    retry_count: int = 0
    context_bytes: int = 0
    error: str = ""
    task_success: bool = False
    verified_success: bool = False
    local_contribution_observed: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    receipt_path: str = ""
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_tokens"] = self.input_tokens.to_dict()
        payload["output_tokens"] = self.output_tokens.to_dict()
        payload["total_tokens"] = self.total_tokens.to_dict()
        payload["local_total_tokens"] = self.local_total_tokens.to_dict()
        payload["combined_total_tokens"] = self.combined_total_tokens.to_dict()
        payload["online_latency_ms"] = self.online_latency_ms.to_dict()
        payload["end_to_end_latency_ms"] = self.end_to_end_latency_ms.to_dict()
        return payload


def _metric_from_usage(
    usage: Mapping[str, Any] | None,
    key: str,
    *,
    quality: str = PROVIDER_REPORTED,
) -> MetricValue:
    if not isinstance(usage, Mapping):
        return MetricValue(None, UNAVAILABLE)
    if key not in usage or usage.get(key) is None:
        return MetricValue(None, UNAVAILABLE)
    try:
        return MetricValue(int(usage[key]), quality)
    except (TypeError, ValueError):
        return MetricValue(None, UNAVAILABLE)


def _delta(a: MetricValue, b: MetricValue) -> dict[str, Any]:
    """B - A when both arms share a comparable quality and values; else unavailable."""
    if a.value is None or b.value is None:
        return {"value": None, "quality": UNAVAILABLE}
    if a.quality not in COMPARABLE_QUALITIES or b.quality not in COMPARABLE_QUALITIES:
        return {"value": None, "quality": UNAVAILABLE}
    if a.quality != b.quality:
        return {"value": None, "quality": UNAVAILABLE}
    return {"value": float(b.value) - float(a.value), "quality": a.quality}


def recompute_deltas(arm_a: Mapping[str, Any], arm_b: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute deltas from stored arm raw metrics (fail-closed on missing arms)."""
    if not isinstance(arm_a, Mapping) or not isinstance(arm_b, Mapping):
        raise ValueError("incomplete_arm_data")
    required = ("total_tokens", "online_latency_ms", "end_to_end_latency_ms", "retry_count", "task_success")
    for key in required:
        if key not in arm_a or key not in arm_b:
            raise ValueError(f"incomplete_arm_data:{key}")

    def _mv(arm: Mapping[str, Any], field: str) -> MetricValue:
        raw = arm.get(field)
        if isinstance(raw, Mapping):
            return MetricValue(raw.get("value"), str(raw.get("quality") or UNAVAILABLE))
        if isinstance(raw, MetricValue):
            return raw
        return MetricValue(None, UNAVAILABLE)

    return {
        "online_token_delta": _delta(_mv(arm_a, "total_tokens"), _mv(arm_b, "total_tokens")),
        "total_token_delta": _delta(_mv(arm_a, "total_tokens"), _mv(arm_b, "total_tokens")),
        "combined_token_delta": _delta(
            _mv(arm_a, "combined_total_tokens")
            if arm_a.get("combined_total_tokens")
            else _mv(arm_a, "total_tokens"),
            _mv(arm_b, "combined_total_tokens")
            if arm_b.get("combined_total_tokens")
            else _mv(arm_b, "total_tokens"),
        ),
        "online_latency_delta": _delta(_mv(arm_a, "online_latency_ms"), _mv(arm_b, "online_latency_ms")),
        "end_to_end_latency_delta": _delta(
            _mv(arm_a, "end_to_end_latency_ms"), _mv(arm_b, "end_to_end_latency_ms")
        ),
        "retry_delta": {
            "value": int(arm_b.get("retry_count") or 0) - int(arm_a.get("retry_count") or 0),
            "quality": LOCALLY_MEASURED,
        },
        "success_delta": {
            "value": int(bool(arm_b.get("task_success"))) - int(bool(arm_a.get("task_success"))),
            "quality": LOCALLY_MEASURED,
        },
    }


def assert_deltas_match_stored(row: Mapping[str, Any]) -> None:
    """Fail closed if stored deltas diverge from recomputed arm values."""
    arm_a = row.get("arm_a")
    arm_b = row.get("arm_b")
    if not isinstance(arm_a, Mapping) or not isinstance(arm_b, Mapping):
        raise ValueError("incomplete_arm_data")
    recomputed = recompute_deltas(arm_a, arm_b)
    stored = row.get("deltas")
    if not isinstance(stored, Mapping):
        raise ValueError("missing_stored_deltas")
    for key, expected in recomputed.items():
        got = stored.get(key)
        if not isinstance(got, Mapping):
            raise ValueError(f"delta_mismatch:{key}")
        if got.get("value") != expected.get("value") or got.get("quality") != expected.get("quality"):
            raise ValueError(f"delta_mismatch:{key}")


def local_contribution_truth(
    *,
    local_invoked: bool,
    local_output_delivered: bool,
    local_context_forwarded: bool,
    online_received_context: bool,
    online_output_delivered: bool,
) -> bool:
    """True only when Local actually contributed context that Online consumed."""
    return bool(
        local_invoked
        and local_output_delivered
        and local_context_forwarded
        and online_received_context
        and online_output_delivered
    )


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
        result.end_to_end_latency_ms = MetricValue(int((time.perf_counter() - t0) * 1000), LOCALLY_MEASURED)
        return result

    elapsed = int((time.perf_counter() - t0) * 1000)
    result.receipt = dict(receipt)
    result.end_to_end_latency_ms = MetricValue(elapsed, LOCALLY_MEASURED)
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
    result.local_provider = str(local_resp.get("provider") or local.get("provider") or ("injected" if result.local_invoked else ""))
    result.local_model = str(local_resp.get("resolved_model") or local_resp.get("model") or "")
    result.online_provider = str(online_payload.get("provider") or online.get("provider") or "")
    result.online_model = str(online_payload.get("model") or "")
    # Injected harness usage is FIXTURE_MEASURED, not real provider reporting.
    selection = str(online_payload.get("selection_source") or online.get("selection_source") or "")
    transport = str(online_payload.get("transport") or "")
    usage_quality = (
        FIXTURE_MEASURED
        if selection == "injected_transport" or transport in {"structured_callable", "injected"} or result.online_provider in {"fixture", "injected"}
        else PROVIDER_REPORTED
    )
    usage = online_payload.get("usage") if isinstance(online_payload.get("usage"), Mapping) else {}
    result.input_tokens = _metric_from_usage(usage, "input_tokens", quality=usage_quality)
    result.output_tokens = _metric_from_usage(usage, "output_tokens", quality=usage_quality)
    result.total_tokens = _metric_from_usage(usage, "total_tokens", quality=usage_quality)
    if result.total_tokens.quality == UNAVAILABLE and "tokens_used" in (usage or {}):
        result.total_tokens = _metric_from_usage(usage, "tokens_used", quality=usage_quality)
    result.local_total_tokens = MetricValue(None, UNAVAILABLE)
    if result.total_tokens.quality != UNAVAILABLE and result.total_tokens.value is not None:
        result.combined_total_tokens = MetricValue(result.total_tokens.value, result.total_tokens.quality)
    else:
        result.combined_total_tokens = MetricValue(None, UNAVAILABLE)
    result.online_latency_ms = MetricValue(elapsed, LOCALLY_MEASURED)
    refs = list(online.get("evidence_refs") or []) + list(online_payload.get("evidence_refs") or [])
    result.evidence_refs = [str(r) for r in refs]
    online_received = any("local_context_forwarded" in r for r in result.evidence_refs)
    result.local_context_forwarded = bool(
        local_resp.get("local_context_forwarded")
        or (result.local_output_delivered and result.local_invoked and local_assist_policy == "advisor")
    )
    result.local_contribution_observed = local_contribution_truth(
        local_invoked=result.local_invoked,
        local_output_delivered=result.local_output_delivered,
        local_context_forwarded=result.local_context_forwarded,
        online_received_context=online_received,
        online_output_delivered=result.online_output_delivered,
    )
    result.task_success = bool(result.online_output_delivered)
    result.verified_success = bool(receipt.get("verifier", {}).get("gate_passed")) if isinstance(receipt.get("verifier"), Mapping) else False
    result.error = str(online_payload.get("error") or local.get("reason") or "")
    return result


def compare_arms(arm_a: ArmResult, arm_b: ArmResult) -> dict[str, Any]:
    # Same-provider / same-revision arm enforcement for pilot integrity.
    if arm_a.workspace_revision != arm_b.workspace_revision:
        raise ValueError("arm_workspace_revision_mismatch")
    if arm_a.task_id != arm_b.task_id:
        raise ValueError("arm_task_id_mismatch")
    # When both arms report a provider identity, they must match.
    if arm_a.online_provider and arm_b.online_provider and arm_a.online_provider != arm_b.online_provider:
        raise ValueError("arm_online_provider_mismatch")

    claim_eligible = (
        arm_a.total_tokens.quality in {PROVIDER_REPORTED, FIXTURE_MEASURED}
        and arm_b.total_tokens.quality in {PROVIDER_REPORTED, FIXTURE_MEASURED}
        and arm_a.total_tokens.quality == arm_b.total_tokens.quality
        and arm_a.online_invoked
        and arm_b.online_invoked
    )
    # Injected fixture measurements never authorize public savings claims.
    public_token_claim = False
    deltas = {
        "online_token_delta": _delta(arm_a.total_tokens, arm_b.total_tokens),
        "total_token_delta": _delta(arm_a.total_tokens, arm_b.total_tokens),
        "combined_token_delta": _delta(arm_a.combined_total_tokens, arm_b.combined_total_tokens),
        "online_latency_delta": _delta(arm_a.online_latency_ms, arm_b.online_latency_ms),
        "end_to_end_latency_delta": _delta(arm_a.end_to_end_latency_ms, arm_b.end_to_end_latency_ms),
        "retry_delta": {
            "value": arm_b.retry_count - arm_a.retry_count,
            "quality": LOCALLY_MEASURED,
        },
        "success_delta": {
            "value": int(arm_b.task_success) - int(arm_a.task_success),
            "quality": LOCALLY_MEASURED,
        },
    }
    row = {
        "task_id": arm_a.task_id,
        "workspace_revision": arm_a.workspace_revision,
        "task_input_hash": "",
        "online_provider": arm_a.online_provider or arm_b.online_provider,
        "online_model": arm_a.online_model or arm_b.online_model,
        "local_provider": arm_b.local_provider,
        "local_model": arm_b.local_model,
        "arm_a": arm_a.to_dict(),
        "arm_b": arm_b.to_dict(),
        "deltas": deltas,
        "local_contribution_observed": bool(arm_b.local_contribution_observed),
        "measurement_quality": {
            "arm_a_tokens": arm_a.total_tokens.quality,
            "arm_b_tokens": arm_b.total_tokens.quality,
            "arm_a_latency": arm_a.end_to_end_latency_ms.quality,
            "arm_b_latency": arm_b.end_to_end_latency_ms.quality,
        },
        "claim_eligibility": {
            "token_savings_claim_allowed": public_token_claim,
            "time_savings_claim_allowed": False,
            "paired_measured": claim_eligible,
            "reason": (
                "injected_or_unmeasured_usage"
                if not claim_eligible
                else "fixture_or_live_measured_but_public_claim_still_false"
            ),
        },
        "claim_boundary": {
            "public_claim_allowed": False,
            "proven_token_savings": False,
            "proven_time_savings": False,
            "proven_cost_reduction": False,
        },
    }
    assert_deltas_match_stored(row)
    return row


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
