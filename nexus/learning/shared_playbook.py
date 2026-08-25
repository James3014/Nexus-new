from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SHARED_PLAYBOOK_SCHEMA = "nexus.shared_playbook.v1"
PLAYBOOK_TRACE_SCHEMA = "nexus.playbook_trace.v1"
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SHARED_PLAYBOOK_IDS = frozenset({"diagnose"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_ALLOWED_STATUSES = frozenset({"CANDIDATE", "ACTIVE"})
_REQUIRED_AUTHORITY_FLAGS = frozenset(
    {
        "route_selection",
        "model_selection",
        "worker_selection",
        "approval",
        "integration",
        "merge",
        "promotion",
        "task_receipt",
        "claim_authority",
        "self_modify",
        "permission_expand",
    }
)
_INHERIT_ONLY_PERMISSION_KEYS = ("filesystem", "network", "tools")
_PLAYBOOK_RECEIPT_KEYS = frozenset(
    {
        "playbook_id",
        "playbook_version",
        "playbook_manifest_sha256",
        "playbook_instructions_sha256",
        "playbook_gate_passed",
        "playbook_violation",
        "playbook_trace",
        "shared_playbook",
    }
)


class SharedPlaybookError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SharedPlaybookIdentity:
    playbook_id: str
    version: str
    status: str
    manifest_sha256: str
    instructions_sha256: str
    manifest_path: str
    instructions_path: str
    primary: bool
    trace_authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "version": self.version,
            "status": self.status,
            "manifest_sha256": self.manifest_sha256,
            "instructions_sha256": self.instructions_sha256,
            "manifest_path": self.manifest_path,
            "instructions_path": self.instructions_path,
            "primary": self.primary,
            "trace_authority": self.trace_authority,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repo_root(root: str | Path | None) -> Path:
    return Path(root).resolve() if root is not None else DEFAULT_REPO_ROOT.resolve()


def _skill_paths(skill_id: str, *, root: str | Path | None = None) -> tuple[Path, Path, Path]:
    if not _SAFE_ID.fullmatch(skill_id):
        raise SharedPlaybookError("shared_playbook_invalid_skill_id")
    repo_root = _repo_root(root)
    skill_dir = repo_root / ".agents" / "skills" / skill_id
    return repo_root, skill_dir / "playbook.yaml", skill_dir / "SKILL.md"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise SharedPlaybookError("shared_playbook_path_escape") from exc


def _mapping(value: Any, *, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SharedPlaybookError(reason)
    return value


def _string_list(value: Any, *, reason: str) -> list[str]:
    if not isinstance(value, list):
        raise SharedPlaybookError(reason)
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise SharedPlaybookError(reason)
    return result


def _validate_authority(payload: dict[str, Any]) -> None:
    authority = _mapping(payload.get("authority"), reason="shared_playbook_authority_contract_missing")
    if not _REQUIRED_AUTHORITY_FLAGS.issubset(authority):
        raise SharedPlaybookError("shared_playbook_authority_contract_incomplete")
    if any(bool(value) for value in authority.values()):
        raise SharedPlaybookError("shared_playbook_authority_escalation")
    if payload.get("auto_chain") is not False:
        raise SharedPlaybookError("shared_playbook_auto_chain_forbidden")
    if str(payload.get("trace_authority") or "") != "DERIVED_ONLY":
        raise SharedPlaybookError("shared_playbook_trace_authority_invalid")


def _validate_permissions(payload: dict[str, Any]) -> None:
    permissions = _mapping(payload.get("permissions"), reason="shared_playbook_permissions_missing")
    for key in _INHERIT_ONLY_PERMISSION_KEYS:
        if str(permissions.get(key) or "") != "INHERIT_ONLY":
            raise SharedPlaybookError("shared_playbook_permission_expansion")


def _validate_learning_writeback(payload: dict[str, Any]) -> None:
    writeback = _mapping(payload.get("learning_writeback"), reason="shared_playbook_learning_writeback_missing")
    if str(writeback.get("mode") or "") != "CANDIDATE_ONLY" or writeback.get("self_modify") is not False:
        raise SharedPlaybookError("shared_playbook_self_modify_forbidden")


def _validate_transitions(payload: dict[str, Any]) -> None:
    stages = payload.get("stages")
    if not isinstance(stages, list) or not stages:
        raise SharedPlaybookError("shared_playbook_stages_missing")
    stage_ids: list[str] = []
    for stage in stages:
        item = _mapping(stage, reason="shared_playbook_stage_invalid")
        stage_id = str(item.get("id") or "").strip()
        exit_evidence = _string_list(item.get("exit_evidence"), reason="shared_playbook_stage_exit_evidence_invalid")
        if not stage_id or not exit_evidence:
            raise SharedPlaybookError("shared_playbook_stage_invalid")
        stage_ids.append(stage_id)
    if len(stage_ids) != len(set(stage_ids)):
        raise SharedPlaybookError("shared_playbook_duplicate_stage")

    local_contract = _mapping(
        payload.get("local_transition_contract"),
        reason="shared_playbook_local_transition_contract_missing",
    )
    required_local_guards = ("same_task", "same_scope", "same_capability", "same_permissions", "same_authority")
    if any(local_contract.get(key) is not True for key in required_local_guards):
        raise SharedPlaybookError("shared_playbook_local_transition_boundary_invalid")

    transitions = payload.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise SharedPlaybookError("shared_playbook_transitions_missing")
    stage_set = set(stage_ids)
    for transition in transitions:
        item = _mapping(transition, reason="shared_playbook_transition_invalid")
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not source or not target or source not in stage_set:
            raise SharedPlaybookError("shared_playbook_transition_invalid")
        if kind == "LOCAL_TRANSITION":
            if target not in stage_set:
                raise SharedPlaybookError("shared_playbook_cross_boundary_requires_handoff")
        elif kind == "HANDOFF_REQUEST":
            continue
        else:
            raise SharedPlaybookError("shared_playbook_transition_kind_invalid")


def _validate_payload(payload: dict[str, Any], *, skill_id: str, capability_mount: str) -> None:
    if str(payload.get("schema") or "") != SHARED_PLAYBOOK_SCHEMA:
        raise SharedPlaybookError("shared_playbook_schema_invalid")
    if str(payload.get("playbook_id") or "") != skill_id or str(payload.get("skill_id") or "") != skill_id:
        raise SharedPlaybookError("shared_playbook_identity_mismatch")
    version = str(payload.get("version") or "").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SharedPlaybookError("shared_playbook_version_invalid")
    if str(payload.get("status") or "") not in _ALLOWED_STATUSES:
        raise SharedPlaybookError("shared_playbook_status_invalid")
    if not isinstance(payload.get("primary"), bool):
        raise SharedPlaybookError("shared_playbook_primary_invalid")
    capabilities = set(
        _string_list(payload.get("capability_mounts"), reason="shared_playbook_capability_mounts_invalid")
    )
    if capability_mount not in capabilities:
        raise SharedPlaybookError("shared_playbook_capability_mismatch")
    stop_conditions = _string_list(payload.get("stop_conditions"), reason="shared_playbook_stop_conditions_invalid")
    if not stop_conditions:
        raise SharedPlaybookError("shared_playbook_stop_conditions_invalid")
    _validate_authority(payload)
    _validate_permissions(payload)
    _validate_learning_writeback(payload)
    _validate_transitions(payload)


def load_selected_shared_playbook(
    skill_id: str,
    capability_mount: str,
    *,
    root: str | Path | None = None,
    required: bool | None = None,
) -> SharedPlaybookIdentity | None:
    repo_root, manifest_path, instructions_path = _skill_paths(skill_id, root=root)
    is_required = skill_id in REQUIRED_SHARED_PLAYBOOK_IDS if required is None else bool(required)
    if not manifest_path.is_file():
        if is_required:
            raise SharedPlaybookError("shared_playbook_missing")
        return None
    if not instructions_path.is_file():
        raise SharedPlaybookError("shared_playbook_instructions_missing")

    manifest_bytes = manifest_path.read_bytes()
    instructions_bytes = instructions_path.read_bytes()
    try:
        payload = yaml.safe_load(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SharedPlaybookError("shared_playbook_manifest_invalid") from exc
    payload = _mapping(payload, reason="shared_playbook_manifest_invalid")
    _validate_payload(payload, skill_id=skill_id, capability_mount=capability_mount)

    return SharedPlaybookIdentity(
        playbook_id=skill_id,
        version=str(payload["version"]),
        status=str(payload["status"]),
        manifest_sha256=_sha256(manifest_bytes),
        instructions_sha256=_sha256(instructions_bytes),
        manifest_path=_relative_path(manifest_path, repo_root),
        instructions_path=_relative_path(instructions_path, repo_root),
        primary=bool(payload["primary"]),
        trace_authority=str(payload["trace_authority"]),
    )


def verify_planned_shared_playbook(
    planned: dict[str, Any],
    *,
    skill_id: str,
    capability_mount: str,
    root: str | Path | None = None,
) -> SharedPlaybookIdentity:
    identity = load_selected_shared_playbook(skill_id, capability_mount, root=root, required=True)
    if identity is None:
        raise SharedPlaybookError("shared_playbook_missing")
    expected = {
        "playbook_id": identity.playbook_id,
        "version": identity.version,
        "manifest_sha256": identity.manifest_sha256,
        "instructions_sha256": identity.instructions_sha256,
        "primary": identity.primary,
        "trace_authority": identity.trace_authority,
    }
    observed = {key: planned.get(key) for key in expected}
    if observed != expected:
        raise SharedPlaybookError("shared_playbook_runtime_identity_mismatch")
    return identity


def _sanitize_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in receipt.items() if key not in _PLAYBOOK_RECEIPT_KEYS}
    if isinstance(clean.get("evidence_refs"), list):
        clean["evidence_refs"] = list(clean["evidence_refs"])
    return clean


def _target_receipts(
    receipts: list[dict[str, Any]],
    *,
    capability_mount: str,
    capability: str,
) -> list[dict[str, Any]]:
    names = {name for name in (capability_mount, capability) if name}
    return [receipt for receipt in receipts if str(receipt.get("name") or "").strip() in names]


def _invalidate_receipts(receipts: list[dict[str, Any]], reason: str) -> None:
    for receipt in receipts:
        receipt["public_claim_safe"] = False
        receipt["gate_passed"] = False
        receipt["outcome_contributed"] = False
        receipt["playbook_gate_passed"] = False
        receipt["playbook_violation"] = reason


def bind_shared_playbook_runtime_receipts(
    *,
    capability_plan_payload: dict[str, Any],
    receipts: list[dict[str, Any]],
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    bound_receipts = [_sanitize_receipt(receipt) for receipt in receipts if isinstance(receipt, dict)]
    snapshot = (
        capability_plan_payload.get("signal_snapshot", {})
        if isinstance(capability_plan_payload.get("signal_snapshot"), dict)
        else {}
    )
    planned_mounts = [
        item
        for item in (snapshot.get("planned_skill_mount_contracts", []) or [])
        if isinstance(item, dict)
        and isinstance(item.get("shared_playbook"), dict)
        and bool(item.get("planner_selected_capability"))
    ]
    primary_mounts = [item for item in planned_mounts if bool(item["shared_playbook"].get("primary"))]
    if len(primary_mounts) > 1:
        for planned in primary_mounts:
            targets = _target_receipts(
                bound_receipts,
                capability_mount=str(planned.get("capability_mount") or "").strip(),
                capability=str(planned.get("capability") or "").strip(),
            )
            _invalidate_receipts(targets, "shared_playbook_second_primary")
        return bound_receipts

    for planned in planned_mounts:
        skill_id = str(planned.get("skill_id") or "").strip()
        capability_mount = str(planned.get("capability_mount") or planned.get("capability") or "").strip()
        targets = _target_receipts(
            bound_receipts,
            capability_mount=capability_mount,
            capability=str(planned.get("capability") or "").strip(),
        )
        try:
            identity = verify_planned_shared_playbook(
                planned["shared_playbook"],
                skill_id=skill_id,
                capability_mount=capability_mount,
                root=root,
            )
        except SharedPlaybookError as exc:
            _invalidate_receipts(targets, exc.reason)
            continue
        for receipt in targets:
            evidence_refs = [str(ref) for ref in (receipt.get("evidence_refs", []) or []) if str(ref).strip()]
            evidence_refs.append(
                "shared_playbook:"
                f"{identity.playbook_id}@{identity.version}:"
                f"manifest={identity.manifest_sha256}:instructions={identity.instructions_sha256}"
            )
            receipt.update(
                {
                    "playbook_id": identity.playbook_id,
                    "playbook_version": identity.version,
                    "playbook_manifest_sha256": identity.manifest_sha256,
                    "playbook_instructions_sha256": identity.instructions_sha256,
                    "playbook_gate_passed": True,
                    "playbook_trace": {
                        "schema": PLAYBOOK_TRACE_SCHEMA,
                        "authority": "DERIVED_ONLY",
                        "selected_by": "CapabilityPlanner",
                        "playbook_id": identity.playbook_id,
                        "version": identity.version,
                    },
                    "evidence_refs": list(dict.fromkeys(evidence_refs)),
                }
            )
    return bound_receipts
