#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.app.research_flow_service import _runtime_receipt_plan_payload, build_route


REPAIR_TASKS = (
    (
        "nexus-value-repair-001",
        "Repair the implementation after an intentionally tempting first patch breaks an invariant; "
        "success requires using the failure tail to produce a bounded second edit.",
    ),
    (
        "nexus-value-repair-002",
        "Repair a flaky-looking timeout calculation without deleting assertions; "
        "success requires preserving the behavioral contract and validating the actual failing branch.",
    ),
)

WEARING_CONTRACT = """

Nexus wearing contract:
- MemPalace: keep the solution inside the task scope and enforce explicit governance constraints.
- Belief: when evidence is incomplete or confidence is low, prefer a conservative fix backed by tests.
- Artifact/Claim: treat completion claims as valid only when backed by concrete artifacts or passing checks.
"""


def _ok(name: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "passed": True, "details": details}


def _fail(name: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "passed": False, "reason": reason, "details": details}


def validate_repair_factory_skipped_routes(repo_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for task_id, desc in REPAIR_TASKS:
        route = build_route(
            repo_root=repo_root,
            task_desc=desc + WEARING_CONTRACT,
            task_type="public_test_repair",
            candidate_count=1,
            root_cause_confidence=1.0,
            findings_query=None,
            target_file=f".nexus/bench_cases/{task_id}/target.py",
        )
        stack = route.get("capability_stack", {}) if isinstance(route.get("capability_stack"), dict) else {}
        plan = route.get("capability_plan", {}) if isinstance(route.get("capability_plan"), dict) else {}
        selected_stack = set(stack.get("selected_capabilities", []) or [])
        selected_plan = set(plan.get("selected_capabilities", []) or [])
        readiness = (route.get("route_features", {}) or {}).get("candidate_factory_readiness_estimate", {})
        forbidden = {"autoreason", "judge_panel", "llm_judge_panel"}
        if forbidden & selected_stack:
            checks.append(
                _fail(
                    "repair_factory_skipped_route",
                    "ranking_layer_selected_in_compat_stack",
                    task_id=task_id,
                    readiness=readiness,
                    selected=sorted(selected_stack),
                )
            )
            continue
        if forbidden & selected_plan:
            checks.append(
                _fail(
                    "repair_factory_skipped_route",
                    "ranking_layer_selected_in_capability_plan",
                    task_id=task_id,
                    readiness=readiness,
                    selected=sorted(selected_plan),
                )
            )
            continue
        checks.append(
            _ok(
                "repair_factory_skipped_route",
                task_id=task_id,
                readiness=readiness,
                selected_stack=sorted(selected_stack),
                selected_plan=sorted(selected_plan),
            )
        )
    return checks


def validate_runtime_receipt_reconcile() -> list[dict[str, Any]]:
    pruned_capabilities: dict[str, Any] = {}
    pruned = _runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper", "autoreason", "judge_panel", "llm_judge_panel"]},
        {
            "capabilities": pruned_capabilities,
            "autoreason": {
                "status": "SKIPPED",
                "stop_reason": "candidate_factory_skipped",
                "judge_votes": [],
            },
        },
    )
    selected_pruned = set(pruned.get("selected_capabilities", []) or [])
    if {"autoreason", "judge_panel", "llm_judge_panel"} & selected_pruned:
        return [_fail("runtime_receipt_reconcile", "skipped_ranking_layer_not_pruned", selected=sorted(selected_pruned))]
    if not pruned_capabilities.get("runtime_pruned_capabilities"):
        return [_fail("runtime_receipt_reconcile", "runtime_pruned_capabilities_missing")]

    restored = _runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
            },
        },
    )
    selected_restored = set(restored.get("selected_capabilities", []) or [])
    if "autoreason" not in selected_restored:
        return [_fail("runtime_receipt_reconcile", "runtime_autoreason_success_not_restored", selected=sorted(selected_restored))]
    return [_ok("runtime_receipt_reconcile", pruned=sorted(selected_pruned), restored=sorted(selected_restored))]


def repair_subset_command(output_dir: str) -> list[str]:
    return [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        "scripts/bench/public_benchmark_nexus_value_v1.json",
        "--nexus-only",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--force-flow",
        "hyper_sprint",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--task-id-filter",
        "nexus-value-repair-001,nexus-value-repair-002",
        "--timeout-sec",
        "300",
        "--per-task-stop-loss-sec",
        "600",
        "--total-timeout-sec",
        "1200",
        "--force-learn-slo-ready",
        "--neutralize-history",
        "--disable-learning-loop",
        "--materialize-missing",
        "--isolation-mode",
        "preserve_target",
        "--evidence-bundle",
        "--output-dir",
        output_dir,
        "--markdown-report",
        "auto",
    ]


def run_repair_subset(repo_root: Path, output_dir: str) -> dict[str, Any]:
    cmd = repair_subset_command(output_dir)
    result = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    return {
        "name": "flash_style_repair_subset",
        "passed": result.returncode == 0,
        "command": cmd,
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
    }


def build_payload(repo_root: Path, *, run_repair: bool, output_dir: str) -> dict[str, Any]:
    checks = [
        *validate_repair_factory_skipped_routes(repo_root),
        *validate_runtime_receipt_reconcile(),
    ]
    if run_repair:
        checks.append(run_repair_subset(repo_root, output_dir))
    failures = [item for item in checks if not item.get("passed")]
    return {
        "schema_version": "nexus_pre_flash_gate.v1",
        "passed": not failures,
        "checks": checks,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fast Nexus checks before expensive Flash A/B benchmarks.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--quick", action="store_true", help="Run deterministic local route/receipt checks only.")
    parser.add_argument("--run-repair-subset", action="store_true", help="Run two-task Flash-style Nexus-only repair subset.")
    parser.add_argument("--output-dir", default=".nexus/reports/bench_flash_repair_pruning_prefash")
    args = parser.parse_args(argv)

    run_repair = bool(args.run_repair_subset and not args.quick)
    payload = build_payload(Path(args.repo_root).resolve(), run_repair=run_repair, output_dir=args.output_dir)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
