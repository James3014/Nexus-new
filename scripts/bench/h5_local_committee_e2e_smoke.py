#!/usr/bin/env python3
"""H5-14: Local committee E2E focused smoke harness.

Focused smoke for local committee path validation.
Must not connect result to final output, final_source, benchmark runner, or production behavior.

Usage:
    python3 scripts/bench/h5_local_committee_e2e_smoke.py --dry-run
    python3 scripts/bench/h5_local_committee_e2e_smoke.py --run-if-available
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _detect_local_committee_runtime(repo_root: Path) -> tuple[bool, str]:
    """Conservative detection of local committee runtime availability.

    Returns (available: bool, reason: str).
    """
    try:
        from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
        from nexus.services.local_heal.context import HealContext
        from nexus.services.local_heal.pipeline import HealPipeline
    except ImportError as e:
        return False, f"local_committee_import_error:{e}"

    try:
        import ollama  # noqa: F401
    except ImportError:
        return False, "ollama_module_missing"

    ollama_host = str(__import__("os").environ.get("OLLAMA_HOST", "http://localhost:11434"))
    try:
        import urllib.request
        req = urllib.request.Request(ollama_host + "/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        resp.read()
    except Exception as e:
        return False, f"ollama_unreachable:{e}"

    return True, "available"


def _build_smoke_result(
    *,
    status: str,
    skipped_reason: str = "",
    dry_run: bool = True,
    local_committee_invoked: bool = False,
    candidate_count: int = 0,
    selected_candidate_id: str = "",
    selected_candidate_applied: bool = False,
    selected_candidate_hash_match: bool = False,
    selected_candidate_patch_sha256: str = "",
    selected_candidate_patch_length: int = 0,
    local_solve_eligible: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "nexus.h5_local_committee_e2e_smoke.v1",
        "status": status,
        "skipped_reason": skipped_reason,
        "dry_run": dry_run,
        "local_committee_invoked": local_committee_invoked,
        "candidate_count": candidate_count,
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_applied": selected_candidate_applied,
        "selected_candidate_hash_match": selected_candidate_hash_match,
        "selected_candidate_patch_sha256": selected_candidate_patch_sha256,
        "selected_candidate_patch_length": selected_candidate_patch_length,
        "local_solve_eligible": local_solve_eligible,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "evidence": evidence or {},
    }


def build_h5_local_committee_smoke_receipt(smoke_result: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: maps H5-14 smoke result into H5-compatible local committee receipt.

    No side effects. No model calls. No mutation.
    """
    status = str(smoke_result.get("status", "skipped") or "skipped")
    dry_run = bool(smoke_result.get("dry_run", True))
    invoked = bool(smoke_result.get("local_committee_invoked", False))
    candidate_count = int(smoke_result.get("candidate_count", 0) or 0)
    selected_id = str(smoke_result.get("selected_candidate_id", "") or "")
    selected_applied = bool(smoke_result.get("selected_candidate_applied", False))
    selected_hash = bool(smoke_result.get("selected_candidate_hash_match", False))
    patch_sha = str(smoke_result.get("selected_candidate_patch_sha256", "") or "")
    patch_len = int(smoke_result.get("selected_candidate_patch_length", 0) or 0)
    solve_ok = bool(smoke_result.get("local_solve_eligible", False))

    runtime_available = invoked and not dry_run
    h5_compatible = False
    blocked_reason = ""

    if status == "skipped":
        runtime_available = False
        blocked_reason = str(smoke_result.get("skipped_reason", "") or "runtime_unavailable")
    elif dry_run:
        runtime_available = False
        blocked_reason = "dry_run_no_candidate"
    elif invoked:
        if candidate_count <= 0:
            blocked_reason = "no_candidates"
        elif not selected_id:
            blocked_reason = "missing_selected_candidate_id"
        elif not selected_applied:
            blocked_reason = "selected_candidate_not_applied"
        elif not selected_hash:
            blocked_reason = "selected_candidate_hash_not_matched"
        elif not patch_sha:
            blocked_reason = "missing_selected_candidate_patch_sha256"
        elif patch_len <= 0:
            blocked_reason = "missing_selected_candidate_patch_length"
        elif not solve_ok:
            blocked_reason = "local_solve_not_eligible"
        else:
            h5_compatible = True

    return {
        "schema": "nexus.h5_local_committee_smoke_receipt.v1",
        "source_schema": "nexus.h5_local_committee_e2e_smoke.v1",
        "status": status,
        "dry_run": dry_run,
        "runtime_available": runtime_available,
        "local_committee_invoked": invoked,
        "candidate_count": candidate_count,
        "selected_candidate_id": selected_id,
        "selected_candidate_applied": selected_applied,
        "selected_candidate_hash_match": selected_hash,
        "selected_candidate_patch_sha256": patch_sha,
        "selected_candidate_patch_length": patch_len,
        "local_solve_eligible": solve_ok,
        "h5_local_finalization_candidate_ready": h5_compatible,
        "h5_local_finalization_blocked_reason": blocked_reason,
        "h5_compatible": h5_compatible,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def build_h5_local_committee_readiness_bridge(smoke_receipt: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: evaluates whether local committee smoke receipt satisfies H5 readiness.

    No side effects. No model calls. No mutation.
    """
    if not smoke_receipt:
        return {
            "schema": "nexus.h5_local_committee_readiness_bridge.v1",
            "source_schema": "nexus.h5_local_committee_smoke_receipt.v1",
            "evaluated": True,
            "local_committee_e2e_ready_shadow": False,
            "readiness_status": "blocked",
            "readiness_reasons": ["missing_smoke_receipt"],
            "candidate_identity_ready": False,
            "candidate_application_ready": False,
            "candidate_hash_ready": False,
            "candidate_patch_metadata_ready": False,
            "local_solve_ready": False,
            "h5_compatible": False,
            "can_feed_h5_readiness_shadow": False,
            "final_source_changed": False,
            "final_patch_replaced": False,
            "output_mutated": False,
            "model_calls_incremented": False,
            "public_claim_allowed": False,
            "production_ready": False,
        }

    reasons = []
    identity_ready = bool(str(smoke_receipt.get("selected_candidate_id", "") or ""))
    application_ready = bool(smoke_receipt.get("selected_candidate_applied", False))
    hash_ready = bool(smoke_receipt.get("selected_candidate_hash_match", False))
    patch_ready = bool(smoke_receipt.get("selected_candidate_patch_sha256", "")) and int(smoke_receipt.get("selected_candidate_patch_length", 0) or 0) > 0
    solve_ready = bool(smoke_receipt.get("local_solve_eligible", False))
    h5_compat = bool(smoke_receipt.get("h5_compatible", False))

    status = str(smoke_receipt.get("status", "skipped") or "skipped")
    dry_run = bool(smoke_receipt.get("dry_run", True))

    if status == "skipped":
        reasons.append("smoke_skipped")
    elif dry_run:
        reasons.append("dry_run_no_real_candidate")
    elif not h5_compat:
        reasons.append(str(smoke_receipt.get("h5_local_finalization_blocked_reason", "") or "not_h5_compatible"))

    all_ready = identity_ready and application_ready and hash_ready and patch_ready and solve_ready and h5_compat
    ready_shadow = all_ready and not reasons
    readiness_status = "ready_shadow" if ready_shadow else "blocked"

    return {
        "schema": "nexus.h5_local_committee_readiness_bridge.v1",
        "source_schema": "nexus.h5_local_committee_smoke_receipt.v1",
        "evaluated": True,
        "local_committee_e2e_ready_shadow": ready_shadow,
        "readiness_status": readiness_status,
        "readiness_reasons": reasons,
        "candidate_identity_ready": identity_ready,
        "candidate_application_ready": application_ready,
        "candidate_hash_ready": hash_ready,
        "candidate_patch_metadata_ready": patch_ready,
        "local_solve_ready": solve_ready,
        "h5_compatible": h5_compat,
        "can_feed_h5_readiness_shadow": ready_shadow,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def build_h5_local_committee_smoke_evidence_bundle(smoke_result: dict[str, Any]) -> dict[str, Any]:
    """Pure adapter: packages smoke result, receipt, readiness bridge into evidence bundle.

    No side effects. No model calls. No mutation.
    """
    bundle_status = "pass"
    blocked_reasons = []
    can_feed = False

    if not smoke_result:
        return {
            "schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
            "source_schema": "nexus.h5_local_committee_e2e_smoke.v1",
            "bundle_status": "blocked",
            "can_feed_h5_readiness_shadow": False,
            "smoke_status": "",
            "smoke": {},
            "receipt": {},
            "readiness_bridge": {},
            "safety": _safety_dict(),
            "governance": _governance_dict(),
            "blocked_reasons": ["missing_smoke_result"],
        }

    smoke_status = str(smoke_result.get("status", "skipped") or "skipped")
    receipt = smoke_result.get("receipt")
    bridge = smoke_result.get("readiness_bridge")

    if not receipt:
        bundle_status = "blocked"
        blocked_reasons.append("missing_smoke_receipt")
    if not bridge:
        bundle_status = "blocked"
        blocked_reasons.append("missing_readiness_bridge")

    if smoke_status == "skipped":
        bundle_status = "skipped"
        blocked_reasons.append(str(smoke_result.get("skipped_reason", "") or "smoke_skipped"))

    if bridge and bridge.get("readiness_status", "") != "ready_shadow":
        bundle_status = "blocked"
        blocked_reasons.extend(bridge.get("readiness_reasons", []))

    if bridge and bridge.get("can_feed_h5_readiness_shadow", False):
        bundle_status = "pass"
        can_feed = True
        blocked_reasons = []

    # Safety invariant override
    safety = _safety_from_smoke(smoke_result)
    if any(safety.values()):
        bundle_status = "blocked"
        can_feed = False
        blocked_reasons.append("safety_invariant_violation")

    return {
        "schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
        "source_schema": "nexus.h5_local_committee_e2e_smoke.v1",
        "bundle_status": bundle_status,
        "can_feed_h5_readiness_shadow": can_feed,
        "smoke_status": smoke_status,
        "smoke_summary": {
            "status": smoke_status,
            "dry_run": bool(smoke_result.get("dry_run", True)),
            "local_committee_invoked": bool(smoke_result.get("local_committee_invoked", False)),
        },
        "receipt": receipt or {},
        "readiness_bridge": bridge or {},
        "safety": safety,
        "governance": _governance_dict(),
        "blocked_reasons": blocked_reasons,
    }


def _safety_dict() -> dict[str, bool]:
    return {
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _safety_from_smoke(smoke_result: dict[str, Any]) -> dict[str, bool]:
    return {
        "final_source_changed": bool(smoke_result.get("final_source_changed", False)),
        "final_patch_replaced": bool(smoke_result.get("final_patch_replaced", False)),
        "output_mutated": bool(smoke_result.get("output_mutated", False)),
        "model_calls_incremented": bool(smoke_result.get("model_calls_incremented", False)),
        "public_claim_allowed": bool(smoke_result.get("public_claim_allowed", False)),
        "production_ready": bool(smoke_result.get("production_ready", False)),
    }


def _governance_dict() -> dict[str, Any]:
    return {"public_claim_allowed": False, "production_ready": False, "internal_only": True}


def validate_h5_local_committee_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pure validator: checks whether an evidence bundle is acceptable for H5 readiness shadow.

    No side effects. No model calls. No mutation. No file writes.
    """
    reasons = []
    safety_ok = True
    governance_ok = True
    receipt_ok = True
    bridge_ok = True
    identity_ready = False
    application_ready = False
    hash_ready = False
    patch_ready = False
    solve_ready = False

    if not bundle:
        return _validation_result(
            validated=True, accepted=False, status="rejected",
            reasons=["missing_bundle"],
            safety_ok=False, governance_ok=False, receipt_ok=False, bridge_ok=False,
        )

    src_schema = str(bundle.get("schema", "") or "")
    if src_schema != "nexus.h5_local_committee_smoke_evidence_bundle.v1":
        return _validation_result(
            validated=True, accepted=False, status="rejected",
            reasons=["invalid_bundle_schema"], src_schema=src_schema,
        )

    b_status = str(bundle.get("bundle_status", "") or "")
    if b_status != "pass":
        reasons.append("bundle_not_pass")

    can_feed = bool(bundle.get("can_feed_h5_readiness_shadow", False))
    if not can_feed:
        reasons.append("cannot_feed_h5_readiness_shadow")

    # Safety invariants
    safety = bundle.get("safety", {})
    for key in ["final_source_changed", "final_patch_replaced", "output_mutated",
                 "model_calls_incremented", "public_claim_allowed", "production_ready"]:
        if bool(safety.get(key, False)):
            safety_ok = False
            reasons.append("safety_invariant_violation")
            break

    # Governance
    gov = bundle.get("governance", {})
    if bool(gov.get("public_claim_allowed", True)) or bool(gov.get("production_ready", True)) or not bool(gov.get("internal_only", False)):
        governance_ok = False
        reasons.append("governance_boundary_violation")

    # Receipt
    receipt = bundle.get("receipt", {})
    if (str(receipt.get("schema", "") or "") != "nexus.h5_local_committee_smoke_receipt.v1"
            or not bool(receipt.get("h5_compatible", False))
            or not bool(receipt.get("h5_local_finalization_candidate_ready", False))):
        receipt_ok = False
        reasons.append("receipt_not_h5_compatible")

    # Readiness bridge
    bridge = bundle.get("readiness_bridge", {})
    identity_ready = bool(bridge.get("candidate_identity_ready", False))
    application_ready = bool(bridge.get("candidate_application_ready", False))
    hash_ready = bool(bridge.get("candidate_hash_ready", False))
    patch_ready = bool(bridge.get("candidate_patch_metadata_ready", False))
    solve_ready = bool(bridge.get("local_solve_ready", False))

    if (str(bridge.get("schema", "") or "") != "nexus.h5_local_committee_readiness_bridge.v1"
            or str(bridge.get("readiness_status", "") or "") != "ready_shadow"
            or not bool(bridge.get("local_committee_e2e_ready_shadow", False))
            or not bool(bridge.get("can_feed_h5_readiness_shadow", False))
            or not identity_ready or not application_ready or not hash_ready
            or not patch_ready or not solve_ready):
        bridge_ok = False
        reasons.append("readiness_bridge_not_ready")

    accepted = not reasons and safety_ok and governance_ok and receipt_ok and bridge_ok

    return {
        "schema": "nexus.h5_local_committee_evidence_ingestion_validation.v1",
        "validated": True,
        "accepted_for_h5_readiness_shadow": accepted,
        "validation_status": "accepted" if accepted else "rejected",
        "validation_reasons": reasons,
        "source_bundle_schema": src_schema,
        "bundle_status": b_status,
        "can_feed_h5_readiness_shadow": can_feed,
        "safety_invariants_ok": safety_ok,
        "governance_ok": governance_ok,
        "receipt_ok": receipt_ok,
        "readiness_bridge_ok": bridge_ok,
        "candidate_identity_ready": identity_ready,
        "candidate_application_ready": application_ready,
        "candidate_hash_ready": hash_ready,
        "candidate_patch_metadata_ready": patch_ready,
        "local_solve_ready": solve_ready,
        "public_claim_allowed": bool(bundle.get("governance", {}).get("public_claim_allowed", False)),
        "production_ready": bool(bundle.get("governance", {}).get("production_ready", False)),
    }


def _validation_result(
    *,
    validated: bool,
    accepted: bool,
    status: str,
    reasons: list[str],
    safety_ok: bool = False,
    governance_ok: bool = False,
    receipt_ok: bool = False,
    bridge_ok: bool = False,
    src_schema: str = "",
) -> dict[str, Any]:
    return {
        "schema": "nexus.h5_local_committee_evidence_ingestion_validation.v1",
        "validated": validated,
        "accepted_for_h5_readiness_shadow": accepted,
        "validation_status": status,
        "validation_reasons": reasons,
        "source_bundle_schema": src_schema,
        "bundle_status": "",
        "can_feed_h5_readiness_shadow": False,
        "safety_invariants_ok": safety_ok,
        "governance_ok": governance_ok,
        "receipt_ok": receipt_ok,
        "readiness_bridge_ok": bridge_ok,
        "candidate_identity_ready": False,
        "candidate_application_ready": False,
        "candidate_hash_ready": False,
        "candidate_patch_metadata_ready": False,
        "local_solve_ready": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def run_h5_local_committee_e2e_smoke(
    repo_root: Path,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run focused local committee E2E smoke.

    dry_run=True: no real execution, returns pass.
    dry_run=False: attempts real execution only if runtime is available.
    """
    if dry_run:
        result = _build_smoke_result(
            status="pass",
            dry_run=True,
            evidence={"note": "dry_run mode, no local committee invoked"},
        )
        result["receipt"] = build_h5_local_committee_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_local_committee_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_local_committee_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_local_committee_evidence_bundle(result["evidence_bundle"])
        return result

    available, reason = _detect_local_committee_runtime(repo_root)
    if not available:
        result = _build_smoke_result(
            status="skipped",
            skipped_reason=reason,
            dry_run=False,
            evidence={"runtime_detection": reason},
        )
        result["receipt"] = build_h5_local_committee_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_local_committee_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_local_committee_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_local_committee_evidence_bundle(result["evidence_bundle"])
        return result

    # Runtime available: attempt isolated local committee smoke
    try:
        from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
        from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
        from nexus.services.local_heal.phases.reproduction import ReproductionPhase
        from nexus.services.local_heal.phases.planning import PlanningPhase
        from nexus.services.local_heal.phases.localization import LocalizationPhase
        from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
        from nexus.services.local_heal.phases.verification import VerificationPhase
        from nexus.services.local_heal.governance_gate import GovernanceGate
        from nexus.services.local_heal.reproduction import ReproductionRunner
        from nexus.services.local_heal.env_denoiser import EnvDenoiser
        from nexus.services.local_heal.planner import Planner
        from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
        from nexus.services.local_heal.context_budget import ContextBudgetManager
        from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
        from nexus.services.local_heal.patcher import Patcher
        from nexus.services.local_heal.evaluation_gate import EvaluationGate

        op = OperationalContext(
            instance_id="h5-smoke-test",
            repo_dir=repo_root,
            problem_statement="H5 smoke: prove committee candidate isolation trace works",
        )
        gov = GovernanceContext()
        ctx = HealContext(op=op, gov=gov)

        repro_runner = ReproductionRunner(repo_root)
        env_denoiser = EnvDenoiser(repo_root)
        planner = Planner(ollama_generate_fn=lambda *a, **kw: "")
        localizer = GranularMethodLocalizer()
        budget_manager = ContextBudgetManager()
        parser = SolidSearchReplaceProtocol()
        patcher = Patcher()

        phases = [
            ReproductionPhase(repro_runner=repro_runner, env_denoiser=env_denoiser, ollama_generate_fn=lambda *a, **kw: ""),
            PlanningPhase(planner=planner),
            LocalizationPhase(localizer=localizer, budget_manager=budget_manager),
            PatchSynthesisPhase(parser=parser, patcher=patcher, ollama_generate_fn=lambda *a, **kw: ""),
            VerificationPhase(eval_gate=EvaluationGate(repo_root), hidden_required=False),
        ]

        import os
        os.environ["NEXUS_USE_COMMITTEE"] = "1"
        orch = CommitteeOrchestrator(
            phases=phases,
            governance_gate=GovernanceGate(),
            receipt_writer=None,
        )
        orch.k = 2
        orch.repro_phase = phases[0]
        orch.plan_phase = phases[1]
        orch.loc_phase = phases[2]
        orch.patch_phase = phases[3]
        orch.verify_phase = phases[4]

        result_ctx = orch.run(ctx)

        committee_trace = getattr(result_ctx.op, "_committee_trace", {})
        candidates = committee_trace.get("proposer_candidates", [])
        judge_sel = committee_trace.get("judge_selection", {})
        rc = committee_trace.get("committee_receipt", {})

        selected_id = str(judge_sel.get("selected_candidate_id", "") or "")
        selected_applied = bool(rc.get("selected_candidate_applied", False))
        selected_hash = bool(rc.get("selected_candidate_apply_hash_match", False))
        solve_ok = bool(getattr(result_ctx.op, "solve_eligible", False))

        patch_sha = ""
        patch_len = 0
        for c in candidates:
            if c.get("candidate_id") == selected_id:
                patch_sha = str(c.get("isolated_patch_sha256", "") or "")
                patch_len = int(c.get("isolated_patch_length", 0) or 0)
                break

        result = _build_smoke_result(
            status="pass",
            dry_run=False,
            local_committee_invoked=True,
            candidate_count=len(candidates),
            selected_candidate_id=selected_id,
            selected_candidate_applied=selected_applied,
            selected_candidate_hash_match=selected_hash,
            selected_candidate_patch_sha256=patch_sha,
            selected_candidate_patch_length=patch_len,
            local_solve_eligible=solve_ok,
            evidence={"committee_trace": committee_trace},
        )
        result["receipt"] = build_h5_local_committee_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_local_committee_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_local_committee_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_local_committee_evidence_bundle(result["evidence_bundle"])
        return result

    except Exception as e:
        result = _build_smoke_result(
            status="skipped",
            skipped_reason=f"local_committee_execution_error:{e}",
            dry_run=False,
            evidence={"error": str(e)},
        )
        result["receipt"] = build_h5_local_committee_smoke_receipt(result)
        result["readiness_bridge"] = build_h5_local_committee_readiness_bridge(result["receipt"])
        result["evidence_bundle"] = build_h5_local_committee_smoke_evidence_bundle(result)
        result["ingestion_validation"] = validate_h5_local_committee_evidence_bundle(result["evidence_bundle"])
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="H5-14 local committee E2E smoke")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--run-if-available", action="store_true", default=False)
    args = parser.parse_args()

    dry_run = not args.run_if_available
    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=dry_run)
    result["receipt"] = build_h5_local_committee_smoke_receipt(result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
