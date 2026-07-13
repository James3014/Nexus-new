"""Run the M3 A/B/C scenarios with explicit, fail-closed authorization.

The harness is intentionally separate from benchmark runners.  It compares
one harmless task statement across:

  A: bare Online provider (control)
  B: Nexus + Online + Local Assist
  C: Nexus + Local Runtime
  D: Nexus + Online (no Local Assist control)

No provider is invoked unless ``--live`` is supplied and the matching
authorization environment variable is set.  A missing authorization produces
an evidence report with ``NOT_RUN`` rather than a simulated success.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SCENARIO_SCHEMA = "nexus.unified_runtime.scenario_receipt.v1"
EXTERNAL_AUTH_ENV = "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"
LOCAL_AUTH_ENV = "NEXUS_LOCAL_MODEL_CALL_ALLOWED"
DEFAULT_REVISION = "live-revision-unrecorded"
LOCAL_ASSIST_CAPABILITIES = ("memory", "semantic_searcher", "codeintel", "prompt_compression")


def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _base_report(*, scenario: str, mode: str, task_group_id: str, task_statement: str) -> dict[str, Any]:
    return {
        "schema": SCENARIO_SCHEMA,
        "scenario": scenario,
        "mode": mode,
        "task_group_id": task_group_id,
        "task_statement_hash": _hash_text(task_statement),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "terminal_status": "NOT_RUN",
        "receipt_complete": False,
        "provider_call_count": 0,
        "latency_sec": 0.0,
        "solved": False,
        "evidence_refs": [],
        "claim_boundary": {
            "same_task_group": True,
            "receipt_complete": False,
            "value_measured": False,
            "measurement_basis": [],
            "public_claim_allowed": False,
        },
    }


def _authorization_error(report: dict[str, Any], reason: str) -> dict[str, Any]:
    report["terminal_status"] = "AUTHORIZATION_REQUIRED_NOT_RUN"
    report["reason"] = reason
    report["claim_boundary"]["reason"] = reason
    return report


def _evidence_precondition_error(report: dict[str, Any], reason: str) -> dict[str, Any]:
    report["terminal_status"] = "EVIDENCE_PRECONDITION_NOT_MET"
    report["reason"] = reason
    report["claim_boundary"]["reason"] = reason
    return report


def _capability_edge_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize selected Local edges without promoting them to live claims."""
    results = receipt.get("capability_results", {}) if isinstance(receipt, Mapping) else {}
    summary: dict[str, Any] = {}
    for name in LOCAL_ASSIST_CAPABILITIES:
        stage = results.get(name, {}) if isinstance(results, Mapping) else {}
        if not isinstance(stage, Mapping):
            stage = {}
        summary[name] = {
            "selected": name in (receipt.get("planner", {}).get("selected_capabilities", []) or [])
            if isinstance(receipt.get("planner", {}), Mapping)
            else False,
            "status": str(stage.get("status", "NOT_SELECTED")),
            "invoked": bool(stage.get("invoked", False)),
            "gate_passed": bool(stage.get("gate_passed", False)),
            "delegated_to": str(stage.get("delegated_to", "")),
            "evidence_refs": [str(ref) for ref in stage.get("evidence_refs", []) or []],
        }
    return summary


