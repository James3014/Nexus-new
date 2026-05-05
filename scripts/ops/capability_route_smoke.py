#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.bench.gemini_nexus_report import _row_route_quality_counts


@dataclass(frozen=True)
class SmokeSuite:
    name: str
    manifest: str
    output_dir: str
    task_ids: tuple[str, ...]
    max_tasks: int | None = None


SMOKE_SUITES: tuple[SmokeSuite, ...] = (
    SmokeSuite(
        name="route_oracles",
        manifest="scripts/bench/public_benchmark_route_oracles_v1.json",
        output_dir=".nexus/reports/bench_route_8oracle_smoke",
        task_ids=(
            "route-oracle-autoreason-001",
            "route-oracle-ddtree-001",
            "route-oracle-ultra-review-001",
            "route-oracle-research-001",
            "route-oracle-lancedb-001",
            "route-oracle-swarm-001",
            "route-oracle-drone-001",
            "route-oracle-nightshift-001",
        ),
        max_tasks=8,
    ),
    SmokeSuite(
        name="codeintel_hyper",
        manifest="scripts/bench/public_benchmark_nexus_value_v1.json",
        output_dir=".nexus/reports/bench_route_codeintel_hyper_smoke",
        task_ids=(
            "nexus-value-repair-001",
            "nexus-value-context-001",
        ),
    ),
    SmokeSuite(
        name="core_governance_gates",
        manifest="scripts/bench/public_benchmark_nexus_value_v1.json",
        output_dir=".nexus/reports/bench_route_core_gates_smoke",
        task_ids=(
            "nexus-value-gov-001",
            "nexus-value-evidence-001",
        ),
    ),
    SmokeSuite(
        name="belief_gate",
        manifest="scripts/bench/public_benchmark_rlm_harder_v2.json",
        output_dir=".nexus/reports/bench_route_belief_smoke",
        task_ids=(
            "rlm-harder-v2-belief-001",
        ),
    ),
)

REQUIRED_NINE_CAPABILITIES = frozenset(
    {
        "autoreason",
        "ddtree",
        "ultra_review",
        "research",
        "lancedb",
        "swarm",
        "drone",
        "nightshift",
        "belief",
    }
)

ROUTE_QUALITY_THRESHOLDS = {
    "selected_to_invoked_rate": 0.70,
    "invoked_to_evidence_rate": 0.95,
    "evidence_to_outcome_rate": 0.90,
    "unnecessary_selected_rate_max": 0.30,
}


def build_command(repo_root: Path, suite: SmokeSuite) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        suite.manifest,
        "--nexus-only",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "off",
        "--force-flow",
        "hyper_sprint",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--task-id-filter",
        ",".join(suite.task_ids),
        "--timeout-sec",
        "90",
        "--per-task-stop-loss-sec",
        "120",
        "--total-timeout-sec",
        "1800",
        "--output-dir",
        suite.output_dir,
        "--markdown-report",
        "auto",
    ]
    if suite.max_tasks is not None:
        cmd[4:4] = ["--max-tasks", str(suite.max_tasks)]
    return cmd


def smoke_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] = "1"
    # Route smoke validates capability selection/receipt contracts.
    # Keep Ultra Review deterministic in dirty benchmark worktrees.
    env["NEXUS_ULTRA_SKIP_GHOST_REGRESSION"] = "1"
    env["NEXUS_ULTRA_REUSE_WORKTREE"] = "1"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) if not existing_pythonpath else f"{repo_root}{os.pathsep}{existing_pythonpath}"
    return env


