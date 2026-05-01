#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.services.codeintel import analyze_impact, scan_codebase
from scripts.bench.capability_ab_runner import _summarize_rlm_trace
from scripts.bench.gemini_nexus_report import _public_claim_gate
from scripts.ops.jit_promotion import build_promotion_report


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / ".nexus" / "reports" / "benchmark_preflight_readiness.json"
DEFAULT_TASKS_FILE = ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"
DEFAULT_MODEL = "gemini-3-flash-preview"


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    evidence: dict[str, Any]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "evidence": self.evidence,
        }


def _check_codeintel(repo_root: Path, changed_file: str) -> ReadinessCheck:
    target = repo_root / changed_file
    if not target.exists():
        return ReadinessCheck(
            name="codeintel_evidence",
            passed=False,
            reason="changed_file_missing",
            evidence={"changed_file": changed_file},
        )
    with tempfile.TemporaryDirectory(prefix="nexus-codeintel-preflight-") as temp_dir:
        scan_path = Path(temp_dir) / "scan.json"
        scan = scan_codebase(repo_root, index_path=scan_path)
        impact = analyze_impact(repo_root, changed_files=[changed_file], index_path=scan.index_path)
    evidence = {
        "schema_version": impact.schema_version,
        "nodes_count": scan.nodes_count,
        "edges_count": scan.edges_count,
        "changed_files": impact.changed_files,
        "impacted_files_count": len(impact.impacted_files),
        "risk_score": impact.risk_score,
        "risk_reason": impact.risk_reason,
    }
    passed = (
        impact.schema_version == "codeintel-v1"
        and changed_file in impact.changed_files
        and len(impact.impacted_files) >= 1
    )
    return ReadinessCheck(
        name="codeintel_evidence",
        passed=passed,
        reason="" if passed else "impact_contract_incomplete",
        evidence=evidence,
    )


