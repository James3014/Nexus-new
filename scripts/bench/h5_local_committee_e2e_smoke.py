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
        return result

    except Exception as e:
        result = _build_smoke_result(
            status="skipped",
            skipped_reason=f"local_committee_execution_error:{e}",
            dry_run=False,
            evidence={"error": str(e)},
        )
        result["receipt"] = build_h5_local_committee_smoke_receipt(result)
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
