#!/usr/bin/env python3
"""P0-T5B Real Provider Canary Operator.

Executes a bounded two-attempt real-provider lifecycle using the existing
UnifiedRuntime, verifying physical process evidence, strict receipt lineage,
and worktree isolation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping

# Ensure repo root is on sys.path
repo_root = str(Path(__file__).resolve().parents[2])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from nexus.evidence.receipt_base import validate_receipt_base
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    build_registered_online_invoker,
)

ALLOWED_PROVIDERS = {"opencode", "gemini"}


def get_git_status(project_root: str) -> str:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return str(res.stdout or "")


def get_provider_version(provider: str) -> str:
    binary = shutil.which(provider)
    if not binary:
        return "not_found"
    try:
        res = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return str(res.stdout or res.stderr or "unknown").strip()
    except Exception:
        return "unknown"


def run_canary_campaign(
    provider: str,
    project_root: str,
    receipt_dir: str,
    timeout_sec: float = 120.0,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    if os.environ.get("NEXUS_P0T5_ALLOW_REAL_PROVIDER") != "1":
        sys.stderr.write("real_provider_canary_not_authorized\n")
        raise RuntimeError("real_provider_canary_not_authorized")

    prov_clean = str(provider or "").strip().lower()
    if prov_clean not in ALLOWED_PROVIDERS:
        sys.stderr.write(f"provider_not_allowed:{prov_clean}\n")
        raise ValueError(f"provider_not_allowed:{prov_clean}")

    project_root_path = Path(project_root).resolve()
    receipt_dir_path = Path(receipt_dir).resolve()
    receipt_dir_path.mkdir(parents=True, exist_ok=True)

    # Worktree status before
    status_before = get_git_status(str(project_root_path))
    hash_before = hashlib.sha256(status_before.encode("utf-8")).hexdigest()

    temp_cwd = tempfile.mkdtemp(prefix="nexus-p0t5b-cwd-")
    try:
        nonce = uuid.uuid4().hex
        canary_prompt = (
            "This is a read-only Nexus transport canary.\n\n"
            "Do not inspect, read, write, edit, execute, list, search, or mention any file.\n"
            "Do not use tools.\n"
            "Do not access the current project.\n"
            "Do not provide explanations.\n\n"
            f"Return exactly one line:\n\nNEXUS_CANARY:{nonce}"
        )

        online_invoker = build_registered_online_invoker(
            provider=prov_clean,
            timeout_sec=timeout_sec,
            runner=runner,
            working_directory=temp_cwd,
        )

        task_id = f"canary-{prov_clean}-{nonce[:8]}"
        req = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision="rev-canary-1",
            task_statement=canary_prompt,
            task_type="public_bugfix",
            route={
                "execution_depth": "LIGHT",
                "recommended_flow": "baseline",
                "route_features": {"risk_score": 10},
                "capability_stack": {"selected_capabilities": ["baseline"]},
            },
            online_enabled=True,
            local_enabled=False,
        )

        runtime = UnifiedRuntime()

        def _make_cap_invoker(name: str):
            return lambda ctx: {
                "status": "SUCCEEDED",
                "invoked": True,
                "evidence": "canary cap ok",
                "evidence_refs": [f"c:{name}:ok"],
                "gate_passed": True,
                "outcome_contributed": True,
            }

        all_caps = [
            "baseline",
            "harness_preflight_sensor",
            "delivery_gate",
            "mempalace_gate",
            "artifact_gate",
            "claim_gate",
        ]
        cap_invokers = {name: _make_cap_invoker(name) for name in all_caps}

        receipt1_path = receipt_dir_path / f"{task_id}_attempt1.json"
        receipt2_path = receipt_dir_path / f"{task_id}_attempt2.json"

        def verifier_attempt1(ctx: Mapping[str, Any]) -> dict[str, Any]:
            online_stg = ctx.get("online") or {}
            online_resp = online_stg.get("response") if isinstance(online_stg.get("response"), Mapping) else {}
            proc_ev = online_resp.get("process_evidence") if isinstance(online_resp.get("process_evidence"), Mapping) else {}

            if not online_stg.get("invoked"):
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "provider_not_invoked"}

            if not online_resp.get("output_delivered"):
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "output_not_delivered"}

            if proc_ev.get("schema") != "nexus.provider_process_evidence.v1":
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "invalid_process_evidence"}

            raw_out = str(online_resp.get("raw_response") or "")
            if nonce not in raw_out:
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "nonce_mismatch_or_missing"}

            # Verified output delivery -> forced trusted failure to trigger replan
            return {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": False,
                "status": "FAILED",
                "evidence": "p0t5_canary_forced_replan_after_provider_delivery",
                "evidence_refs": ["canary:provider_output_verified", "canary:forced_replan"],
            }

        # Attempt 1 execution
        r1 = runtime.run(
            req,
            online_invoker=online_invoker,
            capability_invokers=cap_invokers,
            verifier=verifier_attempt1,
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l1", "evidence_refs": ["l:1"], "gate_passed": True},
            receipt_path=receipt1_path,
        )

        v1_check = validate_receipt_base(r1, mode="strict")
        if not v1_check.get("ok"):
            raise RuntimeError(f"Attempt 1 strict receipt validation failed: {v1_check.get('blockers')}")

        if r1.get("terminal_status") != "INCOMPLETE":
            raise RuntimeError(f"Attempt 1 terminal status unexpected: {r1.get('terminal_status')}")

        previous_receipt = json.loads(receipt1_path.read_text(encoding="utf-8"))

        def verifier_attempt2(ctx: Mapping[str, Any]) -> dict[str, Any]:
            online_stg = ctx.get("online") or {}
            online_resp = online_stg.get("response") if isinstance(online_stg.get("response"), Mapping) else {}
            proc_ev = online_resp.get("process_evidence") if isinstance(online_resp.get("process_evidence"), Mapping) else {}

            if not online_stg.get("invoked") or not online_resp.get("output_delivered"):
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "attempt2_delivery_failed"}

            if proc_ev.get("schema") != "nexus.provider_process_evidence.v1":
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "attempt2_invalid_evidence"}

            raw_out = str(online_resp.get("raw_response") or "")
            if nonce not in raw_out:
                return {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "attempt2_nonce_missing"}

            return {
                "task_id": ctx["task_id"],
                "invoked": True,
                "gate_passed": True,
                "status": "SUCCEEDED",
                "evidence": "p0t5_canary_attempt_2_pass",
                "evidence_refs": ["canary:attempt2_verified"],
            }

        # Attempt 2 execution
        r2 = runtime.run_replan(
            previous_receipt,
            req,
            online_invoker=online_invoker,
            capability_invokers=cap_invokers,
            verifier=verifier_attempt2,
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l2", "evidence_refs": ["l:2"], "gate_passed": True},
            receipt_path=receipt2_path,
        )

        v2_check = validate_receipt_base(r2, mode="strict")
        if not v2_check.get("ok"):
            raise RuntimeError(f"Attempt 2 strict receipt validation failed: {v2_check.get('blockers')}")

        if r2.get("terminal_status") != "SUCCEEDED":
            raise RuntimeError(f"Attempt 2 terminal status unexpected: {r2.get('terminal_status')}")

        # Worktree status after
        status_after = get_git_status(str(project_root_path))
        hash_after = hashlib.sha256(status_after.encode("utf-8")).hexdigest()

        if status_before != status_after:
            raise RuntimeError("TASK_BLOCK: REAL_PROVIDER_MUTATED_WORKTREE")

        pe1 = r1["online"]["response"]["process_evidence"]
        pe2 = r2["online"]["response"]["process_evidence"]

        summary = {
            "campaign_id": f"campaign-{task_id}",
            "provider": prov_clean,
            "provider_version": get_provider_version(prov_clean),
            "real_provider_call_count": 2,
            "attempt_1_process_invocation_id": pe1["process_invocation_id"],
            "attempt_2_process_invocation_id": pe2["process_invocation_id"],
            "attempt_1_stdout_sha256": pe1["stdout_sha256"],
            "attempt_2_stdout_sha256": pe2["stdout_sha256"],
            "attempt_1_receipt_hash": r1["receipt_base"]["receipt_hash"],
            "attempt_2_receipt_hash": r2["receipt_base"]["receipt_hash"],
            "attempt_1_run_anchor_hash": r1["receipt_base"]["run_anchor_hash"],
            "attempt_2_run_anchor_hash": r2["receipt_base"]["run_anchor_hash"],
            "attempt_1_planner_decision_id": r1["planner_decision_id"],
            "attempt_2_planner_decision_id": r2["planner_decision_id"],
            "attempt_1_execution_depth": r1["execution_depth"],
            "attempt_2_execution_depth": r2["execution_depth"],
            "source_replan_request_id": r1["execution_replan_request"]["replan_request_id"],
            "parent_receipt_hash": r2["execution_attempt"]["parent_receipt_hash"],
            "worktree_status_before_hash": hash_before,
            "worktree_status_after_hash": hash_after,
            "worktree_unchanged": hash_before == hash_after,
            "both_strict_validations": bool(v1_check.get("ok") and v2_check.get("ok")),
        }
        return summary
    finally:
        shutil.rmtree(temp_cwd, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="P0-T5B Real Provider Canary Operator")
    parser.add_argument("--provider", default="opencode", choices=["opencode", "gemini"])
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    args = parser.parse_args()

    try:
        summary = run_canary_campaign(
            provider=args.provider,
            project_root=args.project_root,
            receipt_dir=args.receipt_dir,
            timeout_sec=args.timeout_sec,
        )
        print(json.dumps(summary, indent=2))
        sys.exit(0)
    except Exception as exc:
        sys.stderr.write(f"CANARY_CAMPAIGN_FAILED: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
