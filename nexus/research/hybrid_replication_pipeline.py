from __future__ import annotations

import base64
import gzip
import hashlib
import json
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

CAPTURE_MARKER = "<!-- NEXUS-HYBRID-REPLICATION-CAPTURE-V1 -->"
ADMISSION_MARKER = "<!-- NEXUS-HYBRID-REPLICATION-ADMISSION-V1 -->"
CONTRACT_DELTA_MARKER = "<!-- NEXUS-HYBRID-REPLICATION-CONTRACT-DELTA-V1 -->"
CAPTURE_SCHEMA = "nexus.hybrid_replication.capture.v1"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _encode_body(body: str) -> str:
    return base64.b64encode(gzip.compress(body.encode("utf-8"), mtime=0)).decode("ascii")


def _decode_body(value: str) -> str:
    return gzip.decompress(base64.b64decode(value.encode("ascii"))).decode("utf-8")


@dataclass(frozen=True)
class TaskSnapshot:
    repository: str
    issue_number: int
    created_at: str
    captured_at: str
    issue_updated_at: str
    title: str
    body: str
    pre_implementation_revision: str
    default_branch: str
    source_event_id: str
    contract_sha256: str
    capture_sha256: str
    body_gzip_base64: str | None = None
    schema: str = CAPTURE_SCHEMA

    @classmethod
    def create(
        cls,
        *,
        repository: str,
        issue_number: int,
        created_at: str,
        captured_at: str,
        issue_updated_at: str,
        title: str,
        body: str,
        pre_implementation_revision: str,
        default_branch: str,
        source_event_id: str,
    ) -> "TaskSnapshot":
        contract = {
            "body": body,
            "created_at": created_at,
            "issue": int(issue_number),
            "repository": repository,
            "title": title,
            "updated_at": issue_updated_at,
        }
        contract_sha256 = _sha256(_canonical_bytes(contract))
        body_gzip_base64 = _encode_body(body)
        capture_payload = {
            "schema": CAPTURE_SCHEMA,
            "repository": repository,
            "issue_number": int(issue_number),
            "created_at": created_at,
            "captured_at": captured_at,
            "issue_updated_at": issue_updated_at,
            "title": title,
            "body_gzip_base64": body_gzip_base64,
            "pre_implementation_revision": pre_implementation_revision,
            "default_branch": default_branch,
            "source_event_id": source_event_id,
            "contract_sha256": contract_sha256,
        }
        capture_sha256 = _sha256(_canonical_bytes(capture_payload))
        return cls(
            repository=repository,
            issue_number=int(issue_number),
            created_at=created_at,
            captured_at=captured_at,
            issue_updated_at=issue_updated_at,
            title=title,
            body=body,
            pre_implementation_revision=pre_implementation_revision,
            default_branch=default_branch,
            source_event_id=source_event_id,
            contract_sha256=contract_sha256,
            capture_sha256=capture_sha256,
            body_gzip_base64=body_gzip_base64,
        )

    @classmethod
    def from_capture_payload(cls, payload: Mapping[str, Any]) -> "TaskSnapshot":
        if payload.get("schema") != CAPTURE_SCHEMA:
            raise ValueError("capture_schema_mismatch")
        supplied_capture_sha = str(payload.get("capture_sha256") or "")
        hash_payload = dict(payload)
        hash_payload.pop("capture_sha256", None)
        expected_capture_sha = _sha256(_canonical_bytes(hash_payload))
        if supplied_capture_sha != expected_capture_sha:
            raise ValueError("capture_sha256_mismatch")

        body_gzip_base64 = str(payload["body_gzip_base64"])
        raw_body = _decode_body(body_gzip_base64)
        contract = {
            "body": raw_body,
            "created_at": str(payload["created_at"]),
            "issue": int(payload["issue_number"]),
            "repository": str(payload["repository"]),
            "title": str(payload["title"]),
            "updated_at": str(payload["issue_updated_at"]),
        }
        expected_contract_sha = _sha256(_canonical_bytes(contract))
        supplied_contract_sha = str(payload["contract_sha256"])
        if supplied_contract_sha != expected_contract_sha:
            raise ValueError("contract_sha256_mismatch")

        return cls(
            repository=str(payload["repository"]),
            issue_number=int(payload["issue_number"]),
            created_at=str(payload["created_at"]),
            captured_at=str(payload["captured_at"]),
            issue_updated_at=str(payload["issue_updated_at"]),
            title=str(payload["title"]),
            body=raw_body,
            pre_implementation_revision=str(payload["pre_implementation_revision"]),
            default_branch=str(payload["default_branch"]),
            source_event_id=str(payload["source_event_id"]),
            contract_sha256=supplied_contract_sha,
            capture_sha256=supplied_capture_sha,
            body_gzip_base64=body_gzip_base64,
        )

    @property
    def task_key(self) -> str:
        return _task_key(self.repository, self.issue_number)

    def to_capture_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "created_at": self.created_at,
            "captured_at": self.captured_at,
            "issue_updated_at": self.issue_updated_at,
            "title": self.title,
            "body_gzip_base64": self.body_gzip_base64 or _encode_body(self.body),
            "pre_implementation_revision": self.pre_implementation_revision,
            "default_branch": self.default_branch,
            "source_event_id": self.source_event_id,
            "contract_sha256": self.contract_sha256,
            "capture_sha256": self.capture_sha256,
        }


