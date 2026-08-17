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

from nexus.evidence.receipt_base import validate_receipt_base  # noqa: E402
from nexus.services.mainchain_entry import summarize_arm_receipt  # noqa: E402
from nexus.services.unified_runtime import (  # noqa: E402
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    build_registered_online_invoker,  # noqa: F401
    build_subprocess_online_invoker,
    resolve_registered_online_cli_spec,
)

ALLOWED_PROVIDERS = {"opencode"}
CANONICAL_WORKFORCE_BINDING = {
    "worker_id": "opencode_deepseek_v4_flash",
    "provider": "opencode",
    "model": "opencode/deepseek-v4-flash-free",
    "controls": (
        "isolated_directory",
        "bounded_context",
        "json_event_receipt",
        "parser",
        "focused_tests",
        "verifier",
    ),
}


def _canonical_workforce_binding(provider: str) -> dict[str, Any]:
    """Return the sole enrolled read-only canary binding or fail closed."""
    if str(provider).strip().lower() != CANONICAL_WORKFORCE_BINDING["provider"]:
        raise ValueError("workforce_binding_provider_mismatch")
    return {
        "worker_id": CANONICAL_WORKFORCE_BINDING["worker_id"],
        "provider": CANONICAL_WORKFORCE_BINDING["provider"],
        "model": CANONICAL_WORKFORCE_BINDING["model"],
        "controls": list(CANONICAL_WORKFORCE_BINDING["controls"]),
    }


def _assert_canonical_admission(receipt: Mapping[str, Any], attempt: int) -> None:
    admission = receipt.get("workforce_admission")
    if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
        raise RuntimeError(f"workforce_admission_not_allow:attempt{attempt}")
    records = admission.get("records")
    if not isinstance(records, list) or len(records) != 1:
        raise RuntimeError(f"workforce_admission_record_invalid:attempt{attempt}")
    record = records[0]
    decision = record.get("decision") if isinstance(record, Mapping) else None
    expected = _canonical_workforce_binding("opencode")
    if not isinstance(decision, Mapping) or decision.get("decision") != "ALLOW":
        raise RuntimeError(f"workforce_admission_record_not_allow:attempt{attempt}")
    for field, expected_value in (
        ("resolved_worker_id", expected["worker_id"]),
        ("resolved_provider", expected["provider"]),
        ("resolved_model", expected["model"]),
    ):
        if decision.get(field) != expected_value:
            raise RuntimeError(f"workforce_admission_{field}_mismatch:attempt{attempt}")


def _assert_non_invoked_admission_terminal(
    receipt: Mapping[str, Any], attempt: int
) -> None:
    """Validate a non-admitted attempt without granting replan authority."""
    admission = receipt.get("workforce_admission")
    decision = admission.get("overall_decision") if isinstance(admission, Mapping) else ""
    expected_status = {"BLOCK": "BLOCKED", "ESCALATE": "INCOMPLETE"}.get(str(decision))
    if expected_status is None:
        raise RuntimeError(f"workforce_admission_decision_invalid:attempt{attempt}")
    if receipt.get("terminal_status") != expected_status:
        raise RuntimeError(
            f"non_admitted_terminal_status_mismatch:attempt{attempt}:"
            f"expected={expected_status}:actual={receipt.get('terminal_status')}"
        )

    stages = receipt.get("stages")
    if not isinstance(stages, list):
        raise RuntimeError(f"non_admitted_stages_missing:attempt{attempt}")
    stage_map = {
        str(stage.get("name")): stage
        for stage in stages
        if isinstance(stage, Mapping) and stage.get("name")
    }
    for name in ("local", "online", "verifier", "learning"):
        stage = stage_map.get(name)
        if not isinstance(stage, Mapping) or stage.get("status") != "NOT_REQUESTED":
            raise RuntimeError(f"non_admitted_stage_requested:{name}:attempt{attempt}")
        if bool(stage.get("invoked")):
            raise RuntimeError(f"non_admitted_stage_invoked:{name}:attempt{attempt}")


