from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.research.clm_system_one.research_evidence_root import (
    resolve_research_evidence_root,
)

STEP_SCHEMA = "nexus.clm_trajectory_step.v1"
STEP_RESULT_SCHEMA = "nexus.clm_trajectory_step_result.v1"
OUTCOME_SCHEMA = "nexus.clm_trajectory_outcome_binding.v1"
BINDING_SCHEMA = "nexus.clm_trajectory_binding.v1"
READINESS_SCHEMA = "nexus.clm_trajectory_corpus_readiness.v1"
CHECKPOINT_SCHEMA = "nexus.research_experiment_checkpoint.v1"
HEALTH_SCHEMA = "nexus.clm_trajectory_health.v1"

# Minimum independent task families required before READY_TO_REAUDIT
_MIN_TASK_FAMILIES = 5

# Scientific grouping labels are declared by the Task Card issuer BEFORE the
# first action. The existing task-card content hash is the producer authority;
# this research consumer is not a task classifier or a second truth store.
_TRACK1_FAMILY_TAXONOMY = "TRACK1_ENGINEERING_V1"
_TRACK1_FAMILY_CATEGORIES = frozenset({
    "defect_repair",  # repair existing, demonstrably incorrect behavior
    "feature_extension",  # introduce previously absent capability
    "test_oracle",  # test, verifier, or assertion correctness
    "runtime_recovery",  # runtime/transport/restart continuity
    "evidence_integrity",  # evidence identity, lineage, tamper safety
    "architecture_maintenance",  # behavior-preserving internal restructuring
})

# Bounding limits (C: Redact -> Bound -> Hash -> Persist)
_MAX_STATE_ACTION_CHARS = 16384  # max serialized chars for state/action blobs
_MAX_RESULT_INLINE_BYTES = 4096  # results larger than this go to content-addressed blobs

_ALLOWED_CHECKPOINT_STATES = {
    "ACTIVE",
    "WAITING_FOR_DATA",
    "READY_TO_REAUDIT",
    "TERMINAL",
}
_STRONG_LABELS = {"ISOLATED_VERIFIER", "MECHANICAL_GATE"}
_FORBIDDEN_PRE_ACTION_KEYS = {
    "final_verifier_status",
    "final_outcome",
    "final_candidate_status",
    "trajectory_outcome",
}

# Patterns used to detect and redact credentials/secrets from step payloads
# before hashing or persistence.  Conservative: prefer false-positive redaction
# over accidental secret leakage.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)(password|passwd|secret|token|api[_\-]?key|private[_\-]?key|auth[_\-]?key)\s*[=:]\s*\S+"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    # curl -u / --user basic-auth: -u user:password or --user user:password
    re.compile(r"(?i)(?:--user|-u)\s+\S+:\S+"),
    # URL-embedded credentials: scheme://user:password@host
    re.compile(r"(?i)[a-z][a-z0-9+\-.]*://[^/@\s]+:[^/@\s]+@"),
]
_REDACTED_SENTINEL = "[REDACTED]"

# Dict keys whose string values are always fully redacted regardless of value content.
# Matched case-insensitively and with common separators stripped.
_SECRET_KEYS: frozenset[str] = frozenset({
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "auth_key",
    "authkey",
    "authorization",
    "access_token",
    "refresh_token",
    "bearer",
    "credential",
    "credentials",
    "secret_key",
    "secretkey",
    "key_material",
})

_sidecar_logger = logging.getLogger("nexus.trajectory_continuity.sidecar")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _bound_string(s: str, max_chars: int) -> str:
    """Truncate a string to at most max_chars characters, appending a sentinel if truncated."""
    if len(s) <= max_chars:
        return s
    sentinel = "...[BOUNDED]"
    return s[: max_chars - len(sentinel)] + sentinel


def _bound_value(value: Any, max_chars: int) -> Any:
    """Serialize value to JSON, bound to max_chars, then deserialize back.

    Used for state/action payloads after redaction: Redact -> Bound -> Hash -> Persist.
    The bounded representation is what is hashed and stored; raw oversized values are
    never written to disk.
    """
    serialized = _canonical_json(value)
    if len(serialized) <= max_chars:
        return value
    # Bound the serialized form and store as a plain string payload
    return {"_bounded": True, "value": _bound_string(serialized, max_chars)}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"immutable evidence collision: {path}")
        return
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RuntimeError(f"immutable evidence collision: {path}")
    finally:
        tmp_path.unlink(missing_ok=True)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trajectory_storage_key(trajectory_id: str) -> str:
    value = str(trajectory_id or "").strip()
    if not value:
        raise ValueError("trajectory_id is required")
    return _sha256_bytes(value.encode("utf-8"))


def _contains_forbidden_future_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in _FORBIDDEN_PRE_ACTION_KEYS:
                return True
            if _contains_forbidden_future_key(child):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_forbidden_future_key(child) for child in value)
    return False


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------


def _redact_string(value: str) -> str:
    """Redact known secret patterns from a string value."""
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(_REDACTED_SENTINEL, result)
    return result


