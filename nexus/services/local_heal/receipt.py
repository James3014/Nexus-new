from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _nexus_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_instance_id(instance_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", instance_id).strip("_") or "unknown"


def _error_reason(ctx: Any) -> str:
    if getattr(ctx, "solve_eligible", False):
        return ""
    explicit_reason = str(getattr(ctx, "failure_reason", "") or "").strip()
    if explicit_reason:
        return explicit_reason
    errors = getattr(ctx, "errors", []) or []
    if errors:
        latest = errors[-1]
        kind = getattr(getattr(latest, "kind", ""), "name", str(getattr(latest, "kind", "")))
        message = str(getattr(latest, "message", "")).strip()
        return f"{kind}:{message}" if kind else message
    report = str(getattr(ctx, "evaluation_report", "") or "").strip()
    if report:
        return "VERIFICATION_FAILED"
    if not getattr(ctx, "final_patch", ""):
        return "NO_PATCH"
    return "NOT_SOLVE_ELIGIBLE"


def _failure_class(ctx: Any) -> str:
    reason = str(_error_reason(ctx))
    if "AttributeError" in reason or "has no attribute" in reason:
        return "hallucinated_api"
    if "MODEL_TIMEOUT" in reason:
        return "timeout"
    if "OOM" in reason or "killed" in reason.lower():
        return "oom"
    if "syntax" in reason.lower() or "IndentationError" in reason:
        return "syntax_invalid"
    if any(kw in reason for kw in ["ENV_", "ENVIRONMENT", "ImportError", "VIOLATION", "MISSING", "REPRO_"]):
        return "env_noise"
    if "NO_BLOCKS_FOUND" in reason or "NO_PATCH" in reason or "SEARCH_MISMATCH" in reason or "REFUSAL" in reason:
        return "patch_mismatch"
    if "VERIFICATION_FAILED" in reason or "AssertionError" in reason or "LOGIC_REGRESSION" in reason:
        return "semantic_wrong"
    return "unknown"


def build_repair_receipt(ctx: Any, *, model_name: str = "nexus-local-heal") -> dict[str, Any]:
    final_patch = str(getattr(ctx, "final_patch", "") or "")
    evaluation_report = str(getattr(ctx, "evaluation_report", "") or "")
    visible_passed = "[FAIL]" not in evaluation_report if evaluation_report else bool(getattr(ctx, "solve_eligible", False))
    hidden_required = bool(getattr(ctx, "hidden_verifier_required", False))
    hidden_passed = bool(getattr(ctx, "hidden_verifier_passed", False))
    patch_paths = sorted(set(re.findall(r"^\+\+\+ b/(.+)$", final_patch, flags=re.MULTILINE)))
    python_executable = str(getattr(ctx, "python_executable", "") or "python3")

    repro_success = bool(getattr(ctx, "reproduced", False))
    failure_reason = _error_reason(ctx)
    
    env_resolution = dict(getattr(ctx, "env_resolution", {}) or {})
    env_failed = not env_resolution.get("ready", True)
    
    # Granular Repro Status
    if env_failed:
        repro_status = "ENV_BLOCKED"
    elif "ENV_" in failure_reason or "ENVIRONMENT" in failure_reason:
        repro_status = "ENV_BLOCKED"
    elif repro_success:
        repro_status = "ACTIVE_BUG"
    elif "ALREADY_FIXED" in failure_reason:
        repro_status = "ALREADY_FIXED"
    elif "HARNESS_ANOMALY" in failure_reason:
        repro_status = "HARNESS_ANOMALY"
    elif "RESCUE_FAILED" in failure_reason:
        repro_status = "RESCUE_FAILED"
    elif "REPRO_INVALID" in failure_reason or "NOT_REPRODUCED" in failure_reason:
        repro_status = "INVALID"
    elif not getattr(ctx, "repro_script", ""):
        repro_status = "REPRO_NOT_REACHED"
    else:
        repro_status = "GREEN"

    model_decisions = list(getattr(ctx, "model_decisions", []) or [])
    
    # Attempt to inject runtime telemetry from swe_local_heal
    try:
        from benchmarking.swebench_lite.swe_local_heal import telemetry_store
        if hasattr(telemetry_store, "records") and telemetry_store.records:
            total_tokens = sum(r.get("prompt_eval_count", 0) + r.get("eval_count", 0) for r in telemetry_store.records)
            ctx.op.token_total_estimated = total_tokens
            ctx.op.token_telemetry_status = "success"
            for idx, record in enumerate(telemetry_store.records):
                if idx < len(model_decisions):
                    model_decisions[idx]["telemetry"] = record
    except Exception:
        pass
    
    # 決定 gate_exit
    if env_failed:
        gate_exit = "env_resolver"
    elif not repro_success:
        gate_exit = "repro_runner"
    elif not final_patch:
        gate_exit = "patcher"
    else:
        gate_exit = "verification"

    expected_stop = str(getattr(ctx, "expected_stop_layer", "verification") or "verification")
    expected_family = str(getattr(ctx, "expected_reason_family", "SOLVED") or "SOLVED")
    
    actual_family = _failure_class(ctx)
    if getattr(ctx, "solve_eligible", False):
        actual_family = "SOLVED"

    layer_matched = (gate_exit == expected_stop)
    family_matched = (actual_family == expected_family)
    stop_layer_matched = layer_matched and family_matched

    # 萃取模型分工資訊
    search_model = "unknown"
    patch_model = "unknown"
    for decision in model_decisions:
        phase = decision.get("phase")
        model = decision.get("model", "unknown")
        if phase in ["planning", "reproduction"]:
            search_model = model.split(":")[-1] if ":" in model else model
        elif phase == "patch":
            patch_model = model.split(":")[-1] if ":" in model else model

    model_split = f"search={search_model}/patch={patch_model}"
    if not any(d.get("model") for d in model_decisions):
        model_split = "rescue=0-call"

    return {
        "schema": "nexus.local_heal.repair_receipt.v1",
        "instance_id": getattr(ctx, "instance_id", ""),
        "model_name_or_path": model_name,
        "runner_completed": bool(getattr(ctx, "runner_completed", False)),
        "solve_eligible": bool(getattr(ctx, "solve_eligible", False)),
        "reproduced": repro_success,
        "patch_applied": bool(final_patch),
        "visible_passed": bool(visible_passed),
        "hidden_verifier_required": hidden_required,
        "hidden_passed": bool(hidden_passed if hidden_required else True),
        "gate_passed": bool(getattr(ctx, "solve_eligible", False)),
        "failure_reason": failure_reason,
        "eval_metrics": {
            "repro_status": repro_status,
            "failure_class": actual_family,
            "model_phase_split": model_split,
            "context_bytes_before_after": f"{getattr(ctx, 'initial_ctx_len', 0)}/{getattr(ctx, 'final_ctx_len', 0)}",
            "resolved_span_len": int(getattr(ctx, "resolved_span_len", 0) or 0),
            "retry_count": int(getattr(ctx, "attempt", 0) or 0),
            "gate_exit": gate_exit,
            "expected_stop_layer": expected_stop,
            "expected_reason_family": expected_family,
            "stop_layer_matched": stop_layer_matched,
            "layer_matched": layer_matched,
            "family_matched": family_matched,
            "wall_time_sec_measured": float(getattr(ctx, "wall_time_sec", 0.0) or 0.0),
            "token_telemetry_status": str(getattr(ctx, "token_telemetry_status", "not_applicable") or "not_applicable"),
            "token_total_estimated": int(getattr(ctx, "token_total_estimated", 0) or 0),
            "syntax_gate_passed": bool(getattr(ctx, "syntax_gate_passed", True)),
            "claimability": "public_safe" if getattr(ctx, "solve_eligible", False) else "observation_only",
            "diagnostics": {
                "prompt_variant_id": str(getattr(ctx, "prompt_variant_id", "default") or "default"),
                "refusal_detected": bool(getattr(ctx, "refusal_detected", False)),
                "empty_response": bool(getattr(ctx, "empty_response", False)),
            }
        },
        "patch_paths": patch_paths,
        "evidence_refs": [
            "repro_evidence.log",
            "patch.diff" if final_patch else "",
            "verification_report.txt" if evaluation_report else "",
        ],
        "commands": [f"{python_executable} reproduce_bug.py"] if getattr(ctx, "repro_script", "") else [],
        "telemetries": {
            "attempt": int(getattr(ctx, "attempt", 0) or 0),
            "reasoning_mode": getattr(ctx, "reasoning_mode", "INTUITIVE"),
            "patch_len": len(final_patch),
            "model_decisions": model_decisions,
            "env_denoise": dict(getattr(ctx, "env_denoise", {}) or {}),
            "env_resolution": dict(getattr(ctx, "env_resolution", {}) or {}),
        },
    }


def write_repair_receipt(
    ctx: Any,
    *,
    model_name: str = "nexus-local-heal",
    reports_root: Path | None = None,
) -> Path:
    report_dir = (reports_root or (_nexus_root() / ".nexus/reports/local_heal")) / _safe_instance_id(getattr(ctx, "instance_id", ""))
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / "repro_evidence.log").write_text(str(getattr(ctx, "repro_evidence", "") or ""), encoding="utf-8")
    final_patch = str(getattr(ctx, "final_patch", "") or "")
    if final_patch:
        (report_dir / "patch.diff").write_text(final_patch, encoding="utf-8")
    evaluation_report = str(getattr(ctx, "evaluation_report", "") or "")
    if evaluation_report:
        (report_dir / "verification_report.txt").write_text(evaluation_report, encoding="utf-8")

    receipt = build_repair_receipt(ctx, model_name=model_name)
    receipt["evidence_refs"] = [item for item in receipt["evidence_refs"] if item]
    receipt_path = report_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_path