def _assert_replanable_provider_failure(
    receipt: Mapping[str, Any], attempt: int
) -> None:
    """Require admitted provider delivery and trusted verifier failure for replan."""
    admission = receipt.get("workforce_admission")
    if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
        raise RuntimeError(f"replan_requires_admitted_workforce:attempt{attempt}")
    if receipt.get("terminal_status") != "INCOMPLETE":
        raise RuntimeError(f"replan_requires_incomplete_attempt:attempt{attempt}")
    online = receipt.get("online")
    response = online.get("response") if isinstance(online, Mapping) else None
    if not isinstance(online, Mapping) or not online.get("invoked"):
        raise RuntimeError(f"replan_requires_provider_invocation:attempt{attempt}")
    if not isinstance(response, Mapping) or not response.get("output_delivered"):
        raise RuntimeError(f"replan_requires_provider_delivery:attempt{attempt}")
    request = receipt.get("execution_replan_request")
    if (
        not isinstance(request, Mapping)
        or request.get("schema") != "nexus.execution_replan_request.v1"
        or not request.get("replan_required")
        or not request.get("verifier_outcome_trusted")
    ):
        raise RuntimeError(f"replan_requires_trusted_verifier_failure:attempt{attempt}")


def get_git_status(project_root: str) -> str:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return str(res.stdout or "")


def get_provider_executable_identity(
    provider: str, executable: str | None = None
) -> dict[str, Any]:
    binary = str(executable or "").strip() or shutil.which(provider)
    if not binary or not Path(binary).exists():
        return {
            "provider": provider,
            "version_command_exit_code": -1,
            "version_raw_sha256": "",
            "version_normalized": "unknown",
            "version_error_code": "provider_version_query_failed",
            "version_source": "exact_invoked_executable",
            "executable_path_hash": "",
        }
    try:
        res = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw_ver = str(res.stdout or res.stderr or "").strip()
        raw_sha256 = f"sha256:{hashlib.sha256(raw_ver.encode('utf-8')).hexdigest()}"
        path_hash = f"sha256:{hashlib.sha256(binary.encode('utf-8')).hexdigest()}"
        normalized = raw_ver.splitlines()[0].strip() if raw_ver else "unknown"
        return {
            "provider": provider,
            "version_command_exit_code": res.returncode,
            "version_raw_sha256": raw_sha256,
            "version_normalized": normalized,
            "version_source": "exact_invoked_executable",
            "executable_path_hash": path_hash,
        }
    except Exception:
        return {
            "provider": provider,
            "version_command_exit_code": -1,
            "version_raw_sha256": "",
            "version_normalized": "unknown",
            "version_error_code": "provider_version_query_failed",
            "version_source": "exact_invoked_executable",
            "executable_path_hash": "",
        }


def get_provider_version(provider: str, executable: str | None = None) -> str:
    ident = get_provider_executable_identity(provider, executable)
    return str(ident.get("version_normalized") or "unknown")


