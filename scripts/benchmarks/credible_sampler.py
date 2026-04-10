#!/usr/bin/env python3
"""
Credible optimization sampler.

This script performs real repeated measurements (N>=3 by policy), instead of
hard-coded scores. It executes benchmark and acceptance checks per sample,
validates a holdout target file, and computes mu/sigma over observed scores.
"""

from __future__ import annotations

import argparse
import math
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / ".nexus" / "governance_policy.yaml"
DEFAULT_OUTPUT_PATH = REPO_ROOT / ".nexus" / "reports" / "credible_sampling_report.json"
DEFAULT_BENCHMARK_CMD = [
    "uv",
    "run",
    "python3",
    "scripts/benchmarks/engine_v24_benchmark.py",
]
DEFAULT_ACCEPTANCE_CMD = [
    "uv",
    "run",
    "scripts/engine/nexus_cli.py",
    "nexus",
    "acceptance-check",
]
ACCEPTANCE_REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "acceptance_check.json"


@dataclass
class CommandResult:
    cmd: list[str]
    returncode: int
    elapsed_ms: float
    stdout: str
    stderr: str


@dataclass
class SampleResult:
    round_index: int
    score: float
    acceptance_passed: bool
    benchmark_passed: bool
    target_validation_passed: bool
    compression_ratio: float | None
    latency_ms: float
    details: dict[str, Any]


@dataclass
class CanaryDecision:
    canary_enabled: bool
    canary_sample_count: int
    baseline_success_rate: float | None
    canary_avg_success_rate: float | None
    success_rate_drop: float | None
    entropy_proxy: float
    entropy_limit: float
    triggered: bool
    reasons: list[str]
    rollback_recommended: bool
    rollback_executed: bool
    rollback_mode: str
    rollback_files: list[str]


def _load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _get_policy_values(policy: dict[str, Any]) -> dict[str, float]:
    default = policy.get("default", {}) if isinstance(policy, dict) else {}
    credible = default.get("credible_verification", {}) if isinstance(default, dict) else {}
    return {
        "sample_size_min": float(credible.get("sample_size_min", 3)),
        "significance_sigma_max": float(credible.get("significance_sigma_max", 0.05)),
        "generalization_mu_min": 0.90,
    }


