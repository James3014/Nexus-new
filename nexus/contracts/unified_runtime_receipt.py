"""Additive failure diagnostics for the UnifiedRuntime receipt contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

FAILURE_DIAGNOSTICS_SCHEMA = "nexus.unified_runtime.failure_diagnostics.v1"
FAILURE_CLASSES = frozenset(
    {
        "none",
        "authorization_blocked",
        "workforce_admission_blocked",
        "evidence_seal_blocked",
        "provider_unavailable",
        "provider_failed",
        "verifier_failed",
        "learning_failed",
        "capability_skipped",
        "capability_not_executed",
        "unknown_incomplete",
    }
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _stable_reason_code(value: Any, *, default: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if "authorization" in text or "not_authorized" in text or "unauthorized" in text:
        return "authorization"
    if "workforce" in text or "admission" in text:
        return "workforce_admission"
    if "seal" in text or ("evidence" in text and "fail" in text):
        return "evidence_seal"
    if "not_run" in text or "not requested" in text or "unavailable" in text:
        return "provider_unavailable"
    if "timeout" in text or "timed out" in text:
        return "provider_timeout"
    if "quota" in text or "balance" in text or "rate_limit" in text:
        return "provider_capacity"
    if "skipped" in text:
        return "policy_skip"
    if "selected_not_executed" in text or "not_executed" in text:
        return "selected_not_executed"
    if "verifier" in text:
        return "verifier"
    if "learning" in text:
        return "learning"
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:80] or default


def _failure_signal(receipt: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Return class, source stage, stable reason code, and provider identity."""
    terminal = str(receipt.get("terminal_status") or "").upper()
    closure_blockers = [str(item) for item in receipt.get("capability_closure_blockers", []) or []]
    if terminal == "SUCCEEDED" and not closure_blockers:
        return "none", "", "", ""
    if terminal == "BLOCKED":
        workforce = receipt.get("workforce_admission")
        if isinstance(workforce, Mapping) and str(workforce.get("overall_decision") or "").upper() in {"BLOCK", "ESCALATE"}:
            return "workforce_admission_blocked", "workforce_admission", "workforce_admission", ""
        seal = receipt.get("seal_verify")
        if isinstance(seal, Mapping) and seal.get("ok") is False:
            return "evidence_seal_blocked", "evidence_seal", "evidence_seal", ""

    if closure_blockers:
        blocker = closure_blockers[0]
        upper = blocker.upper()
        if "SKIPPED" in upper:
            return "capability_skipped", "capability_closure", _stable_reason_code(blocker, default="policy_skip"), ""
        if "SELECTED_NOT_EXECUTED" in upper or "INVOKED=FALSE" in upper:
            return "capability_not_executed", "capability_closure", "selected_not_executed", ""

    stages = [stage for stage in receipt.get("stages", []) or [] if isinstance(stage, Mapping)]
    for stage in stages:
        name = str(stage.get("name") or "")
        status = str(stage.get("status") or "").upper()
        reason = stage.get("reason") or stage.get("skip_reason") or ""
        if status == "SKIPPED" or bool(stage.get("skipped")):
            return "capability_skipped", name or "capability", _stable_reason_code(reason, default="policy_skip"), str(stage.get("provider") or "")
        if status == "SELECTED_NOT_EXECUTED":
            return "capability_not_executed", name or "capability", "selected_not_executed", str(stage.get("provider") or "")
        if name == "verifier" and (status not in {"SUCCEEDED", "PASS", "PASSED"} or not bool(stage.get("gate_passed"))):
            return "verifier_failed", name, _stable_reason_code(reason, default="verifier"), ""
        if name == "learning" and (status not in {"SUCCEEDED", "PASS", "PASSED"} or not bool(stage.get("gate_passed"))):
            return "learning_failed", name, _stable_reason_code(reason, default="learning"), ""
        if name in {"online", "local"} and status in {"FAILED", "BLOCKED", "NOT_RUN", "NOT_REQUESTED"}:
            reason_code = _stable_reason_code(reason, default="provider_failed" if status in {"FAILED", "BLOCKED"} else "provider_unavailable")
            failure_class = "provider_unavailable" if reason_code == "provider_unavailable" or status in {"NOT_RUN", "NOT_REQUESTED"} else "provider_failed"
            provider = str(stage.get("provider") or "")
            if not provider and isinstance(stage.get("response"), Mapping):
                provider = str(stage["response"].get("provider") or "")
            return failure_class, name, reason_code, provider

    if closure_blockers:
        blocker = closure_blockers[0]
        upper = blocker.upper()
        if "SKIPPED" in upper:
            return "capability_skipped", "capability_closure", _stable_reason_code(blocker, default="policy_skip"), ""
        if "SELECTED_NOT_EXECUTED" in upper or "INVOKED=FALSE" in upper:
            return "capability_not_executed", "capability_closure", "selected_not_executed", ""
        if "VERIFIER" in upper:
            return "verifier_failed", "capability_closure", "verifier", ""
        return "unknown_incomplete", "capability_closure", _stable_reason_code(blocker, default="closure_incomplete"), ""

    if terminal in {"INCOMPLETE", "FAILED", "BLOCKED"}:
        return "unknown_incomplete", "runtime", _stable_reason_code(receipt.get("reason"), default="incomplete"), ""
    return "none", "", "", ""


