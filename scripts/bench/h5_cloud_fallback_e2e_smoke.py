#!/usr/bin/env python3
"""H5-20: Cloud fallback focused smoke harness.

Focused smoke for cloud fallback path validation.
Must not connect result to benchmark runner output, final_source, or production behavior.

Usage:
    python3 scripts/bench/h5_cloud_fallback_e2e_smoke.py --dry-run --provider gemini
    python3 scripts/bench/h5_cloud_fallback_e2e_smoke.py --run-if-allowed --provider gemini
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SUPPORTED_PROVIDERS = {"gemini", "codex"}


def run_h5_cloud_fallback_e2e_smoke(
    *,
    provider: str = "gemini",
    dry_run: bool = True,
    allow_real_call: bool = False,
) -> dict[str, Any]:
    """Run focused cloud fallback E2E smoke.

    dry_run=True by default. allow_real_call=False by default.
    Real cloud calls require both allow_real_call=True and env var.
    """
    if provider not in SUPPORTED_PROVIDERS:
        result = _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=dry_run,
            allow_real_call=allow_real_call,
            skipped_reason="unsupported_provider",
        )
        result["receipt"] = build_h5_cloud_fallback_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_cloud_fallback_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_cloud_fallback_evidence_bundle(result["evidence_bundle"])
        return result

    if dry_run:
        result = _build_cloud_smoke_result(
            status="pass",
            provider=provider,
            dry_run=True,
            allow_real_call=False,
            cloud_fallback_would_invoke=True,
            model_calls_before=0,
            model_calls_after_shadow=1,
            evidence={"note": "dry_run mode, no cloud provider called"},
        )
        result["receipt"] = build_h5_cloud_fallback_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_cloud_fallback_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_cloud_fallback_evidence_bundle(result["evidence_bundle"])
        return result

    if not allow_real_call:
        result = _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=False,
            allow_real_call=False,
            skipped_reason="real_cloud_call_not_allowed",
        )
        result["receipt"] = build_h5_cloud_fallback_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_cloud_fallback_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_cloud_fallback_evidence_bundle(result["evidence_bundle"])
        return result

    env_enabled = os.environ.get("NEXUS_H5_ALLOW_REAL_CLOUD_SMOKE", "").strip() in {"1", "true", "yes"}
    if not env_enabled:
        result = _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=False,
            allow_real_call=True,
            real_call_env_enabled=False,
            skipped_reason="real_cloud_call_env_not_enabled",
        )
        result["receipt"] = build_h5_cloud_fallback_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_cloud_fallback_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_cloud_fallback_evidence_bundle(result["evidence_bundle"])
        return result

    # Real call path — not implemented in this phase
    result = _build_cloud_smoke_result(
        status="skipped",
        provider=provider,
        dry_run=False,
        allow_real_call=True,
        real_call_env_enabled=True,
        skipped_reason="real_cloud_call_not_implemented",
        evidence={"note": "real cloud call path not yet implemented"},
    )
    result["receipt"] = build_h5_cloud_fallback_smoke_receipt(result)
    result["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(result["receipt"])
    result["evidence_bundle"] = build_h5_cloud_fallback_smoke_evidence_bundle(result)
    result["ingestion_validation"] = validate_h5_cloud_fallback_evidence_bundle(result["evidence_bundle"])
    return result


def _build_cloud_smoke_result(
    *,
    status: str,
    provider: str,
    dry_run: bool,
    allow_real_call: bool,
    real_call_env_enabled: bool = False,
    skipped_reason: str = "",
    cloud_fallback_would_invoke: bool = False,
    model_calls_before: int = 0,
    model_calls_after_shadow: int = 0,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "nexus.h5_cloud_fallback_e2e_smoke.v1",
        "status": status,
        "skipped_reason": skipped_reason,
        "provider": provider,
        "dry_run": dry_run,
        "allow_real_call": allow_real_call,
        "real_call_env_enabled": real_call_env_enabled,
        "cloud_fallback_would_invoke": cloud_fallback_would_invoke,
        "cloud_fallback_invoked": False,
        "cloud_model_invoked": False,
        "cloud_output_captured": False,
        "cloud_output_verified": False,
        "model_calls_before": model_calls_before,
        "model_calls_after_shadow": model_calls_after_shadow,
        "model_calls_incremented": False,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "evidence": evidence or {},
    }


def build_h5_cloud_fallback_smoke_receipt(smoke_result: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: maps H5-20 cloud smoke result into H5-compatible receipt.

    No side effects. No model calls. No mutation.
    """
    status = str(smoke_result.get("status", "skipped") or "skipped")
    dry_run = bool(smoke_result.get("dry_run", True))
    provider = str(smoke_result.get("provider", "") or "")
    invoked = bool(smoke_result.get("cloud_fallback_invoked", False))
    model_invoked = bool(smoke_result.get("cloud_model_invoked", False))
    output_captured = bool(smoke_result.get("cloud_output_captured", False))
    output_verified = bool(smoke_result.get("cloud_output_verified", False))
    mb = int(smoke_result.get("model_calls_before", 0) or 0)
    ma = int(smoke_result.get("model_calls_after_shadow", 0) or 0)
    mi = bool(smoke_result.get("model_calls_incremented", False))
    fsc = bool(smoke_result.get("final_source_changed", False))
    fpr = bool(smoke_result.get("final_patch_replaced", False))
    om = bool(smoke_result.get("output_mutated", False))

    runtime_available = invoked and not dry_run
    h5_compatible = False
    blocked = ""

    if status == "skipped":
        runtime_available = False
        blocked = str(smoke_result.get("skipped_reason", "") or "runtime_unavailable")
    elif dry_run:
        runtime_available = False
        blocked = "dry_run_no_cloud_output"
    elif invoked:
        reasons = []
        if not model_invoked:
            reasons.append("cloud_model_not_invoked")
        if not output_captured:
            reasons.append("cloud_output_not_captured")
        if not output_verified:
            reasons.append("cloud_output_not_verified")
        if ma != mb + 1:
            reasons.append("model_call_shadow_accounting_invalid")
        if mi:
            reasons.append("model_calls_incremented_unexpectedly")
        if fsc:
            reasons.append("final_source_changed_unexpectedly")
        if fpr:
            reasons.append("final_patch_replaced_unexpectedly")
        if om:
            reasons.append("output_mutated_unexpectedly")
        if reasons:
            blocked = reasons[0]
        else:
            h5_compatible = True

    return {
        "schema": "nexus.h5_cloud_fallback_smoke_receipt.v1",
        "source_schema": "nexus.h5_cloud_fallback_e2e_smoke.v1",
        "status": status,
        "provider": provider,
        "dry_run": dry_run,
        "runtime_available": runtime_available,
        "cloud_fallback_would_invoke": bool(smoke_result.get("cloud_fallback_would_invoke", False)),
        "cloud_fallback_invoked": invoked,
        "cloud_model_invoked": model_invoked,
        "cloud_output_captured": output_captured,
        "cloud_output_verified": output_verified,
        "model_calls_before": mb,
        "model_calls_after_shadow": ma,
        "model_calls_incremented": mi,
        "h5_cloud_fallback_compatible": h5_compatible,
        "h5_cloud_fallback_ready_shadow": h5_compatible,
        "h5_cloud_fallback_blocked_reason": blocked,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def build_h5_cloud_fallback_readiness_bridge(cloud_receipt: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: evaluates cloud fallback receipt for H5 readiness.

    No side effects. No model calls. No mutation.
    """
    if not cloud_receipt:
        return {
            "schema": "nexus.h5_cloud_fallback_readiness_bridge.v1",
            "source_schema": "nexus.h5_cloud_fallback_smoke_receipt.v1",
            "evaluated": True,
            "cloud_fallback_e2e_ready_shadow": False,
            "readiness_status": "blocked",
            "readiness_reasons": ["missing_cloud_smoke_receipt"],
            "provider_ready": False,
            "cloud_invocation_ready": False,
            "cloud_output_capture_ready": False,
            "cloud_output_verification_ready": False,
            "model_call_accounting_ready": False,
            "h5_cloud_fallback_compatible": False,
            "can_feed_h5_readiness_shadow": False,
            "final_source_changed": False,
            "final_patch_replaced": False,
            "output_mutated": False,
            "model_calls_incremented": False,
            "public_claim_allowed": False,
            "production_ready": False,
        }

    reasons = []
    status = str(cloud_receipt.get("status", "skipped") or "skipped")
    dry_run = bool(cloud_receipt.get("dry_run", True))
    provider = str(cloud_receipt.get("provider", "") or "")
    invoked = bool(cloud_receipt.get("cloud_fallback_invoked", False))
    model_inv = bool(cloud_receipt.get("cloud_model_invoked", False))
    captured = bool(cloud_receipt.get("cloud_output_captured", False))
    verified = bool(cloud_receipt.get("cloud_output_verified", False))
    mb = int(cloud_receipt.get("model_calls_before", 0) or 0)
    ma = int(cloud_receipt.get("model_calls_after_shadow", 0) or 0)
    mi = bool(cloud_receipt.get("model_calls_incremented", False))
    compatible = bool(cloud_receipt.get("h5_cloud_fallback_compatible", False))

    provider_ready = provider in {"gemini", "codex"}
    invocation_ready = invoked and model_inv
    capture_ready = captured
    verify_ready = verified
    accounting_ready = (ma == mb + 1) and not mi

    if status == "skipped":
        reasons.append("cloud_smoke_skipped")
    if dry_run:
        reasons.append("dry_run_no_real_cloud_output")
    if not compatible:
        reasons.append(str(cloud_receipt.get("h5_cloud_fallback_blocked_reason", "") or "not_h5_cloud_fallback_compatible"))

    all_ready = provider_ready and invocation_ready and capture_ready and verify_ready and accounting_ready and compatible
    ready_shadow = all_ready and not reasons
    readiness_status = "ready_shadow" if ready_shadow else "blocked"

    return {
        "schema": "nexus.h5_cloud_fallback_readiness_bridge.v1",
        "source_schema": "nexus.h5_cloud_fallback_smoke_receipt.v1",
        "evaluated": True,
        "cloud_fallback_e2e_ready_shadow": ready_shadow,
        "readiness_status": readiness_status,
        "readiness_reasons": reasons,
        "provider_ready": provider_ready,
        "cloud_invocation_ready": invocation_ready,
        "cloud_output_capture_ready": capture_ready,
        "cloud_output_verification_ready": verify_ready,
        "model_call_accounting_ready": accounting_ready,
        "h5_cloud_fallback_compatible": compatible,
        "can_feed_h5_readiness_shadow": ready_shadow,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def build_h5_cloud_fallback_smoke_evidence_bundle(smoke_result: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: packages cloud smoke result into evidence bundle.

    No side effects. No model calls. No mutation.
    """
    bundle_status = "pass"
    blocked_reasons = []

    if not smoke_result:
        return _cloud_bundle_result("blocked", False, [], smoke_result or {})

    smoke_status = str(smoke_result.get("status", "skipped") or "skipped")
    receipt = smoke_result.get("receipt")
    bridge = smoke_result.get("readiness_bridge")

    if not receipt:
        bundle_status = "blocked"
        blocked_reasons.append("missing_cloud_smoke_receipt")
    if not bridge:
        bundle_status = "blocked"
        blocked_reasons.append("missing_cloud_readiness_bridge")

    if smoke_status == "skipped":
        bundle_status = "skipped"
        blocked_reasons.append(str(smoke_result.get("skipped_reason", "") or "cloud_smoke_skipped"))

    if bridge and bridge.get("readiness_status", "") != "ready_shadow":
        bundle_status = "blocked"
        blocked_reasons.extend(bridge.get("readiness_reasons", []))

    if bridge and bridge.get("can_feed_h5_readiness_shadow", False):
        bundle_status = "pass"
        blocked_reasons = []

    safety = _cloud_safety_from_smoke(smoke_result)
    if any(safety.values()):
        bundle_status = "blocked"
        blocked_reasons.append("safety_invariant_violation")

    can_feed = bundle_status == "pass" and not blocked_reasons
    return _cloud_bundle_result(bundle_status, can_feed, blocked_reasons, smoke_result)


def _cloud_bundle_result(status: str, can_feed: bool, reasons: list[str], smoke: dict[str, Any]) -> dict[str, Any]:
    safety = _cloud_safety_from_smoke(smoke)
    return {
        "schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
        "source_schema": "nexus.h5_cloud_fallback_e2e_smoke.v1",
        "bundle_status": status,
        "can_feed_h5_readiness_shadow": can_feed,
        "smoke_status": str(smoke.get("status", "skipped") or "skipped"),
        "smoke_summary": {
            "status": str(smoke.get("status", "skipped") or "skipped"),
            "provider": str(smoke.get("provider", "") or ""),
            "dry_run": bool(smoke.get("dry_run", True)),
            "cloud_fallback_invoked": bool(smoke.get("cloud_fallback_invoked", False)),
        },
        "receipt": smoke.get("receipt") or {},
        "readiness_bridge": smoke.get("readiness_bridge") or {},
        "safety": safety,
        "governance": {"public_claim_allowed": False, "production_ready": False, "internal_only": True},
        "blocked_reasons": reasons,
    }


def _cloud_safety_from_smoke(smoke: dict[str, Any]) -> dict[str, bool]:
    return {
        "final_source_changed": bool(smoke.get("final_source_changed", False)),
        "final_patch_replaced": bool(smoke.get("final_patch_replaced", False)),
        "output_mutated": bool(smoke.get("output_mutated", False)),
        "model_calls_incremented": bool(smoke.get("model_calls_incremented", False)),
        "public_claim_allowed": bool(smoke.get("public_claim_allowed", False)),
        "production_ready": bool(smoke.get("production_ready", False)),
    }


def validate_h5_cloud_fallback_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pure validator: checks cloud evidence bundle for H5 readiness shadow.

    No side effects. No model calls. No mutation.
    """
    reasons = []

    if not bundle:
        return _cloud_validation_result(["missing_bundle"])

    src = str(bundle.get("schema", "") or "")
    if src != "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1":
        return _cloud_validation_result(["invalid_bundle_schema"], src)

    b_status = str(bundle.get("bundle_status", "") or "")
    if b_status != "pass":
        reasons.append("bundle_not_pass")

    can_feed = bool(bundle.get("can_feed_h5_readiness_shadow", False))
    if not can_feed:
        reasons.append("cannot_feed_h5_readiness_shadow")

    safety = bundle.get("safety", {})
    for key in ["final_source_changed", "final_patch_replaced", "output_mutated",
                 "model_calls_incremented", "public_claim_allowed", "production_ready"]:
        if bool(safety.get(key, False)):
            reasons.append("safety_invariant_violation")
            break

    gov = bundle.get("governance", {})
    if bool(gov.get("public_claim_allowed", True)) or bool(gov.get("production_ready", True)) or not bool(gov.get("internal_only", False)):
        reasons.append("governance_boundary_violation")

    receipt = bundle.get("receipt", {})
    if (str(receipt.get("schema", "") or "") != "nexus.h5_cloud_fallback_smoke_receipt.v1"
            or not bool(receipt.get("h5_cloud_fallback_compatible", False))
            or not bool(receipt.get("h5_cloud_fallback_ready_shadow", False))):
        reasons.append("receipt_not_h5_cloud_fallback_compatible")

    bridge = bundle.get("readiness_bridge", {})
    if (str(bridge.get("schema", "") or "") != "nexus.h5_cloud_fallback_readiness_bridge.v1"
            or str(bridge.get("readiness_status", "") or "") != "ready_shadow"
            or not bool(bridge.get("cloud_fallback_e2e_ready_shadow", False))
            or not bool(bridge.get("can_feed_h5_readiness_shadow", False))
            or not bool(bridge.get("provider_ready", False))
            or not bool(bridge.get("cloud_invocation_ready", False))
            or not bool(bridge.get("cloud_output_capture_ready", False))
            or not bool(bridge.get("cloud_output_verification_ready", False))
            or not bool(bridge.get("model_call_accounting_ready", False))):
        reasons.append("readiness_bridge_not_ready")

    accepted = not reasons

    return {
        "schema": "nexus.h5_cloud_fallback_evidence_ingestion_validation.v1",
        "validated": True,
        "accepted_for_h5_readiness_shadow": accepted,
        "validation_status": "accepted" if accepted else "rejected",
        "validation_reasons": reasons,
        "source_bundle_schema": src,
        "bundle_status": b_status,
        "can_feed_h5_readiness_shadow": can_feed,
        "safety_invariants_ok": not any(reasons),
        "governance_ok": not any("governance_boundary_violation" in r for r in reasons),
        "receipt_ok": not any("receipt_not_h5_cloud_fallback_compatible" in r for r in reasons),
        "readiness_bridge_ok": not any("readiness_bridge_not_ready" in r for r in reasons),
        "provider_ready": bool(bridge.get("provider_ready", False)),
        "cloud_invocation_ready": bool(bridge.get("cloud_invocation_ready", False)),
        "cloud_output_capture_ready": bool(bridge.get("cloud_output_capture_ready", False)),
        "cloud_output_verification_ready": bool(bridge.get("cloud_output_verification_ready", False)),
        "model_call_accounting_ready": bool(bridge.get("model_call_accounting_ready", False)),
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _cloud_validation_result(reasons: list[str], src_schema: str = "") -> dict[str, Any]:
    return {
        "schema": "nexus.h5_cloud_fallback_evidence_ingestion_validation.v1",
        "validated": True,
        "accepted_for_h5_readiness_shadow": False,
        "validation_status": "rejected",
        "validation_reasons": reasons,
        "source_bundle_schema": src_schema,
        "bundle_status": "",
        "can_feed_h5_readiness_shadow": False,
        "safety_invariants_ok": False,
        "governance_ok": False,
        "receipt_ok": False,
        "readiness_bridge_ok": False,
        "provider_ready": False,
        "cloud_invocation_ready": False,
        "cloud_output_capture_ready": False,
        "cloud_output_verification_ready": False,
        "model_call_accounting_ready": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="H5-20 cloud fallback E2E smoke")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--run-if-allowed", action="store_true", default=False)
    parser.add_argument("--provider", default="gemini", choices=["gemini", "codex"])
    args = parser.parse_args()

    dry_run = not args.run_if_allowed
    result = run_h5_cloud_fallback_e2e_smoke(
        provider=args.provider,
        dry_run=dry_run,
        allow_real_call=args.run_if_allowed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