def _run_cmd(cmd: list[str], cwd: Path) -> CommandResult:
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return CommandResult(
        cmd=cmd,
        returncode=proc.returncode,
        elapsed_ms=elapsed_ms,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _git_modified_tracked_files(cwd: Path) -> set[str]:
    """Return tracked modified files from porcelain output."""
    res = _run_cmd(["git", "status", "--porcelain"], cwd=cwd)
    if res.returncode != 0:
        return set()
    files: set[str] = set()
    for line in res.stdout.splitlines():
        if not line:
            continue
        # format: XY <path>
        status = line[:2]
        path = line[3:].strip()
        # Skip untracked files (??), keep tracked modifications only.
        if status == "??":
            continue
        if path:
            files.add(path)
    return files


def _read_acceptance_report() -> dict[str, Any]:
    if not ACCEPTANCE_REPORT_PATH.exists():
        return {}
    try:
        return json.loads(ACCEPTANCE_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_success_rate(report: dict[str, Any]) -> float | None:
    if not isinstance(report, dict):
        return None
    criteria = report.get("criteria", [])
    if not isinstance(criteria, list):
        return None
    for item in criteria:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "auto_repair_success_rate":
            detail = item.get("detail", {})
            if isinstance(detail, dict):
                try:
                    return float(detail.get("success_rate"))
                except (TypeError, ValueError):
                    return None
    return None


def _parse_compression_ratio(output: str) -> float | None:
    pruned_match = re.search(r"Aggression 0\.9 \(Pruned\):\s+(\d+)\s+chars", output)
    full_match = re.search(r"Aggression 0\.1 \(Full\):\s+(\d+)\s+chars", output)
    if not pruned_match or not full_match:
        return None
    pruned = int(pruned_match.group(1))
    full = int(full_match.group(1))
    if pruned <= 0:
        return None
    return full / pruned


def _validate_target_file(target_file: Path) -> tuple[bool, str]:
    if not target_file.exists():
        return False, "target_missing"
    if target_file.suffix != ".py":
        return True, "target_exists_non_python"
    cmd = [sys.executable, "-m", "py_compile", str(target_file)]
    res = _run_cmd(cmd, cwd=REPO_ROOT)
    if res.returncode != 0:
        return False, f"py_compile_failed:{res.stderr.strip()[:200]}"
    return True, "py_compile_ok"


def _evaluate_sample(
    round_index: int,
    target_file: Path,
    benchmark_cmd: list[str],
    acceptance_cmd: list[str],
) -> SampleResult:
    bench_res = _run_cmd(benchmark_cmd, cwd=REPO_ROOT)
    acc_res = _run_cmd(acceptance_cmd, cwd=REPO_ROOT)
    target_ok, target_msg = _validate_target_file(target_file)

    judicial_ok = "POLICY_VIOLATION" in bench_res.stdout
    policy_merge_ok = "Policy Recursive Merge:   SUCCESS" in bench_res.stdout
    benchmark_ok = bench_res.returncode == 0 and judicial_ok and policy_merge_ok

    acceptance_ok = (
        acc_res.returncode == 0
        and "status=PASS" in acc_res.stdout
        and "gate_passed=true" in acc_res.stdout
    )
    acceptance_report = _read_acceptance_report()
    acceptance_success_rate = _extract_success_rate(acceptance_report)

    # Weighted score based on real command outcomes.
    score = 0.0
    score += 0.4 if benchmark_ok else 0.0
    score += 0.4 if acceptance_ok else 0.0
    score += 0.2 if target_ok else 0.0

    compression_ratio = _parse_compression_ratio(bench_res.stdout)
    total_latency_ms = bench_res.elapsed_ms + acc_res.elapsed_ms

    details = {
        "benchmark_cmd": bench_res.cmd,
        "benchmark_returncode": bench_res.returncode,
        "acceptance_cmd": acc_res.cmd,
        "acceptance_returncode": acc_res.returncode,
        "judicial_explanation_found": judicial_ok,
        "policy_merge_success_found": policy_merge_ok,
        "target_validation_message": target_msg,
        "acceptance_success_rate": acceptance_success_rate,
    }
    if bench_res.returncode != 0:
        details["benchmark_stderr_tail"] = bench_res.stderr[-500:]
    if acc_res.returncode != 0:
        details["acceptance_stderr_tail"] = acc_res.stderr[-500:]

    return SampleResult(
        round_index=round_index,
        score=score,
        acceptance_passed=acceptance_ok,
        benchmark_passed=benchmark_ok,
        target_validation_passed=target_ok,
        compression_ratio=compression_ratio,
        latency_ms=total_latency_ms,
        details=details,
    )


def _maybe_execute_soft_rollback(cwd: Path, enabled: bool, files: list[str]) -> tuple[bool, str]:
    if not enabled:
        return False, "disabled"
    if not files:
        return True, "no_scoped_files"
    # Soft rollback: tracked worktree restore only.
    cmd = ["git", "restore", "--worktree", "--", *files]
    res = _run_cmd(cmd, cwd=cwd)
    return res.returncode == 0, "ok" if res.returncode == 0 else f"failed:{res.stderr.strip()[:200]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Credible optimization sampler (real measurement)")
    parser.add_argument(
        "--target-file",
        default="nexus/core/handoff_bundle.py",
        help="Holdout target file path relative to repo root",
    )
    parser.add_argument(
        "--auto-rollback",
        choices=["none", "soft"],
        default="none",
        help="Rollback behavior when canary fails. Default: none (recommend only)",
    )
    parser.add_argument(
        "--force-canary-fail",
        action="store_true",
        help="Testing-only: force canary trigger to verify rollback pipeline",
    )
    parser.add_argument("--n-samples", type=int, default=None, help="Override number of samples")
    parser.add_argument(
        "--policy-path",
        default=str(DEFAULT_POLICY_PATH),
        help="Path to governance policy yaml",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to JSON report output",
    )
    args = parser.parse_args()

    policy_path = Path(args.policy_path)
    output_path = Path(args.output)
    target_file = (REPO_ROOT / args.target_file).resolve()

    policy = _load_policy(policy_path)
    pvals = _get_policy_values(policy)
    sample_size = args.n_samples if args.n_samples is not None else int(pvals["sample_size_min"])
    sample_size = max(sample_size, int(pvals["sample_size_min"]))
    sigma_max = pvals["significance_sigma_max"]
    mu_min = pvals["generalization_mu_min"]
    default = policy.get("default", {}) if isinstance(policy, dict) else {}
    credible_cfg = default.get("credible_verification", {}) if isinstance(default, dict) else {}
    canary_percent = float(credible_cfg.get("canary_traffic_percent", 10))
    entropy_limit = float(credible_cfg.get("rollback_entropy_limit", 30.0))

    # Pre-run baseline from current acceptance report.
    _run_cmd(DEFAULT_ACCEPTANCE_CMD, cwd=REPO_ROOT)
    baseline_report = _read_acceptance_report()
    baseline_success_rate = _extract_success_rate(baseline_report)

    print(f"[credible-sampler] target={target_file}")
    print(f"[credible-sampler] samples={sample_size} (policy_min={int(pvals['sample_size_min'])})")
    print(f"[credible-sampler] thresholds: mu>={mu_min:.2f}, sigma<={sigma_max:.3f}")
    tracked_before = _git_modified_tracked_files(REPO_ROOT)

    results: list[SampleResult] = []
    for i in range(1, sample_size + 1):
        sample = _evaluate_sample(
            round_index=i,
            target_file=target_file,
            benchmark_cmd=DEFAULT_BENCHMARK_CMD,
            acceptance_cmd=DEFAULT_ACCEPTANCE_CMD,
        )
        results.append(sample)
        print(
            f"[sample {i}] score={sample.score:.3f} "
            f"benchmark={sample.benchmark_passed} acceptance={sample.acceptance_passed} "
            f"target={sample.target_validation_passed} latency_ms={sample.latency_ms:.1f}"
        )

    scores = [r.score for r in results]
    mu = mean(scores) if scores else 0.0
    sigma = pstdev(scores) if len(scores) > 1 else 0.0
    avg_latency_ms = mean([r.latency_ms for r in results]) if results else 0.0
    avg_compression_ratio = mean([r.compression_ratio for r in results if r.compression_ratio is not None]) if any(
        r.compression_ratio is not None for r in results
    ) else None

    statistical_rigor = sigma <= sigma_max
    generalization = mu >= mu_min
    credible = statistical_rigor and generalization

    # Canary decision: evaluate only a canary subset of samples.
    canary_count = max(1, int(math.ceil(sample_size * canary_percent / 100.0)))
    canary_samples = results[-canary_count:]
    canary_success_rates = [
        float(s.details["acceptance_success_rate"])
        for s in canary_samples
        if s.details.get("acceptance_success_rate") is not None
    ]
    canary_avg_success_rate = mean(canary_success_rates) if canary_success_rates else None
    success_rate_drop = None
    if baseline_success_rate is not None and canary_avg_success_rate is not None:
        success_rate_drop = baseline_success_rate - canary_avg_success_rate

    # Entropy proxy from execution stability + quality (lower is better).
    failure_rate = 1.0 - mu
    entropy_proxy = (failure_rate * 100.0) + (sigma * 100.0)

    canary_reasons: list[str] = []
    if success_rate_drop is not None and success_rate_drop > 5.0:
        canary_reasons.append("success_rate_drop")
    if entropy_proxy > entropy_limit:
        canary_reasons.append("entropy_proxy_high")
    if any(not s.acceptance_passed for s in canary_samples):
        canary_reasons.append("acceptance_gate_failed")
    if args.force_canary_fail:
        canary_reasons.append("forced_for_test")

    canary_triggered = bool(canary_reasons)
    rollback_recommended = canary_triggered
    rollback_executed = False
    rollback_mode = args.auto_rollback
    rollback_status = "not_requested"
    tracked_after = _git_modified_tracked_files(REPO_ROOT)
    rollback_scope = sorted(list(tracked_after - tracked_before))
    if rollback_recommended and args.auto_rollback == "soft":
        rollback_executed, rollback_status = _maybe_execute_soft_rollback(
            REPO_ROOT, enabled=True, files=rollback_scope
        )

    canary_decision = CanaryDecision(
        canary_enabled=True,
        canary_sample_count=canary_count,
        baseline_success_rate=baseline_success_rate,
        canary_avg_success_rate=canary_avg_success_rate,
        success_rate_drop=success_rate_drop,
        entropy_proxy=entropy_proxy,
        entropy_limit=entropy_limit,
        triggered=canary_triggered,
        reasons=canary_reasons,
        rollback_recommended=rollback_recommended,
        rollback_executed=rollback_executed,
        rollback_mode=rollback_mode,
        rollback_files=rollback_scope,
    )

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_root": str(REPO_ROOT),
        "target_file": str(target_file),
        "policy_path": str(policy_path),
        "thresholds": {
            "sample_size_min": int(pvals["sample_size_min"]),
            "actual_sample_size": sample_size,
            "generalization_mu_min": mu_min,
            "significance_sigma_max": sigma_max,
        },
        "summary": {
            "mu": round(mu, 6),
            "sigma": round(sigma, 6),
            "avg_latency_ms": round(avg_latency_ms, 3),
            "avg_compression_ratio": round(avg_compression_ratio, 6) if avg_compression_ratio is not None else None,
            "statistical_rigor_passed": statistical_rigor,
            "generalization_passed": generalization,
            "credible_optimization": credible,
        },
        "canary": asdict(canary_decision),
        "rollback_status": rollback_status,
        "samples": [asdict(r) for r in results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 68)
    print("Credible Optimization Report")
    print(f"mu={mu:.4f}, sigma={sigma:.4f}, avg_latency_ms={avg_latency_ms:.2f}")
    if avg_compression_ratio is not None:
        print(f"avg_compression_ratio={avg_compression_ratio:.2f}x")
    print(f"statistical_rigor={'PASS' if statistical_rigor else 'FAIL'}")
    print(f"generalization={'PASS' if generalization else 'FAIL'}")
    print(
        f"canary={'TRIGGERED' if canary_triggered else 'STABLE'} "
        f"(entropy_proxy={entropy_proxy:.2f}/{entropy_limit:.2f})"
    )
    if rollback_recommended:
        print(f"rollback=RECOMMENDED mode={args.auto_rollback} status={rollback_status}")
    print(f"overall={'CREDIBLE' if credible else 'NOT_CREDIBLE'}")
    print(f"report={output_path}")
    print("=" * 68)

    return 0 if credible else 2


if __name__ == "__main__":
    raise SystemExit(main())