def _resolve_workspace_revision(project_root: Path, configured: str) -> str:
    revision = str(configured or "").strip()
    if revision and revision != DEFAULT_REVISION:
        return revision
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _ollama_endpoint_available() -> bool:
    configured = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/tags").strip()
    try:
        parsed = urllib.parse.urlsplit(configured)
        tags_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/api/tags", "", ""))
        with urllib.request.urlopen(tags_url, timeout=2) as response:
            return int(getattr(response, "status", 200)) == 200
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def _learning_callback(project_root: Path, task_id: str, task_statement: str):
    def learn(context: Mapping[str, Any]) -> dict[str, Any]:
        online = context.get("online", {}) if isinstance(context, Mapping) else {}
        local = context.get("local", {}) if isinstance(context, Mapping) else {}
        try:
            from nexus.research.learn_mode import LearnModeService

            result = LearnModeService(project_root).sync_phase_learning_closure(
                topic=task_statement,
                metrics={
                    "coverage": 1.0 if online or local else 0.0,
                    "self_question_pass_rate": 1.0 if any(
                        isinstance(stage, Mapping) and stage.get("status") == "SUCCEEDED"
                        for stage in (online, local)
                    ) else 0.0,
                    "citation_valid_ratio": 1.0,
                    "stale_claims_count": 0,
                    "conflict_count": 0,
                    "provider_call_count": int(
                        (online.get("response", {}) or {}).get("provider_call_count", 0)
                        if isinstance(online, Mapping)
                        else 0
                    ),
                },
                phase_status={"P": "SUCCESS", "D": "SUCCESS", "R": "SUCCESS", "A": "SUCCESS", "C": "SUCCESS"},
            )
            passed = str(result.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"}
            return {
                "task_id": task_id,
                "status": "pass" if passed else "fail",
                "invoked": True,
                "gate_passed": passed,
                "evidence": "LearnModeService.sync_phase_learning_closure",
                "evidence_refs": [f"learning:{task_id}:phase_bridge"],
                "response": result,
            }
        except Exception as exc:  # fail closed in the unified receipt
            return {
                "task_id": task_id,
                "status": "fail",
                "invoked": True,
                "gate_passed": False,
                "evidence": "learning_exception",
                "evidence_refs": [f"learning:{task_id}:exception"],
                "error": f"{exc.__class__.__name__}:{exc}",
            }

    return learn


def _verifier(task_id: str):
    def verify(context: Mapping[str, Any]) -> dict[str, Any]:
        stages = [context.get("local", {}), context.get("online", {})]
        usable = [stage for stage in stages if isinstance(stage, Mapping) and stage.get("status") != "NOT_REQUESTED"]
        passed = bool(usable) and all(stage.get("status") == "SUCCEEDED" for stage in usable)
        return {
            "task_id": task_id,
            "status": "pass" if passed else "fail",
            "invoked": True,
            "gate_passed": passed,
            "outcome_contributed": passed,
            "evidence": "scenario_stage_verifier",
            "evidence_refs": [f"verifier:{task_id}:scenario"],
        }

    return verify


def _run_bare(
    *,
    report: dict[str, Any],
    provider: str,
    command: tuple[str, ...] | list[str] | str | None,
    task_statement: str,
    timeout_sec: float,
) -> dict[str, Any]:
    from nexus.services.unified_runtime import resolve_registered_online_cli_spec

    spec = resolve_registered_online_cli_spec(provider, command=command, timeout_sec=timeout_sec)
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(spec.command),
            input=task_statement,
            capture_output=True,
            text=True,
            timeout=spec.timeout_sec,
            check=False,
        )
        stdout = str(result.stdout or "")
        passed = result.returncode == 0 and bool(stdout.strip())
        report.update(
            {
                "provider": spec.provider,
                "provider_command": list(spec.command),
                "provider_call_count": 1,
                "latency_sec": round(time.monotonic() - started, 3),
                "terminal_status": "SUCCEEDED" if passed else "FAILED",
                "receipt_complete": passed,
                "solved": passed,
                "response_preview": stdout[:4000],
                "evidence_refs": [f"bare:{spec.provider}:{report['task_group_id']}:provider_call"],
            }
        )
        report["claim_boundary"].update(
            {
                "receipt_complete": passed,
                "value_measured": passed,
                "measurement_basis": ["solved", "latency_sec", "provider_call_count"] if passed else [],
            }
        )
        if not passed:
            report["reason"] = f"provider_returncode_or_empty_output:{result.returncode}"
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        report.update(
            {
                "provider": spec.provider,
                "provider_command": list(spec.command),
                "latency_sec": round(time.monotonic() - started, 3),
                "terminal_status": "FAILED",
                "reason": f"{exc.__class__.__name__}:{exc}",
            }
        )
    return report


