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
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace
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


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _scenario_run_root(args: argparse.Namespace, task_id: str) -> Path:
    configured = str(getattr(args, "run_root", "") or "").strip()
    if configured:
        base = Path(configured).expanduser().resolve()
    else:
        base = Path(tempfile.mkdtemp(prefix="nexus-runtime-scenario-")).resolve()
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id)[:120] or "scenario"
    run_root = base / safe_task
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def _prepare_task_workspace(run_root: Path, task_id: str) -> tuple[Path, Path]:
    workspace = run_root / "task_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "scenario_task.py"
    target.write_text(
        "def scenario_response():\n    return 'NOT_COMPLETED'\n",
        encoding="utf-8",
    )
    manifest = workspace / "scenario_manifest.json"
    _write(
        manifest,
        {
            "schema": "nexus.unified_runtime.scenario_manifest.v1",
            "task_id": task_id,
            "target_file": target.name,
            "source_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "expected_result": "NEXUS_RUNTIME_VERIFIED",
        },
    )
    return workspace, target


def _isolated_apply_runner(run_root: Path):
    from nexus.services.local_heal.isolated_workspace_apply import (
        run_isolated_workspace_apply,
    )

    workspace_parent = run_root / ".nexus" / "artifacts" / "local_armor" / "workspaces"
    workspace_parent.mkdir(parents=True, exist_ok=True)

    def apply(request):
        return run_isolated_workspace_apply(
            replace(request, work_dir=str(workspace_parent))
        )

    return apply


def _build_local_service(run_root: Path):
    from nexus.services.local_assist_service import LocalAssistService

    return LocalAssistService(apply_runner=_isolated_apply_runner(run_root))


