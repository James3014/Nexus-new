"""Durable, transport-neutral repository mutation admission receipts.

Admission is a Nexus governance projection. It grants no route, worker/model,
verification, acceptance, merge, release, deploy, or production authority.
The receipt is stored under the existing canonical self-hosted state root so it
does not create a second operation database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

SCHEMA = "nexus.mutation_admission.v1"
BINDING_SCHEMA = "nexus.mutation_admission_binding.v1"
_ALLOWED_LANES = frozenset({"DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED"})
_ALLOWED_AUTHORITY = frozenset({"OWNER_INLINE", "TRACKED_TASK_CARD"})
CANONICAL_REPOSITORIES = frozenset({
    "James3014/devspace",
    "James3014/Nexus-new",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine",
    "James3014/nexus-runtime",
    "James3014/nexus-opencli-reviewer",
    "James3014/nexus-deployment-lab",
})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ADMISSION = re.compile(r"^admission-[0-9a-f]{32}$")


class MutationAdmissionError(RuntimeError):
    """Admission request, receipt, or persistence failure."""


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _receipt_hash(payload: Mapping[str, Any]) -> str:
    value = dict(payload)
    value.pop("receipt_hash", None)
    return canonical_hash(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_time(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MutationAdmissionError(f"{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None:
        raise MutationAdmissionError(f"{field.upper()}_INVALID")
    return parsed.astimezone(timezone.utc)


def _validate_authority_reference(
    value: object,
    *,
    operation_id: str,
    repository: str,
    base_sha: str,
    execution_lane: str,
    allowed_paths: tuple[str, ...] | list[str],
    issue_number: int | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_REQUIRED")
    reference = dict(value)
    if (
        reference.get("schema") != "nexus.standing_grant_effect_authorization.v1"
        or reference.get("mutation_authorized") is not True
        or reference.get("owner_id") != "James3014"
        or reference.get("action") != "TASK_SUBMIT"
    ):
        raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_INVALID")
    for field in ("grant_receipt_hash", "effect_hash", "authorization_hash", "standing_grant_key"):
        if not _SHA64.fullmatch(str(reference.get(field) or "")):
            raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_INVALID")
    effect = reference.get("effect")
    expected_effect = {
        "operation_id": operation_id,
        "target_repository": repository,
        "base_sha": base_sha,
        "execution_lane": execution_lane,
        "allowed_paths": list(allowed_paths),
        "issue_number": issue_number,
    }
    if not isinstance(effect, Mapping) or dict(effect) != expected_effect:
        raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_MISMATCH")
    if reference["effect_hash"] != canonical_hash(effect):
        raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_MISMATCH")
    authorization_payload = dict(reference)
    supplied_authorization_hash = str(authorization_payload.pop("authorization_hash"))
    if supplied_authorization_hash != canonical_hash(authorization_payload):
        raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_MISMATCH")
    return reference


def _validate_repo(value: str) -> str:
    repository = str(value).strip()
    if repository not in CANONICAL_REPOSITORIES:
        raise MutationAdmissionError("REPOSITORY_NOT_CANONICAL")
    return repository


def _validate_scope(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 64:
        raise MutationAdmissionError("ALLOWED_PATHS_REQUIRED")
    result: list[str] = []
    for raw in values:
        token = str(raw).strip()
        directory = token.endswith("/**")
        base = token[:-3] if directory else token
        if not base or base.startswith("/") or "\\" in base or any(ch in base for ch in "*?[]"):
            raise MutationAdmissionError("ALLOWED_PATH_INVALID")
        path = PurePosixPath(base)
        if ".." in path.parts or ".git" in path.parts or path.as_posix() != base:
            raise MutationAdmissionError("ALLOWED_PATH_INVALID")
        normalized = base + "/**" if directory else base
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def path_is_allowed(path: str, allowed_paths: tuple[str, ...] | list[str]) -> bool:
    candidate = str(path).strip()
    if not candidate or candidate.startswith("/") or "\\" in candidate:
        return False
    pure = PurePosixPath(candidate)
    if ".." in pure.parts or ".git" in pure.parts or pure.as_posix() != candidate:
        return False
    for pattern in allowed_paths:
        if pattern.endswith("/**"):
            root = pattern[:-3].rstrip("/")
            if candidate == root or candidate.startswith(root + "/"):
                return True
        elif candidate == pattern:
            return True
    return False


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dict(payload), fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def validate_receipt(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    expected_receipt_hash: str | None = None,
) -> dict[str, Any]:
    value = dict(payload)
    if value.get("schema") != SCHEMA:
        raise MutationAdmissionError("ADMISSION_SCHEMA_INVALID")
    if not _ADMISSION.fullmatch(str(value.get("admission_id") or "")):
        raise MutationAdmissionError("ADMISSION_ID_INVALID")
    operation_id = str(value.get("operation_id") or "")
    if not _OPERATION.fullmatch(operation_id):
        raise MutationAdmissionError("OPERATION_ID_INVALID")
    _validate_repo(str(value.get("repository") or ""))
    if not _SHA40.fullmatch(str(value.get("base_sha") or "")):
        raise MutationAdmissionError("BASE_SHA_INVALID")
    lane = str(value.get("execution_lane") or "")
    authority = str(value.get("authority_kind") or "")
    if lane not in _ALLOWED_LANES or authority not in _ALLOWED_AUTHORITY:
        raise MutationAdmissionError("ADMISSION_AUTHORITY_INVALID")
    scope = _validate_scope(list(value.get("allowed_paths") or []))
    issue_number = value.get("issue_number")
    if issue_number is not None and (
        not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1
    ):
        raise MutationAdmissionError("ISSUE_NUMBER_INVALID")
    if lane == "GOVERNED":
        task_id = str(value.get("task_id") or "")
        attempt_id = str(value.get("attempt_id") or "")
        governance_source_head = str(value.get("governance_source_head") or "")
        if (
            authority != "TRACKED_TASK_CARD"
            or issue_number is None
            or not _OPERATION.fullmatch(task_id)
            or not _OPERATION.fullmatch(attempt_id)
            or not value.get("task_card_path")
            or not _SHA64.fullmatch(str(value.get("task_card_hash") or ""))
            or not _SHA40.fullmatch(governance_source_head)
        ):
            raise MutationAdmissionError("GOVERNED_TASK_CARD_REQUIRED")
        if value.get("authority_reference") is not None:
            raise MutationAdmissionError("GOVERNED_OWNER_AUTHORITY_INVALID")
    else:
        if authority != "OWNER_INLINE":
            raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_REQUIRED")
        _validate_authority_reference(
            value.get("authority_reference"),
            operation_id=operation_id,
            repository=str(value.get("repository") or ""),
            base_sha=str(value.get("base_sha") or ""),
            execution_lane=lane,
            allowed_paths=scope,
            issue_number=issue_number,
        )
        if any(
            value.get(field) is not None
            for field in (
                "task_id",
                "attempt_id",
                "task_card_path",
                "task_card_hash",
                "governance_source_head",
            )
        ):
            raise MutationAdmissionError("DIRECT_TASK_CARD_INVALID")
    issued = _parse_time(value.get("issued_at"), "issued_at")
    expires = _parse_time(value.get("expires_at"), "expires_at")
    if expires <= issued:
        raise MutationAdmissionError("ADMISSION_EXPIRY_INVALID")
    current = (now or _utc_now()).astimezone(timezone.utc)
    if expires <= current:
        raise MutationAdmissionError("ADMISSION_EXPIRED")
    supplied = str(value.get("receipt_hash") or "")
    actual = _receipt_hash(value)
    if not _SHA64.fullmatch(supplied) or supplied != actual:
        raise MutationAdmissionError("ADMISSION_RECEIPT_HASH_MISMATCH")
    if expected_receipt_hash is not None and supplied != expected_receipt_hash:
        raise MutationAdmissionError("ADMISSION_RECEIPT_HASH_MISMATCH")
    return value


def pr_binding(receipt: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_receipt(receipt)
    return {
        "schema": BINDING_SCHEMA,
        "admission_id": validated["admission_id"],
        "receipt_hash": validated["receipt_hash"],
    }


def pr_binding_block(receipt: Mapping[str, Any]) -> str:
    binding = pr_binding(receipt)
    return (
        "<!-- NEXUS_MUTATION_ADMISSION_V1\n"
        + json.dumps(binding, sort_keys=True, separators=(",", ":"))
        + "\nNEXUS_MUTATION_ADMISSION_V1 -->"
    )


class MutationAdmissionStore:
    """Durable receipt projection under the existing Nexus canonical state root."""

    def __init__(
        self,
        state_root: str | Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.root = self.state_root / "mutation-admissions"
        self._now_provider = now_provider or _utc_now

    @staticmethod
    def _admission_id(operation_id: str) -> str:
        if not _OPERATION.fullmatch(operation_id):
            raise MutationAdmissionError("OPERATION_ID_INVALID")
        return "admission-" + hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:32]

    def _path(self, admission_id: str) -> Path:
        if not _ADMISSION.fullmatch(admission_id):
            raise MutationAdmissionError("ADMISSION_ID_INVALID")
        return self.root / f"{admission_id}.json"

    def admit(
        self,
        *,
        operation_id: str,
        repository: str,
        base_sha: str,
        execution_lane: str,
        authority_kind: str,
        allowed_paths: list[str] | tuple[str, ...],
        authority_reference: Mapping[str, Any] | None = None,
        issue_number: int | None = None,
        task_id: str | None = None,
        attempt_id: str | None = None,
        task_card_path: str | None = None,
        task_card_hash: str | None = None,
        governance_source_head: str | None = None,
        ttl_minutes: int = 10080,
        runtime_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        repository = _validate_repo(repository)
        operation_id = str(operation_id).strip()
        admission_id = self._admission_id(operation_id)
        if not _SHA40.fullmatch(str(base_sha)):
            raise MutationAdmissionError("BASE_SHA_INVALID")
        lane = str(execution_lane).strip().upper()
        authority = str(authority_kind).strip().upper()
        if lane not in _ALLOWED_LANES or authority not in _ALLOWED_AUTHORITY:
            raise MutationAdmissionError("ADMISSION_AUTHORITY_INVALID")
        scope = _validate_scope(allowed_paths)
        if issue_number is not None and (
            not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1
        ):
            raise MutationAdmissionError("ISSUE_NUMBER_INVALID")
        if (
            not isinstance(ttl_minutes, int)
            or isinstance(ttl_minutes, bool)
            or not 5 <= ttl_minutes <= 43200
        ):
            raise MutationAdmissionError("TTL_MINUTES_INVALID")
        normalized_task_id = str(task_id).strip() if task_id is not None else None
        normalized_attempt_id = str(attempt_id).strip() if attempt_id is not None else None
        normalized_governance_head = (
            str(governance_source_head).strip() if governance_source_head is not None else None
        )
        if lane == "GOVERNED":
            if (
                authority != "TRACKED_TASK_CARD"
                or issue_number is None
                or not normalized_task_id
                or not _OPERATION.fullmatch(normalized_task_id)
                or not normalized_attempt_id
                or not _OPERATION.fullmatch(normalized_attempt_id)
                or not task_card_path
                or not _SHA64.fullmatch(str(task_card_hash or ""))
                or not normalized_governance_head
                or not _SHA40.fullmatch(normalized_governance_head)
            ):
                raise MutationAdmissionError("GOVERNED_TASK_CARD_REQUIRED")
            if authority_reference is not None:
                raise MutationAdmissionError("GOVERNED_OWNER_AUTHORITY_INVALID")
        else:
            if authority != "OWNER_INLINE":
                raise MutationAdmissionError("DIRECT_OWNER_AUTHORITY_REQUIRED")
            _validate_authority_reference(
                authority_reference,
                operation_id=operation_id,
                repository=repository,
                base_sha=str(base_sha),
                execution_lane=lane,
                allowed_paths=scope,
                issue_number=issue_number,
            )
            if any(
                value is not None
                for value in (
                    normalized_task_id,
                    normalized_attempt_id,
                    task_card_path,
                    task_card_hash,
                    normalized_governance_head,
                )
            ):
                raise MutationAdmissionError("DIRECT_TASK_CARD_INVALID")

        request = {
            "operation_id": operation_id,
            "repository": repository,
            "base_sha": str(base_sha),
            "execution_lane": lane,
            "authority_kind": authority,
            "allowed_paths": list(scope),
            "issue_number": issue_number,
            "task_id": normalized_task_id,
            "attempt_id": normalized_attempt_id,
            "task_card_path": task_card_path,
            "task_card_hash": task_card_hash,
            "governance_source_head": normalized_governance_head,
            "ttl_minutes": ttl_minutes,
        }
        request_hash = canonical_hash(request)
        path = self._path(admission_id)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise MutationAdmissionError("ADMISSION_RECORD_INVALID") from exc
            validated = validate_receipt(existing, now=self._now_provider())
            if validated.get("request_hash") != request_hash:
                raise MutationAdmissionError("OPERATION_ID_REUSED_WITH_DIFFERENT_ADMISSION")
            return {
                **validated,
                "duplicate": True,
                "pr_binding": pr_binding(validated),
                "pr_binding_block": pr_binding_block(validated),
            }

        issued = self._now_provider().astimezone(timezone.utc)
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "admission_id": admission_id,
            **request,
            "issued_at": _iso(issued),
            "expires_at": _iso(issued + timedelta(minutes=ttl_minutes)),
            "runtime_identity": dict(runtime_identity or {}),
            "authority_reference": (
                dict(authority_reference) if authority_reference is not None else None
            ),
            "request_hash": request_hash,
            "receipt_hash": "",
        }
        payload["receipt_hash"] = _receipt_hash(payload)
        _atomic_json_write(path, payload)
        validated = validate_receipt(payload, now=issued)
        return {
            **validated,
            "duplicate": False,
            "pr_binding": pr_binding(validated),
            "pr_binding_block": pr_binding_block(validated),
        }

    def status(
        self,
        admission_id: str,
        *,
        expected_receipt_hash: str | None = None,
    ) -> dict[str, Any]:
        path = self._path(str(admission_id))
        if not path.is_file():
            raise MutationAdmissionError("ADMISSION_NOT_FOUND")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MutationAdmissionError("ADMISSION_RECORD_INVALID") from exc
        validated = validate_receipt(
            payload,
            now=self._now_provider(),
            expected_receipt_hash=expected_receipt_hash,
        )
        return {
            **validated,
            "status": "VALID",
            "duplicate": False,
            "pr_binding": pr_binding(validated),
            "pr_binding_block": pr_binding_block(validated),
        }
