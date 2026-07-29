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


# Local-consumable capabilities that may inject compact evidence into provider prompts.
_LOCAL_CONSUMABLE_CAPS = frozenset(
    {
        "local_model_executor",
        "memory",
        "codeintel",
        "belief",
        "semantic_searcher",
        "lancedb",
        "repair_loop",
        "sandbox",
    }
)


def build_local_compact_evidence(
    *,
    bundle: Mapping[str, Any] | None,
    selected_local_capabilities: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build compact evidence for Local provider prompt injection.

    Only Planner-selected local-consumable capabilities with success/invoked_real
    entries are included. Includes bounded consumer_payload when present.
    Returns prompt section text and the exact IDs/payloads serialized.
    """
    from nexus.services.capability_evidence_bundle import (
        consumer_payload_markers,
        hash_consumer_payloads,
    )

    b = dict(bundle) if isinstance(bundle, Mapping) else {}
    if not b:
        return {
            "prompt_section": "",
            "consumed_evidence_ids": [],
            "consumed_capability_payloads": [],
            "capability_payload_consumed": False,
            "consumer_payload_hash": "",
            "payload_markers": [],
            "selected_capabilities_used": [],
            "compact": {},
            "bundle_hash": "",
            "baseline_hash": "",
            "planner_decision_id": "",
        }
    selected = [str(x) for x in (selected_local_capabilities or ()) if str(x)]
    if not selected:
        selected = [
            str(n)
            for n in (b.get("selected_capabilities") or ())
            if str(n) in _LOCAL_CONSUMABLE_CAPS
        ]
    local_set = {str(x) for x in selected if str(x) in _LOCAL_CONSUMABLE_CAPS or str(x)}
    # Prefer explicit local-consumable intersection.
    local_set = {x for x in local_set if x in _LOCAL_CONSUMABLE_CAPS} or {
        x for x in selected if x in _LOCAL_CONSUMABLE_CAPS
    }

    entries_out: list[dict[str, Any]] = []
    consumed_ids: list[str] = []
    payloads: list[dict[str, Any]] = []
    payload_markers: list[str] = []
    caps_used: list[str] = []
    seen_ids: set[str] = set()

    for ent in b.get("entries") or []:
        if not isinstance(ent, Mapping):
            continue
        ename = str(ent.get("name") or "")
        if local_set and ename not in local_set:
            continue
        if not bool(ent.get("success") or ent.get("invoked_real")):
            continue
        eids = [
            str(x).strip()
            for x in (ent.get("evidence_ids") or ent.get("evidence_refs") or [])
            if str(x).strip() and not str(x).startswith("bundle:")
        ]
        cp = ent.get("consumer_payload") if isinstance(ent.get("consumer_payload"), Mapping) else {}
        # Context capabilities without payload: still may list IDs but not mark payload used.
        if not eids and not cp:
            continue
        summary = (
            f"status={ent.get('status') or 'SUCCEEDED'};"
            f"physical={str(ent.get('physical_callable') or '')[:80]}"
        )
        row: dict[str, Any] = {
            "name": ename,
            "status": str(ent.get("status") or ""),
            "success": True,
            "invoked_real": bool(ent.get("invoked_real") or ent.get("success")),
            "outcome_summary": summary,
            "evidence_ids": eids[:8],
            "has_consumer_payload": bool(cp),
        }
        if cp:
            row["consumer_payload"] = dict(cp)
            payloads.append(dict(cp))
            for m in consumer_payload_markers(cp):
                if m not in payload_markers:
                    payload_markers.append(m)
            if ename not in caps_used:
                caps_used.append(ename)
        for eid in eids:
            if eid not in seen_ids:
                seen_ids.add(eid)
                consumed_ids.append(eid)
        # ID-only context entries do not enter selected_capabilities_used as payload-used.
        if eids and not cp and ename not in caps_used:
            # still not "used" for payload causality — leave out of caps_used
            pass
        entries_out.append(row)

    compact = {
        "schema": "nexus.local_capability_evidence.v1",
        "bundle_hash": str(b.get("bundle_hash") or ""),
        "baseline_hash": str(b.get("baseline_hash") or ""),
        "planner_decision_id": str(b.get("planner_decision_id") or ""),
        "task_id": str(b.get("task_id") or ""),
        "selected_capabilities_used": list(caps_used),
        "entries": entries_out[:16],
        "evidence_ids": list(consumed_ids)[:32],
        "consumer_payloads": payloads[:16],
        "payload_markers": payload_markers[:32],
        "consumer_payload_hash": hash_consumer_payloads(payloads) if payloads else "",
        "public_claim_allowed": False,
    }
    prompt_section = ""
    if entries_out and (consumed_ids or payloads):
        prompt_section = (
            "[NEXUS_CAPABILITY_EVIDENCE]\n"
            + json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)
            + "\n"
        )
    payload_serialized = bool(payloads) and bool(prompt_section) and all(
        any(m in prompt_section for m in consumer_payload_markers(p)) or str(p.get("capability") or "") in prompt_section
        for p in payloads
    )
    return {
        "prompt_section": prompt_section,
        "consumed_evidence_ids": list(consumed_ids),
        "consumed_capability_payloads": list(payloads),
        "capability_payload_consumed": bool(payload_serialized),
        "consumer_payload_hash": str(compact.get("consumer_payload_hash") or ""),
        "payload_markers": list(payload_markers),
        "selected_capabilities_used": list(caps_used),
        "compact": compact if entries_out else {},
        "bundle_hash": str(b.get("bundle_hash") or ""),
        "baseline_hash": str(b.get("baseline_hash") or ""),
        "planner_decision_id": str(b.get("planner_decision_id") or ""),
    }


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
    """Match the isolated-apply hash normalization contract."""
    lines: list[str] = []
    for raw_line in diff_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
            continue
        if line.startswith("@@"):
            match = re.match(
                r"^@@\s+-\d+(?:,(\d+))?\s+\+\d+(?:,(\d+))?\s+@@",
                line,
            )
            if match:
                old_count = match.group(1) or "1"
                new_count = match.group(2) or "1"
                lines.append(f"@@ -0,{old_count} +0,{new_count} @@")
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
    # Physical callable identity: advisor → Provider.generate; candidate → Executor.run.
    physical_callable: str = ""
    executor_invoked: bool = False
    provider_call_count: int = 0
    model_call_count: int = 0

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
        from nexus.services.local_substitution import (
            build_verified_local_artifact,
            evaluate_local_eligibility,
            substitution_stage_trace,
        )

        # P2 eligibility: ineligible substitution actions fail closed before model I/O
        # when explicit displacement is required. Advisor path remains assist-only.
        eligibility = evaluate_local_eligibility(
            request,
            local_enabled=True,
            local_mode=str(planner_snapshot.get("local_mode") or request.action or "advisor"),
        )
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
        executor_invoked = False
        physical_callable = ""
        output_delivered = False
        provider_name = "ollama" if isinstance(raw_provider, OllamaLocalModelProvider) else "injected"
        resolved_model = str(planner_snapshot["executor_model"])
        fallback_reason = ""
        rollback_reference = ""
        candidate_patch = ""
        candidate_hash = ""
        provider_time = 0.0
        planner_decision_id = str(
            planner_snapshot.get("planner_decision_id")
            or planner_snapshot.get("plan_hash")
            or ""
        )
        verified_artifact: dict[str, Any] = {}
        stage_trace: dict[str, Any] = substitution_stage_trace()

        # Hard fail closed for explicitly ineligible substitution (missing verifier etc.).
        if (
            not eligibility.eligible
            and eligibility.status == "INELIGIBLE"
            and request.action in {"candidate", "verified-subtask"}
            and "deterministic_verifier_available" in eligibility.reason
        ):
            fallback_reason = eligibility.reason
            terminal_status = "FAILED"
            claim_boundary = {
                "registry_known": True,
                "planner_selected": True,
                "runtime_invoked": False,
                "executor_invoked": False,
                "physical_callable": "",
                "output_delivered": False,
                "agent_consumed": False,
                "outcome_contributed": False,
                "value_measured": False,
                "local_model_executor_invoked": False,
                "eligibility": eligibility.to_dict(),
            }
            stage_trace = substitution_stage_trace(fallback_reason=fallback_reason)
            receipt_path, report_path = self._output_paths(request, report_file)
            receipt = {
                "schema": "nexus.local_assist.execution_receipt.v1",
                "task_id": request.task_id,
                "parent_task_id": request.parent_task_id,
                "workspace_revision": request.workspace_revision,
                "planner_decision_id": planner_decision_id,
                "action": request.action,
                "eligibility": eligibility.to_dict(),
                "substitution_stages": stage_trace,
                "terminal_status": terminal_status,
                "receipt_complete": False,
                "claim_boundary": claim_boundary,
                "fallback_reason": fallback_reason,
                "provider_call_count": 0,
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
                    "planner_decision_id": planner_decision_id,
                    "eligibility": eligibility.to_dict(),
                },
                planner_selected=True,
                local_model_invoked=False,
                output_delivered=False,
                provider=provider_name,
                resolved_models=(resolved_model,),
                local_outputs={"eligibility": eligibility.to_dict()},
                candidate_summary=candidate_summary,
                verifier_summary=verifier_summary,
                receipt_path=str(receipt_path),
                evidence_refs=request.evidence_refs,
                fallback_reason=fallback_reason,
                claim_boundary=claim_boundary,
                physical_callable="",
                executor_invoked=False,
                provider_call_count=0,
                model_call_count=0,
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(response.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            return response

        # Assemble Local-consumable evidence BEFORE any provider/executor call.
        # consumed_evidence_ids are only IDs actually serialized into the prompt.
        _snap_selected = planner_snapshot.get("local_consumable_capabilities") or planner_snapshot.get(
            "selected_capabilities"
        )
        if isinstance(_snap_selected, (list, tuple)) and _snap_selected:
            _local_selected = [str(x) for x in _snap_selected]
        else:
            _local_selected = ["local_model_executor"]
        _bundle = (
            planner_snapshot.get("capability_evidence_bundle")
            if isinstance(planner_snapshot.get("capability_evidence_bundle"), dict)
            else {}
        )
        _local_evidence = build_local_compact_evidence(
            bundle=_bundle if isinstance(_bundle, Mapping) else {},
            selected_local_capabilities=_local_selected,
        )
        _prompt_evidence_section = str(_local_evidence.get("prompt_section") or "")
        _assembled_consumed_ids: list[str] = list(_local_evidence.get("consumed_evidence_ids") or [])
        _assembled_caps_used: list[str] = list(_local_evidence.get("selected_capabilities_used") or [])
        _bundle_hash = str(
            _local_evidence.get("bundle_hash")
            or (_bundle.get("bundle_hash") if isinstance(_bundle, Mapping) else "")
            or planner_snapshot.get("bundle_hash")
            or ""
        )

        try:
            if request.action == "advisor":
                # Advisor identity: LocalModelProvider.generate only — never claim executor INVOKED.
                physical_callable = "LocalModelProvider.generate"
                advisor_prompt = self._advisor_prompt(
                    request,
                    capability_evidence_section=_prompt_evidence_section,
                )
                provider_request = LocalModelProviderRequest(
                    task_id=request.task_id,
                    prompt=advisor_prompt,
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
                executor_invoked = False
                output_delivered = bool(local_model_invoked and provider_response.output_text.strip())
                local_outputs = {
                    "diagnosis": provider_response.output_text,
                    "recommended_next_action": "Online Agent must independently decide and record consumption.",
                    "provider_error": provider_response.error,
                    "capability_evidence_injected": bool(_prompt_evidence_section),
                    "prompt_serialized_evidence_ids": list(_assembled_consumed_ids),
                    # Advisor: payload-injected caps only count as used; never copy full selected.
                    "selected_capabilities": list(_local_selected),
                    "selected_capabilities_used": list(_assembled_caps_used),
                    "capability_usage_status": {
                        **{str(c): "selected_not_consumed" for c in _local_selected},
                        **{str(c): "used" for c in _assembled_caps_used},
                    },
                }
                if not local_model_invoked:
                    fallback_reason = provider_response.error or "provider_not_invoked"
            else:
                # Candidate / verified-subtask identity: LocalModelExecutor.run only.
                physical_callable = "LocalModelExecutor.run"
                # Inject compact evidence into problem_statement AND route_context so the
                # executor path sees the same IDs that will be recorded as consumed.
                _problem = request.task_statement
                if _prompt_evidence_section:
                    _problem = f"{request.task_statement}\n\n{_prompt_evidence_section}"
                executor_request = LocalModelExecutorRequest(
                    task_id=request.task_id,
                    problem_statement=_problem,
                    repo_root=request.workspace_root,
                    target_file=request.target_file,
                    selected_capabilities=tuple(_local_selected),
                    evidence_refs=request.evidence_refs,
                    receipt_context={
                        "parent_task_id": request.parent_task_id,
                        "bundle_hash": _bundle_hash,
                        "consumed_evidence_ids": list(_assembled_consumed_ids),
                        "selected_capabilities": list(_assembled_caps_used or _local_selected),
                        "selected_capabilities_used": list(_assembled_caps_used),
                    },
                    route_context={
                        "signal_snapshot": planner_snapshot,
                        "target_symbol": request.target_symbol,
                        "locked_search": request.locked_search,
                        "verifier_command": list(request.verifier_command),
                        "capability_evidence_bundle": _bundle,
                        "bundle_hash": _bundle_hash,
                        "capability_evidence_context": dict(_local_evidence.get("compact") or {}),
                        "capability_evidence_prompt_section": _prompt_evidence_section,
                        "consumed_evidence_ids": list(_assembled_consumed_ids),
                        "selected_capabilities_used": list(_assembled_caps_used),
                    },
                    model_name=resolved_model,
                    dry_run=False,
                    mutation_allowed=False,
                    verifier_allowed=False,
                    execution_topology=str(planner_snapshot["execution_topology"]),
                )
                executor_response = self._executor_runner(executor_request, provider=raw_provider)
                local_model_invoked = bool(executor_response.local_model_called)
                executor_invoked = bool(executor_response.invoked or executor_response.local_model_called)
                candidate_patch = _recount_unified_diff(str(executor_response.candidate_patch or ""))
                candidate_hash = _canonical_candidate_hash(candidate_patch) if candidate_patch.strip() else ""
                if not isinstance(raw_provider, OllamaLocalModelProvider):
                    provider_name = str(executor_response.provider or provider_name)
                resolved_model = str(executor_response.model_name or resolved_model)
                _exec_meta = (
                    executor_response.raw_model_metadata
                    if isinstance(executor_response.raw_model_metadata, Mapping)
                    else {}
                )
                local_outputs = {
                    "reasoning_summary": executor_response.reasoning_summary,
                    "candidate_patch": candidate_patch,
                    "provider_error": executor_response.error,
                    "raw_model_metadata": executor_response.raw_model_metadata,
                    # Causal used status from LocalModelExecutor (never selected=used copy).
                    "selected_capabilities": list(
                        _exec_meta.get("selected_capabilities") or _local_selected
                    ),
                    "selected_capabilities_used": list(
                        _exec_meta.get("selected_capabilities_used") or []
                    ),
                    "capability_usage_status": dict(
                        _exec_meta.get("capability_usage_status") or {}
                    ),
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
        verifier_passed = str(verifier_summary.get("verifier_status") or "").lower() in {
            "pass",
            "passed",
            "ok",
        }
        # Never claim partial success when verifier failed.
        if request.action == "verified-subtask" and not verifier_passed:
            output_delivered = False
            if not fallback_reason:
                fallback_reason = "verifier_failed_or_blocked"
        stage_trace = substitution_stage_trace(
            model_invoked=local_model_invoked,
            output_delivered=output_delivered,
            candidate_isolated=str(candidate_summary.get("isolation_status")) == "isolated",
            hash_matched=bool(candidate_summary.get("selected_candidate_hash_matches_applied")),
            verifier_reached=bool(verifier_summary.get("verifier_reached")),
            verifier_passed=verifier_passed,
            online_consumed=False,
            final_outcome_contributed=False,
            fallback_reason=fallback_reason,
        )
        # Online-facing concise summary: NEVER use reasoning_summary / CoT / raw patch /
        # raw advisor diagnosis. Only structured status/evidence metadata.
        private_reasoning = str(local_outputs.get("reasoning_summary") or "")
        if request.action == "advisor":
            # Strict whitelist — arbitrary model text cannot substantiate online-safe claims.
            concise = (
                f"action=advisor;"
                f"status={'succeeded' if output_delivered else 'failed'};"
                f"evidence_count={len(request.evidence_refs)};"
                f"target={request.target_file}"
            )
        elif output_delivered:
            concise = (
                f"action={request.action};"
                f"isolation={candidate_summary.get('isolation_status', 'not_run')};"
                f"hash={str(candidate_summary.get('selected_candidate_hash') or candidate_hash or '')[:16]};"
                f"verifier={verifier_summary.get('verifier_status', 'not_run')}"
            )
        else:
            concise = f"local_assist_incomplete;reason={fallback_reason or 'undelivered'}"
        # Online-safe structured artifact (no raw patch / CoT).
        verified_artifact = build_verified_local_artifact(
            task_id=request.task_id,
            action=request.action,
            candidate_hash=str(
                candidate_summary.get("selected_candidate_hash")
                or candidate_hash
                or ""
            ),
            verifier_status=str(verifier_summary.get("verifier_status") or "not_run"),
            evidence_refs=request.evidence_refs,
            concise_summary=concise,
            provider_displacement_type=str(
                planner_snapshot.get("provider_displacement_type")
                or ("call" if request.action == "verified-subtask" else "context")
            ),
            isolation_status=str(candidate_summary.get("isolation_status") or "not_run"),
            hash_matched=bool(candidate_summary.get("selected_candidate_hash_matches_applied")),
            verifier_reached=bool(verifier_summary.get("verifier_reached")),
            model_invoked=local_model_invoked,
            output_delivered=output_delivered,
        ).to_dict()
        # Strip fields that must never reach Online prompt builders or response local_outputs.
        # Private CoT is disk-receipt only — never re-inserted into local_outputs.
        local_outputs = {
            k: v
            for k, v in local_outputs.items()
            if k
            not in {
                "candidate_patch",
                "raw_model_metadata",
                "reasoning_summary",
                "_private_reasoning_not_for_online",
            }
        }
        local_outputs["concise_summary"] = verified_artifact["concise_summary"]
        local_outputs["verified_artifact"] = verified_artifact

        # Shared evidence consumption proof (P3) — only IDs actually serialized into
        # the Local provider/executor prompt at assembly time. Never reverse-infer
        # from the full sealed bundle after the model call.
        # Fail closed without broad exception swallow: record_consumption is pure
        # and must surface programming errors rather than fabricate empty success.
        from nexus.services.capability_evidence_bundle import record_consumption

        _ev_bundle = _bundle if isinstance(_bundle, Mapping) else {}
        # Empty prompt evidence section ⇒ not consumed, even if model was called.
        _ids_for_record = list(_assembled_consumed_ids) if (
            local_model_invoked and _prompt_evidence_section and _assembled_consumed_ids
        ) else []
        _payloads_for_record = list(_local_evidence.get("consumed_capability_payloads") or []) if (
            local_model_invoked and _prompt_evidence_section
        ) else []
        _payload_serialized = bool(
            local_model_invoked
            and _prompt_evidence_section
            and _local_evidence.get("capability_payload_consumed")
            and _payloads_for_record
        )
        _caps_for_record = list(_assembled_caps_used) if (_ids_for_record or _payloads_for_record) else []
        _consumption = record_consumption(
            bundle=_ev_bundle if _ev_bundle else {"bundle_hash": "", "selected_capabilities": []},
            consumer="Local",
            consumed_evidence_ids=_ids_for_record,
            selected_capabilities=_caps_for_record,
            physical_callable=physical_callable,
            consumed_capability_payloads=_payloads_for_record,
            payload_serialized_into_prompt=_payload_serialized,
        )
        _consumption = {
            **_consumption,
            "selected_capabilities_used": list(_caps_for_record),
            "prompt_evidence_injected": bool(_prompt_evidence_section and (_ids_for_record or _payloads_for_record)),
            "payload_markers": list(_local_evidence.get("payload_markers") or []),
            "consumer_payload_hash": str(
                _consumption.get("consumer_payload_hash")
                or _local_evidence.get("consumer_payload_hash")
                or ""
            ),
            "bundle_hash": str(
                _consumption.get("bundle_hash") or _bundle_hash or ""
            ),
            "baseline_hash": str(
                _local_evidence.get("baseline_hash")
                or (_ev_bundle.get("baseline_hash") if isinstance(_ev_bundle, Mapping) else "")
                or ""
            ),
            "planner_decision_id": str(
                _local_evidence.get("planner_decision_id")
                or (_ev_bundle.get("planner_decision_id") if isinstance(_ev_bundle, Mapping) else "")
                or planner_snapshot.get("planner_decision_id")
                or ""
            ),
        }
        local_outputs["evidence_consumption"] = {
            **_consumption,
            "selected_capabilities": list(local_outputs.get("selected_capabilities") or _local_selected),
            "selected_capabilities_used": list(
                local_outputs.get("selected_capabilities_used") or _assembled_caps_used
            ),
            "capability_usage_status": dict(local_outputs.get("capability_usage_status") or {}),
        }
        local_outputs["consumed_evidence_ids"] = list(_consumption.get("consumed_evidence_ids") or [])

        claim_boundary = {
            "registry_known": True,
            "planner_selected": True,
            "runtime_invoked": local_model_invoked,
            "executor_invoked": executor_invoked,
            "physical_callable": physical_callable,
            "output_delivered": output_delivered,
            "agent_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            # Advisor success is not local_model_executor INVOKED.
            "local_model_executor_invoked": bool(executor_invoked and request.action != "advisor"),
            "eligibility": eligibility.to_dict(),
            "partial_success_claimed": False,
        }
        receipt_path, report_path = self._output_paths(request, report_file)
        receipt = {
            "schema": "nexus.local_assist.execution_receipt.v1",
            "task_id": request.task_id,
            "parent_task_id": request.parent_task_id,
            "workspace_revision": request.workspace_revision,
            "planner_decision_id": planner_decision_id,
            "task_statement_hash": _hash_text(request.task_statement),
            "source_snapshot_hash": source_snapshot_hash,
            "planner_snapshot_hash": _hash_json(planner_snapshot),
            "action": request.action,
            "profile": request.requested_role,
            "physical_callable": physical_callable,
            "executor_invoked": executor_invoked,
            "eligibility": eligibility.to_dict(),
            "verified_artifact": verified_artifact,
            "substitution_stages": stage_trace,
            # Disk-only private field — not present on response.local_outputs.
            "private_reasoning_disk_only": private_reasoning[:4000] if private_reasoning else "",
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
                "planner_decision_id": planner_decision_id,
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
            physical_callable=physical_callable,
            executor_invoked=executor_invoked,
            provider_call_count=provider_call_count,
            model_call_count=provider_call_count if local_model_invoked else 0,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(response.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return response

    @staticmethod
    def _advisor_prompt(
        request: LocalAssistRequest,
        *,
        capability_evidence_section: str = "",
    ) -> str:
        base = (
            "You are Nexus Local Assist in advisor mode. Read-only diagnosis only.\n"
            f"Task: {request.task_statement}\n"
            f"Allowed files: {', '.join(request.allowed_files)}\n"
            f"Target: {request.target_file}:{request.target_symbol}\n"
            f"Evidence refs: {', '.join(request.evidence_refs)}\n"
            "Return concise diagnosis, recommended files/symbols, risk findings, confidence, and next action."
        )
        section = str(capability_evidence_section or "").strip()
        if section:
            return f"{base}\n\n{section}"
        return base

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
        # Trust IsolatedApplyReceipt hash match only — never re-project a mismatch into a match.
        model_candidate_hash = candidate_hash
        selected_candidate_hash = candidate_hash
        applied_patch_hash = apply_receipt.applied_patch_hash
        hash_matches = bool(apply_receipt.selected_candidate_hash_matches_applied)
        return {
            "candidate_count": 1,
            "candidate_hashes": list(dict.fromkeys([model_candidate_hash, selected_candidate_hash, applied_patch_hash or ""])),
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
        # Per-task receipt path: never clobber a shared execution_receipt.json when
        # multiple tasks write into the same report directory.
        if report_path.name == "response.json":
            # Default layout: .nexus/reports/local_assist/<task_id>/response.json
            receipt_path = report_path.with_name("execution_receipt.json")
        else:
            receipt_path = report_path.parent / f"{request.task_id}.execution_receipt.json"
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
    """Load a canonical request.v1 or translate live_smoke_task.v1 explicitly.

    Foreign schemas other than the live-smoke operator spec still fail closed.
    """
    from nexus.services.local_assist_live_smoke import (
        is_live_smoke_payload,
        load_local_assist_payload,
        translate_live_smoke_to_request,
    )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("request_must_be_object")
    if is_live_smoke_payload(payload):
        request = translate_live_smoke_to_request(payload)
        request.validate()
        return request
    # Canonical path only — do not silently accept other foreign schemas.
    request = LocalAssistRequest.from_dict(payload)
    request.validate()
    return request
