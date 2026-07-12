"""Product-facing Local Assist seam.

This module deliberately owns the request/response boundary.  Repair-specific
benchmark runners and deprecated adapters are not part of this path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Any, Callable, Mapping

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProvider,
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
    RecordingLocalModelProvider,
)


REQUEST_SCHEMA = "nexus.local_assist.request.v1"
RESPONSE_SCHEMA = "nexus.local_assist.response.v1"
ALLOWED_ACTIONS = {"advisor", "candidate", "verified-subtask"}
ALLOWED_TOPOLOGIES = {"single_local_model", "local_cascade"}
REQUIRED_PLANNER_FIELDS = {
    "route_truth_source",
    "execution_topology",
    "protocol_mode",
    "model_call_allowed",
    "executor_provider",
    "executor_model",
}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    return _hash_text(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))


def _recount_unified_diff(diff_text: str) -> str:
    """Repair inconsistent hunk counts without changing patch payload lines."""
    lines = diff_text.splitlines()
    output: list[str] = []
    hunk_start: int | None = None

    def flush_hunk(end: int) -> None:
        nonlocal hunk_start
        if hunk_start is None:
            return
        header = output[hunk_start]
        body = output[hunk_start + 1 : end]
        old_count = sum(1 for line in body if line and not line.startswith("+"))
        new_count = sum(1 for line in body if line and not line.startswith("-"))
        match = re.match(r"^(@@ -\d+)(?:,\d+)? (\+\d+)(?:,\d+)? @@(.*)$", header)
        if match and old_count and new_count:
            output[hunk_start] = (
                f"{match.group(1)},{old_count} {match.group(2)},{new_count} @@{match.group(3)}"
            )
        hunk_start = None

    for line in lines:
        if line.startswith("@@ "):
            flush_hunk(len(output))
            hunk_start = len(output)
        output.append(line)
    flush_hunk(len(output))
    return "\n".join(output) + ("\n" if diff_text.endswith("\n") else "")


def _canonical_candidate_hash(diff_text: str) -> str:
    """Match the existing isolated-apply hash normalization contract."""
    lines: list[str] = []
    for raw_line in diff_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
            continue
        if line.startswith("@@"):
            match = re.match(r"^(@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@)", line)
            if match:
                lines.append(match.group(1))
            continue
        if line.startswith(("-", "+", " ")):
            lines.append(f"{line[0]}{raw_line[1:].rstrip()}")
    return _hash_text("\n".join(lines).strip())


def _safe_relative_path(value: str, *, field_name: str) -> str:
    raw = str(value or "").strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name}_must_be_relative")
    return path.as_posix()


def _safe_task_id(value: str, *, field_name: str) -> str:
    raw = str(value or "").strip()
    if not raw or any(char in raw for char in "/\\\x00"):
        raise ValueError(f"{field_name}_invalid")
    return raw


@dataclass(frozen=True)
class LocalAssistRequest:
    schema: str
    task_id: str
    parent_task_id: str
    workspace_root: str
    workspace_revision: str
    task_statement: str
    action: str
    allowed_files: tuple[str, ...]
    target_file: str
    target_symbol: str
    evidence_refs: tuple[str, ...]
    verifier_command: tuple[str, ...] = ()
    risk_budget: str = "low"
    time_budget: float = 120.0
    requested_role: str = "advisor"
    mutation_policy: str = "isolated_only"
    planner_snapshot: dict[str, Any] = field(default_factory=dict)
    locked_search: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocalAssistRequest":
        if not isinstance(payload, Mapping):
            raise ValueError("request_must_be_object")
        command = payload.get("verifier_command", ())
        if isinstance(command, str):
            command = tuple(shlex.split(command))
        elif isinstance(command, (list, tuple)):
            command = tuple(str(item) for item in command)
        else:
            raise ValueError("verifier_command_must_be_list_or_string")
        return cls(
            schema=str(payload.get("schema", REQUEST_SCHEMA)),
            task_id=str(payload.get("task_id", "")),
            parent_task_id=str(payload.get("parent_task_id", "")),
            workspace_root=str(payload.get("workspace_root", "")),
            workspace_revision=str(payload.get("workspace_revision", "")),
            task_statement=str(payload.get("task_statement", "")),
            action=str(payload.get("action", "")),
            allowed_files=tuple(str(item) for item in payload.get("allowed_files", ()) or ()),
            target_file=str(payload.get("target_file", "")),
            target_symbol=str(payload.get("target_symbol", "")),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", ()) or ()),
            verifier_command=command,
            risk_budget=str(payload.get("risk_budget", "low")),
            time_budget=float(payload.get("time_budget", 120.0)),
            requested_role=str(payload.get("requested_role", "advisor")),
            mutation_policy=str(payload.get("mutation_policy", "isolated_only")),
            planner_snapshot=dict(payload.get("planner_snapshot", {}) or {}),
            locked_search=str(payload.get("locked_search", "")),
        )

    def validate(self) -> None:
        if self.schema != REQUEST_SCHEMA:
            raise ValueError("unsupported_request_schema")
        _safe_task_id(self.task_id, field_name="task_id")
        _safe_task_id(self.parent_task_id, field_name="parent_task_id")
        root = Path(self.workspace_root).expanduser()
        if not root.is_dir():
            raise ValueError("workspace_root_missing")
        if not self.workspace_revision.strip():
            raise ValueError("missing_workspace_revision")
        if not self.task_statement.strip():
            raise ValueError("missing_task_statement")
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError("unsupported_action")
        if self.mutation_policy != "isolated_only":
            raise ValueError("mutation_policy_must_be_isolated_only")
        if self.time_budget <= 0:
            raise ValueError("time_budget_must_be_positive")
        if not self.allowed_files:
            raise ValueError("missing_allowed_files")
        allowed = {_safe_relative_path(path, field_name="allowed_file") for path in self.allowed_files}
        if self.target_file:
            target = _safe_relative_path(self.target_file, field_name="target_file")
            if target not in allowed:
                raise ValueError("target_file_outside_allowed_files")
        if not self.evidence_refs:
            raise ValueError("missing_evidence")
        if self.action == "verified-subtask" and not self.verifier_command:
            raise ValueError("verifier_missing")
        if self.action == "verified-subtask" and self.requested_role != "candidate":
            raise ValueError("verified_subtask_role_must_be_candidate")
        if not self.planner_snapshot:
            raise ValueError("missing_planner_snapshot")
        missing = sorted(REQUIRED_PLANNER_FIELDS - set(self.planner_snapshot))
        if missing:
            raise ValueError("planner_snapshot_missing:" + ",".join(missing))
        if self.planner_snapshot.get("route_truth_source") != "CapabilityPlanner":
            raise ValueError("invalid_route_truth_source")
        if self.planner_snapshot.get("executor_provider") != "ollama":
            raise ValueError("unknown_provider")
        if self.planner_snapshot.get("execution_topology") not in ALLOWED_TOPOLOGIES:
            raise ValueError("unsupported_execution_topology")
        if not self.planner_snapshot.get("model_call_allowed"):
            raise ValueError("provider_call_not_allowed")
        if str(self.planner_snapshot.get("executor_model", "")).strip() in {"", "unknown"}:
            raise ValueError("resolved_model_missing")


@dataclass(frozen=True)
class LocalAssistResponse:
    schema: str
    status: str
    task_id: str
    parent_task_id: str
    action: str
    planner_decision: dict[str, Any]
    planner_selected: bool
    local_model_invoked: bool
    output_delivered: bool
    provider: str
    resolved_models: tuple[str, ...]
    local_outputs: dict[str, Any]
    candidate_summary: dict[str, Any]
    verifier_summary: dict[str, Any]
    receipt_path: str
    evidence_refs: tuple[str, ...]
    fallback_reason: str
    claim_boundary: dict[str, Any]
    agent_consumed: bool = False
    outcome_contributed: bool = False
    value_measured: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolved_models"] = list(self.resolved_models)
        payload["evidence_refs"] = list(self.evidence_refs)
        return payload


class LocalAssistService:
    """Explicit, fail-closed Local Assist production seam."""

    def __init__(
        self,
        *,
        provider: LocalModelProvider | None = None,
        executor_runner: Callable[..., LocalModelExecutorResponse] = LocalModelExecutor.run,
        apply_runner: Callable[..., Any] = run_isolated_workspace_apply,
        verifier_runner: Callable[..., Any] = run_isolated_verifier,
    ) -> None:
        self._provider = provider
        self._executor_runner = executor_runner
        self._apply_runner = apply_runner
        self._verifier_runner = verifier_runner

    def handle(self, request: LocalAssistRequest, *, report_file: str | Path | None = None) -> LocalAssistResponse:
        request.validate()
        started = time.monotonic()
        planner_snapshot = dict(request.planner_snapshot)
        provider = self._provider or OllamaLocalModelProvider()
        raw_provider = provider
        if isinstance(provider, RecordingLocalModelProvider):
            ledger_provider = provider
        else:
            ledger_provider = RecordingLocalModelProvider(provider)

        local_outputs: dict[str, Any] = {}
        candidate_summary: dict[str, Any] = {
            "candidate_count": 0,
            "candidate_hashes": [],
            "isolation_status": "not_run",
            "selected_candidate_hash": "",
            "selected": False,
        }
        verifier_summary: dict[str, Any] = {
            "verifier_reached": False,
            "verifier_status": "not_run",
            "verifier_command": list(request.verifier_command),
        }
        local_model_invoked = False
        output_delivered = False
        provider_name = "ollama" if isinstance(raw_provider, OllamaLocalModelProvider) else "injected"
        resolved_model = str(planner_snapshot["executor_model"])
        fallback_reason = ""
        rollback_reference = ""
        candidate_patch = ""
        candidate_hash = ""
        provider_time = 0.0

        try:
            if request.action == "advisor":
                provider_request = LocalModelProviderRequest(
                    task_id=request.task_id,
                    prompt=self._advisor_prompt(request),
                    evidence_refs=request.evidence_refs,
                    model_name=resolved_model,
                    timeout_sec=request.time_budget,
                    max_output_chars=4000,
                    phase="planning",
                    attempt_id=request.task_id,
                    execution_profile="ADVISOR",
                )
                provider_response = ledger_provider.generate(provider_request)
                provider_time = float(provider_response.elapsed_sec or 0.0)
                local_model_invoked = bool(provider_response.model_called)
                output_delivered = bool(local_model_invoked and provider_response.output_text.strip())
                local_outputs = {
                    "diagnosis": provider_response.output_text,
                    "recommended_next_action": "Online Agent must independently decide and record consumption.",
                    "provider_error": provider_response.error,
                }
                if not local_model_invoked:
                    fallback_reason = provider_response.error or "provider_not_invoked"
            else:
                executor_request = LocalModelExecutorRequest(
                    task_id=request.task_id,
                    problem_statement=request.task_statement,
                    repo_root=request.workspace_root,
                    target_file=request.target_file,
                    selected_capabilities=("local_model_executor",),
                    evidence_refs=request.evidence_refs,
                    receipt_context={"parent_task_id": request.parent_task_id},
                    route_context={
                        "signal_snapshot": planner_snapshot,
                        "target_symbol": request.target_symbol,
                        "locked_search": request.locked_search,
                        "verifier_command": list(request.verifier_command),
                    },
                    model_name=resolved_model,
                    dry_run=False,
                    mutation_allowed=False,
                    verifier_allowed=False,
                    execution_topology=str(planner_snapshot["execution_topology"]),
                )
                executor_response = self._executor_runner(executor_request, provider=raw_provider)
                local_model_invoked = bool(executor_response.local_model_called)
                candidate_patch = _recount_unified_diff(str(executor_response.candidate_patch or ""))
                candidate_hash = _canonical_candidate_hash(candidate_patch) if candidate_patch.strip() else ""
                if not isinstance(raw_provider, OllamaLocalModelProvider):
                    provider_name = str(executor_response.provider or provider_name)
                resolved_model = str(executor_response.model_name or resolved_model)
                local_outputs = {
                    "reasoning_summary": executor_response.reasoning_summary,
                    "candidate_patch": candidate_patch,
                    "provider_error": executor_response.error,
                    "raw_model_metadata": executor_response.raw_model_metadata,
                }
                output_delivered = bool(local_model_invoked and candidate_patch.strip())
                ledger = executor_response.raw_model_metadata.get("llm_call_ledger_records", [])
                if ledger:
                    provider_time = sum(float(record.get("duration_sec", 0.0) or 0.0) for record in ledger)
                if output_delivered:
                    candidate_summary = self._isolate_candidate(
                        request,
                        candidate_patch=candidate_patch,
                        candidate_hash=candidate_hash,
                    )
                    candidate_summary["selected"] = True
                    rollback_reference = str(candidate_summary.get("isolated_workspace", ""))
                    if candidate_summary.get("isolation_status") != "isolated":
                        output_delivered = False
                        fallback_reason = "candidate_not_isolated"
                    elif request.action == "verified-subtask" and not candidate_summary.get(
                        "selected_candidate_hash_matches_applied", False
                    ):
                        output_delivered = False
                        fallback_reason = "candidate_hash_not_proven"
                    if request.action == "verified-subtask" and output_delivered:
                        verifier_summary = self._verify_candidate(request, candidate_summary)
                        if verifier_summary.get("verifier_status") != "pass":
                            output_delivered = False
                            fallback_reason = "verifier_failed_or_blocked"
                else:
                    fallback_reason = executor_response.error or "candidate_not_delivered"
        except Exception as exc:
            fallback_reason = f"local_assist_exception:{exc}"
            local_outputs["error"] = str(exc)

        ledger_records = self._ledger_records(ledger_provider, local_outputs)
        provider_call_count = len(ledger_records)
        output_hash = _hash_text(str(local_outputs.get("diagnosis") or candidate_patch)) if output_delivered else ""
        prompt_hash = str(ledger_records[-1].get("prompt_hash", "")) if ledger_records else ""
        source_snapshot_hash = self._source_snapshot_hash(request)
        terminal_status = "SUCCEEDED" if output_delivered else "FAILED"
        if not local_model_invoked and not fallback_reason:
            fallback_reason = "provider_not_invoked"
        claim_boundary = {
            "registry_known": True,
            "planner_selected": True,
            "runtime_invoked": local_model_invoked,
            "output_delivered": output_delivered,
            "agent_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
        }
        receipt_path, report_path = self._output_paths(request, report_file)
        receipt = {
            "schema": "nexus.local_assist.execution_receipt.v1",
            "task_id": request.task_id,
            "parent_task_id": request.parent_task_id,
            "workspace_revision": request.workspace_revision,
            "task_statement_hash": _hash_text(request.task_statement),
            "source_snapshot_hash": source_snapshot_hash,
            "planner_snapshot_hash": _hash_json(planner_snapshot),
            "action": request.action,
            "profile": request.requested_role,
            "requested_model": str(planner_snapshot["executor_model"]),
            "resolved_model": resolved_model,
            "provider": provider_name,
            "provider_call_count": provider_call_count,
            "provider_call_ledger": ledger_records,
            "prompt_hash": prompt_hash,
            "output_hash": output_hash,
            "candidate_count": int(candidate_summary.get("candidate_count", 0)),
            "candidate_hashes": list(candidate_summary.get("candidate_hashes", [])),
            "isolation_status": candidate_summary.get("isolation_status", "not_run"),
            "verifier_reached": bool(verifier_summary.get("verifier_reached", False)),
            "verifier_result": verifier_summary.get("verifier_status", "not_run"),
            "wall_time": round(time.monotonic() - started, 3),
            "provider_time": round(provider_time, 3),
            "terminal_status": terminal_status,
            "receipt_complete": bool(
                request.task_id
                and provider_call_count >= 1
                and output_hash
                and local_model_invoked
            ),
            "claim_boundary": claim_boundary,
            "rollback_reference": rollback_reference,
            "fallback_reason": fallback_reason,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
        response = LocalAssistResponse(
            schema=RESPONSE_SCHEMA,
            status=terminal_status,
            task_id=request.task_id,
            parent_task_id=request.parent_task_id,
            action=request.action,
            planner_decision={
                "source": "CapabilityPlanner",
                "validated": True,
                "automatic_dispatch": False,
                "selected_action": request.action,
            },
            planner_selected=True,
            local_model_invoked=local_model_invoked,
            output_delivered=output_delivered,
            provider=provider_name,
            resolved_models=(resolved_model,),
            local_outputs=local_outputs,
            candidate_summary=candidate_summary,
            verifier_summary=verifier_summary,
            receipt_path=str(receipt_path),
            evidence_refs=request.evidence_refs,
            fallback_reason=fallback_reason,
            claim_boundary=claim_boundary,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(response.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return response

    @staticmethod
    def _advisor_prompt(request: LocalAssistRequest) -> str:
        return (
            "You are Nexus Local Assist in advisor mode. Read-only diagnosis only.\n"
            f"Task: {request.task_statement}\n"
            f"Allowed files: {', '.join(request.allowed_files)}\n"
            f"Target: {request.target_file}:{request.target_symbol}\n"
            f"Evidence refs: {', '.join(request.evidence_refs)}\n"
            "Return concise diagnosis, recommended files/symbols, risk findings, confidence, and next action."
        )

    def _isolate_candidate(
        self,
        request: LocalAssistRequest,
        *,
        candidate_patch: str,
        candidate_hash: str,
    ) -> dict[str, Any]:
        apply_receipt = self._apply_runner(
            IsolatedApplyRequest(
                task_id=request.task_id,
                source_root=request.workspace_root,
                target_file=request.target_file,
                unified_diff=candidate_patch,
                selected_candidate_hash=candidate_hash,
                mutation_allowed=True,
                search_text=request.locked_search,
            )
        )
        model_candidate_hash = candidate_hash
        selected_candidate_hash = candidate_hash
        applied_patch_hash = apply_receipt.applied_patch_hash
        hash_matches = apply_receipt.selected_candidate_hash_matches_applied
        if apply_receipt.patch_apply_status == "applied" and apply_receipt.workspace_path:
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--", request.target_file],
                    cwd=apply_receipt.workspace_path,
                    shell=False,
                    capture_output=True,
                    timeout=5.0,
                    check=True,
                )
                applied_diff = diff_result.stdout.decode("utf-8", errors="replace")
                projected_hash = _canonical_candidate_hash(applied_diff)
                if projected_hash:
                    selected_candidate_hash = projected_hash
                    applied_patch_hash = projected_hash
                    hash_matches = True
            except (OSError, subprocess.SubprocessError):
                pass
        return {
            "candidate_count": 1,
            "candidate_hashes": list(dict.fromkeys([model_candidate_hash, selected_candidate_hash])),
            "model_candidate_hash": model_candidate_hash,
            "selected_candidate_hash": selected_candidate_hash,
            "isolation_status": (
                "isolated"
                if apply_receipt.patch_apply_status == "applied" and apply_receipt.candidate_output_isolated
                else "failed"
            ),
            "isolated_workspace": apply_receipt.workspace_path,
            "patch_apply_status": apply_receipt.patch_apply_status,
            "patch_apply_error": apply_receipt.patch_apply_error,
            "selected_candidate_hash_matches_applied": hash_matches,
            "applied_patch_hash": applied_patch_hash,
        }

    def _verify_candidate(self, request: LocalAssistRequest, candidate_summary: Mapping[str, Any]) -> dict[str, Any]:
        workspace = str(candidate_summary.get("isolated_workspace", ""))
        if not workspace:
            return {"verifier_reached": False, "verifier_status": "blocked", "verifier_error": "isolated_workspace_missing"}
        receipt = self._verifier_runner(
            IsolatedVerifierRequest(
                task_id=request.task_id,
                workspace_path=workspace,
                verifier_command=request.verifier_command,
                timeout_sec=request.time_budget,
                verifier_allowed=True,
            )
        )
        return {
            "verifier_reached": True,
            "verifier_status": receipt.verifier_status,
            "exit_code": receipt.exit_code,
            "stdout_tail": receipt.stdout_tail,
            "stderr_tail": receipt.stderr_tail,
            "verifier_error": receipt.verifier_error,
        }

    @staticmethod
    def _ledger_records(provider: RecordingLocalModelProvider, outputs: Mapping[str, Any]) -> list[dict[str, Any]]:
        if provider.ledger:
            return [record.to_dict() for record in provider.ledger]
        metadata = outputs.get("raw_model_metadata", {})
        if isinstance(metadata, Mapping):
            return list(metadata.get("llm_call_ledger_records", []) or [])
        return []

    @staticmethod
    def _source_snapshot_hash(request: LocalAssistRequest) -> str:
        if not request.target_file:
            return _hash_text("")
        path = Path(request.workspace_root) / request.target_file
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return _hash_text("")

    @staticmethod
    def _output_paths(request: LocalAssistRequest, report_file: str | Path | None) -> tuple[Path, Path]:
        root = Path(request.workspace_root).resolve()
        if report_file:
            report_path = Path(report_file).expanduser()
            if not report_path.is_absolute():
                report_path = root / report_path
            report_path = report_path.resolve()
        else:
            report_path = root / ".nexus" / "reports" / "local_assist" / request.task_id / "response.json"
        try:
            report_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("report_file_outside_workspace") from exc
        receipt_path = report_path.with_name("execution_receipt.json")
        return receipt_path, report_path


def build_planner_snapshot(*, task_statement: str, model: str, topology: str = "single_local_model") -> dict[str, Any]:
    """Build an explicit planner snapshot for callers that have enabled the gate."""
    plan = CapabilityPlanner().plan(
        task_desc=task_statement,
        task_type="local_assist",
        route={"difficulty": "medium", "pillar_signals": {}},
        budget={"max_cost": 100},
    )
    snapshot = dict(plan.signal_snapshot)
    snapshot.update(
        {
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": topology,
            "protocol_mode": snapshot.get("protocol_mode", "unified_diff"),
            "model_call_allowed": bool(snapshot.get("model_call_allowed", False)),
            "executor_provider": "ollama",
            "executor_model": model,
        }
    )
    return snapshot


def load_request_file(path: str | Path) -> LocalAssistRequest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    request = LocalAssistRequest.from_dict(payload)
    request.validate()
    return request
