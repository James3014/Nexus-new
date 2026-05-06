#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.app.research_flow_service import _runtime_receipt_plan_payload, build_route
from nexus.engine.autodata_forge import DataForgeManifestRow, classify_trajectory_quality, write_data_forge_manifest
from nexus.engine.openseeker_alignment import build_openseeker_trace
from nexus.events.transport import NexusEventBus
from scripts.ops.codex_nexus_ab_smoke import benchmark_env as codex_smoke_env
from scripts.ops.codex_nexus_ab_smoke import build_command as codex_smoke_command
from scripts.ops.codex_nexus_ab_smoke import validate_smoke_plan as validate_codex_smoke_plan
from scripts.ops.brain_hub_audit import scan_brain_hub
from scripts.ops.hallucination_guard_drift import audit_drift


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


def validate_brain_hub_alignment(repo_root: Path) -> list[dict[str, Any]]:
    drift = audit_drift()
    hub = scan_brain_hub(repo_root, [], manifest_path=repo_root / "docs" / "ops" / "brain_hub_manifest.json")
    checks: list[dict[str, Any]] = []
    if drift.passed:
        checks.append(
            _ok(
                "hallucination_guard_drift",
                runtime_probes=drift.runtime_probes,
                scoring_spec_rules=drift.scoring_spec_rules,
            )
        )
    else:
        checks.append(
            _fail(
                "hallucination_guard_drift",
                "drift_audit_failed",
                failures=drift.failures,
                runtime_probes=drift.runtime_probes,
            )
        )
    if hub.passed:
        checks.append(
            _ok(
                "brain_hub_audit",
                document_count=len(hub.documents),
                s_stage_runtime_contract=hub.runtime_checklist.get("s_stage_runtime_contract", {}),
            )
        )
    else:
        checks.append(
            _fail(
                "brain_hub_audit",
                "brain_hub_audit_failed",
                failures=hub.failures,
                s_stage_runtime_contract=hub.runtime_checklist.get("s_stage_runtime_contract", {}),
            )
        )
    return checks


def validate_event_contracts(repo_root: Path, *, strict_raw: bool | None = None) -> list[dict[str, Any]]:
    NexusEventBus.configure(repo_root)
    strict_raw = os.environ.get("NEXUS_EVENT_RAW_STRICT") == "1" if strict_raw is None else bool(strict_raw)
    audit = NexusEventBus.audit_event_contracts(fail_on_raw=strict_raw)
    if audit.get("passed"):
        return [
            _ok(
                "event_contract_audit",
                events_scanned=audit.get("events_scanned", 0),
                semantic_event_count=audit.get("semantic_event_count", 0),
                raw_event_count=audit.get("raw_event_count", 0),
                transition_status=audit.get("transition_status", ""),
                strict_raw_mode=audit.get("strict_raw_mode", False),
                unknown_event_types=audit.get("unknown_event_types", []),
            )
        ]
    reason = "event_contract_audit_failed"
    failure_reasons = audit.get("failure_reasons", [])
    if "unknown_event_types_present" in failure_reasons:
        reason = "unknown_event_types_present"
    elif "raw_event_types_present" in failure_reasons:
        reason = "raw_event_types_present"
    return [
        _fail(
            "event_contract_audit",
            reason,
            events_scanned=audit.get("events_scanned", 0),
            raw_event_types=audit.get("raw_event_types", []),
            unknown_event_types=audit.get("unknown_event_types", []),
            strict_raw_mode=audit.get("strict_raw_mode", False),
            failure_reasons=failure_reasons,
        )
    ]


def validate_codex_nexus_smoke_plan() -> list[dict[str, Any]]:
    task_ids = (
        "rlm-harder-v2-governance-001",
        "rlm-harder-v2-evidence-001",
        "rlm-harder-v2-belief-001",
        "rlm-harder-v2-memory-001",
    )
    cmd = codex_smoke_command(
        output_dir=".nexus/reports/bench_codex55_nexus_local_smoke",
        task_ids=task_ids,
        preflight_only=True,
    )
    payload = validate_codex_smoke_plan(cmd=cmd, env=codex_smoke_env("gpt-5.5"), task_ids=task_ids)
    if payload.get("passed"):
        return [_ok("codex_nexus_smoke_plan", **payload)]
    return [_fail("codex_nexus_smoke_plan", "codex_nexus_smoke_plan_invalid", **payload)]


