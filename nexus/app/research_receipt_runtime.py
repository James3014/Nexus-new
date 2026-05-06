from __future__ import annotations

from typing import Any

from nexus.engine.capability_receipts import build_trace_receipts


def runtime_receipt_plan_payload(
    capability_plan_payload: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
) -> dict[str, Any]:
    plan = dict(capability_plan_payload)
    selected = [str(item).strip() for item in (plan.get("selected_capabilities", []) or []) if str(item).strip()]
    if not selected:
        return plan

    capabilities = nexus_usage_trace.get("capabilities", {}) if isinstance(nexus_usage_trace.get("capabilities"), dict) else {}
    autoreason = nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {}
    pruned: dict[str, str] = {}

    def remove_selected(name: str, reason: str) -> None:
        aliases = {name}
        if name == "judge_panel":
            aliases.add("llm_judge_panel")
        removed = [item for item in selected if item in aliases]
        if not removed:
            return
        selected[:] = [item for item in selected if item not in aliases]
        for item in removed:
            pruned[item] = reason

    judge_selected = bool({"judge_panel", "llm_judge_panel"} & set(selected))
    judge_used = bool(capabilities.get("judge_panel_used") or capabilities.get("llm_judge_panel_used"))
    if judge_selected and not judge_used:
        status = str(autoreason.get("status") or "").strip().upper()
        stop_reason = str(autoreason.get("stop_reason") or "").strip()
        if status in {"SKIPPED", "DISABLED", "FEATURE_FLAG_DISABLED", "NOOP"} or stop_reason:
            remove_selected("judge_panel", stop_reason or status.lower() or "runtime_judge_not_executable")

    autoreason_selected = "autoreason" in selected
    autoreason_used = bool(autoreason.get("enabled") or str(autoreason.get("status") or "").strip().upper() == "SUCCESS")
    if autoreason_used and not autoreason_selected:
        selected.append("autoreason")
        plan["selected_capabilities"] = selected
    if autoreason_selected and not autoreason_used:
        status = str(autoreason.get("status") or "").strip().upper()
        stop_reason = str(autoreason.get("stop_reason") or "").strip()
        if status in {"SKIPPED", "DISABLED", "FEATURE_FLAG_DISABLED", "NOOP"} or stop_reason:
            remove_selected("autoreason", stop_reason or status.lower() or "runtime_autoreason_not_executable")

    hyper_used = bool(capabilities.get("hyper_used", False))
    if hyper_used and "hyper" not in selected:
        selected.append("hyper")
        plan["selected_capabilities"] = selected

    if pruned:
        plan["selected_capabilities"] = selected
        capabilities["runtime_pruned_capabilities"] = pruned
        capabilities["runtime_pruned_capability_count"] = len(pruned)
    return plan


def build_capability_receipt_payloads(
    capability_plan_payload: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
) -> list[dict[str, Any]]:
    runtime_plan = runtime_receipt_plan_payload(capability_plan_payload, nexus_usage_trace)
    capabilities = nexus_usage_trace.get("capabilities", {}) if isinstance(nexus_usage_trace.get("capabilities"), dict) else {}
    return [
        item.to_dict()
        for item in build_trace_receipts(
            plan=runtime_plan,
            capabilities=capabilities,
            autoreason=nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {},
            ddtree=nexus_usage_trace.get("ddtree", {}) if isinstance(nexus_usage_trace.get("ddtree"), dict) else {},
            ultra_review=nexus_usage_trace.get("ultra_review", {}) if isinstance(nexus_usage_trace.get("ultra_review"), dict) else {},
            codeintel=nexus_usage_trace.get("codeintel", {}) if isinstance(nexus_usage_trace.get("codeintel"), dict) else {},
        )
    ]