def _run_nexus(
    *,
    report: dict[str, Any],
    project_root: Path,
    provider: str,
    command: tuple[str, ...] | list[str] | str | None,
    task_statement: str,
    workspace_revision: str,
    local_enabled: bool,
    timeout_sec: float,
) -> dict[str, Any]:
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.local_assist_service import (
        REQUEST_SCHEMA,
        LocalAssistRequest,
        LocalAssistService,
    )
    from nexus.services.unified_runtime import (
        UnifiedRuntime,
        UnifiedRuntimeRequest,
        build_local_memory_capability_invoker,
        build_local_search_ranking_capability_invoker,
        build_local_ast_capability_invoker,
        build_prompt_compression_capability_invoker,
    )

    task_id = f"{report['task_group_id']}-{report['scenario'].lower()}"
    local_request = None
    if local_enabled:
        local_request = LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(project_root),
            workspace_revision=workspace_revision,
            task_statement=task_statement,
            action="advisor",
            allowed_files=("MUSE_PROTO.md",),
            target_file="",
            target_symbol="",
            evidence_refs=(f"scenario:{report['scenario']}:request",),
            time_budget=timeout_sec,
        )
    # Explicit command (e.g. python -c print) is a deterministic injected Online
    # runner — never a live provider claim. Real physical CLIs require a separate
    # product path with OnlineExecutionDecision.physical_invocation_allowed.
    injected_online = command is not None
    route: dict[str, Any] = {
        "recommended_flow": (
            "hybrid"
            if local_enabled
            else "local_only"
            if report["scenario"] == "C"
            else "direct"
        ),
        "provider": provider,
        "online_command": command,
        "timeout_sec": timeout_sec,
        # Scenario B/C must exercise the real Local capability edges. The
        # planner otherwise keeps them optional and a receipt would only
        # prove the generic local_model_executor path.
        "route_decision": {
            "selected_capabilities": list(LOCAL_ASSIST_CAPABILITIES) if local_enabled else [],
        },
        "prompt_compression": bool(local_enabled),
        "target_file": "nexus/services/unified_runtime.py",
        # Capabilities that the Online stage is allowed to consume are
        # explicit route authority, not inferred from Planner selection.
        # Local model execution remains delegated by UnifiedRuntime's
        # dedicated local stage.
        "online_capabilities": (
            "research_route",
            "repair_loop",
            "delivery_gate",
            "artifact_gate",
            "claim_gate",
        ),
        # A real bounded memory read is part of the Local Assist proof;
        # the hit/no-match result remains in the same task receipt.
        "route_features": {"memory_hits": 1, "findings_hits": 1},
        "workspace_root": str(project_root),
    }
    if injected_online:
        route.update(
            {
                "injected_transport": True,
                "selection_source": "injected_transport",
                "live_provider_claim": False,
                # Empty task policy + inject authorizes fixtures; explicit deny
                # would still win. Do not rely on workspace allow for inject.
                "online_policy": "auto",
            }
        )
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=workspace_revision,
        task_statement=task_statement,
        task_type="repair",
        route=route,
        online_enabled=report["scenario"] != "C",
        local_enabled=local_enabled,
        online_prompt=task_statement,
        online_payload="Return a concise answer to the harmless task.",
        local_request=local_request,
        evidence_refs=(f"scenario:{report['scenario']}:request",),
    )
    verifier = _verifier(task_id)
    learning = _learning_callback(project_root, task_id, task_statement)
    started = time.monotonic()
    local_service = LocalAssistService() if local_enabled else None
    gateway = BattlesuitGateway(project_root=project_root)
    capability_invokers = {
        "memory": build_local_memory_capability_invoker(project_root),
        "semantic_searcher": build_local_search_ranking_capability_invoker(project_root),
        "codeintel": build_local_ast_capability_invoker(project_root),
        "prompt_compression": build_prompt_compression_capability_invoker(),
    }
    if request.online_enabled:
        receipt = gateway.ask_unified(
            request,
            local_service=local_service,
            capability_invokers=capability_invokers,
            verifier=verifier,
            learning=learning,
        )
    else:
        receipt = UnifiedRuntime(
            planner=CapabilityPlanner(),
            local_service=local_service,
        ).run(
            request,
            capability_invokers=capability_invokers,
            verifier=verifier,
            learning=learning,
        )
    elapsed = round(time.monotonic() - started, 3)
    online = receipt.get("online", {}) if isinstance(receipt, Mapping) else {}
    response = online.get("response", {}) if isinstance(online, Mapping) else {}
    receipt_complete = bool(receipt.get("receipt_complete", False))
    solved = bool(receipt_complete and receipt.get("claim_boundary", {}).get("outcome_contributed", False))
    provider_call_count = int(response.get("provider_call_count", 0) or 0) if isinstance(response, Mapping) else 0
    capability_summary = _capability_edge_summary(receipt)
    capability_runtime_complete = bool(
        local_enabled
        and all(
            item["selected"]
            and item["invoked"]
            and item["gate_passed"]
            and item["status"] == "SUCCEEDED"
            for item in capability_summary.values()
        )
    )
    capability_online_forwarded = bool(
        request.online_enabled
        and any(
            "capability_context_forwarded" in str(ref)
            for ref in (receipt.get("online", {}).get("evidence_refs", []) or [])
        )
    )
    report.update(
        {
            "task_id": task_id,
            "provider": provider if request.online_enabled else "ollama",
            "latency_sec": elapsed,
            "provider_call_count": provider_call_count,
            "terminal_status": receipt.get("terminal_status", "INCOMPLETE"),
            "receipt_complete": receipt_complete,
            "solved": solved,
            "unified_receipt": receipt,
            "evidence_refs": list(receipt.get("evidence_refs", []) or []),
            "capability_edges": capability_summary,
            "capability_runtime_complete": capability_runtime_complete,
            "capability_online_forwarded": capability_online_forwarded,
        }
    )
    report["claim_boundary"].update(
        {
            "receipt_complete": bool(receipt.get("receipt_complete", False)),
            "value_measured": bool(receipt_complete and solved),
            "measurement_basis": ["solved", "latency_sec", "provider_call_count", "receipt_complete"]
            if receipt_complete and solved
            else [],
            "same_task_id": receipt.get("task_id") == task_id,
        }
    )
    return report