def validate_openseeker_autodata_smoke(repo_root: Path) -> list[dict[str, Any]]:
    receipts = [
        {"name": "semantic_searcher", "invoked": True, "evidence_refs": ["semantic:route:doc"]},
        {"name": "belief", "invoked": True, "evidence_refs": ["belief:route:confidence:0.8"]},
    ]
    trace = build_openseeker_trace(
        usage_trace={
            "route_decision": {
                "selected_capabilities": ["semantic_searcher", "belief"],
                "stop_policy": {"tactical_sequence": ["semantic_searcher", "belief"]},
            },
            "capabilities": {"claim_verified": True},
        },
        capability_receipts=receipts,
    )
    label = classify_trajectory_quality(strong_score=0.85, weak_score=0.55, audit_passed=True)
    row = DataForgeManifestRow(
        task_id="pre_flash_smoke",
        label=label,
        evidence_refs=tuple(ref for receipt in receipts for ref in receipt["evidence_refs"]),
        trajectory_step_count=max(10, int(trace["trajectory_step_count"])),
    )
    summary = write_data_forge_manifest(repo_root / ".nexus" / "reports" / "pre_flash_autodata_manifest.json", [row])
    if trace.get("action_catalog_schema_version") != "nexus_openseeker_action_catalog.v1":
        return [_fail("openseeker_autodata_smoke", "action_catalog_missing", trace=trace)]
    if summary.get("training_eligible_count") != 1:
        return [_fail("openseeker_autodata_smoke", "autodata_training_eligibility_missing", summary=summary)]
    return [
        _ok(
            "openseeker_autodata_smoke",
            trajectory_step_count=trace.get("trajectory_step_count", 0),
            action_catalog_count=len(trace.get("action_catalog", [])),
            autodata_manifest=summary,
        )
    ]


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


