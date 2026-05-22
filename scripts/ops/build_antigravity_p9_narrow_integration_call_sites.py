#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ANTIGRAVITY_P9_NARROW_INTEGRATION_CALL_SITES_2026-05-22.json")
SCHEMA = "nexus.antigravity_p9_narrow_integration_call_sites.v1"

FORBIDDEN_PATHS = (
    ".obsidian/",
    "benchmarks/",
    "logs/",
    "nexus_swarm/",
    "packages/",
)

RETRIEVED_LESSONS = (
    {
        "source_path": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
        "applicability": "capability_ab_runner and public-gate extractions require focused contract tests first.",
        "plan_effect": "P9 remains a plan-only report and does not edit public benchmark gates.",
    },
    {
        "source_path": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
        "applicability": "run_auto_flow execution branches should move only after pure helper seams are tested.",
        "plan_effect": "P9 selects call sites without wiring orchestration branches.",
    },
    {
        "source_path": "docs/plans/NEXUS_ANTIGRAVITY_CLOSURE_AND_DECOUPLED_SWARM_PLAN_2026-05-22.md",
        "applicability": "P9 exit requires one file, one call site, one focused test, and one rollback plan per proposal.",
        "plan_effect": "Every selected row carries explicit test and rollback fields.",
    },
)


@dataclass(frozen=True)
class Probe:
    path: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class CallSite:
    adapter: str
    file: str
    call_site: str
    focused_test: str
    rollback_plan: str
    probe: Probe
    implementation_scope: str
    decision: str = "SELECTED_PLAN_ONLY"


CALL_SITES: tuple[CallSite, ...] = (
    CallSite(
        adapter="evidence_sealing_barrier",
        file="scripts/bench/gemini_nexus_report.py",
        call_site="_load_evidence_bundle",
        focused_test=(
            "tests/benchmark/test_gemini_nexus_report.py::"
            "test_load_evidence_bundle_can_require_sealed_evidence_policy"
        ),
        rollback_plan="Keep current direct JSON evidence bundle read when seal-required policy is disabled.",
        probe=Probe("scripts/bench/gemini_nexus_report.py", ("_load_evidence_bundle", "evidence_bundle")),
        implementation_scope="claim/report reader only; historical unsealed bundles stay compatible unless policy opts in.",
    ),
    CallSite(
        adapter="sqlite_retry_handler",
        file="nexus/core/memory_manager.py",
        call_site="_execute_with_retry",
        focused_test=(
            "tests/core/test_memory_manager_sqlite_retry.py::"
            "test_execute_with_retry_uses_sqlite_retry_handler_for_busy_then_success"
        ),
        rollback_plan="Restore local retry loop around _is_retryable_sqlite_lock and _sqlite_jitter_delay.",
        probe=Probe("nexus/core/memory_manager.py", ("_execute_with_retry", "_is_retryable_sqlite_lock")),
        implementation_scope="single SQLite writer retry seam; no global storage or runtime default change.",
    ),
    CallSite(
        adapter="fault_tolerant_ast_snapshot",
        file="nexus/services/codeintel/skeleton_context_adapter.py",
        call_site="build_code_skeleton_context",
        focused_test=(
            "tests/nexus/codeintel/test_skeleton_context_adapter.py::"
            "test_skeleton_context_can_use_last_known_good_snapshot_on_parse_failure"
        ),
        rollback_plan="Keep existing lookup_implementation path and skip snapshot fallback injection.",
        probe=Probe(
            "nexus/services/codeintel/skeleton_context_adapter.py",
            ("build_code_skeleton_context", "lookup_implementation"),
        ),
        implementation_scope="CodeIntel context adapter only; stores compact symbol metadata, not source text.",
    ),
    CallSite(
        adapter="local_gateway",
        file="tests/contracts/test_antigravity_local_simulation_contracts.py",
        call_site="test_local_gateway_allows_non_network_provider_gate_without_sidecar",
        focused_test=(
            "tests/contracts/test_antigravity_local_simulation_contracts.py::"
            "test_local_gateway_allows_non_network_provider_gate_without_sidecar"
        ),
        rollback_plan="Leave provider/tool/network calls on their current guarded paths until a real unsafe call site is proven.",
        probe=Probe(
            "tests/contracts/test_antigravity_local_simulation_contracts.py",
            ("build_local_gateway_receipt", "provider_call"),
        ),
        implementation_scope="contract-ready test-only proof; no provider proxy or sidecar.",
    ),
    CallSite(
        adapter="local_memory_hub",
        file="tests/contracts/test_antigravity_local_simulation_contracts.py",
        call_site="test_local_memory_hub_snapshot_is_read_only_and_health_checked",
        focused_test=(
            "tests/contracts/test_antigravity_local_simulation_contracts.py::"
            "test_local_memory_hub_snapshot_is_read_only_and_health_checked"
        ),
        rollback_plan="Keep memory/health snapshots out of runtime receipts until a read-only report consumer is selected.",
        probe=Probe(
            "tests/contracts/test_antigravity_local_simulation_contracts.py",
            ("build_local_memory_hub_snapshot", "mutable_global_singleton"),
        ),
        implementation_scope="contract-ready read-only snapshot; no globals or distributed heartbeat.",
    ),
    CallSite(
        adapter="local_event_pipeline",
        file="tests/contracts/test_antigravity_local_simulation_contracts.py",
        call_site="test_local_event_pipeline_preserves_order_and_blocks_unsealed_evidence",
        focused_test=(
            "tests/contracts/test_antigravity_local_simulation_contracts.py::"
            "test_local_event_pipeline_preserves_order_and_blocks_unsealed_evidence"
        ),
        rollback_plan="Keep event publication test-only and do not add daemon/server wiring.",
        probe=Probe(
            "tests/contracts/test_antigravity_local_simulation_contracts.py",
            ("LocalEventPipeline", "unsealed_evidence_event_blocked"),
        ),
        implementation_scope="test-only async progress pipeline; no daemon or server.",
    ),
)


