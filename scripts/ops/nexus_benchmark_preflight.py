#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.services.codeintel import analyze_impact, scan_codebase
from scripts.bench.capability_ab_runner import _summarize_rlm_trace
from scripts.bench.gemini_nexus_report import _public_claim_gate
from scripts.ops.jit_promotion import build_promotion_report


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / ".nexus" / "reports" / "benchmark_preflight_readiness.json"


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


def build_preflight_report(repo_root: Path, *, changed_file: str) -> dict[str, Any]:
    checks = [
        _check_codeintel(repo_root, changed_file),
        _check_rlm_trace_quality(),
        _check_jit_promotion_boundary(),
        _check_public_claim_gate(),
    ]
    return {
        "schema": "nexus_benchmark_preflight_readiness_v1",
        "ready_for_benchmark": all(check.passed for check in checks),
        "changed_file": changed_file,
        "checks": [check.to_dict() for check in checks],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Nexus benchmark readiness checks without Gemini.")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--changed-file", default="nexus/app/research_flow_service.py")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_preflight_report(Path(args.repo_root), changed_file=args.changed_file)
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