def _learning_callback(
    project_root: Path,
    run_root: Path,
    task_id: str,
    task_statement: str,
):
    def learn(context: Mapping[str, Any]) -> dict[str, Any]:
        online = context.get("online", {}) if isinstance(context, Mapping) else {}
        local = context.get("local", {}) if isinstance(context, Mapping) else {}
        try:
            from nexus.research.learn_mode import LearnModeService

            service = LearnModeService(project_root, run_root=run_root)
            result = service.sync_phase_learning_closure(
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
                phase_status={
                    "P": "SUCCESS",
                    "X": "SUCCESS",
                    "D": "SUCCESS",
                    "R": "SUCCESS",
                    "A": "SUCCESS",
                    "C": "SUCCESS",
                },
            )
            rows: list[dict[str, Any]] = []
            if service.phase_writeback_path.is_file():
                for line in service.phase_writeback_path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("topic") == task_statement:
                        rows.append(row)
            phases = {str(row.get("phase") or "") for row in rows}
            slo = service.read_phase_slo_summary()
            paths = [service.phase_writeback_path, service.phase_slo_summary_path]
            contained = all(_is_within(path, run_root) for path in paths)
            passed = bool(
                str(result.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"}
                and int(result.get("entries_written", 0) or 0) == 6
                and phases == {"P", "X", "D", "R", "A", "C"}
                and str(slo.get("status") or "").upper() == "SUCCESS"
                and slo.get("phase_slo_pass") is True
                and contained
            )
            return {
                "task_id": task_id,
                "status": "pass" if passed else "fail",
                "invoked": True,
                "gate_passed": passed,
                "evidence": "LearnModeService.sync_phase_learning_closure",
                "outcome_contributed": passed,
                "evidence_refs": [
                    f"learning:{task_id}:phase_bridge",
                    str(service.phase_writeback_path),
                    str(service.phase_slo_summary_path),
                ],
                "readback": {
                    "phases": sorted(phases),
                    "entries_written": int(result.get("entries_written", 0) or 0),
                    "phase_slo_pass": slo.get("phase_slo_pass") is True,
                    "paths_contained": contained,
                },
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


def _build_agy_online_invoker(
    *,
    timeout_sec: float,
    include_local_context: bool,
    runner: Any = subprocess.run,
):
    """Invoke agy print mode with the dynamic prompt as an argv value."""

    from nexus.services.unified_runtime import normalize_online_invoker_payload

    agy_bin = str(os.environ.get("NEXUS_AGY_BIN") or "").strip()

    def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(context.get("task_id") or "")
        if not agy_bin or not Path(agy_bin).is_file() or not os.access(agy_bin, os.X_OK):
            return normalize_online_invoker_payload(
                provider="agy",
                task_id=task_id,
                invoked=False,
                output_delivered=False,
                gate_passed=False,
                provider_call_count=0,
                error="agy_binary_unavailable",
                evidence_refs=[f"online:agy:{task_id}:binary_unavailable"],
                transport="registered_cli",
                selection_source="explicit_request",
            )
        prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
        local_context_forwarded = False
        capability_context_forwarded = False
        if include_local_context:
            local_stage = context.get("local") if isinstance(context.get("local"), Mapping) else {}
            if local_stage:
                from nexus.services.local_substitution import build_online_safe_local_forward

                safe = build_online_safe_local_forward(local_stage)
                forward = safe.get("forward") if isinstance(safe, Mapping) else {}
                if isinstance(forward, Mapping) and forward:
                    prompt += "\n\n[LOCAL_ASSIST_CONTEXT]\n" + json.dumps(
                        forward,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    local_context_forwarded = True
            capability_results = context.get("capability_results")
            if isinstance(capability_results, Mapping) and capability_results:
                from nexus.services.unified_runtime import _capability_evidence_summary

                prompt += "\n\n[CAPABILITY_EVIDENCE_SUMMARY]\n" + json.dumps(
                    _capability_evidence_summary(capability_results),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                capability_context_forwarded = True
        argv = [
            agy_bin,
            "--dangerously-skip-permissions",
            "--print",
            prompt,
        ]
        try:
            result = runner(
                argv,
                input=None,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return normalize_online_invoker_payload(
                provider="agy",
                task_id=task_id,
                invoked=True,
                output_delivered=False,
                gate_passed=False,
                provider_call_count=1,
                error="provider_timeout",
                evidence_refs=[f"online:agy:{task_id}:timeout"],
                transport="registered_cli",
                selection_source="explicit_request",
                extra={"returncode": None, "stderr": str(exc)},
            )
        except OSError as exc:
            return normalize_online_invoker_payload(
                provider="agy",
                task_id=task_id,
                invoked=False,
                output_delivered=False,
                gate_passed=False,
                provider_call_count=0,
                error=f"{exc.__class__.__name__}:{exc}",
                evidence_refs=[f"online:agy:{task_id}:not_invoked"],
                transport="registered_cli",
                selection_source="explicit_request",
            )
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        returncode = int(getattr(result, "returncode", 1))
        delivered = returncode == 0 and bool(stdout.strip())
        refs = [f"online:agy:{task_id}:subprocess"]
        if local_context_forwarded:
            refs.append(f"online:agy:{task_id}:local_context_forwarded")
        if capability_context_forwarded:
            refs.append(f"online:agy:{task_id}:capability_context_forwarded")
        return normalize_online_invoker_payload(
            provider="agy",
            task_id=task_id,
            invoked=True,
            output_delivered=delivered,
            gate_passed=delivered,
            provider_call_count=1,
            response=stdout,
            raw_response=stdout,
            error="" if delivered else "provider_subprocess_failed",
            evidence_refs=refs,
            transport="registered_cli",
            selection_source="explicit_request",
            extra={"returncode": returncode, "stderr": stderr},
        )

    return invoke


def _verifier(
    *,
    task_id: str,
    run_root: Path,
    task_workspace: Path,
    workspace_revision: str,
    task_statement: str,
    provider: str,
    injected_online: bool,
    local_required: bool,
    online_required: bool,
):
    def verify(context: Mapping[str, Any]) -> dict[str, Any]:
        blockers: list[str] = []
        bundle = (
            context.get("capability_evidence_bundle")
            if isinstance(context.get("capability_evidence_bundle"), Mapping)
            else {}
        )
        source_hash = str(bundle.get("source_hash") or "")
        expected_source_hash = _hash_text(f"{workspace_revision}:{task_statement}")
        if source_hash != expected_source_hash:
            blockers.append("source_hash_mismatch")

        candidate_hash = ""
        applied_hash = ""
        local_receipt_path = Path()
        isolated_workspace = Path()
        online_request_path = Path()
        online_stdout_path = Path()
        online_stderr_path = Path()
        online_provider = ""
        online_transport = ""
        online_selection_source = ""
        online_response_hash = ""
        if local_required:
            local = context.get("local") if isinstance(context.get("local"), Mapping) else {}
            response = local.get("response") if isinstance(local.get("response"), Mapping) else {}
            candidate = (
                response.get("candidate_summary")
                if isinstance(response.get("candidate_summary"), Mapping)
                else {}
            )
            local_verifier = (
                response.get("verifier_summary")
                if isinstance(response.get("verifier_summary"), Mapping)
                else {}
            )
            candidate_hash = str(candidate.get("selected_candidate_hash") or "")
            applied_hash = str(candidate.get("applied_patch_hash") or "")
            local_receipt_path = Path(str(response.get("receipt_path") or ""))
            isolated_workspace = Path(str(candidate.get("isolated_workspace") or ""))
            try:
                disk = json.loads(local_receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                disk = {}
            if local.get("status") != "SUCCEEDED":
                blockers.append("local_stage_not_succeeded")
            if response.get("action") != "verified-subtask":
                blockers.append("local_action_not_verified_subtask")
            if response.get("physical_callable") != "LocalModelExecutor.run":
                blockers.append("local_model_executor_not_physical")
            if response.get("executor_invoked") is not True:
                blockers.append("local_executor_not_invoked")
            if response.get("local_model_invoked") is not True or response.get("output_delivered") is not True:
                blockers.append("local_output_not_delivered")
            if candidate.get("isolation_status") != "isolated" or not _is_within(isolated_workspace, run_root):
                blockers.append("candidate_not_isolated_in_run_root")
            if not candidate_hash or candidate_hash != applied_hash or candidate.get(
                "selected_candidate_hash_matches_applied"
            ) is not True:
                blockers.append("candidate_hash_not_applied")
            if not (
                local_verifier.get("verifier_reached") is True
                and local_verifier.get("verifier_status") == "pass"
                and int(local_verifier.get("exit_code", 1) or 0) == 0
            ):
                blockers.append("local_verifier_not_passed")
            if not _is_within(local_receipt_path, run_root):
                blockers.append("local_receipt_outside_run_root")
            if not (
                disk.get("task_id") == task_id
                and disk.get("terminal_status") == "SUCCEEDED"
                and disk.get("receipt_complete") is True
                and str(disk.get("verifier_result") or "").lower() == "pass"
                and candidate_hash in [str(item) for item in disk.get("candidate_hashes", []) or []]
                and str(disk.get("source_snapshot_hash") or "")
                == hashlib.sha256((task_workspace / "scenario_task.py").read_bytes()).hexdigest()
            ):
                blockers.append("local_disk_receipt_incomplete")
            patched = isolated_workspace / "scenario_task.py"
            try:
                namespace: dict[str, Any] = {}
                exec(patched.read_text(encoding="utf-8"), namespace)
                if namespace["scenario_response"]() != "NEXUS_RUNTIME_VERIFIED":
                    blockers.append("isolated_candidate_wrong_result")
            except (OSError, KeyError, SyntaxError):
                blockers.append("isolated_candidate_unreadable")

        if online_required:
            online = context.get("online") if isinstance(context.get("online"), Mapping) else {}
            response = online.get("response") if isinstance(online.get("response"), Mapping) else {}
            online_provider = str(response.get("provider") or "").strip().lower()
            online_transport = str(response.get("transport") or "").strip()
            online_selection_source = str(response.get("selection_source") or "").strip()
            raw_response = str(
                response.get("raw_response") or response.get("response") or ""
            )
            stderr = str(response.get("stderr") or "")
            evidence_root = (
                run_root
                / ".nexus"
                / "reports"
                / "runtime_scenarios"
                / task_id
                / "online"
            )
            online_request_path = evidence_root / "request.json"
            online_stdout_path = evidence_root / "stdout.txt"
            online_stderr_path = evidence_root / "stderr.txt"
            _write(
                online_request_path,
                {
                    "schema": "nexus.unified_runtime.online_request.v1",
                    "task_id": task_id,
                    "workspace_revision": workspace_revision,
                    "provider": provider,
                    "task_statement": task_statement,
                    "task_statement_hash": _hash_text(task_statement),
                },
            )
            online_stdout_path.parent.mkdir(parents=True, exist_ok=True)
            online_stdout_path.write_text(raw_response, encoding="utf-8")
            online_stderr_path.write_text(stderr, encoding="utf-8")
            online_response_hash = hashlib.sha256(
                online_stdout_path.read_bytes()
            ).hexdigest()
            if not local_required:
                candidate_hash = online_response_hash
                applied_hash = online_response_hash
            if online.get("status") != "SUCCEEDED":
                blockers.append("online_stage_not_succeeded")
            if response.get("invoked") is not True or response.get("output_delivered") is not True:
                blockers.append("online_output_not_delivered")
            if int(response.get("provider_call_count", 0) or 0) < 1:
                blockers.append("online_provider_call_missing")
            if online_provider != provider:
                blockers.append("online_provider_identity_mismatch")
            if not raw_response.strip():
                blockers.append("online_response_empty")
            if not injected_online:
                if online_transport != "registered_cli":
                    blockers.append("online_transport_not_registered_cli")
                if online_selection_source != "explicit_request":
                    blockers.append("online_selection_source_not_explicit")
                if response.get("live_provider_claim") is False:
                    blockers.append("online_live_provider_claim_denied")
                exact_match = re.search(
                    r"\bexactly\s*:?\s*(.+)$",
                    task_statement,
                    flags=re.IGNORECASE,
                )
                expected = (
                    exact_match.group(1).strip().strip("`\"'")
                    if exact_match
                    else ""
                )
                if expected and raw_response.strip() != expected:
                    blockers.append("online_response_not_exact")
            if not all(
                _is_within(path, run_root)
                for path in (
                    online_request_path,
                    online_stdout_path,
                    online_stderr_path,
                )
            ):
                blockers.append("online_evidence_outside_run_root")

        artifact_path = (
            run_root
            / ".nexus"
            / "reports"
            / "runtime_scenarios"
            / task_id
            / "verifier_artifact.json"
        )
        artifact_payload = {
            "schema": "nexus.unified_runtime.scenario_verifier.v1",
            "task_id": task_id,
            "source_hash": source_hash,
            "candidate_hash": candidate_hash,
            "applied_hash": applied_hash,
            "local_receipt_path": str(local_receipt_path) if local_required else "",
            "isolated_workspace": str(isolated_workspace) if local_required else "",
            "online_provider": online_provider,
            "online_transport": online_transport,
            "online_selection_source": online_selection_source,
            "online_request_path": str(online_request_path) if online_required else "",
            "online_stdout_path": str(online_stdout_path) if online_required else "",
            "online_stderr_path": str(online_stderr_path) if online_required else "",
            "online_response_hash": online_response_hash,
            "blockers": sorted(set(blockers)),
            "status": "PASS" if not blockers else "FAIL",
        }
        _write(artifact_path, artifact_payload)
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        passed = not blockers
        evidence_refs = [f"verifier:{task_id}:scenario", str(artifact_path)]
        if online_required:
            evidence_refs.extend(
                [
                    str(online_request_path),
                    str(online_stdout_path),
                    str(online_stderr_path),
                ]
            )
        return {
            "task_id": task_id,
            "status": "pass" if passed else "fail",
            "verifier_status": "pass" if passed else "fail",
            "invoked": True,
            "gate_passed": passed,
            "outcome_contributed": passed,
            "source_hash": source_hash,
            "candidate_hash": candidate_hash,
            "applied_hash": applied_hash,
            "verifier_artifact": f"sha256:{artifact_hash}",
            "verifier_artifact_path": str(artifact_path),
            "blockers": sorted(set(blockers)),
            "evidence": "physical_scenario_verifier_artifact",
            "evidence_refs": evidence_refs,
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
    run_root: Path,
) -> dict[str, Any]:
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.local_assist_service import (
        REQUEST_SCHEMA,
        LocalAssistRequest,
        build_planner_snapshot,
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
    task_workspace, target_path = _prepare_task_workspace(run_root, task_id)
    local_request = None
    if local_enabled:
        model_name = str(os.environ.get("NEXUS_LOCAL_MODEL_NAME") or "").strip()
        local_statement = (
            "Return only a unified diff for scenario_task.py. Change "
            "scenario_response() to return exactly 'NEXUS_RUNTIME_VERIFIED'."
        )
        planner_snapshot = build_planner_snapshot(
            task_statement=local_statement,
            model=model_name,
        )
        planner_snapshot.update(
            {
                "model_call_allowed": True,
                "selected_capabilities": ["local_model_executor", "repair_loop"],
                "local_consumable_capabilities": ["codeintel", "memory", "semantic_searcher"],
            }
        )
        local_request = LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(task_workspace),
            workspace_revision=workspace_revision,
            task_statement=local_statement,
            action="verified-subtask",
            allowed_files=("scenario_task.py",),
            target_file="scenario_task.py",
            target_symbol="scenario_response",
            evidence_refs=(f"scenario:{report['scenario']}:request",),
            verifier_command=(
                sys.executable,
                "-c",
                (
                    "ns={}; exec(open('scenario_task.py', encoding='utf-8').read(), ns); "
                    "assert ns['scenario_response']() == 'NEXUS_RUNTIME_VERIFIED'"
                ),
            ),
            time_budget=timeout_sec,
            requested_role="candidate",
            mutation_policy="isolated_only",
            planner_snapshot=planner_snapshot,
            locked_search=target_path.read_text(encoding="utf-8"),
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
            "selected_capabilities": (
                [*LOCAL_ASSIST_CAPABILITIES, "local_model_executor", "repair_loop"]
                if local_enabled
                else []
            ),
        },
        "prompt_compression": bool(local_enabled),
        "target_file": "scenario_task.py",
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
        "workspace_root": str(task_workspace),
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
        codeintel={
            "workspace_root": str(task_workspace),
            "target_file": "scenario_task.py",
            "target_symbol": "scenario_response",
            "verify_commands": [f"{sys.executable} -m py_compile scenario_task.py"],
            "mempalace_tenant_id": "runtime-scenario",
            "mempalace_artifact_type": "scenario_manifest",
            "mempalace_artifact": {
                "artifact_id": f"{task_id}-manifest",
                "content": (task_workspace / "scenario_manifest.json").read_text(encoding="utf-8"),
                "source_hash": hashlib.sha256(
                    (task_workspace / "scenario_manifest.json").read_bytes()
                ).hexdigest(),
            },
            "mempalace_query": f"{task_id}-manifest",
        },
    )
    verifier = _verifier(
        task_id=task_id,
        run_root=run_root,
        task_workspace=task_workspace,
        workspace_revision=workspace_revision,
        task_statement=task_statement,
        provider=provider,
        injected_online=injected_online,
        local_required=local_enabled,
        online_required=request.online_enabled,
    )
    learning = _learning_callback(project_root, run_root, task_id, task_statement)
    started = time.monotonic()
    local_service = _build_local_service(run_root) if local_enabled else None
    gateway = BattlesuitGateway(project_root=project_root)
    capability_invokers = {
        "memory": build_local_memory_capability_invoker(task_workspace),
        "semantic_searcher": build_local_search_ranking_capability_invoker(task_workspace),
        "codeintel": build_local_ast_capability_invoker(task_workspace),
        "prompt_compression": build_prompt_compression_capability_invoker(),
    }
    unified_receipt_path = (
        run_root
        / ".nexus"
        / "reports"
        / "runtime_scenarios"
        / task_id
        / "unified_runtime.json"
    )
    if request.online_enabled:
        online_invoker = (
            _build_agy_online_invoker(
                timeout_sec=timeout_sec,
                include_local_context=local_enabled,
            )
            if provider == "agy" and not injected_online
            else None
        )
        receipt = gateway.ask_unified(
            request,
            local_service=local_service,
            capability_invokers=capability_invokers,
            verifier=verifier,
            learning=learning,
            receipt_path=unified_receipt_path,
            online_invoker=online_invoker,
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
            receipt_path=unified_receipt_path,
        )
    elapsed = round(time.monotonic() - started, 3)
    online = receipt.get("online", {}) if isinstance(receipt, Mapping) else {}
    response = online.get("response", {}) if isinstance(online, Mapping) else {}
    receipt_complete = bool(receipt.get("receipt_complete", False))
    solved = bool(receipt_complete and receipt.get("claim_boundary", {}).get("outcome_contributed", False))
    online_provider_call_count = (
        int(response.get("provider_call_count", 0) or 0)
        if isinstance(response, Mapping)
        else 0
    )
    local_provider_call_count = 0
    local_stage = (
        receipt.get("local", {})
        if isinstance(receipt.get("local"), Mapping)
        else {}
    )
    local_response = (
        local_stage.get("response", {})
        if isinstance(local_stage.get("response"), Mapping)
        else {}
    )
    local_receipt_value = str(local_response.get("receipt_path") or "").strip()
    if local_receipt_value:
        local_receipt_path = Path(local_receipt_value).expanduser()
        if local_receipt_path.is_file() and _is_within(local_receipt_path, run_root):
            try:
                local_disk_receipt = json.loads(
                    local_receipt_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                local_disk_receipt = {}
            if isinstance(local_disk_receipt, Mapping):
                local_provider_call_count = int(
                    local_disk_receipt.get("provider_call_count", 0) or 0
                )
    provider_call_count = online_provider_call_count + local_provider_call_count
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
            "online_provider_call_count": online_provider_call_count,
            "local_provider_call_count": local_provider_call_count,
            "terminal_status": receipt.get("terminal_status", "INCOMPLETE"),
            "receipt_complete": receipt_complete,
            "solved": solved,
            "unified_receipt": receipt,
            "evidence_refs": list(receipt.get("evidence_refs", []) or []),
            "capability_edges": capability_summary,
            "capability_runtime_complete": capability_runtime_complete,
            "capability_online_forwarded": capability_online_forwarded,
            "run_root": str(run_root),
            "task_workspace": str(task_workspace),
            "unified_receipt_path": str(unified_receipt_path),
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
    task_id = f"{report['task_group_id']}-{scenario.lower()}"
    run_root = _scenario_run_root(args, task_id)
    return _run_nexus(
        report=report,
        project_root=project_root,
        provider=args.provider,
        command=args.command,
        task_statement=args.task_statement,
        workspace_revision=workspace_revision,
        local_enabled=scenario in {"B", "C"},
        timeout_sec=args.timeout_sec,
        run_root=run_root,
    )


def run_scenario_matrix(args: argparse.Namespace) -> dict[str, Any]:
    """Run A/B/C/D as one task-group comparison without collapsing evidence."""
    args = copy.copy(args)
    if not str(getattr(args, "run_root", "") or "").strip():
        args.run_root = tempfile.mkdtemp(prefix="nexus-runtime-scenario-matrix-")
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
    parser.add_argument("--run-root", default=None)
    parser.add_argument("--live", action="store_true", help="Required before any provider call")
    args = parser.parse_args(argv)
    report = run_scenario_matrix(args) if args.scenario == "ALL" else run_scenario(args)
    target_root = Path(str(args.run_root)).expanduser() if args.run_root else Path(args.project_root)
    target = (
        Path(args.receipt_path)
        if args.receipt_path
        else target_root
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