def build_capture_comment(snapshot: TaskSnapshot) -> str:
    payload = snapshot.to_capture_payload()
    return (
        f"{CAPTURE_MARKER}\n"
        "Authority: `RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY`\n\n"
        "<details><summary>Hybrid replication capture receipt</summary>\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n</details>"
    )


def parse_capture_comment(body: str) -> TaskSnapshot:
    if CAPTURE_MARKER not in body:
        raise ValueError("capture_marker_missing")
    start = body.find("```json")
    if start < 0:
        raise ValueError("capture_json_block_missing")
    start = body.find("\n", start)
    if start < 0:
        raise ValueError("capture_json_block_malformed")
    end = body.find("```", start + 1)
    if end < 0:
        raise ValueError("capture_json_block_unterminated")
    payload = json.loads(body[start + 1 : end])
    return TaskSnapshot.from_capture_payload(payload)


@dataclass(frozen=True)
class RouteClassification:
    stratum: str
    reason: str
    capture_sha256: str
    frozen_policy_sha256: str
    decided_at: str

    def __post_init__(self) -> None:
        if self.stratum not in {"A", "B", "C"}:
            raise ValueError("invalid_replication_stratum")
        if len(self.capture_sha256) != 64:
            raise ValueError("invalid_capture_sha256")
        if len(self.frozen_policy_sha256) != 64:
            raise ValueError("invalid_frozen_policy_sha256")


@dataclass(frozen=True)
class RawRouteResult:
    route: str
    provider: str
    requested_model: str
    resolved_model: str
    model_call_count: int
    input_tokens: int | None
    uncached_input_tokens: int | None
    output_tokens: int | None
    wall_time_seconds: float
    failures: tuple[str, ...]
    retries: int
    fallbacks: tuple[str, ...]
    raw_response: Mapping[str, Any]
    output_sha256: str

    @classmethod
    def create(
        cls,
        *,
        route: str,
        provider: str,
        requested_model: str,
        resolved_model: str,
        model_call_count: int,
        input_tokens: int | None,
        uncached_input_tokens: int | None,
        output_tokens: int | None,
        wall_time_seconds: float,
        failures: tuple[str, ...],
        retries: int,
        fallbacks: tuple[str, ...],
        raw_response: Mapping[str, Any],
    ) -> "RawRouteResult":
        return cls(
            route=route,
            provider=provider,
            requested_model=requested_model,
            resolved_model=resolved_model,
            model_call_count=model_call_count,
            input_tokens=input_tokens,
            uncached_input_tokens=uncached_input_tokens,
            output_tokens=output_tokens,
            wall_time_seconds=wall_time_seconds,
            failures=failures,
            retries=retries,
            fallbacks=fallbacks,
            raw_response=dict(raw_response),
            output_sha256=_sha256(_canonical_bytes(raw_response)),
        )

    def __post_init__(self) -> None:
        if self.route not in {"A", "B", "C"}:
            raise ValueError("invalid_replication_route")
        if self.model_call_count < 0 or self.retries < 0 or self.wall_time_seconds < 0:
            raise ValueError("invalid_raw_route_metric")
        if self.output_sha256 != _sha256(_canonical_bytes(self.raw_response)):
            raise ValueError("output_sha256_mismatch")


@dataclass(frozen=True)
class FrozenStackOutcome:
    stratum: str
    deterministic_receipt: Mapping[str, Any]
    candidate_packet: Mapping[str, Any] | None
    jev_raw_response: Mapping[str, Any] | None
    dm1_decision: Mapping[str, Any] | None
    strong_online_raw_response: Mapping[str, Any] | None
    raw_result: RawRouteResult

    def validate(self) -> None:
        if self.stratum != self.raw_result.route:
            raise ValueError("stack_raw_route_mismatch")
        if self.stratum == "A":
            if self.raw_result.model_call_count != 0:
                raise ValueError("a_requires_zero_model_calls")
            if not self.deterministic_receipt:
                raise ValueError("a_requires_deterministic_receipt")
            return
        if self.stratum == "B":
            if (
                not self.candidate_packet
                or not self.jev_raw_response
                or not self.dm1_decision
                or not self.strong_online_raw_response
            ):
                raise ValueError("b_requires_candidate_jev_dm1_strong_evidence")
            choice = str(self.dm1_decision.get("choice") or "")
            top = float(self.dm1_decision.get("top_probability") or 0.0)
            margin = float(self.dm1_decision.get("margin") or 0.0)
            accepted = choice != "ESCALATE" and top >= 0.70 and margin >= 0.30
            if not accepted:
                raise ValueError("b_requires_dm1_accept")
            return
        if self.stratum == "C":
            if not self.strong_online_raw_response:
                raise ValueError("c_requires_strong_online_raw_response")
            if self.raw_result.model_call_count < 1:
                raise ValueError("c_requires_model_call")
            return
        raise ValueError("invalid_replication_stratum")