def _amplification_root_id(failure_class: str, source_stage: str, reason_code: str, provider: str) -> str:
    if failure_class == "none":
        return ""
    payload = {
        "schema": FAILURE_DIAGNOSTICS_SCHEMA,
        "failure_class": failure_class,
        "source_stage": source_stage,
        "reason_code": reason_code,
        "provider": provider,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_failure_diagnostics(receipt: Mapping[str, Any]) -> dict[str, Any]:
    failure_class, source_stage, reason_code, provider = _failure_signal(receipt)
    root_id = _amplification_root_id(failure_class, source_stage, reason_code, provider)
    return {
        "schema": FAILURE_DIAGNOSTICS_SCHEMA,
        "failure_class": failure_class,
        "amplification_root_id": root_id,
        "source_stage": source_stage,
        "reason_code": reason_code,
        "provider": provider,
        "grouping_scope": "cross_task_normalized_cause" if root_id else "none",
        "public_claim_allowed": False,
    }


def attach_failure_diagnostics(receipt: dict[str, Any]) -> dict[str, Any]:
    diagnostics = build_failure_diagnostics(receipt)
    receipt["failure_class"] = diagnostics["failure_class"]
    receipt["amplification_root_id"] = diagnostics["amplification_root_id"]
    receipt["failure_diagnostics"] = diagnostics
    return receipt


def validate_failure_diagnostics(receipt: Mapping[str, Any]) -> list[str]:
    diagnostics = receipt.get("failure_diagnostics")
    blockers: list[str] = []
    if not isinstance(diagnostics, Mapping):
        return ["failure_diagnostics_missing"]
    if diagnostics.get("schema") != FAILURE_DIAGNOSTICS_SCHEMA:
        blockers.append("failure_diagnostics_schema_invalid")
    failure_class = str(receipt.get("failure_class") or "")
    if failure_class not in FAILURE_CLASSES:
        blockers.append("failure_class_invalid")
    if diagnostics.get("failure_class") != failure_class:
        blockers.append("failure_class_projection_mismatch")
    root_id = str(receipt.get("amplification_root_id") or "")
    if diagnostics.get("amplification_root_id") != root_id:
        blockers.append("amplification_root_projection_mismatch")
    if failure_class == "none":
        if root_id:
            blockers.append("success_amplification_root_must_be_empty")
    elif not _SHA256_RE.fullmatch(root_id):
        blockers.append("failure_amplification_root_invalid")
    if diagnostics.get("public_claim_allowed") is not False:
        blockers.append("failure_diagnostics_claim_boundary_open")
    return sorted(set(blockers))


__all__ = [
    "FAILURE_CLASSES",
    "FAILURE_DIAGNOSTICS_SCHEMA",
    "attach_failure_diagnostics",
    "build_failure_diagnostics",
    "validate_failure_diagnostics",
]