def build_report(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    selected = [_row_for(repo_root, call_site) for call_site in CALL_SITES]
    missing = [
        {
            "adapter": row["adapter"],
            "file": row["file"],
            "missing_tokens": row["missing_tokens"],
        }
        for row in selected
        if not row["probe_matched"]
    ]
    forbidden_paths_touched = sorted(
        {
            row["file"]
            for row in selected
            if any(row["file"].startswith(pattern) for pattern in FORBIDDEN_PATHS)
        }
    )
    status = "PASS" if not missing and not forbidden_paths_touched else "RETURN"
    return {
        "schema": SCHEMA,
        "date": "2026-05-22",
        "status": status,
        "claim_class": "PLAN_ONLY",
        "runtime_default_change_allowed": False,
        "public_benchmark_allowed": False,
        "zero_trust_v2_files_touched": False,
        "forbidden_paths_touched": forbidden_paths_touched,
        "retrieved_lessons": list(RETRIEVED_LESSONS),
        "selected_call_sites": selected,
        "missing_probes": missing,
        "summary": {
            "selected_count": len(selected),
            "missing_probe_count": len(missing),
            "runtime_integration_started": False,
            "requires_new_plan_before_code_wiring": True,
            "max_files_per_future_slice": 10,
        },
    }


def write_report(*, repo_root: Path, output: Path, dry_run: bool = False) -> dict[str, Any]:
    report = build_report(repo_root)
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": report["status"],
        "output": output.as_posix(),
        "dry_run": dry_run,
        "selected_count": report["summary"]["selected_count"],
        "missing_probe_count": report["summary"]["missing_probe_count"],
    }


def _row_for(repo_root: Path, call_site: CallSite) -> dict[str, Any]:
    path = repo_root / call_site.probe.path
    text = ""
    if path.exists():
        text = path.read_text(encoding="utf-8")
    missing_tokens = [token for token in call_site.probe.tokens if token not in text]
    return {
        "adapter": call_site.adapter,
        "decision": call_site.decision,
        "file": call_site.file,
        "call_site": call_site.call_site,
        "focused_test": call_site.focused_test,
        "rollback_plan": call_site.rollback_plan,
        "implementation_scope": call_site.implementation_scope,
        "probe_matched": path.exists() and not missing_tokens,
        "missing_tokens": missing_tokens,
        "runtime_default_change_allowed": False,
        "public_benchmark_allowed": False,
        "zero_trust_v2_touch_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Antigravity P9 narrow integration call-site report.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=args.output_dir)
    summary = write_report(repo_root=args.repo_root, output=output, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
