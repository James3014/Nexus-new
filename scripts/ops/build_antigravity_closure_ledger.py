#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.ops.report_output import resolve_report_output


DEFAULT_SOURCE_ROOT = Path(
    "/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790"
)
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ANTIGRAVITY_CLOSURE_LEDGER_2026-05-22.json")

SOURCE_FILES = (
    "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
    "nexus_routing_spec_v2.md",
    "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
    "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
    "NEXUS_REMAINING_DEBT_BACKLOG.md",
    "NEXUS_SWARM_DECOUPLED_SPEC.md",
)

FORBIDDEN_PATTERNS = (
    ".obsidian/",
    "benchmarks/",
    "logs/",
    "nexus_swarm/",
    "packages/",
    "ZERO_TRUST",
    "zero_trust",
)


@dataclass(frozen=True)
class Probe:
    path: str
    contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class LedgerItem:
    item_id: str
    source: str
    recommendation: str
    status: str
    successor_action: str
    probes: tuple[Probe, ...] = ()
    evidence_note: str = ""


LEDGER_ITEMS: tuple[LedgerItem, ...] = (
    LedgerItem(
        "routing_v2_outcome_memory_writeback",
        "nexus_routing_spec_v2.md",
        "OutcomeMemory automatic episode writeback and dynamic policy tuning.",
        "DONE",
        "Preserve current writeback and focused tests.",
        (
            Probe("nexus/learning/outcome_memory.py", ("OutcomeMemoryManager", "EpisodeOutcomeRecord")),
            Probe("nexus/app/research_flow_service.py", ("OutcomeMemoryManager", "save_episode_and_tune_sync")),
            Probe("tests/engine/test_rlm_outcome_integration.py", ("OutcomeMemoryManager",)),
        ),
    ),
    LedgerItem(
        "routing_v2_bounded_rlm_receipt",
        "nexus_routing_spec_v2.md",
        "RLM X/R-loop budget receipts before recursive runtime dispatch.",
        "DONE",
        "Keep as bounded adapter until a separate runtime gate authorizes recursion.",
        (
            Probe("nexus/engine/rlm_controller.py", ("RlmController", "build_bounded_rlm_orchestration_receipt")),
            Probe(
                "tests/contracts/test_routing_spec_v2_backlog.py",
                ("IMPLEMENTED_AS_BOUNDED_ADAPTER", "full_recursive_dispatch_requires_separate_runtime_authorization"),
            ),
        ),
    ),
    LedgerItem(
        "routing_v2_full_recursive_dispatch",
        "nexus_routing_spec_v2.md",
        "Full ResearchFlowService X-loop/R-loop recursive runtime orchestration.",
        "APPROVED_BOUNDED_GATE_REPORTED",
        "Keep runtime defaults locked; bounded implementation gate is approved.",
        (
            Probe("docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md", ("Full recursive dispatch remains a separate authorization gate",)),
            Probe("docs/plans/NEXUS_OPTIMIZATION_CONTRACT_AND_RETENTION_2026-05-19.md", ("full recursive dispatch remains a separate runtime authorization gate",)),
            Probe(
                "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json",
                ("APPROVED", "max_recursion_depth"),
            ),
        ),
    ),
    LedgerItem(
        "clean_code_route_decider_extraction",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Extract research route decisions from ResearchFlowService.",
        "DONE",
        "Preserve compatibility wrapper and monkeypatch-sensitive tests.",
        (
            Probe("nexus/research/flow/route_decider.py", ("collect_route_signals", "decide_flow")),
            Probe("nexus/app/research_flow_service.py", ("route_decider",)),
        ),
    ),
    LedgerItem(
        "clean_code_evidence_packer_extraction",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Extract research evidence packing from ResearchFlowService.",
        "DONE",
        "Preserve current evidence read-model fields.",
        (
            Probe("nexus/research/flow/evidence_packer.py", ("build_research_context", "write_msa_receipt_reports")),
            Probe("nexus/app/research_flow_service.py", ("evidence_packer",)),
        ),
    ),
    LedgerItem(
        "clean_code_signal_collector_module",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Create a dedicated flow/signal_collector.py module.",
        "DONE",
        "Preserve route_decider compatibility facade and reexport test.",
        (
            Probe("nexus/research/flow/signal_collector.py", ("collect_route_signals", "RouteSignals")),
            Probe("nexus/research/flow/route_decider.py", ("signal_collector", "collect_route_signals")),
            Probe("tests/app/test_research_flow_service.py", ("test_route_decider_reexports_split_signal_collector_contracts",)),
        ),
        "Signal collection is extracted into signal_collector.py with route_decider reexport compatibility.",
    ),
    LedgerItem(
        "clean_code_orchestrator_module",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Create a dedicated flow/orchestrator.py module for R/X-loop orchestration.",
        "DONE_BOUNDED_POLICY_READY",
        "Keep runtime defaults locked until post-implementation smoke explicitly promotes them.",
        (Probe("nexus/research/flow/orchestrator.py"),),
    ),
    LedgerItem(
        "clean_code_pipeline_repair_split",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Split pipeline repair audit evaluation and escalation management.",
        "PARTIAL_CLOSED_FOR_CBO",
        "Reopen only under a failing RLM/repair acceptance gate.",
        (
            Probe("nexus/engine/repair/audit_evaluator.py", ("evaluate_audit_result",)),
            Probe("nexus/engine/repair/escalation_manager.py", ("handle_escalation",)),
            Probe("nexus/engine/pipeline_repair.py"),
            Probe("docs/plans/NEXUS_CODEBASE_OPTIMIZATION_TASK_PLAN_2026-05-20.md", ("pipeline_repair.py", "large legacy facade")),
        ),
    ),
    LedgerItem(
        "clean_code_capability_planner_split",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Split capability planner A/B evaluation and policy application.",
        "PARTIAL_CLOSED_FOR_CLEAN_CODE",
        "Do not split further unless policy order or test injection requires it.",
        (
            Probe("nexus/engine/planner/ab_evaluator.py", ("build_decision_trace",)),
            Probe("nexus/engine/planner/policy_applier.py", ("apply_learning_policy",)),
            Probe("nexus/engine/learning_policy_store.py", ("LearningPolicyStore",)),
            Probe("nexus/engine/capability_planner.py"),
        ),
    ),
    LedgerItem(
        "clean_code_root_cleanup",
        "NEXUS_CLEAN_CODE_AUDIT_REPORT.md",
        "Move or clean root scripts and loose entrypoints.",
        "DONE_WITH_ZERO_MOVES",
        "Future movement needs compatibility wrappers and owner review.",
        (
            Probe("docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md", ("CC-8 Root Script Cleanup Result", "moved `0` files")),
            Probe("docs/reports/NEXUS_CLEAN_CODE_ROOT_CLEANUP_SAFETY_REVIEW_2026-05-20.md"),
        ),
    ),
    LedgerItem(
        "cbo_belief_state_atomic_write",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Make belief_state.json writes atomic and locked.",
        "DONE",
        "Preserve StateJsonStore.",
        (
            Probe("nexus/infrastructure/state_json_store.py", ("fcntl.flock", "os.replace", "fsync")),
            Probe("nexus/core/belief_engine.py", ("StateJsonStore",)),
        ),
    ),
    LedgerItem(
        "cbo_findings_vector_split",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Decouple findings-card persistence from vector sync.",
        "DONE",
        "Keep vector sync injectable and persistence file-first.",
        (
            Probe("nexus/research/findings_store.py", ("FindingsFileStore",)),
            Probe("nexus/research/findings_vector_sync.py", ("MemoryRepositoryFindingsVectorSync",)),
            Probe("nexus/research/findings_memory.py", ("FindingsFileStore", "vector_sync")),
        ),
    ),
    LedgerItem(
        "cbo_scoped_lancedb_lifecycle",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Reuse LanceDB/retrieval repository lifecycle without hidden globals.",
        "DONE",
        "Use ScopedMemoryRepositoryRegistry for local registry-like work.",
        (
            Probe("nexus/services/memory_repository_lifecycle.py", ("ScopedMemoryRepositoryRegistry",)),
            Probe("tests/services/test_memory_repository_lifecycle.py", ("ScopedMemoryRepositoryRegistry",)),
        ),
    ),
    LedgerItem(
        "cbo_guarded_fetch",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Guard remote source refresh paths from SSRF, unsafe redirects, and private targets.",
        "DONE_FOR_SOURCE_REFRESH_PATHS",
        "Extend only after a new unguarded fetch call site is identified.",
        (
            Probe("nexus/infrastructure/guarded_fetch.py", ("GuardedFetcher", "GuardedFetchError")),
            Probe("nexus/research/doc_scout_adapter.py", ("GuardedFetcher",)),
            Probe("tests/contracts/test_network_fetch_guard.py", ("blocks_private",)),
        ),
    ),
    LedgerItem(
        "cbo_retrieval_query_guard",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Add typed retrieval query sanitizer and receipt.",
        "DONE",
        "Keep query-shape safety separate from relevance claims.",
        (
            Probe("nexus/contracts/retrieval_query.py", ("RetrievalQuery",)),
            Probe("tests/contracts/test_retrieval_query.py", ("build_retrieval_query",)),
        ),
    ),
    LedgerItem(
        "cbo_history_signal_store",
        "NEXUS_CODEBASE_OPTIMIZATION_PLAN.md",
        "Bound auto-flow-history reads and avoid unbounded route memory ingestion.",
        "DONE_FAIL_CLOSED",
        "Add rollup writer only as a later evidence-preserving successor.",
        (
            Probe("nexus/research/flow/history_signal_store.py", ("HistorySignalStore", "max_entries", "max_bytes")),
            Probe("tests/research/test_history_signal_store.py", ("HistorySignalStore",)),
        ),
    ),
    LedgerItem(
        "deep_context_dependencies_strict_mode",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Make ContextHub dependency injection strict and stateless-coordinator compatible.",
        "DONE",
        "Preserve strict deps and runtime adapter seams.",
        (
            Probe("nexus/core/context_hub.py", ("ContextDependencies", "strict_deps")),
            Probe("nexus/core/context_runtime_adapter.py", ("StatelessContextCoordinator",)),
            Probe("tests/core/test_context_hub_strict_deps.py", ("strict_deps", "StatelessContextCoordinator")),
        ),
    ),
    LedgerItem(
        "deep_contexthub_physical_split",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Physically split ContextHub into smaller deep modules.",
        "PARTIAL_GATE_REPORTED",
        "Keep ContextHub as compatibility facade until caller map and deletion tests are green.",
        (
            Probe("nexus/core/context_hub.py", ("class ContextHub",)),
            Probe("docs/plans/NEXUS_ANTIGRAVITY_CLOSURE_AND_DECOUPLED_SWARM_PLAN_2026-05-22.md", ("P8 - ContextHub Physical Split Pregate",)),
            Probe(
                "docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json",
                ("physical_split_requires_caller_map_and_deletion_tests",),
            ),
        ),
        "Strict deps exist, but ContextHub remains the compatibility facade.",
    ),
    LedgerItem(
        "deep_evidence_sealing_contract",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Hash-seal evidence records.",
        "DONE",
        "Use as primitive for the runtime read barrier.",
        (
            Probe("nexus/contracts/evidence_sealing.py", ("sha256", "seal")),
            Probe("tests/contracts/test_evidence_sealing.py", ("tamper",)),
        ),
    ),
    LedgerItem(
        "deep_evidence_sealing_runtime_barrier",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Block claim reads from unsealed evidence with an explicit barrier.",
        "DONE_CONTRACT_BARRIER",
        "Integrate into a concrete claim/report reader only after a narrow call site is selected.",
        (
            Probe("nexus/contracts/evidence_sealing.py", ("seal",)),
            Probe(
                "nexus/contracts/evidence_sealing_barrier.py",
                ("UnsealedEvidenceError", "claim_read_allowed", "partial_telemetry_detected"),
            ),
            Probe("tests/contracts/test_evidence_sealing_barrier.py", ("UnsealedEvidenceError", "tampered")),
        ),
        "A contract-level barrier exists; broad claim-reader integration remains a separate narrow call-site task.",
    ),
    LedgerItem(
        "deep_fault_tolerant_ast_snapshot",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Add last-known-good AST snapshot fallback for parse-noise resilience.",
        "DONE_ADAPTER_READY",
        "Integrate only through existing CodeIntel skeleton callers after a narrow caller map.",
        (
            Probe(
                "nexus/services/codeintel/fault_tolerant_ast_snapshot.py",
                ("FaultTolerantASTSnapshot", "UNPARSABLE_HOTSPOT", "stores_source_text"),
            ),
            Probe(
                "tests/nexus/codeintel/test_fault_tolerant_ast_snapshot.py",
                ("used_last_known_good", "UNPARSABLE_HOTSPOT"),
            ),
            Probe("nexus/services/codeintel/skeleton_provider.py", ("Skeleton",)),
        ),
        "A bounded snapshot adapter now wraps the existing skeleton provider without broad caller migration.",
    ),
    LedgerItem(
        "deep_sqlite_retry_handler",
        "NEXUS_OPT_DEEP_VULNERABILITY_AUDIT.md",
        "Add jittered SQLite busy retry handler for concurrent writes.",
        "DONE_ADAPTER_READY",
        "Integrate into one SQLite-backed service only after selecting a narrow write path.",
        (
            Probe("nexus/infrastructure/sqlite_retry.py", ("SQLiteRetryHandler", "is_retryable_sqlite_busy")),
            Probe("tests/infrastructure/test_sqlite_retry.py", ("sqlite_busy_retry_exhausted", "sqlite_error_not_retryable")),
            Probe("nexus/contracts/sqlite_write_guard.py", ("sqlite",)),
        ),
        "A reusable bounded retry adapter exists; broad service integration remains a separate narrow call-site task.",
    ),
    LedgerItem(
        "swarm_direct_sidecar_registry_nsp",
        "NEXUS_SWARM_DECOUPLED_SPEC.md",
        "Implement Go Swarm Sidecar Webhook, Registry Board 2.0, and NSP v0.2 directly.",
        "FORBIDDEN_DIRECT",
        "Do not touch nexus_swarm; translate only into local simulation seams.",
        (),
        "Direct Swarm/NSP/Go sidecar work is outside the current allowed path boundary.",
    ),
    LedgerItem(
        "swarm_local_gateway",
        "NEXUS_SWARM_DECOUPLED_SPEC.md",
        "Translate sidecar request governance into a local gateway contract.",
        "DONE_CONTRACT_READY",
        "Integrate only after a real unguarded provider/tool call site is identified.",
        (
            Probe("nexus/contracts/local_gateway.py", ("build_local_gateway_receipt", "circuit_open")),
            Probe("tests/contracts/test_antigravity_local_simulation_contracts.py", ("private_network_targets",)),
        ),
    ),
    LedgerItem(
        "swarm_local_memory_hub",
        "NEXUS_SWARM_DECOUPLED_SPEC.md",
        "Translate Registry Board 2.0 into local capability and health snapshots.",
        "DONE_CONTRACT_READY",
        "Wire into route receipts only after selecting stable read-only inputs.",
        (
            Probe("nexus/contracts/local_memory_hub.py", ("build_local_memory_hub_snapshot", "mutable_global_singleton")),
            Probe("tests/contracts/test_antigravity_local_simulation_contracts.py", ("local_memory_hub",)),
        ),
    ),
    LedgerItem(
        "swarm_local_event_pipeline",
        "NEXUS_SWARM_DECOUPLED_SPEC.md",
        "Translate NSP v0.2 streaming semantics into local async event envelopes.",
        "DONE_CONTRACT_READY",
        "Keep in-memory and test-only until runtime authorization exists.",
        (
            Probe("nexus/contracts/local_event_pipeline.py", ("LocalEventPipeline", "unsealed_evidence_event_blocked")),
            Probe("tests/contracts/test_antigravity_local_simulation_contracts.py", ("preserves_order",)),
        ),
    ),
)