def run_canary_campaign(
    provider: str,
    project_root: str,
    receipt_dir: str,
    timeout_sec: float = 120.0,
    runner: Any = subprocess.run,
    entrypoint: str = "runtime",
) -> dict[str, Any]:
    if os.environ.get("NEXUS_P0T5_ALLOW_REAL_PROVIDER") != "1":
        sys.stderr.write("real_provider_canary_not_authorized\n")
        raise RuntimeError("real_provider_canary_not_authorized")

    prov_clean = str(provider or "").strip().lower()
    if prov_clean not in ALLOWED_PROVIDERS:
        sys.stderr.write(f"provider_not_allowed:{prov_clean}\n")
        raise ValueError(f"provider_not_allowed:{prov_clean}")

    entry_clean = str(entrypoint or "runtime").strip().lower()
    if entry_clean not in {"runtime", "mainchain"}:
        raise ValueError(f"entrypoint_not_allowed:{entry_clean}")

    project_root_path = Path(project_root).resolve()
    receipt_dir_path = Path(receipt_dir).resolve()
    receipt_dir_path.mkdir(parents=True, exist_ok=True)

    # Worktree status before
    status_before = get_git_status(str(project_root_path))
    hash_before = hashlib.sha256(status_before.encode("utf-8")).hexdigest()

    temp_cwd = tempfile.mkdtemp(prefix="nexus-p0t5b-cwd-")
    try:
        # Resolve exact executable ONCE before Attempt 1
        spec = resolve_registered_online_cli_spec(prov_clean, working_directory=temp_cwd)
        invoked_executable = spec.command[0] if spec and spec.command else prov_clean
        prov_identity = get_provider_executable_identity(prov_clean, invoked_executable)

        nonce = uuid.uuid4().hex
        canary_prompt = (
            "This is a read-only Nexus transport canary.\n\n"
            "Do not inspect, read, write, edit, execute, list, search, or mention any file.\n"
            "Do not use tools.\n"
            "Do not access the current project.\n"
            "Do not provide explanations.\n\n"
            f"Return exactly one line:\n\nNEXUS_CANARY:{nonce}"
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
                # This canary is a read-only candidate-generation probe.  Bind
                # the exact enrolled worker explicitly so the normal Planner
                # demand reaches Workforce admission (and never falls back to
                # a provider/model default).
                "workforce_admission_enabled": True,
                "mutation_requested": False,
                "topology_facts": {
                    "candidate_generation_only": True,
                    "mutation_requested": False,
                },
                "workforce_bindings": {
                    "online": _canonical_workforce_binding(prov_clean),
                },
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "with_nexus_armor": True,
                "product_entry": "mainchain",
            },
            online_enabled=True,
            local_enabled=False,
            canonical_context={
                "task_facts": {
                    "candidate_generation_only": True,
                    "mutation_requested": False,
                }
            },
        )

        runtime = UnifiedRuntime()

        def _make_cap_invoker(name: str):
            return lambda ctx: {
                "task_id": ctx.get("task_id", task_id),
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
                "evidence_present": True,
                "evidence": "p0t5_canary_forced_replan_after_provider_delivery",
                "evidence_refs": ["canary:provider_output_verified", "canary:forced_replan"],
            }

        # Attempt 1 execution
        online_invoker1 = build_subprocess_online_invoker(
            spec,
            runner=runner,
        )
        r1 = runtime.run(
            req,
            online_invoker=online_invoker1,
            capability_invokers=cap_invokers,
            verifier=verifier_attempt1,
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l1", "evidence_refs": ["l:1"], "gate_passed": True},
            receipt_path=receipt1_path,
        )

        v1_check = validate_receipt_base(r1, mode="strict")
        if not v1_check.get("ok"):
            raise RuntimeError(f"Attempt 1 strict receipt validation failed: {v1_check.get('blockers')}")
        admission = r1.get("workforce_admission")
        admission_decision = admission.get("overall_decision") if isinstance(admission, Mapping) else ""
        if admission_decision != "ALLOW":
            _assert_non_invoked_admission_terminal(r1, 1)
            raise RuntimeError(
                f"Attempt 1 admission {admission_decision}: terminal "
                f"{r1.get('terminal_status')}; provider call and replan not allowed"
            )

        _assert_canonical_admission(r1, 1)
        _assert_replanable_provider_failure(r1, 1)

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
                "evidence_present": True,
                "evidence": "p0t5_canary_attempt_2_pass",
                "evidence_refs": ["canary:attempt2_verified"],
            }

        # Attempt 2 execution
        online_invoker2 = build_subprocess_online_invoker(
            spec,
            runner=runner,
        )
        r2 = runtime.run_replan(
            previous_receipt,
            req,
            online_invoker=online_invoker2,
            capability_invokers=cap_invokers,
            verifier=verifier_attempt2,
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l2", "evidence_refs": ["l:2"], "gate_passed": True},
            receipt_path=receipt2_path,
        )

        v2_check = validate_receipt_base(r2, mode="strict")
        if not v2_check.get("ok"):
            raise RuntimeError(f"Attempt 2 strict receipt validation failed: {v2_check.get('blockers')}")
        _assert_canonical_admission(r2, 2)

        if r2.get("terminal_status") != "SUCCEEDED":
            raise RuntimeError(f"Attempt 2 terminal status unexpected: {r2.get('terminal_status')}")

        # Worktree status after
        status_after = get_git_status(str(project_root_path))
        hash_after = hashlib.sha256(status_after.encode("utf-8")).hexdigest()

        if status_before != status_after:
            raise RuntimeError("TASK_BLOCK: REAL_PROVIDER_MUTATED_WORKTREE")

        pe1 = r1["online"]["response"]["process_evidence"]
        pe2 = r2["online"]["response"]["process_evidence"]

        # Milestone B Section 15.3: Process evidence executable identity equality check
        def _norm_hash(h: str) -> str:
            s = str(h or "").strip()
            if not s:
                return ""
            return s if s.startswith("sha256:") else f"sha256:{s}"

        ident_hash = _norm_hash(prov_identity.get("executable_path_hash"))
        pe1_hash = _norm_hash(pe1.get("executable_path_hash"))
        pe2_hash = _norm_hash(pe2.get("executable_path_hash"))

        if ident_hash and (pe1_hash != ident_hash or pe2_hash != ident_hash):
            raise RuntimeError("TASK_BLOCK: PROVIDER_EXECUTABLE_IDENTITY_MISMATCH")

        s1 = summarize_arm_receipt(r1, prompt=canary_prompt)
        s2 = summarize_arm_receipt(r2, prompt=canary_prompt)

        summary = {
            "campaign_id": f"campaign-{task_id}",
            "entrypoint": entry_clean,
            "provider": prov_clean,
            "provider_version": prov_identity["version_normalized"],
            "provider_executable_identity": prov_identity,
            "real_provider_call_count": 2,
            "attempt_1_mainchain_entry": s1["mainchain_entry"],
            "attempt_2_mainchain_entry": s2["mainchain_entry"],
            "attempt_1_route_freeze": s1["route_freeze"],
            "attempt_2_route_freeze": s2["route_freeze"],
            "attempt_1_mainchain_route_version": s1["mainchain_route_version"],
            "attempt_2_mainchain_route_version": s2["mainchain_route_version"],
            "attempt_1_with_nexus_armor": s1["with_nexus_armor"],
            "attempt_2_with_nexus_armor": s2["with_nexus_armor"],
            "attempt_1_mainchain_identity_complete": s1["mainchain_identity_complete"],
            "attempt_2_mainchain_identity_complete": s2["mainchain_identity_complete"],
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
            "attempt_2_terminal_status": r2.get("terminal_status"),
            "source_replan_request_id": r1["execution_replan_request"]["replan_request_id"],
            "parent_receipt_hash": r2["execution_attempt"]["parent_receipt_hash"],
            "worktree_status_before_hash": hash_before,
            "worktree_status_after_hash": hash_after,
            "worktree_unchanged": hash_before == hash_after,
            "both_strict_validations": bool(v1_check.get("ok") and v2_check.get("ok")),
            "attempt_1_strict_validation": bool(v1_check.get("ok")),
            "attempt_2_strict_validation": bool(v2_check.get("ok")),
        }
        return summary
    finally:
        shutil.rmtree(temp_cwd, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="P0-T5B Real Provider Canary Operator")
    parser.add_argument("--provider", default="opencode", choices=["opencode"])
    parser.add_argument("--entrypoint", default="runtime", choices=["runtime", "mainchain"])
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
            entrypoint=args.entrypoint,
        )
        print(json.dumps(summary, indent=2))
        sys.exit(0)
    except Exception as exc:
        sys.stderr.write(f"CANARY_CAMPAIGN_FAILED: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
