"""Agent-facing Local Assist consumption and closeout contract."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "nexus.local_assist.agent_closeout.v1"
ALLOWED_AGENTS = {"gemini", "grok", "codex", "chatgpt"}
ALLOWED_ACTIONS = {"advisor", "candidate", "verified-subtask"}
ALLOWED_CONTRIBUTION_CLAIMS = {
    "not_claimed",
    "consumed_for_localization",
    "consumed_for_candidate_selection",
}


@dataclass(frozen=True)
class AgentCloseoutValidation:
    ok: bool
    blockers: tuple[str, ...]
    claim_boundary: dict[str, Any]
    receipt_summaries: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class LocalAssistAgentCloseout:
    schema: str
    task_id: str
    agent_provider: str
    local_assist_requested: bool
    local_assist_selected: tuple[str, ...]
    local_assist_invoked: bool
    local_assist_receipt_paths: tuple[str, ...]
    local_assist_output_delivered: bool
    local_assist_output_consumed: bool
    local_candidate_selected: bool
    local_assist_contribution_claim: str
    output_consumption_evidence: tuple[str, ...] = ()
    final_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocalAssistAgentCloseout":
        if not isinstance(payload, Mapping):
            raise ValueError("closeout_must_be_object")
        return cls(
            schema=str(payload.get("schema", "")),
            task_id=str(payload.get("task_id", "")),
            agent_provider=str(payload.get("agent_provider", "")),
            local_assist_requested=bool(payload.get("local_assist_requested", False)),
            local_assist_selected=tuple(str(item) for item in payload.get("local_assist_selected", ()) or ()),
            local_assist_invoked=bool(payload.get("local_assist_invoked", False)),
            local_assist_receipt_paths=tuple(
                str(item) for item in payload.get("local_assist_receipt_paths", ()) or ()
            ),
            local_assist_output_delivered=bool(payload.get("local_assist_output_delivered", False)),
            local_assist_output_consumed=bool(payload.get("local_assist_output_consumed", False)),
            local_candidate_selected=bool(payload.get("local_candidate_selected", False)),
            local_assist_contribution_claim=str(
                payload.get("local_assist_contribution_claim", "not_claimed")
            ),
            output_consumption_evidence=tuple(
                str(item) for item in payload.get("output_consumption_evidence", ()) or ()
            ),
            final_output=str(payload.get("final_output", "")),
            metadata=dict(payload.get("metadata", {}) or {}),
        )

    def validate(self, repo_root: str | Path) -> AgentCloseoutValidation:
        root = Path(repo_root).resolve()
        blockers: list[str] = []
        summaries: list[dict[str, Any]] = []

        if self.schema != SCHEMA:
            blockers.append("unsupported_closeout_schema")
        if not self.task_id.strip():
            blockers.append("missing_task_id")
        if self.agent_provider not in ALLOWED_AGENTS:
            blockers.append("unsupported_agent_provider")
        if any(action not in ALLOWED_ACTIONS for action in self.local_assist_selected):
            blockers.append("unsupported_selected_action")
        if self.local_assist_requested and not self.local_assist_selected:
            blockers.append("requested_without_selection")
        if not self.local_assist_requested and (
            self.local_assist_selected
            or self.local_assist_invoked
            or self.local_assist_receipt_paths
            or self.local_assist_output_consumed
        ):
            blockers.append("unrequested_assist_claimed")
        if self.local_assist_output_delivered and not self.local_assist_invoked:
            blockers.append("output_delivered_without_invocation")
        if self.local_assist_invoked and not self.local_assist_receipt_paths:
            blockers.append("invoked_without_receipts")
        if self.local_assist_contribution_claim not in ALLOWED_CONTRIBUTION_CLAIMS:
            blockers.append("unsupported_contribution_claim")
        if self.local_assist_contribution_claim != "not_claimed" and not self.local_assist_output_consumed:
            blockers.append("contribution_claim_without_consumption")

        valid_receipts: list[dict[str, Any]] = []
        for raw_path in self.local_assist_receipt_paths:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                blockers.append(f"receipt_outside_repo:{raw_path}")
                continue
            if not path.is_file():
                blockers.append(f"receipt_missing:{relative}")
                continue
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                blockers.append(f"receipt_invalid:{relative}")
                continue
            if receipt.get("receipt_complete") is not True:
                blockers.append(f"receipt_incomplete:{relative}")
            if int(receipt.get("provider_call_count", 0) or 0) < 1:
                blockers.append(f"receipt_without_provider_call:{relative}")
            if receipt.get("provider") != "ollama":
                blockers.append(f"receipt_provider_not_ollama:{relative}")
            if not str(receipt.get("resolved_model", "")).strip() or receipt.get("resolved_model") == "unknown":
                blockers.append(f"receipt_model_missing:{relative}")
            boundary = receipt.get("claim_boundary", {})
            if boundary.get("runtime_invoked") is not True:
                blockers.append(f"receipt_runtime_not_invoked:{relative}")
            if boundary.get("output_delivered") is not True:
                blockers.append(f"receipt_output_not_delivered:{relative}")
            valid_receipts.append(
                {
                    "path": str(path),
                    "relative_path": relative,
                    "task_id": str(receipt.get("task_id", "")),
                    "action": str(receipt.get("action", "")),
                    "candidate_count": int(receipt.get("candidate_count", 0) or 0),
                    "verifier_result": str(receipt.get("verifier_result", "")),
                }
            )

        if self.local_assist_output_consumed:
            if not self.local_assist_output_delivered:
                blockers.append("output_consumed_without_delivery")
            if not self.output_consumption_evidence or not self.final_output.strip():
                blockers.append("output_consumed_requires_evidence")
            combined = "\n".join((*self.output_consumption_evidence, self.final_output))
            for receipt in valid_receipts:
                identifiers = (receipt["relative_path"], receipt["path"], receipt["task_id"])
                if not any(identifier and identifier in combined for identifier in identifiers):
                    blockers.append(f"receipt_not_referenced:{receipt['relative_path']}")

        if self.local_candidate_selected:
            if not any(
                receipt["action"] in {"candidate", "verified-subtask"}
                and receipt["candidate_count"] > 0
                for receipt in valid_receipts
            ):
                blockers.append("candidate_selected_without_candidate_receipt")

        claim_boundary = {
            "local_assist_requested": self.local_assist_requested,
            "local_assist_selected": bool(self.local_assist_selected),
            "local_assist_invoked": self.local_assist_invoked and not any(
                blocker.startswith(("receipt_", "invoked_")) for blocker in blockers
            ),
            "local_assist_output_delivered": self.local_assist_output_delivered,
            "output_consumed": self.local_assist_output_consumed and not any(
                blocker.startswith("output_consumed") or blocker.startswith("receipt_not_referenced")
                for blocker in blockers
            ),
            "outcome_contributed": False,
            "value_measured": False,
        }
        return AgentCloseoutValidation(
            ok=not blockers,
            blockers=tuple(sorted(set(blockers))),
            claim_boundary=claim_boundary,
            receipt_summaries=tuple(valid_receipts),
        )


@dataclass(frozen=True)
class LocalAssistCloseoutRun:
    exit_code: int
    report_path: str
    report: dict[str, Any]


def run_local_assist_closeout(
    *,
    closeout_file: str | Path,
    repo_root: str | Path,
    report_file: str | Path | None = None,
) -> LocalAssistCloseoutRun:
    root = Path(repo_root).resolve()
    payload = json.loads(Path(closeout_file).read_text(encoding="utf-8"))
    closeout = LocalAssistAgentCloseout.from_dict(payload)
    validation = closeout.validate(root)
    output = Path(report_file) if report_file else root / ".nexus" / "reports" / "local_assist" / closeout.task_id / "agent_closeout.json"
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("closeout_report_outside_repo") from exc
    report = {
        "schema": SCHEMA,
        "status": "VERIFIED" if validation.ok else "REJECTED",
        "task_id": closeout.task_id,
        "agent_provider": closeout.agent_provider,
        "local_assist_requested": closeout.local_assist_requested,
        "local_assist_selected": list(closeout.local_assist_selected),
        "local_assist_invoked": closeout.local_assist_invoked,
        "local_assist_receipt_paths": list(closeout.local_assist_receipt_paths),
        "local_assist_output_delivered": closeout.local_assist_output_delivered,
        "local_assist_output_consumed": closeout.local_assist_output_consumed,
        "local_candidate_selected": closeout.local_candidate_selected,
        "local_assist_contribution_claim": closeout.local_assist_contribution_claim,
        "claim_boundary": validation.claim_boundary,
        "receipt_summaries": list(validation.receipt_summaries),
        "blockers": list(validation.blockers),
        "output_consumption_evidence": list(closeout.output_consumption_evidence),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return LocalAssistCloseoutRun(
        exit_code=0 if validation.ok else 1,
        report_path=str(output),
        report=report,
    )