def _contains_all(path: Path, needles: tuple[str, ...]) -> bool:
    if not needles:
        return path.exists()
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return all(needle in text for needle in needles)


def _probe(repo_root: Path, probe: Probe) -> dict[str, Any]:
    path = repo_root / probe.path
    matched = _contains_all(path, probe.contains)
    return {
        "path": probe.path,
        "exists": path.exists(),
        "contains": list(probe.contains),
        "matched": matched,
    }


def _source_status(source_root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": (source_root / name).as_posix(),
            "name": name,
            "exists": (source_root / name).exists(),
        }
        for name in SOURCE_FILES
    ]


def _validate_no_forbidden_rows(rows: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for row in rows:
        text = " ".join(
            [
                str(row.get("item_id", "")),
                str(row.get("recommendation", "")),
                str(row.get("successor_action", "")),
                " ".join(evidence.get("path", "") for evidence in row.get("evidence", [])),
            ]
        )
        if "zero_trust" in text.lower() or "ZERO_TRUST" in text:
            violations.append(str(row["item_id"]))
    return violations


def build_ledger(*, repo_root: Path = Path("."), source_root: Path = DEFAULT_SOURCE_ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    sources = _source_status(source_root)
    rows: list[dict[str, Any]] = []
    for item in LEDGER_ITEMS:
        evidence = [_probe(repo_root, probe) for probe in item.probes]
        rows.append(
            {
                "item_id": item.item_id,
                "source": item.source,
                "recommendation": item.recommendation,
                "status": item.status,
                "successor_action": item.successor_action,
                "evidence_note": item.evidence_note,
                "evidence": evidence,
                "all_evidence_matched": all(evidence_item["matched"] for evidence_item in evidence) if evidence else True,
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    source_missing = [source["name"] for source in sources if not source["exists"]]
    forbidden_row_violations = _validate_no_forbidden_rows(rows)
    status = "PASS" if not forbidden_row_violations else "FAIL"
    return {
        "schema": "nexus.antigravity_closure_ledger.v1",
        "status": status,
        "claim_class": "PLAN_ONLY",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "performance_improvement_claim_allowed": False,
        "swarm_direct_implementation_allowed": False,
        "zero_trust_v2_modification_allowed": False,
        "source_root": source_root.as_posix(),
        "source_files": sources,
        "summary": {
            "row_count": len(rows),
            "source_file_count": len(sources),
            "source_files_missing": source_missing,
            "status_counts": dict(sorted(status_counts.items())),
            "forbidden_row_violations": forbidden_row_violations,
        },
        "retrieved_lessons": [
            {
                "source": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
                "lesson": "report-retention cleanup should avoid git index mutation unless explicitly staging or committing",
                "plan_effect": "this ledger writes reports only and performs no git operations",
            },
            {
                "source": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
                "lesson": "empty output-dir must normalize to no override before resolving report outputs",
                "plan_effect": "the CLI treats empty string and dot output-dir as None",
            },
            {
                "source": "docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md",
                "lesson": "full RLM recursive dispatch remains a separate authorization gate",
                "plan_effect": "recursive dispatch is classified DEFERRED_BY_GATE",
            },
            {
                "source": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
                "lesson": "closure ledger probes should avoid brittle full-sentence matches",
                "plan_effect": "evidence probes use stable symbols or short independent tokens",
            },
        ],
        "forbidden_patterns": list(FORBIDDEN_PATTERNS),
        "rows": rows,
        "next_recommended_slice": {
            "id": "P9",
            "name": "Select narrow integration call sites",
            "reason": "all non-runtime plan slices now have adapters or fail-closed gate reports",
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_ledger(
    *,
    repo_root: Path = Path("."),
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output: Path = DEFAULT_OUTPUT,
    dry_run: bool = False,
) -> dict[str, Any]:
    ledger = build_ledger(repo_root=repo_root, source_root=source_root)
    if not dry_run:
        _write_json(output, ledger)
    return {
        "status": ledger["status"],
        "dry_run": dry_run,
        "output": output.as_posix(),
        **ledger["summary"],
    }


def _normalize_output_dir(value: Path) -> Path | None:
    return value if str(value) not in {"", "."} else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Nexus Antigravity closure ledger.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path(""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output = resolve_report_output(
        DEFAULT_OUTPUT,
        output=args.output,
        output_dir=_normalize_output_dir(args.output_dir),
    )
    summary = write_ledger(
        repo_root=args.repo_root,
        source_root=args.source_root,
        output=output,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
