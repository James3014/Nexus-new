"""Durable one-shot consumer for Owner break-glass recovery authority.

The store is intentionally outside the normal standing-grant/Gateway/lifecycle
plane. It records evidence transitions only; it never edits repository source,
runs arbitrary commands, merges, reloads runtime, releases, or issues authority.
"""

from __future__ import annotations

import json
import os
import pwd
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from nexus.contracts.break_glass_recovery import (
    BreakGlassActivationPayload,
    BreakGlassAppliedEvidence,
    BreakGlassGovernanceCanaryEvidence,
    BreakGlassOwnerIntegrationPayload,
    BreakGlassPhase,
    BreakGlassVerificationEvidence,
    OwnerActivationEnvelope,
    OwnerCanaryEnvelope,
    OwnerIntegrationEnvelope,
    OwnerTerminalEnvelope,
    OwnerVerificationEnvelope,
    canonical_json_bytes,
    canonical_sha256,
)

_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
DEFAULT_BREAK_GLASS_ROOT = _HOME / ".local/state/nexus/authority/break-glass"
_MAX_TRANSITION_BYTES = 64 * 1024
_PHASE_FILE = {
    BreakGlassPhase.PREPARED: "01-prepared.json",
    BreakGlassPhase.APPLIED: "02-applied.json",
    BreakGlassPhase.VERIFIED: "03-verified.json",
    BreakGlassPhase.CONSUMED: "04-consumed.json",
}
_PHASE_ORDER = tuple(_PHASE_FILE)
_INTEGRATION_PREPARED_FILE = "01-integration-prepared.json"
_INTEGRATION_CONSUMED_FILE = "02-integration-consumed.json"


class BreakGlassRecoveryError(Exception):
    """Fail-closed recovery-consumer error."""


def _attempt_dir(
    activation: BreakGlassActivationPayload, *, state_root: Path | None = None
) -> Path:
    root = state_root or DEFAULT_BREAK_GLASS_ROOT
    return root / activation.recovery_id / activation.attempt_id