@dataclass(frozen=True)
class GroundTruthEvidence:
    terminal_state: str
    terminal_at: str
    evidence_refs: tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.terminal_state.strip():
            raise ValueError("terminal_state_required")
        if not self.evidence_refs:
            raise ValueError("ground_truth_evidence_required")


def _task_dir_name(task_key: str) -> str:
    return task_key.replace("/", "__").replace("#", "--")


def _task_key(repository: str, issue_number: int) -> str:
    return f"{repository}#{int(issue_number)}"


PRIMARY_ADMISSION_DISPOSITION = "ADMITTED_PRIMARY_FRESH_TASK"
READINESS_CONTROL_DISPOSITION = "READINESS_CONTROL_EXCLUDED"
READINESS_CONTROL_ACTIVATION_STATE = "READINESS_CONTROL_PENDING"
_EXECUTABLE_ADMISSION_DISPOSITIONS = {
    PRIMARY_ADMISSION_DISPOSITION,
    READINESS_CONTROL_DISPOSITION,
}


@dataclass(frozen=True)
class AdmissionReceipt:
    task_key: str
    capture_sha256: str
    disposition: str
    activation_boundary: str
    activation_state: str
    exclusion_set_sha256: str
    issue_state_at_admission: str
    implementation_pr_numbers: tuple[int, ...]
    tracked_parent_issue_number: int | None
    tracked_parent_created_at: str | None
    admitted_at: str
    receipt_sha256: str
    schema: str = "nexus.hybrid_replication.admission.v1"

    def __post_init__(self) -> None:
        if self.disposition == READINESS_CONTROL_DISPOSITION:
            if self.activation_state != READINESS_CONTROL_ACTIVATION_STATE:
                raise ValueError("readiness_control_pending_required")
        elif self.activation_state != "AUTOMATIC_CAPTURE_READY":
            raise ValueError("automatic_capture_ready_required")
        if len(self.exclusion_set_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.exclusion_set_sha256
        ):
            raise ValueError("exclusion_set_sha256_required")
        if self.issue_state_at_admission not in {"open", "closed"}:
            raise ValueError("invalid_issue_state_at_admission")

    @classmethod
    def create(
        cls,
        *,
        snapshot: TaskSnapshot,
        disposition: str,
        activation_boundary: str,
        activation_state: str,
        exclusion_set_sha256: str,
        issue_state_at_admission: str,
        implementation_pr_numbers: tuple[int, ...],
        tracked_parent_issue_number: int | None,
        tracked_parent_created_at: str | None,
        admitted_at: str,
    ) -> "AdmissionReceipt":
        if not activation_boundary:
            raise ValueError("activation_boundary_required")
        if disposition == READINESS_CONTROL_DISPOSITION:
            if activation_state != READINESS_CONTROL_ACTIVATION_STATE:
                raise ValueError("readiness_control_pending_required")
        elif activation_state != "AUTOMATIC_CAPTURE_READY":
            raise ValueError("automatic_capture_ready_required")
        if len(exclusion_set_sha256) != 64:
            raise ValueError("exclusion_set_sha256_required")
        payload = {
            "schema": "nexus.hybrid_replication.admission.v1",
            "task_key": snapshot.task_key,
            "capture_sha256": snapshot.capture_sha256,
            "disposition": disposition,
            "activation_boundary": activation_boundary,
            "activation_state": activation_state,
            "exclusion_set_sha256": exclusion_set_sha256,
            "issue_state_at_admission": issue_state_at_admission,
            "implementation_pr_numbers": list(implementation_pr_numbers),
            "tracked_parent_issue_number": tracked_parent_issue_number,
            "tracked_parent_created_at": tracked_parent_created_at,
            "admitted_at": admitted_at,
        }
        return cls(
            task_key=snapshot.task_key,
            capture_sha256=snapshot.capture_sha256,
            disposition=disposition,
            activation_boundary=activation_boundary,
            activation_state=activation_state,
            exclusion_set_sha256=exclusion_set_sha256,
            issue_state_at_admission=issue_state_at_admission,
            implementation_pr_numbers=tuple(implementation_pr_numbers),
            tracked_parent_issue_number=tracked_parent_issue_number,
            tracked_parent_created_at=tracked_parent_created_at,
            admitted_at=admitted_at,
            receipt_sha256=_sha256(_canonical_bytes(payload)),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_key": self.task_key,
            "capture_sha256": self.capture_sha256,
            "disposition": self.disposition,
            "activation_boundary": self.activation_boundary,
            "activation_state": self.activation_state,
            "exclusion_set_sha256": self.exclusion_set_sha256,
            "issue_state_at_admission": self.issue_state_at_admission,
            "implementation_pr_numbers": list(self.implementation_pr_numbers),
            "tracked_parent_issue_number": self.tracked_parent_issue_number,
            "tracked_parent_created_at": self.tracked_parent_created_at,
            "admitted_at": self.admitted_at,
            "receipt_sha256": self.receipt_sha256,
        }


