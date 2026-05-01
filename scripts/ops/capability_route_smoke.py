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
    for row in rows:
        coverage = row.get("expected_capability_receipt_coverage") or {}
        expected.update(str(item) for item in coverage.get("expected", []) or [])
        public_safe.update(str(item) for item in coverage.get("public_safe", []) or [])
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
    return {
        "file": str(path),
        "tasks": len(rows),
        "expected_capabilities": sorted(expected),
        "public_safe_capabilities": sorted(public_safe),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed Nexus capability route smoke suite.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--print-only", action="store_true", help="Print commands without running benchmarks.")
    parser.add_argument("--summary-path", default=".nexus/reports/capability_route_smoke_summary.json")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    summaries = [run_suite(repo_root, suite, print_only=args.print_only) for suite in SMOKE_SUITES]
    failures = [failure for summary in summaries for failure in summary.get("failures", [])]
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