def _ensure_safe_dir(path: Path, *, create: bool) -> None:
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = path
    while True:
        try:
            st = current.lstat()
        except OSError as exc:
            raise BreakGlassRecoveryError("STATE_DIRECTORY_UNSAFE") from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise BreakGlassRecoveryError("STATE_DIRECTORY_UNSAFE")
        if current == path:
            if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
                try:
                    os.chmod(current, 0o700)
                    st = current.lstat()
                except OSError as exc:
                    raise BreakGlassRecoveryError("STATE_DIRECTORY_UNSAFE") from exc
                if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
                    raise BreakGlassRecoveryError("STATE_DIRECTORY_UNSAFE")
        if current == current.parent:
            break
        current = current.parent


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        st = path.lstat()
    except OSError as exc:
        raise BreakGlassRecoveryError("STATE_READ_FAILED") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise BreakGlassRecoveryError("STATE_FILE_UNSAFE")
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
        raise BreakGlassRecoveryError("STATE_FILE_UNSAFE")
    if st.st_size > _MAX_TRANSITION_BYTES:
        raise BreakGlassRecoveryError("STATE_FILE_TOO_LARGE")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BreakGlassRecoveryError("STATE_MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise BreakGlassRecoveryError("STATE_MALFORMED")
    claimed = parsed.get("transition_hash")
    body = {key: value for key, value in parsed.items() if key != "transition_hash"}
    if not isinstance(claimed, str) or claimed != canonical_sha256(body):
        raise BreakGlassRecoveryError("STATE_HASH_INVALID")
    return parsed


def _atomic_create(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    canonical = {
        **body,
        "transition_hash": canonical_sha256(body),
    }
    encoded = canonical_json_bytes(canonical) + b"\n"
    if len(encoded) > _MAX_TRANSITION_BYTES:
        raise BreakGlassRecoveryError("STATE_FILE_TOO_LARGE")

    if path.exists() or path.is_symlink():
        existing = _load_json_file(path)
        if canonical_json_bytes(existing) == canonical_json_bytes(canonical):
            return existing
        raise BreakGlassRecoveryError("TRANSITION_CONFLICT")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = _load_json_file(path)
        if canonical_json_bytes(existing) == canonical_json_bytes(canonical):
            return existing
        raise BreakGlassRecoveryError("TRANSITION_CONFLICT")
    except OSError as exc:
        raise BreakGlassRecoveryError("STATE_WRITE_FAILED") from exc
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # The immutable transition exists and is fsynced; an unavailable
        # directory fsync lowers durability but must not trigger a duplicate
        # replacement write. Reconciliation reads the exact file on retry.
        pass
    return _load_json_file(path)


def _envelope_hash(envelope: OwnerActivationEnvelope) -> str:
    return canonical_sha256(envelope.model_dump(mode="json"))


def _base_transition(
    *,
    envelope: OwnerActivationEnvelope,
    phase: BreakGlassPhase,
    predecessor_hash: str | None,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "nexus.break_glass_transition.v1",
        "repository": envelope.repository,
        "issue": envelope.issue,
        "comment_id": envelope.comment_id,
        "activation_envelope_sha256": _envelope_hash(envelope),
        "activation_payload_sha256": envelope.payload_sha256,
        "recovery_id": envelope.payload.recovery_id,
        "attempt_id": envelope.payload.attempt_id,
        "effect_class": envelope.payload.effect_class.value,
        "phase": phase.value,
        "predecessor_hash": predecessor_hash,
        "evidence": dict(evidence),
    }


def _read_chain(
    activation: BreakGlassActivationPayload, *, state_root: Path | None = None
) -> list[dict[str, Any]]:
    attempt_dir = _attempt_dir(activation, state_root=state_root)
    if not attempt_dir.exists():
        return []
    _ensure_safe_dir(attempt_dir, create=False)
    chain: list[dict[str, Any]] = []
    predecessor: str | None = None
    gap_seen = False
    for phase in _PHASE_ORDER:
        path = attempt_dir / _PHASE_FILE[phase]
        if not path.exists() and not path.is_symlink():
            gap_seen = True
            continue
        if gap_seen:
            raise BreakGlassRecoveryError("TRANSITION_ORDER_INVALID")
        record = _load_json_file(path)
        if record.get("phase") != phase.value:
            raise BreakGlassRecoveryError("TRANSITION_PHASE_INVALID")
        if (
            record.get("recovery_id") != activation.recovery_id
            or record.get("attempt_id") != activation.attempt_id
        ):
            raise BreakGlassRecoveryError("ATTEMPT_IDENTITY_MISMATCH")
        if record.get("effect_class") != activation.effect_class.value:
            raise BreakGlassRecoveryError("EFFECT_CLASS_MISMATCH")
        if record.get("predecessor_hash") != predecessor:
            raise BreakGlassRecoveryError("TRANSITION_CHAIN_INVALID")
        predecessor = str(record["transition_hash"])
        chain.append(record)
    return chain


def inspect_attempt(
    activation: BreakGlassActivationPayload, *, state_root: Path | None = None
) -> dict[str, Any]:
    chain = _read_chain(activation, state_root=state_root)
    if not chain:
        return {
            "schema": "nexus.break_glass_inspection.v1",
            "status": "MISSING",
            "recovery_id": activation.recovery_id,
            "attempt_id": activation.attempt_id,
        }
    latest = chain[-1]
    return {
        "schema": "nexus.break_glass_inspection.v1",
        "status": latest["phase"],
        "recovery_id": activation.recovery_id,
        "attempt_id": activation.attempt_id,
        "latest_transition_hash": latest["transition_hash"],
        "transition_count": len(chain),
        "latest": latest,
    }


def _assert_envelope_matches_existing(
    envelope: OwnerActivationEnvelope, chain: list[dict[str, Any]]
) -> None:
    expected = _envelope_hash(envelope)
    for record in chain:
        if record.get("activation_envelope_sha256") != expected:
            raise BreakGlassRecoveryError("ACTIVATION_ENVELOPE_MISMATCH")
        if record.get("activation_payload_sha256") != envelope.payload_sha256:
            raise BreakGlassRecoveryError("ACTIVATION_PAYLOAD_MISMATCH")
        if record.get("comment_id") != envelope.comment_id:
            raise BreakGlassRecoveryError("OWNER_COMMENT_MISMATCH")


def prepare_source_repair(
    envelope: OwnerActivationEnvelope,
    *,
    observed_base_sha: str,
    observed_base_tree: str,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
    if observed_base_sha != activation.base_sha or observed_base_tree != activation.base_tree:
        raise BreakGlassRecoveryError("BASE_IDENTITY_MISMATCH")
    chain = _read_chain(activation, state_root=state_root)
    if chain:
        _assert_envelope_matches_existing(envelope, chain)
        if chain[-1]["phase"] == BreakGlassPhase.CONSUMED.value:
            raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")
        if chain[0]["phase"] == BreakGlassPhase.PREPARED.value:
            return chain[0]
        raise BreakGlassRecoveryError("TRANSITION_ORDER_INVALID")

    attempt_dir = _attempt_dir(activation, state_root=state_root)
    _ensure_safe_dir(attempt_dir, create=True)
    payload = _base_transition(
        envelope=envelope,
        phase=BreakGlassPhase.PREPARED,
        predecessor_hash=None,
        evidence={
            "observed_base_sha": observed_base_sha,
            "observed_base_tree": observed_base_tree,
            "allowed_paths": list(activation.allowed_paths),
            "forbidden_paths": list(activation.forbidden_paths),
            "failure_evidence_sha256": activation.failure_evidence_sha256,
            "claim_ceiling": activation.claim_ceiling,
        },
    )
    return _atomic_create(attempt_dir / _PHASE_FILE[BreakGlassPhase.PREPARED], payload)


def record_source_repair_applied(
    envelope: OwnerActivationEnvelope,
    applied: BreakGlassAppliedEvidence,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
    activation.assert_paths_authorized(applied.changed_paths)
    chain = _read_chain(activation, state_root=state_root)
    if not chain:
        raise BreakGlassRecoveryError("PREPARE_REQUIRED")
    _assert_envelope_matches_existing(envelope, chain)
    latest = chain[-1]
    if latest["phase"] == BreakGlassPhase.CONSUMED.value:
        raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")
    if latest["phase"] in {
        BreakGlassPhase.APPLIED.value,
        BreakGlassPhase.VERIFIED.value,
    }:
        applied_record = chain[1]
        if applied_record["evidence"].get("applied_evidence_sha256") == applied.evidence_sha256:
            return applied_record
        raise BreakGlassRecoveryError("APPLIED_EVIDENCE_CONFLICT")
    if latest["phase"] != BreakGlassPhase.PREPARED.value:
        raise BreakGlassRecoveryError("TRANSITION_ORDER_INVALID")
    attempt_dir = _attempt_dir(activation, state_root=state_root)
    payload = _base_transition(
        envelope=envelope,
        phase=BreakGlassPhase.APPLIED,
        predecessor_hash=str(latest["transition_hash"]),
        evidence={
            "applied_evidence_sha256": applied.evidence_sha256,
            "applied": applied.model_dump(mode="json"),
        },
    )
    return _atomic_create(attempt_dir / _PHASE_FILE[BreakGlassPhase.APPLIED], payload)


def record_source_repair_verified(
    envelope: OwnerActivationEnvelope,
    verification_envelope: OwnerVerificationEnvelope,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
    verification_envelope.payload.assert_current(now=now)
    verified = verification_envelope.payload
    if (
        verified.recovery_id != activation.recovery_id
        or verified.source_attempt_id != activation.attempt_id
        or verified.source_activation_payload_sha256 != envelope.payload_sha256
    ):
        raise BreakGlassRecoveryError("VERIFICATION_AUTHORITY_MISMATCH")
    chain = _read_chain(activation, state_root=state_root)
    if len(chain) < 2:
        raise BreakGlassRecoveryError("APPLIED_EVIDENCE_REQUIRED")
    _assert_envelope_matches_existing(envelope, chain)
    latest = chain[-1]
    if latest["phase"] == BreakGlassPhase.CONSUMED.value:
        raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")
    applied = BreakGlassAppliedEvidence.model_validate(chain[1]["evidence"]["applied"])
    if verified.verifier_id == applied.implementer_id:
        raise BreakGlassRecoveryError("INDEPENDENT_VERIFIER_REQUIRED")
    if (
        verified.verified_commit_sha != applied.repair_commit_sha
        or verified.verified_tree_sha != applied.repair_tree_sha
        or verified.verified_diff_sha256 != applied.full_diff_sha256
    ):
        raise BreakGlassRecoveryError("VERIFICATION_SUBJECT_MISMATCH")
    verification = BreakGlassVerificationEvidence(
        verifier_id=verified.verifier_id,
        verifier_evidence_sha256=verification_envelope.payload_sha256,
        verified_commit_sha=verified.verified_commit_sha,
        verified_tree_sha=verified.verified_tree_sha,
        verified_diff_sha256=verified.verified_diff_sha256,
    )
    if latest["phase"] == BreakGlassPhase.VERIFIED.value:
        if latest["evidence"].get("owner_verification_payload_sha256") == (
            verification_envelope.payload_sha256
        ):
            return latest
        raise BreakGlassRecoveryError("VERIFICATION_EVIDENCE_CONFLICT")
    if latest["phase"] != BreakGlassPhase.APPLIED.value:
        raise BreakGlassRecoveryError("TRANSITION_ORDER_INVALID")
    attempt_dir = _attempt_dir(activation, state_root=state_root)
    payload = _base_transition(
        envelope=envelope,
        phase=BreakGlassPhase.VERIFIED,
        predecessor_hash=str(latest["transition_hash"]),
        evidence={
            "owner_verification_comment_id": verification_envelope.comment_id,
            "owner_verification_payload_sha256": verification_envelope.payload_sha256,
            "verification_evidence_sha256": verification.evidence_sha256,
            "verification": verification.model_dump(mode="json"),
            "checks": [item.model_dump(mode="json") for item in verified.checks],
        },
    )
    return _atomic_create(attempt_dir / _PHASE_FILE[BreakGlassPhase.VERIFIED], payload)


def consume_source_repair_authority(
    envelope: OwnerActivationEnvelope,
    canary_envelope: OwnerCanaryEnvelope,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
    owner_canary = canary_envelope.payload
    if (
        owner_canary.recovery_id != activation.recovery_id
        or owner_canary.source_attempt_id != activation.attempt_id
        or owner_canary.source_activation_payload_sha256 != envelope.payload_sha256
    ):
        raise BreakGlassRecoveryError("GOVERNANCE_CANARY_AUTHORITY_MISMATCH")
    canary = BreakGlassGovernanceCanaryEvidence(
        recovery_id=owner_canary.recovery_id,
        source_attempt_id=owner_canary.source_attempt_id,
        integrated_main_sha=owner_canary.integrated_main_sha,
        source_runtime_identity_sha256=owner_canary.source_runtime_identity_sha256,
        action_binding_sha256=owner_canary.action_binding_sha256,
        normal_authority_readback_sha256=owner_canary.normal_authority_readback_sha256,
        governance_operation_receipt_sha256=owner_canary.governance_operation_receipt_sha256,
        verifier_receipt_sha256=owner_canary.verifier_receipt_sha256,
        observed_at=owner_canary.observed_at,
        normal_governance_restored=owner_canary.normal_governance_restored,
    )
    chain = _read_chain(activation, state_root=state_root)
    if not chain:
        raise BreakGlassRecoveryError("VERIFIED_EVIDENCE_REQUIRED")
    _assert_envelope_matches_existing(envelope, chain)
    latest = chain[-1]
    if latest["phase"] == BreakGlassPhase.CONSUMED.value:
        raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")
    if latest["phase"] != BreakGlassPhase.VERIFIED.value:
        raise BreakGlassRecoveryError("VERIFIED_EVIDENCE_REQUIRED")
    attempt_dir = _attempt_dir(activation, state_root=state_root)
    payload = _base_transition(
        envelope=envelope,
        phase=BreakGlassPhase.CONSUMED,
        predecessor_hash=str(latest["transition_hash"]),
        evidence={
            "verified_transition_hash": latest["transition_hash"],
            "owner_canary_comment_id": canary_envelope.comment_id,
            "owner_canary_payload_sha256": canary_envelope.payload_sha256,
            "governance_canary_sha256": canary.evidence_sha256,
            "governance_canary": canary.model_dump(mode="json"),
            "authority_terminal": True,
            "post_consume_replay": "DENY",
            "granted_effect": "SOURCE_REPAIR_ONLY",
            "excluded_effects": [
                "ACCEPTANCE",
                "GITHUB_MERGE",
                "PROTECTED_REF_MUTATION",
                "RUNTIME_RECOVERY",
                "RELEASE",
                "PRODUCTION_PUBLIC_CLAIM",
            ],
        },
    )
    return _atomic_create(attempt_dir / _PHASE_FILE[BreakGlassPhase.CONSUMED], payload)


def _integration_attempt_dir(
    integration: BreakGlassOwnerIntegrationPayload, *, state_root: Path | None = None
) -> Path:
    root = state_root or DEFAULT_BREAK_GLASS_ROOT
    return root / integration.recovery_id / integration.integration_attempt_id


def _integration_envelope_hash(envelope: OwnerIntegrationEnvelope) -> str:
    return canonical_sha256(envelope.model_dump(mode="json"))


def prepare_emergency_integration(
    source_envelope: OwnerActivationEnvelope,
    integration_envelope: OwnerIntegrationEnvelope,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    source = source_envelope.payload
    integration = integration_envelope.payload
    source.assert_current(now=now)
    integration.assert_current(now=now)
    if (
        integration.recovery_id != source.recovery_id
        or integration.source_attempt_id != source.attempt_id
        or integration.source_activation_payload_sha256 != source_envelope.payload_sha256
    ):
        raise BreakGlassRecoveryError("INTEGRATION_AUTHORITY_MISMATCH")

    chain = _read_chain(source, state_root=state_root)
    if len(chain) < 3 or chain[-1]["phase"] != BreakGlassPhase.VERIFIED.value:
        raise BreakGlassRecoveryError("VERIFIED_EVIDENCE_REQUIRED")
    _assert_envelope_matches_existing(source_envelope, chain)
    verified_record = chain[2]
    if verified_record["evidence"].get("owner_verification_payload_sha256") != (
        integration.verification_payload_sha256
    ):
        raise BreakGlassRecoveryError("INTEGRATION_VERIFICATION_MISMATCH")
    applied = BreakGlassAppliedEvidence.model_validate(chain[1]["evidence"]["applied"])
    if (
        integration.accepted_head_sha != applied.repair_commit_sha
        or integration.accepted_tree_sha != applied.repair_tree_sha
        or integration.accepted_diff_sha256 != applied.full_diff_sha256
    ):
        raise BreakGlassRecoveryError("INTEGRATION_SUBJECT_MISMATCH")

    attempt_dir = _integration_attempt_dir(integration, state_root=state_root)
    _ensure_safe_dir(attempt_dir, create=True)
    consumed_path = attempt_dir / _INTEGRATION_CONSUMED_FILE
    if consumed_path.exists() or consumed_path.is_symlink():
        raise BreakGlassRecoveryError("INTEGRATION_REPLAY_DENIED")
    payload = {
        "schema": "nexus.break_glass_integration_transition.v1",
        "repository": integration.repository,
        "issue": integration.issue,
        "recovery_id": integration.recovery_id,
        "integration_attempt_id": integration.integration_attempt_id,
        "source_attempt_id": integration.source_attempt_id,
        "effect_class": integration.effect_class,
        "phase": "PREPARED",
        "integration_comment_id": integration_envelope.comment_id,
        "integration_envelope_sha256": _integration_envelope_hash(integration_envelope),
        "integration_payload_sha256": integration_envelope.payload_sha256,
        "source_activation_payload_sha256": source_envelope.payload_sha256,
        "verification_payload_sha256": integration.verification_payload_sha256,
        "pr_number": integration.pr_number,
        "expected_base_sha": integration.expected_base_sha,
        "accepted_head_sha": integration.accepted_head_sha,
        "accepted_tree_sha": integration.accepted_tree_sha,
        "accepted_diff_sha256": integration.accepted_diff_sha256,
        "merge_method": integration.merge_method,
        "checks": [item.model_dump(mode="json") for item in integration.checks],
        "claim_ceiling": integration.claim_ceiling,
        "forbidden_effects": [
            "FORCE_PUSH",
            "REF_DELETE",
            "UNRELATED_MERGE",
            "RUNTIME_RECOVERY",
            "RELEASE",
            "PRODUCTION_PUBLIC_CLAIM",
        ],
    }
    return _atomic_create(attempt_dir / _INTEGRATION_PREPARED_FILE, payload)


def record_emergency_integration_consumed(
    integration_envelope: OwnerIntegrationEnvelope,
    *,
    merge_commit_sha: str,
    observed_main_sha: str,
    merged_pr_number: int,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    integration = integration_envelope.payload
    integration.assert_current(now=now)
    if merged_pr_number != integration.pr_number:
        raise BreakGlassRecoveryError("INTEGRATION_PR_MISMATCH")
    if not re_full_sha40(merge_commit_sha) or not re_full_sha40(observed_main_sha):
        raise BreakGlassRecoveryError("GIT_SHA_INVALID")
    if merge_commit_sha != observed_main_sha:
        raise BreakGlassRecoveryError("INTEGRATION_READBACK_MISMATCH")

    attempt_dir = _integration_attempt_dir(integration, state_root=state_root)
    _ensure_safe_dir(attempt_dir, create=False)
    prepared_path = attempt_dir / _INTEGRATION_PREPARED_FILE
    if not prepared_path.exists() and not prepared_path.is_symlink():
        raise BreakGlassRecoveryError("INTEGRATION_PREPARE_REQUIRED")
    prepared = _load_json_file(prepared_path)
    if (
        prepared.get("integration_envelope_sha256")
        != _integration_envelope_hash(integration_envelope)
        or prepared.get("accepted_head_sha") != integration.accepted_head_sha
        or prepared.get("expected_base_sha") != integration.expected_base_sha
    ):
        raise BreakGlassRecoveryError("INTEGRATION_PREPARED_MISMATCH")

    consumed_path = attempt_dir / _INTEGRATION_CONSUMED_FILE
    payload = {
        "schema": "nexus.break_glass_integration_transition.v1",
        "repository": integration.repository,
        "issue": integration.issue,
        "recovery_id": integration.recovery_id,
        "integration_attempt_id": integration.integration_attempt_id,
        "source_attempt_id": integration.source_attempt_id,
        "effect_class": integration.effect_class,
        "phase": "CONSUMED",
        "predecessor_hash": prepared["transition_hash"],
        "integration_comment_id": integration_envelope.comment_id,
        "integration_envelope_sha256": _integration_envelope_hash(integration_envelope),
        "integration_payload_sha256": integration_envelope.payload_sha256,
        "pr_number": integration.pr_number,
        "accepted_head_sha": integration.accepted_head_sha,
        "expected_base_sha": integration.expected_base_sha,
        "merge_commit_sha": merge_commit_sha,
        "observed_main_sha": observed_main_sha,
        "authority_terminal": True,
        "post_consume_replay": "DENY",
        "granted_effect": "EMERGENCY_INTEGRATION_ONLY",
    }
    if consumed_path.exists() or consumed_path.is_symlink():
        existing = _load_json_file(consumed_path)
        candidate = {**payload, "transition_hash": canonical_sha256(payload)}
        if canonical_json_bytes(existing) == canonical_json_bytes(candidate):
            return existing
        raise BreakGlassRecoveryError("INTEGRATION_CONSUME_CONFLICT")
    return _atomic_create(consumed_path, payload)


def inspect_emergency_integration(
    integration_envelope: OwnerIntegrationEnvelope, *, state_root: Path | None = None
) -> dict[str, Any]:
    integration = integration_envelope.payload
    attempt_dir = _integration_attempt_dir(integration, state_root=state_root)
    if not attempt_dir.exists():
        return {
            "schema": "nexus.break_glass_integration_inspection.v1",
            "status": "MISSING",
            "recovery_id": integration.recovery_id,
            "integration_attempt_id": integration.integration_attempt_id,
        }
    _ensure_safe_dir(attempt_dir, create=False)
    prepared_path = attempt_dir / _INTEGRATION_PREPARED_FILE
    consumed_path = attempt_dir / _INTEGRATION_CONSUMED_FILE
    prepared = _load_json_file(prepared_path)
    if consumed_path.exists() or consumed_path.is_symlink():
        consumed = _load_json_file(consumed_path)
        if consumed.get("predecessor_hash") != prepared.get("transition_hash"):
            raise BreakGlassRecoveryError("INTEGRATION_CHAIN_INVALID")
        return {
            "schema": "nexus.break_glass_integration_inspection.v1",
            "status": "CONSUMED",
            "recovery_id": integration.recovery_id,
            "integration_attempt_id": integration.integration_attempt_id,
            "latest": consumed,
        }
    return {
        "schema": "nexus.break_glass_integration_inspection.v1",
        "status": "PREPARED",
        "recovery_id": integration.recovery_id,
        "integration_attempt_id": integration.integration_attempt_id,
        "latest": prepared,
    }


def assert_emergency_integration_not_consumed(
    integration_envelope: OwnerIntegrationEnvelope, *, state_root: Path | None = None
) -> None:
    inspection = inspect_emergency_integration(integration_envelope, state_root=state_root)
    if inspection["status"] == "CONSUMED":
        raise BreakGlassRecoveryError("INTEGRATION_REPLAY_DENIED")


def re_full_sha40(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def assert_source_not_globally_terminal(
    envelope: OwnerActivationEnvelope,
    terminal_envelopes: tuple[OwnerTerminalEnvelope, ...],
) -> None:
    activation = envelope.payload
    for terminal in terminal_envelopes:
        payload = terminal.payload
        if (
            payload.recovery_id == activation.recovery_id
            and payload.source_attempt_id == activation.attempt_id
            and payload.source_activation_payload_sha256 == envelope.payload_sha256
        ):
            raise BreakGlassRecoveryError("RECOVERY_GLOBALLY_TERMINAL")


def assert_source_repair_not_consumed(
    envelope: OwnerActivationEnvelope, *, state_root: Path | None = None
) -> None:
    chain = _read_chain(envelope.payload, state_root=state_root)
    _assert_envelope_matches_existing(envelope, chain)
    if chain and chain[-1]["phase"] == BreakGlassPhase.CONSUMED.value:
        raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")


__all__ = [
    "DEFAULT_BREAK_GLASS_ROOT",
    "BreakGlassRecoveryError",
    "prepare_source_repair",
    "record_source_repair_applied",
    "record_source_repair_verified",
    "consume_source_repair_authority",
    "inspect_attempt",
    "assert_source_repair_not_consumed",
    "assert_source_not_globally_terminal",
    "prepare_emergency_integration",
    "record_emergency_integration_consumed",
    "inspect_emergency_integration",
    "assert_emergency_integration_not_consumed",
]