def _parse_progress_events(stderr: str) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    parse_errors = 0
    for line in (stderr or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(payload, dict) and payload.get("event"):
            events.append(payload)
    return events, parse_errors


def _progress_summary(progress_events: list[dict[str, Any]]) -> dict[str, Any]:
    starts = [item for item in progress_events if item.get("event") == "task_start"]
    ends = [item for item in progress_events if item.get("event") == "task_end"]
    stop_losses = [item for item in progress_events if item.get("event") == "task_stop_loss"]
    total_timeouts = [item for item in progress_events if item.get("event") == "total_timeout"]
    started = {str(item.get("task_id")) for item in starts if item.get("task_id")}
    completed = {str(item.get("task_id")) for item in ends if item.get("task_id")}
    last = progress_events[-1] if progress_events else {}
    return {
        "task_start_count": len(starts),
        "task_end_count": len(ends),
        "task_stop_loss_count": len(stop_losses),
        "total_timeout_count": len(total_timeouts),
        "last_event": str(last.get("event") or "") if last else "",
        "last_task_id": str(last.get("task_id") or "") if last else "",
        "last_mode": str(last.get("mode") or "") if last else "",
        "last_status": str(last.get("status") or "") if last else "",
        "completed_task_ids": sorted(completed),
        "active_task_ids": sorted(started - completed),
    }


def _repair_classification(*, returncode: int | None, timed_out: bool, progress_events: list[dict[str, Any]], stdout: str, stderr: str) -> str:
    has_total_timeout = any(item.get("event") == "total_timeout" for item in progress_events)
    if timed_out and not progress_events:
        return "hang"
    if timed_out or has_total_timeout:
        return "timeout"
    if returncode == 0:
        return "success"
    if progress_events:
        return "progress"
    if not stdout.strip() and not stderr.strip():
        return "hang"
    return "failure"


def _repair_failure_category(*, classification: str, progress_events: list[dict[str, Any]]) -> str:
    if classification == "success":
        return ""
    if classification == "hang":
        return "timeout_no_progress" if progress_events == [] else "no_output_failure"
    if classification == "timeout":
        if not progress_events:
            return "timeout_no_progress"
        last = str((progress_events[-1] or {}).get("event") or "")
        return "timeout_after_task_start" if last == "task_start" else "timeout_after_progress"
    if classification == "progress":
        return "runner_failed_after_progress"
    return "runner_failed"


def _repair_subset_payload(
    *,
    cmd: list[str],
    returncode: int | None,
    stdout: str,
    stderr: str,
    duration_sec: float,
    timeout_sec: float,
    timed_out: bool,
) -> dict[str, Any]:
    progress_events, parse_errors = _parse_progress_events(stderr)
    last_event = progress_events[-1] if progress_events else {}
    classification = _repair_classification(
        returncode=returncode,
        timed_out=timed_out,
        progress_events=progress_events,
        stdout=stdout,
        stderr=stderr,
    )
    failure_category = _repair_failure_category(
        classification=classification,
        progress_events=progress_events,
    )
    progress_summary = _progress_summary(progress_events)
    return {
        "name": "flash_style_repair_subset",
        "passed": classification == "success",
        "classification": classification,
        "command": cmd,
        "returncode": returncode,
        "duration_sec": round(duration_sec, 4),
        "timeout_sec": timeout_sec,
        "timed_out": timed_out,
        "failure_category": failure_category,
        "stdout_empty": not bool((stdout or "").strip()),
        "progress_observed": bool(progress_events),
        "progress_event_count": len(progress_events),
        "progress_parse_errors": parse_errors,
        "progress_summary": progress_summary,
        "last_progress_event": last_event,
        "stdout_tail": (stdout or "")[-2000:],
        "stderr_tail": (stderr or "")[-2000:],
    }


def run_repair_subset(repo_root: Path, output_dir: str, *, timeout_sec: float = 1200.0) -> dict[str, Any]:
    cmd = repair_subset_command(output_dir)
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=max(1.0, float(timeout_sec or 1200.0)),
        )
        return _repair_subset_payload(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            duration_sec=time.monotonic() - started,
            timeout_sec=timeout_sec,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _repair_subset_payload(
            cmd=cmd,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            duration_sec=time.monotonic() - started,
            timeout_sec=timeout_sec,
            timed_out=True,
        )


def build_payload(
    repo_root: Path,
    *,
    run_repair: bool,
    output_dir: str,
    repair_timeout_sec: float = 1200.0,
    strict_event_contracts: bool | None = None,
) -> dict[str, Any]:
    checks = [
        *validate_repair_factory_skipped_routes(repo_root),
        *validate_runtime_receipt_reconcile(),
        *validate_brain_hub_alignment(repo_root),
        *validate_event_contracts(repo_root, strict_raw=strict_event_contracts),
        *validate_codex_nexus_smoke_plan(),
        *validate_openseeker_autodata_smoke(repo_root),
    ]
    if run_repair:
        checks.append(run_repair_subset(repo_root, output_dir, timeout_sec=repair_timeout_sec))
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
    parser.add_argument("--strict-event-contracts", action="store_true", help="Fail the gate when legacy raw transition events are present.")
    parser.add_argument("--output-dir", default=".nexus/reports/bench_flash_repair_pruning_prefash")
    parser.add_argument("--repair-timeout-sec", type=float, default=1200.0)
    args = parser.parse_args(argv)

    run_repair = bool(args.run_repair_subset and not args.quick)
    payload = build_payload(
        Path(args.repo_root).resolve(),
        run_repair=run_repair,
        output_dir=args.output_dir,
        repair_timeout_sec=args.repair_timeout_sec,
        strict_event_contracts=True if args.strict_event_contracts else None,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
