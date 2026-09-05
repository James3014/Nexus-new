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
    BreakGlassContractError,
    BreakGlassPhase,
    BreakGlassVerificationEvidence,
    OwnerActivationEnvelope,
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
        if record.get("recovery_id") != activation.recovery_id or record.get(
            "attempt_id"
        ) != activation.attempt_id:
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
    verification: BreakGlassVerificationEvidence,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
    chain = _read_chain(activation, state_root=state_root)
    if len(chain) < 2:
        raise BreakGlassRecoveryError("APPLIED_EVIDENCE_REQUIRED")
    _assert_envelope_matches_existing(envelope, chain)
    latest = chain[-1]
    if latest["phase"] == BreakGlassPhase.CONSUMED.value:
        raise BreakGlassRecoveryError("RECOVERY_REPLAY_DENIED")
    applied = BreakGlassAppliedEvidence.model_validate(chain[1]["evidence"]["applied"])
    if verification.verifier_id == applied.implementer_id:
        raise BreakGlassRecoveryError("INDEPENDENT_VERIFIER_REQUIRED")
    if (
        verification.verified_commit_sha != applied.repair_commit_sha
        or verification.verified_tree_sha != applied.repair_tree_sha
        or verification.verified_diff_sha256 != applied.full_diff_sha256
    ):
        raise BreakGlassRecoveryError("VERIFICATION_SUBJECT_MISMATCH")
    if latest["phase"] == BreakGlassPhase.VERIFIED.value:
        if latest["evidence"].get("verification_evidence_sha256") == verification.evidence_sha256:
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
            "verification_evidence_sha256": verification.evidence_sha256,
            "verification": verification.model_dump(mode="json"),
        },
    )
    return _atomic_create(attempt_dir / _PHASE_FILE[BreakGlassPhase.VERIFIED], payload)


def consume_source_repair_authority(
    envelope: OwnerActivationEnvelope,
    *,
    now: datetime,
    state_root: Path | None = None,
) -> dict[str, Any]:
    activation = envelope.payload
    activation.assert_current(now=now)
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
]
