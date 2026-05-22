#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_BACKLOG = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
DEFAULT_MANIFEST = Path("docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_MANIFEST_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json")
RUNNER_CAPABILITY_ALIAS = {
    "benchmark_meta_opt": "judge_panel",
    "direct_master_loop": "hyper",
    "autonomic_router": "autoreason",
    "external_productivity": "research",
    "file_lock_security_gate": "ultra_review",
    "forecast_pregate": "autoreason",
    "governance_and_trust": "mempalace_gate",
    "hyper_sprint": "hyper",
    "learn_ask": "semantic_searcher",
    "learning_closure": "semantic_failure_sensor",
    "mempalace": "mempalace_gate",
    "metabolism_resume": "semantic_failure_sensor",
    "policy_capability_gate": "mempalace_gate",
    "registry_skills_sync": "semantic_searcher",
    "regression_guard": "semantic_failure_sensor",
    "repair_loop": "hyper",
    "research_control_plane": "research",
    "research_and_source_discipline": "research",
    "sandbox_replay": "harness_preflight_sensor",
    "swarm_multi_agent": "swarm",
    "ui_validator": "ultra_review",
    "xray": "codeintel",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _task_for_candidate(item: dict, *, index: int) -> dict:
    capability_id = str(item.get("capability_id") or "")
    skill_id = str(item.get("skill_id") or "")
    runner_capability = RUNNER_CAPABILITY_ALIAS.get(capability_id, capability_id)
    task_id = f"ztv2-fresh-{_slug(capability_id)}-{index:03d}"
    return {
        "id": task_id,
        "task_desc": (
            "Implement compute_backoff(attempt) in target.py so the visible and hidden pytest "
            "contracts pass. Required behavior: attempt 1 returns 1, attempt 2 returns 2, "
            "attempt 3 returns 4, and non-positive attempts are rejected. This is the fresh "
            f"Zero-Trust V2 behavior canary for capability {capability_id} and candidate "
            f"skill {skill_id}; promotion still requires runtime-signed V2 receipts."
        ),
        "target_file": "target.py",
        "test_file": "test_visible.py",
        "success_criteria": "visible_and_hidden_pytest_pass_with_runtime_signed_v2_receipt",
        "category": capability_id,
        "difficulty": "medium",
        "repo_kind": "neutral_fixture",
        "repo": "fixture://zero-trust-v2-fresh-skill-behavior",
        "repo_ref": "v1",
        "fixture_kind": "pytest_async_repair",
        "mutation_required": True,
        "allowed_files": ["target.py"],
        "forbidden_files": [".nexus/", "logs/", "benchmarks/"],
        "setup_command": "python -m pytest --version",
        "verification_command": "python -m pytest -q test_visible.py",
        "expected_capabilities": [runner_capability],
        "capability_activation_contract": "required",
        "eligibility_class": "model_required",
        "public_claim_allowed_metrics": [],
    }


def build_zero_trust_v2_fresh_task_refs(*, backlog: dict, manifest_path: str = str(DEFAULT_MANIFEST)) -> dict:
    candidates = [item for item in backlog.get("items", []) or [] if isinstance(item, dict)]
    tasks = [_task_for_candidate(item, index=index) for index, item in enumerate(candidates, start=1)]
    manifest = {
        "schema": "nexus.zero_trust_v2.fresh_task_manifest.v1",
        "version": "2026-05-21",
        "frozen": True,
        "benchmark_id": "zero-trust-v2-fresh-task-ref-v1",
        "description": "Fresh task manifest for Zero Trust V2 physical behavior runs.",
        "created_at": datetime.now(UTC).isoformat(),
        "tasks": tasks,
    }
    write_json(manifest_path, manifest)
    items = []
    for item, task in zip(candidates, tasks, strict=False):
        items.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "skill_id": str(item.get("skill_id") or ""),
                "priority": str(item.get("priority") or ""),
                "task_ref": {"manifest": manifest_path, "task_id": task["id"]},
                "promotion_credit_allowed": False,
            }
        )
    priority_counts = {priority: sum(1 for item in items if item["priority"] == priority) for priority in ("P0", "P1", "P2")}
    return {
        "schema": "nexus.zero_trust_v2.fresh_task_refs.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_backlog": str(DEFAULT_BACKLOG),
        "fresh_task_manifest": manifest_path,
        "zero_trust_v2_task_metadata": [
            {
                "task_id": task["id"],
                "capability_id": str(item.get("capability_id") or ""),
                "runner_capability": (task.get("expected_capabilities") or [""])[0],
                "candidate_skill_id": str(item.get("skill_id") or ""),
                "requires_runtime_signed_receipt": True,
                "requires_physical_sandbox": True,
                "requires_clean_slate": True,
            }
            for item, task in zip(candidates, tasks, strict=False)
        ],
        "summary": {
            "candidate_count": len(items),
            "fresh_task_ref_count": len(items),
            "p0_count": priority_counts["P0"],
            "p1_count": priority_counts["P1"],
            "p2_count": priority_counts["P2"],
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "items": items,
        "claim_boundary": [
            "Fresh task_ref enables execution planning only.",
            "Promotion credit remains false until physical behavior execution emits signed V2 receipts.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 fresh task refs.")
    parser.add_argument("--backlog", default=str(DEFAULT_BACKLOG))
    parser.add_argument("--manifest-output", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_fresh_task_refs(backlog=read_json(args.backlog), manifest_path=args.manifest_output)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