def build_admission_comment(receipt: AdmissionReceipt) -> str:
    return (
        f"{ADMISSION_MARKER}\n"
        "Authority: `RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY`\n\n"
        "```json\n"
        + json.dumps(receipt.to_payload(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```"
    )


def parse_admission_comment(body: str) -> AdmissionReceipt:
    if ADMISSION_MARKER not in body:
        raise ValueError("admission_marker_missing")
    start = body.find("```json")
    start = body.find("\n", start)
    end = body.find("```", start + 1)
    if start < 0 or end < 0:
        raise ValueError("admission_json_block_malformed")
    payload = json.loads(body[start + 1 : end])
    supplied = str(payload.pop("receipt_sha256", ""))
    expected = _sha256(_canonical_bytes(payload))
    if supplied != expected:
        raise ValueError("admission_receipt_sha256_mismatch")
    if payload.get("schema") != "nexus.hybrid_replication.admission.v1":
        raise ValueError("admission_schema_mismatch")
    return AdmissionReceipt(
        task_key=str(payload["task_key"]),
        capture_sha256=str(payload["capture_sha256"]),
        disposition=str(payload["disposition"]),
        activation_boundary=str(payload["activation_boundary"]),
        activation_state=str(payload["activation_state"]),
        exclusion_set_sha256=str(payload["exclusion_set_sha256"]),
        issue_state_at_admission=str(payload["issue_state_at_admission"]),
        implementation_pr_numbers=tuple(
            int(item) for item in payload.get("implementation_pr_numbers", []) or []
        ),
        tracked_parent_issue_number=(
            None
            if payload.get("tracked_parent_issue_number") is None
            else int(payload["tracked_parent_issue_number"])
        ),
        tracked_parent_created_at=(
            None
            if payload.get("tracked_parent_created_at") is None
            else str(payload["tracked_parent_created_at"])
        ),
        admitted_at=str(payload["admitted_at"]),
        receipt_sha256=supplied,
    )


@dataclass(frozen=True)
class IssueAdmissionPolicy:
    prospective_boundary: str
    experiment_control_task: str
    candidate_repositories: tuple[str, ...]
    excluded_task_keys: tuple[str, ...] = ()
    campaign_task_keys: tuple[str, ...] = (
        "James3014/Nexus-new#1216",
        "James3014/Nexus-new#1196",
    )
    campaign_markers: tuple[str, ...] = (
        "#1216",
        "#1196",
        "NEXUS-HYBRID-REPLICATION",
        "hybrid replication",
        "hybrid-replication",
        "hybrid_replication",
    )


def _references_campaign(snapshot: TaskSnapshot, policy: IssueAdmissionPolicy) -> bool:
    if snapshot.task_key in set(policy.campaign_task_keys):
        return True
    text = f"{snapshot.title}\n{snapshot.body}".lower()
    return any(marker.lower() in text for marker in policy.campaign_markers)


def classify_opened_issue(
    snapshot: TaskSnapshot,
    policy: IssueAdmissionPolicy,
    *,
    issue_state_at_admission: str = "open",
    implementation_pr_numbers: tuple[int, ...] = (),
    tracked_parent_created_at: str | None = None,
) -> str:
    if snapshot.repository not in set(policy.candidate_repositories):
        return "UNTRACKED_WORK_ITEM_SCOPE_GAP"
    if snapshot.task_key == policy.experiment_control_task:
        return "EXPERIMENT_CONTROL_ISSUE"
    if snapshot.task_key in set(policy.excluded_task_keys):
        return "CONTAMINATION_EXCLUDED"
    if _references_campaign(snapshot, policy):
        return "CAMPAIGN_META_WORK_EXCLUDED"
    if snapshot.created_at < policy.prospective_boundary:
        return "EXCLUDED_PRE_BOUNDARY"
    if tracked_parent_created_at is not None:
        if tracked_parent_created_at < policy.prospective_boundary:
            return "EXCLUDE_PARENT_TASK_PRE_BOUNDARY"
        return "PARENT_TASK_SCOPE_GAP"
    referenced = {
        repo
        for repo in policy.candidate_repositories
        if repo != snapshot.repository and (repo in snapshot.title or repo in snapshot.body)
    }
    if referenced:
        return "CROSS_REPO_SCOPE_GAP"
    if issue_state_at_admission != "open":
        return "INTAKE_PROTOCOL_LOSS_TERMINAL_BEFORE_ADMISSION"
    if implementation_pr_numbers:
        return "INTAKE_PROTOCOL_LOSS_IMPLEMENTATION_PRESENT"
    return "ADMITTED_PRIMARY_FRESH_TASK"


def build_contract_delta_comment(
    *,
    snapshot: TaskSnapshot,
    edited_at: str,
    issue_updated_at: str,
    title: str,
    body: str,
    source_event_id: str,
) -> str:
    delta_payload = {
        "schema": "nexus.hybrid_replication.contract_delta.v1",
        "task_key": snapshot.task_key,
        "original_capture_sha256": snapshot.capture_sha256,
        "edited_at": edited_at,
        "issue_updated_at": issue_updated_at,
        "title": title,
        "body_gzip_base64": _encode_body(body),
        "source_event_id": source_event_id,
    }
    delta_payload["delta_sha256"] = _sha256(_canonical_bytes(delta_payload))
    return (
        f"{CONTRACT_DELTA_MARKER}\n"
        "Authority: `RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY`\n\n"
        "```json\n"
        + json.dumps(delta_payload, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```"
    )


def parse_contract_delta_comment(body: str) -> dict[str, Any]:
    if CONTRACT_DELTA_MARKER not in body:
        raise ValueError("contract_delta_marker_missing")
    start = body.find("```json")
    if start < 0:
        raise ValueError("contract_delta_json_block_missing")
    start = body.find("\n", start)
    end = body.find("```", start + 1)
    if start < 0 or end < 0:
        raise ValueError("contract_delta_json_block_malformed")
    payload = json.loads(body[start + 1 : end])
    supplied = str(payload.get("delta_sha256") or "")
    unsigned = dict(payload)
    unsigned.pop("delta_sha256", None)
    if supplied != _sha256(_canonical_bytes(unsigned)):
        raise ValueError("contract_delta_sha256_mismatch")
    payload["body"] = _decode_body(str(payload["body_gzip_base64"]))
    return payload


def _localization_score(
    raw_response: Any, ground_truth_details: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(raw_response, Mapping) or "candidate_packet" not in raw_response:
        return {
            "dm1_applicable": False,
            "accepted": False,
            "accepted_path": None,
            "accepted_path_in_changed_files": None,
            "d0_top8_hit_count": None,
            "packet_candidate_hit_count": None,
            "candidate_count": 0,
            "wrong_confident_dm1_accept": False,
            "legacy_raw": True,
        }
    packet = raw_response.get("candidate_packet") or {}
    candidates = [
        str(item.get("path")) for item in packet.get("candidate_catalog") or [] if item.get("path")
    ]
    # Frozen D0 top-8 as sealed in raw; the D2 packet prepends literal task paths
    # and truncates, so it is not a D0 measurement. Absent seal -> unknown.
    d0_top8 = raw_response.get("d0_top8_paths")
    changed = {str(path) for path in ground_truth_details.get("changed_files") or []}
    accepted = bool(raw_response.get("accepted_by_frozen_policy"))
    accepted_path = raw_response.get("localization_hint_path") if accepted else None
    accepted_path = str(accepted_path) if accepted_path else None
    in_changed = None if not changed or not accepted else accepted_path in changed
    return {
        "dm1_applicable": bool(raw_response.get("dm1_applicable")),
        "accepted": accepted,
        "accepted_path": accepted_path,
        "accepted_path_in_changed_files": in_changed,
        "d0_top8_hit_count": (
            len({str(path) for path in d0_top8[:8]} & changed)
            if changed and isinstance(d0_top8, list)
            else None
        ),
        "packet_candidate_hit_count": (len(set(candidates) & changed) if changed else None),
        "candidate_count": len(candidates),
        "wrong_confident_dm1_accept": bool(accepted and changed and accepted_path not in changed),
    }


def frozen_stack_outcome_from_payload(payload: Mapping[str, Any]) -> FrozenStackOutcome:
    raw_payload = dict(payload.get("raw_result") or {})
    raw_response = dict(raw_payload.pop("raw_response", {}) or {})
    supplied_output_sha = str(raw_payload.pop("output_sha256", "") or "")
    raw = RawRouteResult.create(raw_response=raw_response, **raw_payload)
    if supplied_output_sha and supplied_output_sha != raw.output_sha256:
        raise ValueError("external_stack_output_sha256_mismatch")
    outcome = FrozenStackOutcome(
        stratum=str(payload.get("stratum") or ""),
        deterministic_receipt=dict(payload.get("deterministic_receipt") or {}),
        candidate_packet=(
            None
            if payload.get("candidate_packet") is None
            else dict(payload.get("candidate_packet") or {})
        ),
        jev_raw_response=(
            None
            if payload.get("jev_raw_response") is None
            else dict(payload.get("jev_raw_response") or {})
        ),
        dm1_decision=(
            None if payload.get("dm1_decision") is None else dict(payload.get("dm1_decision") or {})
        ),
        strong_online_raw_response=(
            None
            if payload.get("strong_online_raw_response") is None
            else dict(payload.get("strong_online_raw_response") or {})
        ),
        raw_result=raw,
    )
    outcome.validate()
    return outcome


class ExternalFrozenStackRunner:
    def __init__(self, command: str) -> None:
        self.argv = tuple(shlex.split(command))
        if not self.argv:
            raise ValueError("stack_command_required")

    def __call__(self, snapshot: TaskSnapshot) -> FrozenStackOutcome:
        completed = subprocess.run(
            self.argv,
            input=json.dumps(snapshot.to_capture_payload(), ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"frozen_stack_command_failed:{completed.returncode}:{completed.stderr.strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("frozen_stack_command_invalid_json") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("frozen_stack_command_payload_must_be_object")
        return frozen_stack_outcome_from_payload(payload)


class ExternalGroundTruthResolver:
    def __init__(self, command: str) -> None:
        self.argv = tuple(shlex.split(command))
        if not self.argv:
            raise ValueError("ground_truth_command_required")

    def __call__(self, task_state: Mapping[str, Any]) -> GroundTruthEvidence | None:
        completed = subprocess.run(
            self.argv,
            input=json.dumps(task_state, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 3:
            return None
        if completed.returncode != 0:
            raise RuntimeError(
                f"ground_truth_command_failed:{completed.returncode}:{completed.stderr.strip()}"
            )
        payload = json.loads(completed.stdout)
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise ValueError("ground_truth_command_payload_must_be_object")
        return GroundTruthEvidence(
            terminal_state=str(payload.get("terminal_state") or ""),
            terminal_at=str(payload.get("terminal_at") or ""),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", []) or []),
            details=dict(payload.get("details") or {}),
        )


class AutomaticReplicationController:
    def __init__(
        self,
        *,
        store: "AutomaticReplicationStore",
        frozen_policy_sha256: str,
        stack_runner: Any,
        terminal_resolver: Any,
        clock: Any,
    ) -> None:
        if len(frozen_policy_sha256) != 64:
            raise ValueError("invalid_frozen_policy_sha256")
        self.store = store
        self.frozen_policy_sha256 = frozen_policy_sha256
        self.stack_runner = stack_runner
        self.terminal_resolver = terminal_resolver
        self.clock = clock

    def advance(self, task_key: str) -> dict[str, Any]:
        state = self.store.load_task(task_key)
        if state is None:
            raise ValueError("task_capture_missing")
        if state.get("admission_disposition") not in _EXECUTABLE_ADMISSION_DISPOSITIONS:
            return state
        if state.get("phase") == "SCORED":
            return self.store.score_task(task_key)
        if state.get("phase") == "ADMITTED":
            payload = dict(state["snapshot"])
            snapshot = TaskSnapshot.from_capture_payload(payload)
            outcome = self.stack_runner(snapshot)
            if not isinstance(outcome, FrozenStackOutcome):
                raise ValueError("stack_runner_must_return_frozen_stack_outcome")
            outcome.validate()
            route = RouteClassification(
                stratum=outcome.stratum,
                reason="frozen_incumbent_stack_typed_outcome",
                capture_sha256=snapshot.capture_sha256,
                frozen_policy_sha256=self.frozen_policy_sha256,
                decided_at=str(self.clock()),
            )
            self.store.freeze_route(task_key, route)
            self.store.seal_raw(task_key, outcome.raw_result)
            state = self.store.load_task(task_key)
        if state is None:
            raise ValueError("task_state_lost")
        if state.get("phase") == "RAW_SEALED":
            ground_truth = self.terminal_resolver(state)
            if ground_truth is not None:
                if not isinstance(ground_truth, GroundTruthEvidence):
                    raise ValueError("terminal_resolver_must_return_ground_truth_evidence")
                self.store.bind_ground_truth(task_key, ground_truth)
                state = self.store.load_task(task_key)
        if state is None:
            raise ValueError("task_state_lost")
        if state.get("phase") == "GROUND_TRUTH_BOUND":
            state = self.store.score_task(task_key)
        return state


class AutomaticReplicationStore:
    """Create-only task evidence store for the #1216 research projection.

    The store is deliberately not an engineering authority. Every task has one
    canonical state document plus create-only raw/ground-truth receipts. Derived
    ledgers can be rebuilt from these task directories without dual-writing a
    second source of truth.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.tasks_root = self.root / "tasks"
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def _dir(self, task_key: str) -> Path:
        return self.tasks_root / _task_dir_name(task_key)

    def _state_path(self, task_key: str) -> Path:
        return self._dir(task_key) / "state.json"

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any], *, create_only: bool = False) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _canonical_bytes(value) + b"\n"
        if create_only:
            with path.open("xb") as handle:
                handle.write(data)
        else:
            temp = path.with_suffix(path.suffix + ".tmp")
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
            temp.replace(path)
        return _sha256(data)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def load_task(self, task_key: str) -> dict[str, Any] | None:
        path = self._state_path(task_key)
        if not path.exists():
            return None
        return self._read_json(path)

    def load_sealed_raw(self, task_key: str) -> dict[str, Any]:
        state = self.load_task(task_key)
        if state is None:
            raise ValueError("capture_required_before_raw_read")
        seal = state.get("raw_seal")
        if not isinstance(seal, Mapping):
            raise ValueError("raw_seal_required_before_raw_read")
        raw_path = self._dir(task_key) / str(seal.get("path") or "")
        if not raw_path.is_file():
            raise ValueError("raw_seal_file_missing")
        raw_bytes = raw_path.read_bytes()
        if _sha256(raw_bytes) != seal.get("raw_sha256"):
            raise ValueError("raw_seal_hash_mismatch")
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict):
            raise ValueError("raw_payload_must_be_object")
        return raw

    def capture(self, snapshot: TaskSnapshot, *, admission_disposition: str) -> dict[str, Any]:
        if admission_disposition not in {
            PRIMARY_ADMISSION_DISPOSITION,
            READINESS_CONTROL_DISPOSITION,
            "EXPERIMENT_CONTROL_ISSUE",
            "EXCLUDED_PRE_BOUNDARY",
            "CROSS_REPO_SCOPE_GAP",
            "CONTAMINATION_EXCLUDED",
            "CAMPAIGN_META_WORK_EXCLUDED",
            "UNTRACKED_WORK_ITEM_SCOPE_GAP",
            "EXCLUDE_PARENT_TASK_PRE_BOUNDARY",
            "PARENT_TASK_SCOPE_GAP",
            "INTAKE_PROTOCOL_LOSS_TERMINAL_BEFORE_ADMISSION",
            "INTAKE_PROTOCOL_LOSS_IMPLEMENTATION_PRESENT",
            "PRE_AUTOMATION_PROVISIONAL_CAPTURE",
        }:
            raise ValueError("invalid_admission_disposition")
        task_key = snapshot.task_key
        existing = self.load_task(task_key)
        if existing is not None:
            if (
                existing.get("capture_sha256") == snapshot.capture_sha256
                and existing.get("admission_disposition") == admission_disposition
            ):
                return existing
            raise ValueError("capture_identity_conflict")
        if admission_disposition in _EXECUTABLE_ADMISSION_DISPOSITIONS:
            phase = "ADMITTED"
        elif admission_disposition == "PRE_AUTOMATION_PROVISIONAL_CAPTURE":
            phase = "CAPTURED_PROVISIONAL"
        else:
            phase = "CAPTURED_EXCLUDED"
        state = {
            "schema": "nexus.hybrid_replication.task_state.v1",
            "task_key": task_key,
            "phase": phase,
            "admission_disposition": admission_disposition,
            "capture_sha256": snapshot.capture_sha256,
            "contract_sha256": snapshot.contract_sha256,
            "snapshot": snapshot.to_capture_payload(),
            "route": None,
            "raw_seal": None,
            "ground_truth": None,
            "score": None,
        }
        self._write_json(self._state_path(task_key), state, create_only=True)
        return state

    def apply_admission(self, receipt: AdmissionReceipt) -> dict[str, Any]:
        state = self.load_task(receipt.task_key)
        if state is None:
            raise ValueError("capture_required_before_admission")
        if state.get("capture_sha256") != receipt.capture_sha256:
            raise ValueError("admission_capture_identity_mismatch")
        existing_sha = state.get("admission_receipt_sha256")
        if existing_sha:
            if existing_sha == receipt.receipt_sha256:
                return state
            raise ValueError("admission_identity_conflict")
        if state.get("phase") not in {"CAPTURED_PROVISIONAL", "CAPTURED_EXCLUDED"}:
            raise ValueError("invalid_phase_for_admission")
        state["admission_disposition"] = receipt.disposition
        state["admission_receipt_sha256"] = receipt.receipt_sha256
        state["activation_boundary"] = receipt.activation_boundary
        state["admitted_at"] = receipt.admitted_at
        state["phase"] = (
            "ADMITTED"
            if receipt.disposition in _EXECUTABLE_ADMISSION_DISPOSITIONS
            else "CAPTURED_EXCLUDED"
        )
        self._write_json(self._state_path(receipt.task_key), state)
        return state

    def freeze_route(self, task_key: str, route: RouteClassification) -> dict[str, Any]:
        state = self.load_task(task_key)
        if state is None:
            raise ValueError("capture_required_before_route")
        if state.get("admission_disposition") not in _EXECUTABLE_ADMISSION_DISPOSITIONS:
            raise ValueError("only_executable_admitted_tasks_may_route")
        if state.get("capture_sha256") != route.capture_sha256:
            raise ValueError("route_capture_identity_mismatch")
        existing = state.get("route")
        payload = asdict(route)
        if existing is not None:
            if existing == payload:
                return state
            raise ValueError("route_already_frozen")
        if state.get("phase") != "ADMITTED":
            raise ValueError("invalid_phase_for_route_freeze")
        state["route"] = payload
        state["phase"] = "ROUTE_FROZEN"
        self._write_json(self._state_path(task_key), state)
        return state

    def seal_raw(self, task_key: str, raw: RawRouteResult) -> dict[str, Any]:
        state = self.load_task(task_key)
        if state is None or state.get("route") is None:
            raise ValueError("route_freeze_required_before_raw_seal")
        if state.get("phase") != "ROUTE_FROZEN":
            if state.get("raw_seal") is not None:
                raise FileExistsError("raw_seal_already_exists")
            raise ValueError("invalid_phase_for_raw_seal")
        if state["route"].get("stratum") != raw.route:
            raise ValueError("raw_route_mismatch")
        raw_payload = asdict(raw)
        raw_path = self._dir(task_key) / "raw.json"
        raw_sha = self._write_json(raw_path, raw_payload, create_only=True)
        seal = {
            "schema": "nexus.hybrid_replication.raw_seal.v1",
            "raw_sha256": raw_sha,
            "path": "raw.json",
        }
        self._write_json(self._dir(task_key) / "raw_seal.json", seal, create_only=True)
        state["raw_seal"] = seal
        state["phase"] = "RAW_SEALED"
        self._write_json(self._state_path(task_key), state)
        return seal

    def bind_ground_truth(self, task_key: str, evidence: GroundTruthEvidence) -> dict[str, Any]:
        state = self.load_task(task_key)
        if state is None:
            raise ValueError("capture_required_before_ground_truth")
        if state.get("raw_seal") is None or state.get("phase") != "RAW_SEALED":
            raise ValueError("raw_seal_required_before_ground_truth")
        raw_path = self._dir(task_key) / str(state["raw_seal"]["path"])
        actual_raw_sha = _sha256(raw_path.read_bytes())
        if actual_raw_sha != state["raw_seal"].get("raw_sha256"):
            raise ValueError("raw_seal_hash_mismatch")
        payload = asdict(evidence)
        gt_sha = self._write_json(
            self._dir(task_key) / "ground_truth.json", payload, create_only=True
        )
        state["ground_truth"] = {"sha256": gt_sha, **payload}
        state["phase"] = "GROUND_TRUTH_BOUND"
        self._write_json(self._state_path(task_key), state)
        return state

    def score_task(self, task_key: str) -> dict[str, Any]:
        state = self.load_task(task_key)
        if state is None:
            raise ValueError("capture_required_before_score")
        if state.get("phase") == "SCORED":
            score = state.get("score") or {}
            score_path = self._dir(task_key) / str(score.get("path") or "score.json")
            if not score_path.is_file():
                raise ValueError("score_receipt_missing")
            actual_sha = _sha256(score_path.read_bytes())
            if actual_sha != score.get("sha256"):
                raise ValueError("score_receipt_hash_mismatch")
            return state
        if state.get("phase") != "GROUND_TRUTH_BOUND" or state.get("ground_truth") is None:
            raise ValueError("ground_truth_required_before_score")
        if state.get("raw_seal") is None or state.get("route") is None:
            raise ValueError("raw_route_required_before_score")

        raw_path = self._dir(task_key) / str(state["raw_seal"]["path"])
        raw_bytes = raw_path.read_bytes()
        if _sha256(raw_bytes) != state["raw_seal"].get("raw_sha256"):
            raise ValueError("raw_seal_hash_mismatch")
        raw = json.loads(raw_bytes)
        ground_truth = dict(state["ground_truth"])
        ground_truth_path = self._dir(task_key) / "ground_truth.json"
        ground_truth_bytes = ground_truth_path.read_bytes()
        if _sha256(ground_truth_bytes) != ground_truth.get("sha256"):
            raise ValueError("ground_truth_hash_mismatch")
        localization = _localization_score(
            raw.get("raw_response"),
            ground_truth.get("details") or {},
        )
        score_payload = {
            "schema": "nexus.hybrid_replication.task_score.v1",
            "task_key": task_key,
            "capture_sha256": state["capture_sha256"],
            "route": state["route"]["stratum"],
            "raw_sha256": state["raw_seal"]["raw_sha256"],
            "ground_truth_sha256": ground_truth["sha256"],
            "terminal_state": ground_truth["terminal_state"],
            "terminal_at": ground_truth["terminal_at"],
            "evidence_refs": list(ground_truth.get("evidence_refs") or []),
            "quality": {
                "terminal_state": ground_truth["terminal_state"],
                "evidence_refs": list(ground_truth.get("evidence_refs") or []),
                "details": dict(ground_truth.get("details") or {}),
            },
            "localization": localization,
            "economics": {
                "provider": raw.get("provider"),
                "requested_model": raw.get("requested_model"),
                "resolved_model": raw.get("resolved_model"),
                "model_call_count": raw.get("model_call_count"),
                "input_tokens": raw.get("input_tokens"),
                "uncached_input_tokens": raw.get("uncached_input_tokens"),
                "output_tokens": raw.get("output_tokens"),
                "wall_time_seconds": raw.get("wall_time_seconds"),
                "failures": list(raw.get("failures") or []),
                "retries": raw.get("retries"),
                "fallbacks": list(raw.get("fallbacks") or []),
            },
        }
        score_path = self._dir(task_key) / "score.json"
        expected_score_bytes = _canonical_bytes(score_payload) + b"\n"
        expected_score_sha = _sha256(expected_score_bytes)
        if score_path.exists():
            if score_path.read_bytes() != expected_score_bytes:
                raise ValueError("score_receipt_conflict")
            score_sha = expected_score_sha
        else:
            score_sha = self._write_json(score_path, score_payload, create_only=True)
        state["score"] = {
            "schema": score_payload["schema"],
            "sha256": score_sha,
            "path": "score.json",
            "terminal_state": score_payload["terminal_state"],
            "route": score_payload["route"],
        }
        state["phase"] = "SCORED"
        self._write_json(self._state_path(task_key), state)
        return state

    def reconcile_expected_work_items(self, expected: list[tuple[str, int]]) -> dict[str, Any]:
        missing = [
            _task_key(repo, issue)
            for repo, issue in expected
            if self.load_task(_task_key(repo, issue)) is None
        ]
        return {
            "schema": "nexus.hybrid_replication.intake_reconciliation.v1",
            "status": "INTAKE_GAP" if missing else "COMPLETE",
            "missing": sorted(missing),
            "backfilled": [],
        }