def run_scenario(args: argparse.Namespace) -> dict[str, Any]:
    args = copy.copy(args)
    project_root = Path(args.project_root).expanduser().resolve()
    scenario = args.scenario.upper()
    workspace_revision = _resolve_workspace_revision(project_root, args.workspace_revision)
    mode = {
        "A": "bare_online",
        "B": "nexus_online_local",
        "C": "nexus_local",
        "D": "nexus_online",
    }[scenario]
    report = _base_report(
        scenario=scenario,
        mode=mode,
        task_group_id=args.task_group_id,
        task_statement=args.task_statement,
    )
    report["project_root"] = str(project_root)
    report["workspace_revision"] = workspace_revision
    if not args.live:
        return _authorization_error(report, "live_flag_required")
    if scenario != "A" and not workspace_revision:
        return _evidence_precondition_error(report, "workspace_revision_required")
    if scenario in {"A", "B", "D"} and os.environ.get(EXTERNAL_AUTH_ENV) != "1":
        return _authorization_error(report, f"{EXTERNAL_AUTH_ENV}=1_required")
    if scenario in {"B", "C"} and os.environ.get(LOCAL_AUTH_ENV) != "1":
        return _authorization_error(report, f"{LOCAL_AUTH_ENV}=1_required")
    if scenario in {"B", "C"}:
        local_provider = (
            os.environ.get("NEXUS_LOCAL_MODEL_PROVIDER")
            or os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER")
            or ""
        ).strip().lower()
        if local_provider != "ollama":
            return _evidence_precondition_error(report, "local_provider_ollama_required")
        if not os.environ.get("NEXUS_LOCAL_MODEL_NAME", "").strip():
            return _evidence_precondition_error(report, "local_model_name_required")
        if not _ollama_endpoint_available():
            return _evidence_precondition_error(report, "ollama_endpoint_unavailable")
    if scenario == "A":
        return _run_bare(
            report=report,
            provider=args.provider,
            command=args.command,
            task_statement=args.task_statement,
            timeout_sec=args.timeout_sec,
        )
    return _run_nexus(
        report=report,
        project_root=project_root,
        provider=args.provider,
        command=args.command,
        task_statement=args.task_statement,
        workspace_revision=workspace_revision,
        local_enabled=scenario in {"B", "C"},
        timeout_sec=args.timeout_sec,
    )