def _check_rlm_trace_quality() -> ReadinessCheck:
    with tempfile.TemporaryDirectory(prefix="nexus-rlm-preflight-") as temp_dir:
        trace_path = Path(temp_dir) / "rlm.jsonl"
        trace_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "phase": "R",
                            "iteration_id": "r-1",
                            "action_type": "research_auto_flow",
                            "stop_reason": "submit",
                            "confidence": 0.72,
                            "allowed_tools": ["pytest", "read_file"],
                            "artifact_refs": ["patch.diff"],
                        }
                    ),
                    json.dumps(
                        {
                            "phase": "A",
                            "iteration_id": "a-1",
                            "action_type": "acceptance_gate",
                            "stop_reason": "verified",
                            "confidence": 0.9,
                            "artifact_refs": ["pytest.log"],
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        summary = _summarize_rlm_trace(str(trace_path))
    passed = (
        summary["rlm_trace_quality_score"] >= 60
        and summary["rlm_submit_count"] == 1
        and summary["rlm_verified_count"] == 1
    )
    return ReadinessCheck(
        name="rlm_trace_quality",
        passed=passed,
        reason="" if passed else "rlm_trace_contract_incomplete",
        evidence=summary,
    )


def _check_jit_promotion_boundary() -> ReadinessCheck:
    observations = [
        {
            "event": "changed_only",
            "changed_paths": [f"nexus/core/preflight_{index}.py"],
            "targets": ["tests/core"],
            "fallback_used": False,
            "unmatched_paths": [],
            "predictive_saved_runtime_sec": 1.0,
        }
        for index in range(3)
    ]
    promote = build_promotion_report(
        observations,
        [{"mode": "nightly-full", "success": True}],
        {"missed_count": 0, "missed_candidates": []},
        {"mappings": {"nexus/core/preflight_1.py": {"tests/core": {"score": 3.0}}}},
        min_observations=3,
        min_nightly_full=1,
    )
    hold = build_promotion_report(
        observations[:1],
        [{"mode": "nightly-full", "success": False}],
        {"missed_count": 1, "missed_candidates": [{"target": "tests/services"}]},
        {"mappings": {}},
        min_observations=1,
        min_nightly_full=1,
    )
    passed = (
        promote["verdict"] == "PROMOTE_CANDIDATE"
        and promote["trial_lane_allowed"] is True
        and promote["default_switch_allowed"] is False
        and hold["verdict"] == "HOLD"
        and hold["default_switch_allowed"] is False
    )
    return ReadinessCheck(
        name="jit_promotion_boundary",
        passed=passed,
        reason="" if passed else "jit_boundary_not_fail_closed",
        evidence={
            "promote_verdict": promote["verdict"],
            "trial_lane_allowed": promote["trial_lane_allowed"],
            "default_switch_allowed": promote["default_switch_allowed"],
            "hold_verdict": hold["verdict"],
            "hold_miss_rate": hold["miss_rate"],
        },
    )


def _check_public_claim_gate() -> ReadinessCheck:
    task_row = {
        "task_id": "preflight",
        "trial_index": 0,
        "run_eligible": True,
        "token_status": "measured",
        "total_tokens": 100,
    }
    rows_without = [task_row | {"mode": "without_nexus"}]
    rows_with = [
        task_row
        | {
            "mode": "with_nexus",
            "status": "SUCCESS",
            "route_decision_schema_version": "nexus_route_decision_v1",
            "rlm_trace_present": True,
            "rlm_submit_count": 1,
            "rlm_verified_count": 1,
            "rlm_audit_rejected_count": 0,
            "rlm_trace_quality_score": 90,
            "rlm_loop_phase": "X",
            "rlm_x_loop_budget_observed": True,
        }
    ]
    summary = {
        "token_measured_rate": 1.0,
        "gemini_uses_nexus_rate": 1.0,
        "nexus_usage_valid_rate": 1.0,
        "phase_completion_rate": 1.0,
        "claim_verified_rate": 1.0,
    }
    pass_gate = _public_claim_gate(
        rows_without=rows_without,
        rows_with=rows_with,
        summary_without={"token_measured_rate": 1.0},
        summary_with=summary,
        formal={"valid_rate": 1.0},
    )
    fail_gate = _public_claim_gate(
        rows_without=rows_without,
        rows_with=[rows_with[0] | {"rlm_verified_count": 0, "rlm_trace_quality_score": 10}],
        summary_without={"token_measured_rate": 1.0},
        summary_with=summary,
        formal={"valid_rate": 1.0},
    )
    passed = pass_gate["verdict"] == "PASS" and fail_gate["verdict"] == "FAIL"
    return ReadinessCheck(
        name="public_claim_gate",
        passed=passed,
        reason="" if passed else "public_claim_gate_not_enforced",
        evidence={"pass_gate": pass_gate, "fail_gate": fail_gate},
    )


def _check_memory_bootstrap(repo_root: Path, threshold_sec: float = 5.0) -> ReadinessCheck:
    previous = {
        "NEXUS_MEMORY_AUTO_INIT": os.environ.get("NEXUS_MEMORY_AUTO_INIT"),
        "NEXUS_MEMORY_DB_PATH": os.environ.get("NEXUS_MEMORY_DB_PATH"),
    }
    with tempfile.TemporaryDirectory(prefix="nexus-memory-preflight-") as temp_dir:
        os.environ["NEXUS_MEMORY_AUTO_INIT"] = "0"
        os.environ["NEXUS_MEMORY_DB_PATH"] = str(Path(temp_dir) / "memory.lancedb")
        start = time.monotonic()
        try:
            from nexus.services.memory import MemoryService

            memory = MemoryService(str(repo_root))
            elapsed = time.monotonic() - start
            status = str(getattr(memory, "bootstrap_status", "unknown"))
            db_path = str(getattr(memory, "db_path", ""))
            error = ""
        except Exception as exc:
            elapsed = time.monotonic() - start
            status = "error"
            db_path = ""
            error = str(exc)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    passed = status != "error" and elapsed <= threshold_sec
    return ReadinessCheck(
        name="memory_bootstrap_fail_open",
        passed=passed,
        reason="" if passed else "memory_bootstrap_slow_or_error",
        evidence={
            "bootstrap_status": status,
            "elapsed_sec": round(elapsed, 4),
            "threshold_sec": threshold_sec,
            "db_path": db_path,
            "error": error,
            "auto_init": "0",
        },
    )


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _model_lock(model_name: str) -> dict[str, Any]:
    env_model = os.environ.get("NEXUS_GEMINI_MODEL_NAME") or model_name
    direct_model = os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or model_name
    return {
        "without_model_name": direct_model,
        "with_model_name": env_model,
        "same_model": bool(env_model and direct_model and env_model == direct_model),
        "provider": "gemini",
    }


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _contract(
    identifier: str,
    *,
    what: str,
    why: str,
    how: str,
    status: str,
    blocks_benchmark: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "what": what,
        "why": why,
        "how": how,
        "status": status,
        "blocks_benchmark": blocks_benchmark,
        "evidence": evidence,
    }


def _build_contract_matrix(
    *,
    checks: list[ReadinessCheck],
    tasks_file: Path,
    model_name: str,
    max_tasks: int,
    repeat_trials: int,
    timeout_sec: int,
    total_timeout_sec: int,
    stop_loss_sec: int,
    per_task_stop_loss_sec: int,
    hidden_verifier_required: bool,
    evidence_bundle_required: bool,
    markdown_report_required: bool,
) -> list[dict[str, Any]]:
    check_map = {check.name: check for check in checks}
    manifest_sha = _sha256_file(tasks_file)
    model_lock = _model_lock(model_name)
    hidden_verifier_enabled = _env_flag("NEXUS_VALUE_HIDDEN_VERIFIER")
    hidden_verifier_ok = (not hidden_verifier_required) or hidden_verifier_enabled
    timeout_ok = (
        0 < per_task_stop_loss_sec <= 600
        and timeout_sec > 0
        and total_timeout_sec > 0
        and stop_loss_sec > 0
    )
    codeintel_ok = check_map["codeintel_evidence"].passed
    rlm_ok = check_map["rlm_trace_quality"].passed
    jit_ok = check_map["jit_promotion_boundary"].passed
    public_gate_ok = check_map["public_claim_gate"].passed
    return [
        _contract(
            "P1",
            what="Benchmark preflight fixed gate",
            why="Avoid spending Gemini quota on broken local evidence/report gates.",
            how="Run nexus_benchmark_preflight.py before any public-candidate benchmark.",
            status="ready" if all(check.passed for check in checks) else "blocked",
            blocks_benchmark=not all(check.passed for check in checks),
            evidence={"passed_checks": [check.name for check in checks if check.passed]},
        ),
        _contract(
            "P2",
            what="Model/quota eligibility",
            why="Quota/auth/CLI failures must not enter solve-rate denominators.",
            how="Use runner eligibility fields during 3-task smoke; local preflight verifies the schema contract only.",
            status="deferred_smoke",
            blocks_benchmark=False,
            evidence={
                "required_fields": [
                    "run_eligible",
                    "infra_invalid_reason",
                    "invocation_started",
                    "model_response_received",
                    "provider",
                    "model_name",
                ]
            },
        ),
        _contract(
            "P3",
            what="Benchmark manifest freeze",
            why="Public lift percentages require the same task set and verifier.",
            how="Record manifest path/hash, max tasks, repeat trials, hidden verifier, and report requirements.",
            status="ready" if tasks_file.exists() and bool(manifest_sha) and hidden_verifier_ok else "blocked",
            blocks_benchmark=not (tasks_file.exists() and bool(manifest_sha) and hidden_verifier_ok),
            evidence={
                "manifest_path": str(tasks_file),
                "manifest_sha256": manifest_sha,
                "max_tasks": max_tasks,
                "repeat_trials": repeat_trials,
                "hidden_verifier_required": hidden_verifier_required,
                "hidden_verifier_enabled": hidden_verifier_enabled,
                "evidence_bundle_required": evidence_bundle_required,
                "markdown_report_required": markdown_report_required,
            },
        ),
        _contract(
            "P4",
            what="Same-model lock",
            why="Nexus is a battlesuit; comparison must keep the base model identical.",
            how="Require NEXUS_GEMINI_MODEL_NAME and NEXUS_DIRECT_GEMINI_MODEL to match.",
            status="ready" if model_lock["same_model"] else "blocked",
            blocks_benchmark=not model_lock["same_model"],
            evidence=model_lock,
        ),
        _contract(
            "P5",
            what="Nexus wearing proof",
            why="The with-Nexus arm must prove Gemini used Nexus context rather than Nexus solving alone.",
            how="Runner rows must expose model calls, context delivery, usage validity, and verified claim fields.",
            status="ready",
            blocks_benchmark=False,
            evidence={
                "required_fields": [
                    "model_calls",
                    "gemini_uses_nexus",
                    "nexus_context_delivered",
                    "nexus_usage_valid",
                    "capability_claim_verified",
                ]
            },
        ),
        _contract(
            "P6",
            what="Five-pillar evidence gate",
            why="Public reports must explain which Nexus pillar created the lift.",
            how="Runner rows must include LanceDB, Memory, MemPalace, Belief, and Artifact fields.",
            status="ready",
            blocks_benchmark=False,
            evidence={
                "pillars": ["lancedb", "memory", "mempalace", "belief", "artifact"],
                "required_rates": [
                    "pillar_lancedb_active_rate",
                    "pillar_memory_active_rate",
                    "pillar_mempalace_active_rate",
                    "pillar_belief_active_rate",
                    "pillar_artifact_active_rate",
                ],
            },
        ),
        _contract(
            "P7",
            what="S/P/X/D/R/A/C phase trace",
            why="Nexus value is governed process quality, not only final answer accuracy.",
            how="Runner rows must expose phase labels and phase wall-clock fields.",
            status="ready",
            blocks_benchmark=False,
            evidence={
                "phase_fields": ["phase_p", "phase_x", "phase_d", "phase_r", "phase_a", "phase_c"],
                "wall_fields": [
                    "phase_wall_p_sec",
                    "phase_wall_x_sec",
                    "phase_wall_d_sec",
                    "phase_wall_r_sec",
                    "phase_wall_a_sec",
                    "phase_wall_c_sec",
                ],
            },
        ),
        _contract(
            "P8",
            what="CodeIntel evidence",
            why="Code tasks need impact/context evidence before claiming Nexus code-intel lift.",
            how="Local preflight runs scan_codebase plus analyze_impact against the real repo.",
            status="ready" if codeintel_ok else "blocked",
            blocks_benchmark=not codeintel_ok,
            evidence=check_map["codeintel_evidence"].evidence,
        ),
        _contract(
            "P9",
            what="RLM trace quality",
            why="RLM claims require submit, A-gate, evidence, and budget observability.",
            how="Local preflight summarizes a deterministic RLM trace using the benchmark runner parser.",
            status="ready" if rlm_ok else "blocked",
            blocks_benchmark=not rlm_ok,
            evidence=check_map["rlm_trace_quality"].evidence,
        ),
        _contract(
            "P10",
            what="JIT boundary",
            why="Predictive JIT may be observed, but must not silently become default CI behavior.",
            how="Promotion report may allow trial lane, while default switch remains fail-closed.",
            status="ready" if jit_ok else "blocked",
            blocks_benchmark=not jit_ok,
            evidence=check_map["jit_promotion_boundary"].evidence,
        ),
        _contract(
            "P11",
            what="MSA capability evidence",
            why="Swarm, Drone, and Nightshift must not be counted from broad labels alone.",
            how="Rows must distinguish recommended, invoked, recovered, count, and evidence path fields.",
            status="ready",
            blocks_benchmark=False,
            evidence={
                "nightshift_fields": [
                    "capability_nightshift_recommended",
                    "capability_nightshift_invoked",
                    "capability_nightshift_recovered",
                    "capability_nightshift_report_path",
                ],
                "swarm_fields": ["capability_swarm_used", "capability_swarm_evidence_count"],
                "drone_fields": ["capability_drone_used", "capability_drone_invoked_count"],
            },
        ),
        _contract(
            "P12",
            what="Timeout and stop-loss policy",
            why="Abnormally long tasks must stop before they pollute benchmark interpretation.",
            how="Preflight blocks per-task stop-loss over 600s and records total/direct/gateway timeout policy.",
            status="ready" if timeout_ok else "blocked",
            blocks_benchmark=not timeout_ok,
            evidence={
                "timeout_sec": timeout_sec,
                "total_timeout_sec": total_timeout_sec,
                "stop_loss_sec": stop_loss_sec,
                "per_task_stop_loss_sec": per_task_stop_loss_sec,
                "max_allowed_per_task_stop_loss_sec": 600,
            },
        ),
        _contract(
            "P13",
            what="Token and cost interpretation",
            why="Gemini CLI token visibility can be partial; public cost claims need source labeling.",
            how="Require token status/source fields and only treat measured tokens as precise cost evidence.",
            status="ready",
            blocks_benchmark=False,
            evidence={
                "token_policy": "measured_required_for_cost_claim",
                "required_fields": [
                    "token_capture_status",
                    "token_measured",
                    "gateway_token_source",
                    "gateway_stats_present",
                    "gateway_usage_metadata_present",
                ],
            },
        ),
    ]


def build_preflight_report(
    repo_root: Path,
    *,
    changed_file: str,
    tasks_file: Path | None = None,
    model_name: str = DEFAULT_MODEL,
    max_tasks: int = 12,
    repeat_trials: int = 3,
    timeout_sec: int = 180,
    total_timeout_sec: int = 3600,
    stop_loss_sec: int = 3600,
    per_task_stop_loss_sec: int = 600,
    hidden_verifier_required: bool = True,
    evidence_bundle_required: bool = True,
    markdown_report_required: bool = True,
) -> dict[str, Any]:
    tasks_path = tasks_file or DEFAULT_TASKS_FILE
    tasks_path = tasks_path if tasks_path.is_absolute() else repo_root / tasks_path
    checks = [
        _check_codeintel(repo_root, changed_file),
        _check_rlm_trace_quality(),
        _check_jit_promotion_boundary(),
        _check_public_claim_gate(),
        _check_memory_bootstrap(repo_root),
    ]
    contract_matrix = _build_contract_matrix(
        checks=checks,
        tasks_file=tasks_path,
        model_name=model_name,
        max_tasks=max_tasks,
        repeat_trials=repeat_trials,
        timeout_sec=timeout_sec,
        total_timeout_sec=total_timeout_sec,
        stop_loss_sec=stop_loss_sec,
        per_task_stop_loss_sec=per_task_stop_loss_sec,
        hidden_verifier_required=hidden_verifier_required,
        evidence_bundle_required=evidence_bundle_required,
        markdown_report_required=markdown_report_required,
    )
    blocking_contracts = [item["id"] for item in contract_matrix if item["blocks_benchmark"]]
    ready = all(check.passed for check in checks) and not blocking_contracts
    return {
        "schema": "nexus_benchmark_preflight_readiness_v1",
        "ready_for_benchmark": ready,
        "ready_for_smoke": ready,
        "changed_file": changed_file,
        "benchmark_contract_matrix": contract_matrix,
        "blocking_contracts": blocking_contracts,
        "checks": [check.to_dict() for check in checks],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Nexus benchmark readiness checks without Gemini.")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--changed-file", default="nexus/app/research_flow_service.py")
    parser.add_argument("--tasks-file", default=str(DEFAULT_TASKS_FILE))
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--max-tasks", type=int, default=12)
    parser.add_argument("--repeat-trials", type=int, default=3)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--total-timeout-sec", type=int, default=3600)
    parser.add_argument("--stop-loss-sec", type=int, default=3600)
    parser.add_argument("--per-task-stop-loss-sec", type=int, default=600)
    parser.add_argument("--no-hidden-verifier", action="store_true")
    parser.add_argument("--no-evidence-bundle", action="store_true")
    parser.add_argument("--no-markdown-report", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_preflight_report(
        Path(args.repo_root),
        changed_file=args.changed_file,
        tasks_file=Path(args.tasks_file),
        model_name=args.model_name,
        max_tasks=args.max_tasks,
        repeat_trials=args.repeat_trials,
        timeout_sec=args.timeout_sec,
        total_timeout_sec=args.total_timeout_sec,
        stop_loss_sec=args.stop_loss_sec,
        per_task_stop_loss_sec=args.per_task_stop_loss_sec,
        hidden_verifier_required=not args.no_hidden_verifier,
        evidence_bundle_required=not args.no_evidence_bundle,
        markdown_report_required=not args.no_markdown_report,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.output_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "status": "SUCCESS" if report["ready_for_benchmark"] else "FAILED",
                    "ready_for_benchmark": report["ready_for_benchmark"],
                    "output": str(output),
                },
                ensure_ascii=False,
            )
        )
    return 0 if report["ready_for_benchmark"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
