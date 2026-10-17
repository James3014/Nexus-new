"""Record-backed ``EffectAuthorityPort`` for governed runtime runs (#2344).

Owner decision (James, 2026-10-16, recorded on #2344): "do it".

nexus-runtime's effect authorization host only integrity-checks a request's
``effect_authorization``: its ``authorization_hash`` is an unkeyed self-hash and
``authority_id`` / ``authority_ref`` are caller-asserted, so a caller can
self-sign a broader authorization. This module supplies the host-side check:
an authorization is accepted only when ``authority_ref`` names an existing
Nexus-new authority record (a BOOTSTRAP agent-authority record or a valid
Owner standing-grant receipt), the authority id and repository equal the
record's, and every requested effect domain is present in the record with the
same constraints. Anything else, including any lookup error, is a refusal.

Rollout (#2344): measured first. Normal governed runs carry no runtime
``effect_authorization`` today and the existing records are not shaped as
runtime effect ceilings, so strict mode would refuse every normal governed run.
The default is therefore SHADOW: the decision is evaluated and recorded as
``effect_authority_shadow`` but not enforced. ``NEXUS_EFFECT_AUTHORITY_STRICT=1``
only ENABLES strict mode (port attached and ``require_effect_authority=True``);
no value of it weakens any existing check.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus_runtime.execution_coordination import (
    EffectAuthorityPort,
    EffectAuthorization,
    EffectAuthorizationError,
)

logger = logging.getLogger(__name__)

STRICT_ENV = "NEXUS_EFFECT_AUTHORITY_STRICT"
SHADOW_FIELD = "effect_authority_shadow"
DECISION_ALLOW = "ALLOW"
DECISION_WOULD_REFUSE = "WOULD_REFUSE"
BOOTSTRAP_AUTHORITY_ID = "bootstrap_agent"

RecordLookup = Callable[[str], "Mapping[str, Any] | None"]


def strict_enabled() -> bool:
    """True only when the operator explicitly enabled strict enforcement."""
    return os.environ.get(STRICT_ENV, "").strip() == "1"


def _bootstrap_record(directory: Path, authority_ref: str) -> dict[str, Any] | None:
    from nexus.orchestrator import bootstrap_agent_authority as bootstrap

    path = directory / bootstrap.RECORD_FILENAME
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise EffectAuthorizationError("bootstrap authority record file is unsafe")
        raw = bootstrap._read_all(fd)
    finally:
        os.close(fd)
    # A tampered or forked chain backs nothing.
    bootstrap._verify_chain(raw)
    for line in raw.split(b"\n"):
        if not line:
            continue
        record = json.loads(line.decode("utf-8"))
        if record.get("record_hash") != authority_ref:
            continue
        repository = record.get("repository")
        return {
            "authority_id": BOOTSTRAP_AUTHORITY_ID,
            "repository": (
                repository.get("repository_id") if isinstance(repository, Mapping) else None
            ),
            "effects": {str(record.get("effect")): record.get("effect_payload")},
        }
    return None


def _standing_grant_record(authority_ref: str, now: datetime) -> dict[str, Any] | None:
    from nexus.orchestrator import standing_grant_store as store

    for path, _key, structural in store._structural_entries():
        if structural.receipt_hash != authority_ref:
            continue
        # Re-load with the time checks: expired, revoked or not-yet-valid raises.
        receipt = store._load_receipt_at(path, now=now)
        return {
            "authority_id": receipt.grant_id,
            "repository": receipt.context.repository.repository_id,
            "effects": {action.value: {} for action in receipt.context.allowed_actions},
        }
    return None


def production_record_lookup(authority_ref: str) -> dict[str, Any] | None:
    """Find the authority record ``authority_ref`` names, read-only.

    Sources are the existing machine-local authority directory: the BOOTSTRAP
    agent-authority chain (by ``record_hash``) and the Owner standing-grant
    receipts (by ``receipt_hash``). Returns a projection
    ``{authority_id, repository, effects}`` or ``None``.
    """
    from nexus.orchestrator import standing_grant_store as store

    directory = store.DEFAULT_RECEIPT_PATH.parent
    record = _bootstrap_record(directory, authority_ref)
    if record is not None:
        return record
    return _standing_grant_record(authority_ref, datetime.now(timezone.utc))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def evaluate_authorization(
    authorization: EffectAuthorization, lookup: RecordLookup
) -> tuple[bool, str]:
    """Return ``(accepted, reason)``; accepted only on an exact record match."""
    try:
        record = lookup(authorization.authority_ref)
    except Exception as exc:  # any lookup failure backs nothing
        return False, f"RECORD_LOOKUP_FAILED:{type(exc).__name__}"
    if not isinstance(record, Mapping):
        return False, "NO_RECORD_FOR_AUTHORITY_REF"
    if record.get("authority_id") != authorization.authority_id:
        return False, "AUTHORITY_ID_MISMATCH"
    if record.get("repository") != authorization.repository:
        return False, "REPOSITORY_MISMATCH"
    recorded = record.get("effects")
    if not isinstance(recorded, Mapping):
        return False, "RECORD_EFFECTS_MALFORMED"
    for domain, constraints in authorization.effects.items():
        if domain not in recorded:
            return False, f"EFFECT_BROADER_THAN_RECORD:{domain}"
        if _canonical(constraints) != _canonical(recorded[domain]):
            return False, f"EFFECT_CONSTRAINTS_DIFFER_FROM_RECORD:{domain}"
    return True, "RECORD_MATCH"


def record_backed_port(lookup: RecordLookup = production_record_lookup) -> EffectAuthorityPort:
    """An ``EffectAuthorityPort`` that returns True only on an exact record match."""

    def verifier(authorization: EffectAuthorization) -> bool:
        accepted, _reason = evaluate_authorization(authorization, lookup)
        return accepted is True

    return EffectAuthorityPort(verifier)


def shadow_decision(
    request: Any, lookup: RecordLookup = production_record_lookup
) -> dict[str, Any]:
    """What strict mode would decide for ``request``, without enforcing it."""
    raw = request.get("effect_authorization") if isinstance(request, Mapping) else None
    if not isinstance(raw, Mapping):
        return {
            "decision": DECISION_WOULD_REFUSE,
            "reason": "NO_EFFECT_AUTHORIZATION_ON_REQUEST",
        }
    try:
        authorization = EffectAuthorization.from_mapping(raw)
    except EffectAuthorizationError as exc:
        return {"decision": DECISION_WOULD_REFUSE, "reason": f"AUTHORIZATION_INVALID:{exc}"}
    accepted, reason = evaluate_authorization(authorization, lookup)
    return {
        "decision": DECISION_ALLOW if accepted else DECISION_WOULD_REFUSE,
        "reason": reason,
        "authority_ref": authorization.authority_ref,
    }