def _redact_value(value: Any, *, _depth: int = 0, _parent_key: str = "") -> Any:
    """Recursively redact credential/private-key/token patterns from a value.

    Two complementary strategies:
    1. Key-based: when the parent dict key is in ``_SECRET_KEYS``, the value is
       unconditionally replaced with ``[REDACTED]``.
    2. Pattern-based: string values are scanned for inline credential patterns
       (``bearer <token>``, ``password=<val>`` inside shell commands, etc.).

    Operates without mutating the original value.  Depth is capped at 32 to
    prevent runaway recursion on pathological inputs.
    """
    if _depth > 32:
        return _REDACTED_SENTINEL
    # Key-based: parent key flagged as a credential → redact value unconditionally
    if (
        _parent_key
        and isinstance(value, str)
        and _parent_key.lower().replace("-", "_") in _SECRET_KEYS
    ):
        return _REDACTED_SENTINEL
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return {
            k: _redact_value(v, _depth=_depth + 1, _parent_key=str(k)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(item, _depth=_depth + 1) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


# ---------------------------------------------------------------------------
# Sidecar health (fail-visible, main workflow fail-open)
# Schema: nexus.clm_trajectory_health.v1 — sidecar-only, NEVER affects routing/selection/acceptance
# ---------------------------------------------------------------------------


def _read_health_snapshot(health_snapshot_path: Path) -> dict[str, Any]:
    """Read the current health snapshot, returning an empty baseline if absent."""
    if health_snapshot_path.exists():
        try:
            return json.loads(health_snapshot_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {
        "schema": HEALTH_SCHEMA,
        "attempted_step_count": 0,
        "persisted_step_count": 0,
        "instrumentation_error_count": 0,
        "last_error_class": None,
        "last_successful_observation": None,
        "trajectory_groups_completed": 0,
        "strong_label_bindings_completed": 0,
    }


def _write_health_snapshot(health_snapshot_path: Path, snapshot: dict[str, Any]) -> None:
    """Atomically write health snapshot. Caller is responsible for swallowing errors."""
    _atomic_replace(health_snapshot_path, _json_bytes(snapshot))


def _health_snapshot_path(evidence_root: Path) -> Path:
    return evidence_root / "trajectory" / "sidecar_health_snapshot.json"


def _increment_health(
    evidence_root: Path,
    *,
    attempted: bool = False,
    persisted: bool = False,
    error_class: str | None = None,
    last_success_ts: str | None = None,
    groups_completed: bool = False,
    strong_bindings: bool = False,
) -> None:
    """Update the mutable health snapshot atomically.

    All errors are swallowed; this MUST NOT affect routing, selection, or acceptance.
    """
    try:
        snap_path = _health_snapshot_path(evidence_root)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap = _read_health_snapshot(snap_path)
        if attempted:
            snap["attempted_step_count"] = snap.get("attempted_step_count", 0) + 1
        if persisted:
            snap["persisted_step_count"] = snap.get("persisted_step_count", 0) + 1
        if error_class is not None:
            snap["instrumentation_error_count"] = snap.get("instrumentation_error_count", 0) + 1
            snap["last_error_class"] = error_class
        if last_success_ts is not None:
            snap["last_successful_observation"] = last_success_ts
        if groups_completed:
            snap["trajectory_groups_completed"] = snap.get("trajectory_groups_completed", 0) + 1
        if strong_bindings:
            snap["strong_label_bindings_completed"] = (
                snap.get("strong_label_bindings_completed", 0) + 1
            )
        snap["schema"] = HEALTH_SCHEMA
        _write_health_snapshot(snap_path, snap)
    except Exception as exc:  # noqa: BLE001
        _sidecar_logger.warning("health snapshot write failed (swallowed): %s", exc)


def _record_sidecar_health_event(
    *,
    evidence_root: Path,
    event_type: str,
    detail: str,
) -> None:
    """Append a health event to the optional sidecar health event log.

    This is fire-and-forget from the main workflow's perspective: failures here
    must never propagate to the caller (fail-open).  But the record itself is
    visible (fail-visible) for operators.
    The snapshot (``sidecar_health_snapshot.json``) is the required sidecar;
    the event log is optional.
    """
    try:
        health_path = evidence_root / "trajectory" / "sidecar_health.jsonl"
        health_path.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            json.dumps(
                {
                    "event_type": event_type,
                    "detail": detail,
                    "observed_at": _now(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        with health_path.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception as exc:  # noqa: BLE001
        _sidecar_logger.warning("sidecar health write failed: %s", exc)


# ---------------------------------------------------------------------------
# Step data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryStepRef:
    trajectory_id: str
    step_index: int
    step_sha256: str
    step_ref: str


# ---------------------------------------------------------------------------
# Supervision mode
# ---------------------------------------------------------------------------


def _supervision_mode(has_step_oracle: bool) -> str:
    """Return the supervision label for a trajectory step."""
    return "ORACLE_SUPERVISED" if has_step_oracle else "WEAK_SUPERVISION"


# ---------------------------------------------------------------------------
# Core trajectory API
# ---------------------------------------------------------------------------


def self_hosted_worker_trajectory_id(*, task_id: str, attempt_id: str, provider: str) -> str:
    """Return the deterministic passive trajectory identity for one provider attempt."""

    values = [
        str(task_id or "").strip(),
        str(attempt_id or "").strip(),
        str(provider or "").strip(),
    ]
    if not all(values):
        raise ValueError("task/attempt/provider identity is required")
    payload = "\0".join(values).encode("utf-8")
    return "self-hosted-" + hashlib.sha256(payload).hexdigest()


def seal_trajectory_step(
    *,
    evidence_root: str | Path,
    task_id: str,
    trajectory_id: str,
    attempt_id: str,
    candidate_id: str | None,
    step_index: int,
    source_revision: str,
    pre_action_state: Any,
    action_type: str,
    action_payload: Any,
    observed_at: str | None = None,
    base_source_revision: str = "",
    working_state_manifest_sha256: str = "",
    step_oracle: Any = None,
) -> TrajectoryStepRef:
    """Seal a pre-action state/action pair as an immutable, hash-chained step.

    Changes vs #1197:
    - ``candidate_id`` is now nullable (``None`` or ``""`` is accepted for
      pre-candidate steps; an explicit ``""``) and stored as ``""`` in the
      record.
    - ``base_source_revision`` records the fixed repository revision at
      trajectory-open time; ``working_state_manifest_sha256`` is a per-step
      content hash of the working tree manifest (both optional).
    - State and action payloads are *redacted then bounded* before hashing or
      persistence.  No raw secrets or private-key material reach disk.
    - The ``supervision_mode`` field is set to ``WEAK_SUPERVISION`` when no
      ``step_oracle`` is provided.
    - A sidecar health event is written on any storage error (fail-visible);
      the main workflow is unaffected (fail-open).
    """
    root = Path(evidence_root).expanduser().resolve()
    if step_index < 0:
        raise ValueError("step_index must be non-negative")
    if not task_id or not trajectory_id or not attempt_id:
        raise ValueError("task/trajectory/attempt identity is required")
    # candidate_id is nullable (pre-candidate steps have no candidate yet)
    normalized_candidate_id = str(candidate_id).strip() if candidate_id is not None else ""

    if _contains_forbidden_future_key(pre_action_state):
        raise ValueError("pre-action state contains forbidden final-outcome evidence")

    # Increment attempted_step_count BEFORE any persistence (health B contract)
    _increment_health(root, attempted=True)

    # Redact -> Bound -> Hash -> Persist (C contract)
    redacted_state = _redact_value(pre_action_state)
    redacted_action = _redact_value(action_payload)
    bounded_state = _bound_value(redacted_state, _MAX_STATE_ACTION_CHARS)
    bounded_action = _bound_value(redacted_action, _MAX_STATE_ACTION_CHARS)

    # Check for closed trajectory (outcome already bound)
    outcome_path = (
        root / "trajectory" / "outcomes" / f"{_trajectory_storage_key(trajectory_id)}.json"
    )
    if outcome_path.exists():
        _record_sidecar_health_event(
            evidence_root=root,
            event_type="CLOSED_TRAJECTORY_APPEND_ATTEMPT",
            detail=f"trajectory_id={trajectory_id!r} step_index={step_index}",
        )
        raise ValueError("trajectory is closed: cannot append steps after outcome has been bound")

    state_sha = _sha256_json(bounded_state)
    action_sha = _sha256_json(bounded_action)
    state_path = root / "trajectory" / "state" / state_sha[:2] / f"{state_sha}.json"
    action_path = root / "trajectory" / "action" / action_sha[:2] / f"{action_sha}.json"

    try:
        _write_create_only(state_path, _json_bytes(bounded_state))
        _write_create_only(action_path, _json_bytes(bounded_action))
    except Exception as exc:
        _record_sidecar_health_event(
            evidence_root=root,
            event_type="STEP_STORAGE_ERROR",
            detail=str(exc),
        )
        _increment_health(root, error_class=type(exc).__name__)
        raise

    steps_dir = root / "trajectory" / "steps" / _trajectory_storage_key(trajectory_id)
    previous_sha = ""
    if step_index:
        previous_path = steps_dir / f"{step_index - 1:08d}.json"
        if not previous_path.exists():
            raise ValueError("trajectory step order gap")
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_sha = str(previous.get("record_sha256") or "")

    supervision = _supervision_mode(step_oracle is not None)

    step_body = {
        "schema": STEP_SCHEMA,
        "task_id": task_id,
        "trajectory_id": trajectory_id,
        "attempt_id": attempt_id,
        "candidate_id": normalized_candidate_id,
        "step_index": step_index,
        "source_revision": source_revision,
        "base_source_revision": str(base_source_revision or ""),
        "working_state_manifest_sha256": str(working_state_manifest_sha256 or ""),
        "pre_action_state_sha256": state_sha,
        "pre_action_state_ref": str(state_path.relative_to(root)),
        "action_type": action_type,
        "action_sha256": action_sha,
        "action_ref": str(action_path.relative_to(root)),
        "parent_step_sha256": previous_sha,
        "observed_at": observed_at or _now(),
        "sealed_before_result": True,
        "supervision_mode": supervision,
    }
    step_sha = _sha256_json(step_body)
    step = dict(step_body, record_sha256=step_sha)
    step_path = steps_dir / f"{step_index:08d}.json"
    try:
        _write_create_only(step_path, _json_bytes(step))
    except Exception as exc:
        _record_sidecar_health_event(
            evidence_root=root,
            event_type="STEP_RECORD_WRITE_ERROR",
            detail=str(exc),
        )
        _increment_health(root, error_class=type(exc).__name__)
        raise
    # Step persisted successfully: increment persisted count and last success
    _increment_health(root, persisted=True, last_success_ts=step_body["observed_at"])
    return TrajectoryStepRef(trajectory_id, step_index, step_sha, str(step_path.relative_to(root)))


def bind_trajectory_step_result(
    *,
    evidence_root: str | Path,
    step_ref: TrajectoryStepRef,
    action_result: Any,
    observed_at: str | None = None,
) -> str:
    root = Path(evidence_root).expanduser().resolve()
    step_path = root / step_ref.step_ref
    if not step_path.exists():
        raise ValueError("step_ref not found")
    step = json.loads(step_path.read_text(encoding="utf-8"))
    if step.get("record_sha256") != step_ref.step_sha256:
        raise ValueError("step_ref hash mismatch")

    # Redact -> Bound -> Hash -> Persist (C contract)
    # Secrets must be redacted BEFORE any sizing/hashing/persistence.
    redacted_result = _redact_value(action_result)

    # Serialize the redacted result before deciding inline vs offload.
    redacted_json_bytes = _json_bytes(redacted_result)

    # Large results are content-addressed by the exact bytes persisted.
    if len(redacted_json_bytes) > _MAX_RESULT_INLINE_BYTES:
        if isinstance(redacted_result, str):
            blob_ext = ".txt"
            blob_payload = redacted_result.encode("utf-8")
        else:
            blob_ext = ".json"
            blob_payload = redacted_json_bytes
        result_sha = _sha256_bytes(blob_payload)
        blob_path = root / "trajectory" / "blobs" / result_sha[:2] / f"{result_sha}{blob_ext}"
        try:
            _write_create_only(blob_path, blob_payload)
        except Exception as exc:
            _record_sidecar_health_event(
                evidence_root=root,
                event_type="RESULT_BLOB_WRITE_ERROR",
                detail=str(exc),
            )
            _increment_health(root, error_class=type(exc).__name__)
            raise
        # Result record carries only the content-addressed ref/hash, no inline payload
        result_blob = None  # no inline result blob in trajectory/result/
        action_result_inline = None
        action_result_blob_ref = str(blob_path.relative_to(root))
        action_result_blob_sha256 = result_sha
    else:
        # Inline results are also addressed by the exact JSON bytes persisted.
        result_sha = _sha256_bytes(redacted_json_bytes)
        result_blob = root / "trajectory" / "result" / result_sha[:2] / f"{result_sha}.json"
        try:
            _write_create_only(result_blob, redacted_json_bytes)
        except Exception as exc:
            _record_sidecar_health_event(
                evidence_root=root,
                event_type="RESULT_STORAGE_ERROR",
                detail=str(exc),
            )
            _increment_health(root, error_class=type(exc).__name__)
            raise
        action_result_inline = str(result_blob.relative_to(root))
        action_result_blob_ref = None
        action_result_blob_sha256 = None

    ts = observed_at or _now()
    body: dict[str, Any] = {
        "schema": STEP_RESULT_SCHEMA,
        "trajectory_id": step_ref.trajectory_id,
        "step_index": step_ref.step_index,
        "step_sha256": step_ref.step_sha256,
        "action_result_sha256": result_sha,
        "observed_at": ts,
    }
    if action_result_inline is not None:
        body["action_result_ref"] = action_result_inline
    if action_result_blob_ref is not None:
        body["action_result_blob_ref"] = action_result_blob_ref
        body["action_result_blob_sha256"] = action_result_blob_sha256

    record_sha = _sha256_json(body)
    record = dict(body, record_sha256=record_sha)
    record_path = (
        root
        / "trajectory"
        / "step_results"
        / _trajectory_storage_key(step_ref.trajectory_id)
        / f"{step_ref.step_index:08d}.json"
    )
    try:
        _write_create_only(record_path, _json_bytes(record))
    except Exception as exc:
        _record_sidecar_health_event(
            evidence_root=root,
            event_type="RESULT_RECORD_WRITE_ERROR",
            detail=str(exc),
        )
        _increment_health(root, error_class=type(exc).__name__)
        raise
    # Successful result record: update last_successful_observation
    _increment_health(root, last_success_ts=ts)
    return str(record_path.relative_to(root))


def bind_trajectory_outcome(
    *,
    evidence_root: str | Path,
    trajectory_id: str,
    candidate_evidence_ref: str,
) -> str:
    """Bind outcome evidence to a trajectory.

    Validates the full trajectory→candidate→completion chain:
    - Candidate ref must resolve within root and exist.
    - Candidate must be dataset_eligible with a strong label.
    - Candidate ``trajectory_id`` / ``attempt_id`` / ``candidate_id`` must
      bind back to this trajectory's steps.
    - Trajectory must be complete (no missing steps, no chain gaps).
    - Outcome file is write-once (closed trajectories cannot be re-bound).
    """
    root = Path(evidence_root).expanduser().resolve()
    candidate_path = (root / candidate_evidence_ref).resolve()
    if root not in candidate_path.parents or not candidate_path.exists():
        raise ValueError("candidate evidence ref is invalid")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not candidate.get("dataset_eligible"):
        raise ValueError("candidate evidence is not dataset eligible")
    label_quality = str(candidate.get("label_quality") or "")
    verifier_status = str(candidate.get("verifier_status") or "")
    if label_quality not in _STRONG_LABELS or verifier_status not in {"PASS", "FAIL"}:
        raise ValueError("candidate evidence is not strong verifier truth")

    # Validate trajectory completeness first.
    complete, problems = _trajectory_complete(root, trajectory_id)
    if not complete:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError(f"trajectory is incomplete before outcome binding: {problems}")

    # Bind candidate evidence to the exact task/attempt/candidate identity carried
    # by the sealed steps. Early pre-candidate steps may have candidate_id="" but
    # any non-empty candidate identity must agree with the final candidate row.
    steps_dir = root / "trajectory" / "steps" / _trajectory_storage_key(trajectory_id)
    step_records = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(steps_dir.glob("*.json"))
    ]
    task_ids = {str(step.get("task_id") or "") for step in step_records}
    attempt_ids = {str(step.get("attempt_id") or "") for step in step_records}
    candidate_ids = {
        str(step.get("candidate_id") or "")
        for step in step_records
        if str(step.get("candidate_id") or "")
    }
    source_revisions = {
        str(step.get("source_revision") or "")
        for step in step_records
        if str(step.get("source_revision") or "")
    }
    if len(task_ids) != 1 or len(attempt_ids) != 1 or len(candidate_ids) > 1:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("trajectory step identity drift")
    if len(source_revisions) > 1:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("trajectory source revision drift")

    candidate_task_id = str(candidate.get("task_id") or "")
    candidate_attempt_id = str(candidate.get("attempt_id") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    candidate_source_revision = str(candidate.get("source_revision") or "")
    if task_ids != {candidate_task_id}:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("candidate task_id does not match trajectory")
    if attempt_ids != {candidate_attempt_id}:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("candidate attempt_id does not match trajectory")
    if candidate_ids and candidate_ids != {candidate_id}:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("candidate_id does not match trajectory")
    if source_revisions and candidate_source_revision not in source_revisions:
        _increment_health(root, error_class="OutcomeBindingError")
        raise ValueError("candidate source_revision does not match trajectory")

    # Outcome binding is write-once: a closed trajectory cannot receive a new outcome
    outcome_path = (
        root / "trajectory" / "outcomes" / f"{_trajectory_storage_key(trajectory_id)}.json"
    )
    if outcome_path.exists():
        raise ValueError("trajectory is already closed: outcome already bound for this trajectory")

    terminal_step = step_records[-1]
    body = {
        "schema": BINDING_SCHEMA,
        "legacy_schema": OUTCOME_SCHEMA,
        "trajectory_id": trajectory_id,
        "task_id": candidate_task_id,
        "attempt_id": candidate_attempt_id,
        "candidate_id": candidate_id,
        "comparison_group_sha256": str(candidate.get("comparison_group_sha256") or ""),
        "candidate_evidence_ref": candidate_evidence_ref,
        "candidate_record_sha256": str(candidate.get("record_sha256") or ""),
        "verifier_status": verifier_status,
        "label_quality": label_quality,
        "step_count": len(step_records),
        "terminal_step_sha256": str(terminal_step.get("record_sha256") or ""),
        "bound_at": _now(),
    }
    record_sha = _sha256_json(body)
    record = dict(
        body,
        binding_sha256=record_sha,
        record_sha256=record_sha,
    )
    _write_create_only(outcome_path, _json_bytes(record))
    # Outcome successfully bound: update health counters
    _increment_health(
        root,
        groups_completed=True,
        strong_bindings=True,
        last_success_ts=body["bound_at"],
    )
    return str(outcome_path.relative_to(root))


def _trajectory_complete(root: Path, trajectory_id: str) -> tuple[bool, list[str]]:
    steps_dir = root / "trajectory" / "steps" / _trajectory_storage_key(trajectory_id)
    result_dir = root / "trajectory" / "step_results" / _trajectory_storage_key(trajectory_id)
    if not steps_dir.exists():
        return False, ["missing_steps"]
    steps = sorted(steps_dir.glob("*.json"))
    if not steps:
        return False, ["missing_steps"]
    problems: list[str] = []
    previous_sha = ""
    for expected, step_path in enumerate(steps):
        step = json.loads(step_path.read_text(encoding="utf-8"))
        if step.get("step_index") != expected:
            problems.append("step_index_gap")
        if str(step.get("parent_step_sha256") or "") != previous_sha:
            problems.append("parent_step_mismatch")
        if step.get("sealed_before_result") is not True:
            problems.append("unsealed_pre_action_state")
        previous_sha = str(step.get("record_sha256") or "")
        result_path = result_dir / f"{expected:08d}.json"
        if not result_path.exists():
            problems.append("missing_step_result")
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("step_sha256") != previous_sha:
            problems.append("step_result_binding_mismatch")
    return not problems, sorted(set(problems))


def _labels_by_group(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            continue
        groups.setdefault(value, set()).add(str(row.get("verifier_status") or ""))
    return groups


def _two_group_binary_split_possible(groups: Mapping[str, set[str]]) -> bool:
    binary = [key for key, labels in groups.items() if {"PASS", "FAIL"} <= labels]
    return len(binary) >= 2


def project_corpus_readiness(
    *,
    evidence_root: str | Path,
    holdout_task_ids: Sequence[str] = (),
    task_family_by_task: Mapping[str, str] | None = None,
    excluded_trajectory_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Assess corpus readiness for T1 re-audit.

    Hardening changes vs #1197:
    - Incomplete trajectories, rows with ``verifier_status`` not in
      {``PASS``, ``FAIL``}, and rows without a strong label are all ineligible
      (already enforced via ``dataset_eligible`` on the candidate evidence but
      guarded explicitly here too).
    - Requires ≥ ``_MIN_TASK_FAMILIES`` (5) distinct mapped task families,
      overall strong PASS+FAIL coverage, and family-disjoint split capability;
      an individual family does not need to contain both labels.
    - Task-level and family-level split capability are reported separately;
      readiness requires the family-disjoint capability.
    - ``READY_TO_REAUDIT`` still means ``AUTO_CHAIN=false``.
    """
    root = Path(evidence_root).expanduser().resolve()
    holdout = set(holdout_task_ids)
    families = dict(task_family_by_task or {})
    excluded_ids = {str(value) for value in excluded_trajectory_ids if str(value)}
    valid: list[dict[str, Any]] = []
    malformed: list[str] = []
    leakage: list[str] = []
    overlap: list[str] = []
    excluded: list[str] = []
    outcomes_dir = root / "trajectory" / "outcomes"
    if outcomes_dir.exists():
        for path in sorted(outcomes_dir.glob("*.json")):
            try:
                outcome = json.loads(path.read_text(encoding="utf-8"))
                trajectory_id = str(outcome.get("trajectory_id") or "")
                if trajectory_id in excluded_ids:
                    excluded.append(trajectory_id)
                    continue
                complete, problems = _trajectory_complete(root, trajectory_id)
                if not complete:
                    leakage.extend(f"{trajectory_id}:{problem}" for problem in problems)
                    continue
                candidate_path = (root / str(outcome.get("candidate_evidence_ref") or "")).resolve()
                if root not in candidate_path.parents or not candidate_path.exists():
                    malformed.append(f"{trajectory_id}:candidate_ref_invalid")
                    continue
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                if candidate.get("record_sha256") != outcome.get("candidate_record_sha256"):
                    malformed.append(f"{trajectory_id}:candidate_hash_mismatch")
                    continue
                if not candidate.get("dataset_eligible"):
                    malformed.append(f"{trajectory_id}:candidate_not_eligible")
                    continue
                # Explicit ineligibility guards (defence-in-depth):
                # - verifier_status must be PASS or FAIL (not UNKNOWN/incomplete)
                # - label_quality must be a strong label (not CRITIC, UNSPECIFIED, etc.)
                vs = str(candidate.get("verifier_status") or "")
                lq = str(candidate.get("label_quality") or "")
                if vs not in {"PASS", "FAIL"}:
                    malformed.append(f"{trajectory_id}:incomplete_or_unknown_verifier_status")
                    continue
                if lq not in _STRONG_LABELS:
                    malformed.append(f"{trajectory_id}:ineligible_label_quality")
                    continue
                task_id = str(outcome.get("task_id") or "")
                if task_id in holdout:
                    overlap.append(trajectory_id)
                    continue
                valid.append(dict(outcome))
            except Exception:
                malformed.append(path.name)

    pass_count = sum(1 for row in valid if row.get("verifier_status") == "PASS")
    fail_count = sum(1 for row in valid if row.get("verifier_status") == "FAIL")
    task_groups = _labels_by_group(valid, "task_id")
    # Task-level disjoint split: kept for backward-compatible reporting only.
    # Requires >=2 task IDs each with both PASS and FAIL.
    task_split = _two_group_binary_split_possible(task_groups)

    family_rows = [
        dict(row, task_family=families.get(str(row.get("task_id") or ""), ""))
        for row in valid
        if families.get(str(row.get("task_id") or ""))
    ]
    family_groups = _labels_by_group(family_rows, "task_family")

    # task_family_count: number of *distinct* mapped task families (regardless of per-family label mix)
    task_family_count = len(family_groups)

    # family_disjoint_split_possible: can a family-disjoint split physically be formed?
    # This requires >=2 distinct mapped families in the valid corpus.
    family_disjoint_split_possible = task_family_count >= 2

    # strong_family_count: families that each contain both PASS and FAIL (kept for reporting)
    strong_family_count = sum(1 for labels in family_groups.values() if {"PASS", "FAIL"} <= labels)

    blockers: list[str] = []
    if not valid:
        blockers.append("no_strong_label_trajectories")
    # task_disjoint_split_unavailable is only a blocker when family-level evidence
    # is also unavailable.  When task_family_count >= _MIN_TASK_FAMILIES and
    # family_disjoint_split_possible is True, the family-disjoint split supersedes.
    if not task_split and not family_disjoint_split_possible:
        blockers.append("task_disjoint_split_unavailable")
    if not family_disjoint_split_possible:
        blockers.append("family_disjoint_split_unavailable")
    # Readiness requires >=_MIN_TASK_FAMILIES distinct mapped families
    if task_family_count < _MIN_TASK_FAMILIES:
        blockers.append(
            f"insufficient_task_families_need_{_MIN_TASK_FAMILIES}_have_{task_family_count}"
        )
    if leakage:
        blockers.append("trajectory_leakage_or_binding_problem")
    if overlap:
        blockers.append("holdout_overlap")
    if malformed:
        blockers.append("malformed_evidence")
    # READY_TO_REAUDIT requires: no blockers AND strong PASS trajectories AND strong FAIL trajectories
    disposition = (
        "READY_TO_REAUDIT"
        if not blockers and pass_count > 0 and fail_count > 0
        else "WAITING_FOR_DATA"
    )
    provenance: dict[str, int] = {}
    for row in valid:
        label = str(row.get("label_quality") or "")
        provenance[label] = provenance.get(label, 0) + 1
    return {
        "schema": READINESS_SCHEMA,
        "disposition": disposition,
        "eligible_strong_label_trajectories": len(valid),
        "pass_trajectories": pass_count,
        "fail_trajectories": fail_count,
        "unknown_trajectories": 0,
        "independent_task_count": len(task_groups),
        "task_family_count": task_family_count,
        "strong_family_count": strong_family_count,
        "strong_label_provenance": provenance,
        "task_disjoint_split_possible": task_split,
        "family_disjoint_split_possible": family_disjoint_split_possible,
        "holdout_overlap_trajectories": overlap,
        "excluded_trajectories": sorted(excluded),
        "leakage_findings": leakage,
        "malformed_evidence": malformed,
        "blockers": blockers,
        "observed_at": _now(),
    }


def write_experiment_checkpoint(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
    status: str,
    claim_ceiling: str,
    source_revision: str,
    holdout_manifest_ref: str,
    holdout_manifest_sha256: str,
    corpus_audit_ref: str,
    corpus_audit_sha256: str,
    blockers: Sequence[str],
    resume_gate: str,
    next_allowed_action: str,
    evidence_refs: Sequence[str] = (),
    updated_at: str | None = None,
) -> dict[str, Any]:
    if status not in _ALLOWED_CHECKPOINT_STATES:
        raise ValueError("invalid checkpoint status")
    if status == "READY_TO_REAUDIT" and next_allowed_action != "T0_T1_REAUDIT_ONLY":
        raise ValueError("READY_TO_REAUDIT may only unlock T0_T1_REAUDIT_ONLY")
    if "TRAIN" in next_allowed_action.upper() or "FINE_TUNE" in next_allowed_action.upper():
        raise ValueError("checkpoint may not auto-chain into training")
    root = Path(evidence_root).expanduser().resolve()
    checkpoint_body = {
        "schema": CHECKPOINT_SCHEMA,
        "experiment_id": experiment_id,
        "track_id": track_id,
        "status": status,
        "claim_ceiling": claim_ceiling,
        "source_revision": source_revision,
        "holdout_manifest_ref": holdout_manifest_ref,
        "holdout_manifest_sha256": holdout_manifest_sha256,
        "corpus_audit_ref": corpus_audit_ref,
        "corpus_audit_sha256": corpus_audit_sha256,
        "blockers": list(blockers),
        "resume_gate": resume_gate,
        "next_allowed_action": next_allowed_action,
        "auto_chain": False,
        "evidence_refs": list(evidence_refs),
        "updated_at": updated_at or _now(),
    }
    digest = _sha256_json(checkpoint_body)
    checkpoint = dict(checkpoint_body, checkpoint_sha256=digest)
    slug = f"{experiment_id}__{track_id}"
    base = root / "experiments" / slug
    history_path = base / "history" / f"{digest}.json"
    _write_create_only(history_path, _json_bytes(checkpoint))
    pointer = {
        "schema": "nexus.research_experiment_checkpoint_pointer.v1",
        "experiment_id": experiment_id,
        "track_id": track_id,
        "checkpoint_sha256": digest,
        "checkpoint_ref": str(history_path.relative_to(root)),
        "updated_at": checkpoint["updated_at"],
    }
    _atomic_replace(base / "checkpoint.json", _json_bytes(pointer))
    return checkpoint


def read_experiment_checkpoint(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
) -> dict[str, Any]:
    root = Path(evidence_root).expanduser().resolve()
    slug = f"{experiment_id}__{track_id}"
    pointer_path = root / "experiments" / slug / "checkpoint.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    checkpoint_path = root / str(pointer.get("checkpoint_ref") or "")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    digest = str(checkpoint.get("checkpoint_sha256") or "")
    body = dict(checkpoint)
    body.pop("checkpoint_sha256", None)
    if _sha256_json(body) != digest or digest != pointer.get("checkpoint_sha256"):
        raise RuntimeError("checkpoint digest mismatch")
    return checkpoint


def refresh_checkpoint_from_readiness(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
    readiness: Mapping[str, Any],
    claim_ceiling: str,
    source_revision: str,
    holdout_manifest_ref: str,
    holdout_manifest_sha256: str,
    corpus_audit_ref: str,
    corpus_audit_sha256: str,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    disposition = str(readiness.get("disposition") or "WAITING_FOR_DATA")
    status = "READY_TO_REAUDIT" if disposition == "READY_TO_REAUDIT" else "WAITING_FOR_DATA"
    return write_experiment_checkpoint(
        evidence_root=evidence_root,
        experiment_id=experiment_id,
        track_id=track_id,
        status=status,
        claim_ceiling=claim_ceiling,
        source_revision=source_revision,
        holdout_manifest_ref=holdout_manifest_ref,
        holdout_manifest_sha256=holdout_manifest_sha256,
        corpus_audit_ref=corpus_audit_ref,
        corpus_audit_sha256=corpus_audit_sha256,
        blockers=list(readiness.get("blockers") or []),
        resume_gate="TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT",
        next_allowed_action=(
            "T0_T1_REAUDIT_ONLY"
            if status == "READY_TO_REAUDIT"
            else "WAIT_FOR_MORE_VERIFIER_BACKED_TRAJECTORIES"
        ),
        evidence_refs=evidence_refs,
    )


def read_registered_experiment(
    *,
    repo_root: str | Path,
    canonical_state_root: str | Path,
    spec_name: str = "trajectory_verifier_v2_spec.json",
) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    spec_path = repo / "nexus" / "research" / "clm_system_one" / spec_name
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    continuity = dict(spec.get("continuity") or {})
    checkpoint_root = Path(canonical_state_root).expanduser().resolve() / str(
        continuity.get("checkpoint_relative_root") or "research/clm_system_one"
    )
    checkpoint = read_experiment_checkpoint(
        evidence_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
    )

    integrity: dict[str, bool] = {}
    for key in ("holdout_manifest", "last_corpus_audit", "last_experiment_report"):
        item = dict(spec.get(key) or {})
        rel = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        target = (repo / rel).resolve()
        if repo not in target.parents or not target.exists():
            integrity[key] = False
            continue
        integrity[key] = _sha256_bytes(target.read_bytes()) == expected

    checkpoint_matches_spec = bool(
        checkpoint.get("experiment_id") == spec.get("experiment_id")
        and checkpoint.get("track_id") == spec.get("track_id")
        and checkpoint.get("claim_ceiling") == spec.get("claim_ceiling")
        and checkpoint.get("holdout_manifest_sha256")
        == (spec.get("holdout_manifest") or {}).get("sha256")
        and checkpoint.get("corpus_audit_sha256")
        == (spec.get("last_corpus_audit") or {}).get("sha256")
        and checkpoint.get("auto_chain") is False
    )
    all_integrity_ok = all(integrity.values()) and checkpoint_matches_spec
    return {
        "schema": "nexus.research_experiment_readback.v1",
        "issue": spec.get("issue"),
        "experiment_id": spec.get("experiment_id"),
        "track_id": spec.get("track_id"),
        "spec_ref": str(spec_path.relative_to(repo)),
        "checkpoint_root": str(checkpoint_root),
        "checkpoint": checkpoint,
        "artifact_integrity": integrity,
        "checkpoint_matches_spec": checkpoint_matches_spec,
        "readback_ok": all_integrity_ok,
    }


def resolve_canonical_state_root() -> Path:
    configured = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path.home()
    for candidate in (
        home / "Workspace" / "Nexus-new-self-hosted-state",
        home / "workspace" / "Nexus-new-self-hosted-state",
    ):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("canonical Nexus state root is unavailable")


def _git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _write_readiness_snapshot(
    *,
    checkpoint_root: Path,
    experiment_id: str,
    track_id: str,
    readiness: Mapping[str, Any],
) -> tuple[str, str]:
    body = dict(readiness)
    digest = _sha256_json(body)
    slug = f"{experiment_id}__{track_id}"
    path = checkpoint_root / "experiments" / slug / "readiness" / f"{digest}.json"
    _write_create_only(path, _json_bytes(body))
    pointer = {
        "schema": "nexus.clm_trajectory_corpus_readiness_pointer.v1",
        "readiness_sha256": digest,
        "readiness_ref": str(path.relative_to(checkpoint_root)),
        "updated_at": body.get("observed_at") or _now(),
    }
    _atomic_replace(
        checkpoint_root / "experiments" / slug / "readiness.json",
        _json_bytes(pointer),
    )
    return str(path.relative_to(checkpoint_root)), digest


def _verified_preexecution_task_families(
    *,
    repo: Path,
    state_root: Path,
    evidence_root: Path,
    excluded_trajectory_ids: Sequence[str] = (),
    holdout_task_ids: Sequence[str] = (),
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Derive research family labels from pre-action, hash-bound Task Cards.

    Only an issuer's declaration already frozen by the canonical lifecycle
    state can count. There is no task-ID classifier, post-outcome labeling,
    silent fallback, or new authority store. Missing/ambiguous material is
    deliberately left unclassified.
    """
    families: dict[str, str] = {}
    provenance: dict[str, dict[str, str]] = {}
    rejected: set[str] = set()
    excluded_ids = set(excluded_trajectory_ids)
    holdout_ids = set(holdout_task_ids)
    outcomes_root = (evidence_root / "trajectory" / "outcomes").resolve()
    if not outcomes_root.is_dir():
        return families, provenance

    # The old readiness interface groups by task ID only. Until it has a
    # per-attempt provenance binding, reject a task entirely when its outcomes
    # span distinct attempts. Otherwise a later family declaration could
    # silently relabel an earlier, unproven trajectory.
    observed_attempts: dict[str, set[str]] = {}
    for path in sorted(outcomes_root.glob("*.json")):
        try:
            outcome = json.loads(path.read_text(encoding="utf-8"))
            task = str(outcome.get("task_id") or "")
            if (
                task
                and task not in holdout_ids
                and str(outcome.get("trajectory_id") or "") not in excluded_ids
            ):
                observed_attempts.setdefault(task, set()).add(str(outcome.get("attempt_id") or ""))
        except (OSError, ValueError, TypeError):
            continue
    rejected.update(
        task for task, attempts in observed_attempts.items() if len(attempts) > 1 or "" in attempts
    )

    def _one_card_field(text: str, key: str) -> str:
        pattern = re.compile(rf"^{re.escape(key)}:[ \t]*([^\r\n]*?)[ \t]*$", re.MULTILINE)
        found = pattern.findall(text)
        return found[0] if len(found) == 1 else ""

    for outcome_path in sorted(outcomes_root.glob("*.json")):
        try:
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            task_id = str(outcome.get("task_id") or "")
            if str(outcome.get("trajectory_id") or "") in excluded_ids or task_id in holdout_ids:
                continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id):
                continue
            if task_id in rejected:
                continue
            state_path = (state_root / f"{task_id}.json").resolve()
            if state_root.resolve() not in state_path.parents or not state_path.is_file():
                continue
            state = json.loads(state_path.read_text(encoding="utf-8"))
            contract = state.get("contract")
            if not isinstance(contract, Mapping) or not contract:
                continue
            if not all(
                str(row.get("task_id") or "") == task_id for row in (outcome, state, contract)
            ):
                continue
            attempt_id = str(outcome.get("attempt_id") or "")
            if not attempt_id or attempt_id != str(state.get("attempt_id") or ""):
                continue

            candidate_path = (
                evidence_root / str(outcome.get("candidate_evidence_ref") or "")
            ).resolve()
            if evidence_root not in candidate_path.parents or not candidate_path.is_file():
                continue
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            if (
                candidate.get("task_id") != task_id
                or candidate.get("attempt_id") != attempt_id
                or candidate.get("record_sha256") != outcome.get("candidate_record_sha256")
                or candidate.get("record_sha256")
                != _sha256_json({
                    key: value for key, value in candidate.items() if key != "record_sha256"
                })
                or candidate.get("task_contract_sha256") != _sha256_json(contract)
                or candidate.get("dataset_eligible") is not True
                or candidate.get("verifier_status") not in {"PASS", "FAIL"}
                or candidate.get("label_quality") not in _STRONG_LABELS
            ):
                continue
            target_rev = str(
                contract.get("target_base_revision") or contract.get("controller_revision") or ""
            )
            if target_rev and target_rev != str(candidate.get("source_revision") or ""):
                continue

            submitted = datetime.fromisoformat(str(state["submitted_at"]).replace("Z", "+00:00"))
            bound = datetime.fromisoformat(str(outcome["bound_at"]).replace("Z", "+00:00"))
            if submitted.tzinfo is None or bound.tzinfo is None or submitted > bound:
                continue

            card_rel = Path(str(state.get("task_card_path") or ""))
            if (
                card_rel.is_absolute()
                or ".." in card_rel.parts
                or len(card_rel.parts) < 3
                or card_rel.parts[0] != "tasks"
                or card_rel.suffix != ".md"
            ):
                continue
            card_revision = str(state.get("controller_revision") or "")
            expected_sha = str(state.get("task_card_hash") or "")
            if (
                not re.fullmatch(r"[0-9a-f]{40}", card_revision)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
                or contract.get("controller_revision") != card_revision
            ):
                continue
            # Source is the immutable Git object at the issuer's recorded
            # pre-execution revision, never the mutable current working tree.
            proc = subprocess.run(
                ["git", "show", f"{card_revision}:{card_rel.as_posix()}"],
                cwd=repo,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if proc.returncode != 0 or hashlib.sha256(proc.stdout).hexdigest() != expected_sha:
                continue
            text = proc.stdout.decode("utf-8")
            if f"task_id: `{task_id}`" not in text and f"task_id: {task_id}" not in text:
                continue
            # The issuer's metadata must occupy one explicit, frozen section;
            # arbitrary objective or example text cannot become a label.
            heading = "## Track 1 task-family declaration (issuer, pre-action)"
            if text.count(heading) != 1:
                continue
            section = text.split(heading, 1)[1].split("\n## ", 1)[0]
            taxonomy = _one_card_field(section, "track1_taxonomy")
            family = _one_card_field(section, "track1_family")
            rationale = _one_card_field(section, "track1_family_rationale")
            if (
                taxonomy != _TRACK1_FAMILY_TAXONOMY
                or family not in _TRACK1_FAMILY_CATEGORIES
                or len(rationale) < 15
            ):
                continue

            ref = {
                "family": family,
                "taxonomy": taxonomy,
                "verifier_status": str(candidate["verifier_status"]),
                "task_card_sha256": expected_sha,
                "task_contract_sha256": str(candidate["task_contract_sha256"]),
                "task_card_path": card_rel.as_posix(),
                "preexecution_revision": card_revision,
            }
            if task_id in families and provenance[task_id] != ref:
                rejected.add(task_id)
                families.pop(task_id, None)
                provenance.pop(task_id, None)
                continue
            families[task_id] = family
            provenance[task_id] = ref
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, subprocess.TimeoutExpired):
            # A corrupt, absent, stale or post-effect declaration never
            # manufactures an independently counted family.
            continue
    return families, provenance


def refresh_registered_experiment(
    *,
    repo_root: str | Path,
    candidate_evidence_root: str | Path | None = None,
    canonical_state_root: str | Path | None = None,
    spec_name: str = "trajectory_verifier_v2_spec.json",
) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    spec_path = repo / "nexus" / "research" / "clm_system_one" / spec_name
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    holdout_info = dict(spec.get("holdout_manifest") or {})
    holdout_path = (repo / str(holdout_info.get("path") or "")).resolve()
    if repo not in holdout_path.parents or not holdout_path.exists():
        raise ValueError("registered holdout manifest is unavailable")
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout_tasks = list(holdout.get("historical_replay_tasks") or [])
    corpus_exclusions = dict(spec.get("corpus_exclusions") or {})
    excluded_trajectories = list(corpus_exclusions.get("trajectory_ids") or [])

    evidence_root = (
        Path(candidate_evidence_root).expanduser().resolve()
        if candidate_evidence_root is not None
        else resolve_research_evidence_root(repo)
    )
    state_root = (
        Path(canonical_state_root).expanduser().resolve()
        if canonical_state_root is not None
        else resolve_canonical_state_root()
    )
    task_families, family_provenance = _verified_preexecution_task_families(
        repo=repo,
        state_root=state_root,
        evidence_root=evidence_root,
        excluded_trajectory_ids=excluded_trajectories,
        holdout_task_ids=holdout_tasks,
    )
    readiness = project_corpus_readiness(
        evidence_root=evidence_root,
        holdout_task_ids=holdout_tasks,
        task_family_by_task=task_families,
        excluded_trajectory_ids=excluded_trajectories,
    )
    # A derived, hash-sealed readback of family provenance. The Task Cards and
    # pre-execution state remain sole producers; this is not a second SSOT.
    readiness["task_family_provenance"] = family_provenance
    # The strong PASS and FAIL that unlock a family-disjoint re-audit must
    # themselves have proven family provenance. An unmapped historical PASS
    # must never complete the labeled family's binary coverage.
    verified_labels = [row["verifier_status"] for row in family_provenance.values()]
    readiness["mapped_family_strong_labels"] = {
        status: verified_labels.count(status) for status in ("PASS", "FAIL")
    }
    if not {"PASS", "FAIL"} <= set(verified_labels):
        readiness["blockers"].append("mapped_family_binary_coverage_unavailable")
        readiness["disposition"] = "WAITING_FOR_DATA"
    ordered = sorted(set(task_families.values()))
    readiness["family_disjoint_split_witness"] = (
        {
            "train_families": ordered[:-1],
            "dev_families": ordered[-1:],
            "train_dev_overlap": [],
        }
        if len(ordered) >= 2
        else None
    )
    continuity = dict(spec.get("continuity") or {})
    checkpoint_root = state_root / str(
        continuity.get("checkpoint_relative_root") or "research/clm_system_one"
    )
    readiness_ref, readiness_sha = _write_readiness_snapshot(
        checkpoint_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
        readiness=readiness,
    )
    audit = dict(spec.get("last_corpus_audit") or {})
    checkpoint = refresh_checkpoint_from_readiness(
        evidence_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
        readiness=readiness,
        claim_ceiling=str(spec.get("claim_ceiling") or "EXPERIMENTAL_SHADOW_ONLY"),
        source_revision=_git_head(repo),
        holdout_manifest_ref=str(holdout_info.get("path") or ""),
        holdout_manifest_sha256=str(holdout_info.get("sha256") or ""),
        corpus_audit_ref=str(audit.get("path") or ""),
        corpus_audit_sha256=str(audit.get("sha256") or ""),
        evidence_refs=[
            f"readiness:{readiness_sha}:{readiness_ref}",
            "github:James3014/Nexus-new#1197",
        ],
    )
    return {
        "schema": "nexus.research_experiment_refresh.v1",
        "readiness": readiness,
        "readiness_ref": readiness_ref,
        "readiness_sha256": readiness_sha,
        "checkpoint": checkpoint,
    }