def latest_with_nexus_file(output_dir: Path, *, exclude: set[Path] | None = None) -> Path:
    excluded = {path.resolve() for path in (exclude or set())}
    candidates = sorted(
        (path for path in output_dir.glob("with_nexus_*.jsonl") if path.resolve() not in excluded),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(f"no with_nexus jsonl found in {output_dir}")
    return candidates[-1]


def summarize_jsonl(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[dict[str, Any]] = []
    public_safe: set[str] = set()
    expected: set[str] = set()
    selected_total = 0
    invoked_total = 0
    evidence_total = 0
    outcome_total = 0
    for row in rows:
        coverage = row.get("expected_capability_receipt_coverage") or {}
        expected.update(str(item) for item in coverage.get("expected", []) or [])
        public_safe.update(str(item) for item in coverage.get("public_safe", []) or [])
        route_quality_counts = _row_route_quality_counts(row)
        if route_quality_counts is None:
            selected_total += int(row.get("route_decision_selected_count", 0) or 0)
            invoked_total += int(row.get("route_decision_invoked_count", 0) or 0)
            evidence_total += int(row.get("route_decision_evidence_count", 0) or 0)
            outcome_total += int(row.get("route_decision_outcome_count", 0) or 0)
        else:
            selected_total += route_quality_counts["selected"]
            invoked_total += route_quality_counts["invoked"]
            evidence_total += route_quality_counts["evidence"]
            outcome_total += route_quality_counts["outcome"]
        row_failures: list[str] = []
        if row.get("status") != "SUCCESS":
            row_failures.append("status_not_success")
        if row.get("semantic_status") != "VERIFIED":
            row_failures.append("semantic_not_verified")
        if coverage.get("missing"):
            row_failures.append("expected_capability_not_public_safe")
        if coverage.get("expected") and not bool(coverage.get("all_public_safe", False)):
            row_failures.append("expected_capability_coverage_incomplete")
        if not str(row.get("route_decision_schema_version") or "").strip():
            row_failures.append("route_decision_missing")
        if int(row.get("route_decision_selected_count", 0) or 0) <= 0:
            row_failures.append("route_decision_empty")
        if bool(row.get("legacy_override_detected", False)):
            row_failures.append("legacy_override_detected")
        if row_failures:
            failures.append(
                {
                    "task_id": row.get("task_id"),
                    "status": row.get("status"),
                    "semantic_status": row.get("semantic_status"),
                    "missing": coverage.get("missing", []),
                    "failure_reasons": coverage.get("failure_reasons", {}),
                    "row_failures": row_failures,
                }
            )
    selected_to_invoked_rate = (invoked_total / selected_total) if selected_total > 0 else 0.0
    invoked_to_evidence_rate = (evidence_total / invoked_total) if invoked_total > 0 else 0.0
    evidence_to_outcome_rate = (outcome_total / evidence_total) if evidence_total > 0 else 0.0
    unnecessary_selected_rate = ((selected_total - invoked_total) / selected_total) if selected_total > 0 else 0.0
    return {
        "file": str(path),
        "tasks": len(rows),
        "expected_capabilities": sorted(expected),
        "public_safe_capabilities": sorted(public_safe),
        "route_quality": {
            "selected_total": selected_total,
            "invoked_total": invoked_total,
            "evidence_total": evidence_total,
            "outcome_total": outcome_total,
            "selected_to_invoked_rate": selected_to_invoked_rate,
            "invoked_to_evidence_rate": invoked_to_evidence_rate,
            "evidence_to_outcome_rate": evidence_to_outcome_rate,
            "unnecessary_selected_rate": unnecessary_selected_rate,
        },
        "failures": failures,
    }


def run_suite(repo_root: Path, suite: SmokeSuite, *, print_only: bool) -> dict[str, Any]:
    cmd = build_command(repo_root, suite)
    if print_only:
        return {"suite": suite.name, "command": cmd}
    output_dir = repo_root / suite.output_dir
    before = {path.resolve() for path in output_dir.glob("with_nexus_*.jsonl")}
    result = subprocess.run(cmd, cwd=repo_root, env=smoke_env(repo_root), text=True, check=False)
    try:
        summary = summarize_jsonl(latest_with_nexus_file(output_dir, exclude=before))
    except FileNotFoundError as exc:
        summary = {
            "file": "",
            "tasks": 0,
            "expected_capabilities": [],
            "public_safe_capabilities": [],
            "failures": [{"suite": suite.name, "error": str(exc)}],
        }
    summary["suite"] = suite.name
    summary["returncode"] = result.returncode
    if result.returncode != 0:
        summary["failures"].append({"suite": suite.name, "returncode": result.returncode})
    return summary


def validate_nine_capability_identity(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    nine_target_summaries = [summary for summary in summaries if summary.get("suite") in {"route_oracles", "belief_gate"}]
    nine_expected = {
        cap
        for summary in nine_target_summaries
        for cap in (summary.get("expected_capabilities") or [])
        if isinstance(cap, str)
    }
    nine_public_safe = {
        cap
        for summary in nine_target_summaries
        for cap in (summary.get("public_safe_capabilities") or [])
        if isinstance(cap, str)
    }
    if nine_expected != REQUIRED_NINE_CAPABILITIES:
        failures.append(
            {
                "task_id": "__route_oracle_plus_belief__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": sorted(REQUIRED_NINE_CAPABILITIES - nine_expected),
                "failure_reasons": {
                    "expected_capabilities": {
                        "required_nine": sorted(REQUIRED_NINE_CAPABILITIES),
                        "actual": sorted(nine_expected),
                    }
                },
                "row_failures": ["expected_capability_not_exact_nine"],
            }
        )
    if nine_public_safe != REQUIRED_NINE_CAPABILITIES:
        failures.append(
            {
                "task_id": "__route_oracle_plus_belief__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": sorted(REQUIRED_NINE_CAPABILITIES - nine_public_safe),
                "failure_reasons": {
                    "public_safe_capabilities": {
                        "required_nine": sorted(REQUIRED_NINE_CAPABILITIES),
                        "actual": sorted(nine_public_safe),
                    }
                },
                "row_failures": ["public_safe_capability_not_exact_nine"],
            }
        )
    return failures


def validate_route_quality_gate(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    selected_total = 0
    invoked_total = 0
    evidence_total = 0
    outcome_total = 0
    for summary in summaries:
        quality = summary.get("route_quality") or {}
        if not isinstance(quality, dict):
            continue
        selected_total += int(quality.get("selected_total", 0) or 0)
        invoked_total += int(quality.get("invoked_total", 0) or 0)
        evidence_total += int(quality.get("evidence_total", 0) or 0)
        outcome_total += int(quality.get("outcome_total", 0) or 0)

    if selected_total <= 0:
        failures.append(
            {
                "task_id": "__route_quality__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": [],
                "failure_reasons": {"route_quality": {"selected_total": selected_total}},
                "row_failures": ["route_quality_selected_total_zero"],
            }
        )
        return failures

    selected_to_invoked_rate = invoked_total / selected_total
    invoked_to_evidence_rate = (evidence_total / invoked_total) if invoked_total > 0 else 0.0
    evidence_to_outcome_rate = (outcome_total / evidence_total) if evidence_total > 0 else 0.0
    unnecessary_selected_rate = max(selected_total - invoked_total, 0) / selected_total

    if selected_to_invoked_rate < ROUTE_QUALITY_THRESHOLDS["selected_to_invoked_rate"]:
        failures.append(
            {
                "task_id": "__route_quality__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": [],
                "failure_reasons": {"selected_to_invoked_rate": selected_to_invoked_rate},
                "row_failures": ["route_quality_selected_to_invoked_below_threshold"],
            }
        )
    if invoked_to_evidence_rate < ROUTE_QUALITY_THRESHOLDS["invoked_to_evidence_rate"]:
        failures.append(
            {
                "task_id": "__route_quality__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": [],
                "failure_reasons": {"invoked_to_evidence_rate": invoked_to_evidence_rate},
                "row_failures": ["route_quality_invoked_to_evidence_below_threshold"],
            }
        )
    if evidence_to_outcome_rate < ROUTE_QUALITY_THRESHOLDS["evidence_to_outcome_rate"]:
        failures.append(
            {
                "task_id": "__route_quality__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": [],
                "failure_reasons": {"evidence_to_outcome_rate": evidence_to_outcome_rate},
                "row_failures": ["route_quality_evidence_to_outcome_below_threshold"],
            }
        )
    if unnecessary_selected_rate > ROUTE_QUALITY_THRESHOLDS["unnecessary_selected_rate_max"]:
        failures.append(
            {
                "task_id": "__route_quality__",
                "status": "SUMMARY",
                "semantic_status": "SUMMARY",
                "missing": [],
                "failure_reasons": {"unnecessary_selected_rate": unnecessary_selected_rate},
                "row_failures": ["route_quality_unnecessary_selected_above_threshold"],
            }
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed Nexus capability route smoke suite.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--print-only", action="store_true", help="Print commands without running benchmarks.")
    parser.add_argument("--summary-path", default=".nexus/reports/capability_route_smoke_summary.json")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    summaries = [run_suite(repo_root, suite, print_only=args.print_only) for suite in SMOKE_SUITES]
    failures = [failure for summary in summaries for failure in summary.get("failures", [])]
    if not args.print_only:
        failures.extend(validate_nine_capability_identity(summaries))
        failures.extend(validate_route_quality_gate(summaries))
    payload = {
        "schema_version": "nexus_capability_route_smoke.v1",
        "diagnostic_type": "receipt_diagnostic",
        "receipt_diagnostic_pass": not failures,
        "public_benchmark_claim_allowed": False,
        "public_benchmark_claim_blocked_reason": "nexus_only_receipt_smoke_not_same_model_ab",
        "suites": summaries,
        "failures": failures,
        "passed": not failures,
    }
    if not args.print_only:
        summary_path = repo_root / args.summary_path
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        payload["summary_path"] = str(summary_path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