def run_scenario_matrix(args: argparse.Namespace) -> dict[str, Any]:
    """Run A/B/C/D as one task-group comparison without collapsing evidence."""
    reports: list[dict[str, Any]] = []
    for scenario in ("A", "B", "C", "D"):
        child = copy.copy(args)
        child.scenario = scenario
        reports.append(run_scenario(child))
    capability_reports = [
        report for report in reports
        if report.get("mode") in {"nexus_online_local", "nexus_local"}
    ]
    capability_runtime_complete = bool(
        len(capability_reports) == 2
        and all(bool(report.get("capability_runtime_complete", False)) for report in capability_reports)
    )
    capability_online_forwarded = bool(
        any(report.get("mode") == "nexus_online_local" for report in capability_reports)
        and all(
            bool(report.get("capability_online_forwarded", False))
            for report in capability_reports
            if report.get("mode") == "nexus_online_local"
        )
    )
    complete = all(bool(report.get("receipt_complete")) for report in reports)
    same_task_statement = len({report.get("task_statement_hash") for report in reports}) == 1
    same_workspace_revision = len({report.get("workspace_revision", "") for report in reports}) == 1
    return {
        "schema": "nexus.unified_runtime.scenario_matrix.v1",
        "task_group_id": args.task_group_id,
        "task_statement_hash": _hash_text(args.task_statement),
        "scenarios": reports,
        "comparison": [
            {
                "scenario": report.get("scenario"),
                "mode": report.get("mode"),
                "task_statement_hash": report.get("task_statement_hash"),
                "workspace_revision": report.get("workspace_revision", ""),
                "solved": bool(report.get("solved")),
                "latency_sec": float(report.get("latency_sec", 0.0) or 0.0),
                "provider_call_count": int(report.get("provider_call_count", 0) or 0),
                "receipt_complete": bool(report.get("receipt_complete")),
                "evidence_count": len(report.get("evidence_refs", []) or []),
                "capability_runtime_complete": bool(report.get("capability_runtime_complete", False)),
                "capability_online_forwarded": bool(report.get("capability_online_forwarded", False)),
                "capability_edges": report.get("capability_edges", {}),
                "learning_status": (
                    (report.get("unified_receipt", {}).get("learning", {}) or {}).get("status", "NOT_REQUESTED")
                    if isinstance(report.get("unified_receipt"), Mapping)
                    else "NOT_REQUESTED"
                ),
            }
            for report in reports
        ],
        "terminal_status": "SUCCEEDED" if complete else "INCOMPLETE",
        "receipt_complete": complete,
        "claim_boundary": {
            "same_task_group": len({report.get("task_group_id") for report in reports}) == 1,
            "same_task_statement": same_task_statement,
            "same_workspace_revision": same_workspace_revision,
            "all_scenarios_complete": complete,
            "capability_runtime_complete": capability_runtime_complete,
            "capability_online_forwarded": capability_online_forwarded,
            "value_measured": complete and same_task_statement and same_workspace_revision and all(
                bool(report.get("claim_boundary", {}).get("value_measured")) for report in reports
            ),
            "measurement_basis": [
                "same_task_statement", "same_workspace_revision", "solved", "latency_sec",
                "provider_call_count", "receipt", "evidence", "learning",
            ]
            if complete and same_task_statement and same_workspace_revision
            else [],
            "public_claim_allowed": False,
        },
        "next_gate": "Require authorized live A/B/C/D receipts and value measurement before promotion.",
        "capability_gate": {
            "required_modes": ["nexus_online_local", "nexus_local"],
            "runtime_complete": capability_runtime_complete,
            "online_forwarded": capability_online_forwarded,
            "status": "PROVEN_BOUNDED_RUNTIME" if capability_runtime_complete and capability_online_forwarded else "CAPABILITY_LIVE_GATE_OPEN",
            "live_provider_evidence": "UNVERIFIED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("A", "B", "C", "D", "ALL"), required=True)
    parser.add_argument("--task-group-id", default="m3-live-001")
    parser.add_argument("--task-statement", default="Reply with exactly: NEXUS_RUNTIME_SCENARIO_OK")
    parser.add_argument("--workspace-revision", default=DEFAULT_REVISION)
    parser.add_argument("--provider", default="grok")
    parser.add_argument(
        "--command",
        default=None,
        help="Explicit provider argv; otherwise resolve the registered binary",
    )
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--receipt-path", default=None)
    parser.add_argument("--live", action="store_true", help="Required before any provider call")
    args = parser.parse_args(argv)
    report = run_scenario_matrix(args) if args.scenario == "ALL" else run_scenario(args)
    target = (
        Path(args.receipt_path)
        if args.receipt_path
        else Path(args.project_root)
        / ".nexus"
        / "reports"
        / "runtime_scenarios"
        / f"{args.task_group_id}-{args.scenario}.json"
    )
    _write(target, report)
    print(json.dumps({"receipt_path": str(target), **report}, ensure_ascii=False, indent=2))
    return 0 if report.get("terminal_status") in {"SUCCEEDED", "AUTHORIZATION_REQUIRED_NOT_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
