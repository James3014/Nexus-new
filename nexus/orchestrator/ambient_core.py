from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping, Protocol

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SESSION_RE = re.compile(r"^cms_[0-9a-f]{32}$")
_COMMIT_RE = re.compile(r"^git-commit:[0-9a-f]{40}$")
_TREE_RE = re.compile(r"^git-tree:[0-9a-f]{40}$")
CORE_RESPONSE_SCHEMA = "nexus.core.generic-verification-response.v1-experimental"
PREPARATION_SCHEMA = "nexus.ambient-core-preparation.v1"
VERIFICATION_PROJECTION_SCHEMA = "nexus.ambient-core-verification-projection.v1"


class AmbientCoreControlPort(Protocol):
    """Host transport boundary; it owns no route, lane, worker or completion truth."""

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def revalidate_mutation_binding(
        self, preparation: Mapping[str, Any], **kwargs: Any
    ) -> None: ...

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]: ...


def ambient_core_required(request: Mapping[str, Any]) -> bool:
    value = request.get("core_envelope_required", False)
    if type(value) is not bool:
        raise ValueError("core_envelope_required must be boolean")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\0" in value:
        raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
    return value


def normalize_preparation(value: Mapping[str, Any], *, attempt_id: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise RuntimeError("AMBIENT_CORE_PREPARATION_INVALID")
    normalized = {
        "schema": PREPARATION_SCHEMA,
        "session_id": _required_text(value.get("session_id"), "session_id"),
        "binding_id": _required_text(value.get("binding_id"), "binding_id"),
        "binding_hash": _required_text(value.get("binding_hash"), "binding_hash"),
        "operation_id": _required_text(value.get("operation_id"), "operation_id"),
        "attempt_id": _required_text(value.get("attempt_id"), "attempt_id"),
        "acceptance_contract_hash": _required_text(
            value.get("acceptance_contract_hash"), "acceptance_contract_hash"
        ),
        "source_revision": _required_text(value.get("source_revision"), "source_revision"),
        "source_tree": _required_text(value.get("source_tree"), "source_tree"),
    }
    if not _SESSION_RE.fullmatch(normalized["session_id"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:session_id")
    for field in ("binding_hash", "acceptance_contract_hash"):
        if not _HASH_RE.fullmatch(normalized[field]):
            raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
    if not _COMMIT_RE.fullmatch(normalized["source_revision"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:source_revision")
    if not _TREE_RE.fullmatch(normalized["source_tree"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:source_tree")
    if normalized["attempt_id"] != attempt_id:
        raise RuntimeError("AMBIENT_CORE_ATTEMPT_MISMATCH")
    return normalized


def normalize_verification_projection(
    value: Mapping[str, Any],
    *,
    preparation: Mapping[str, Any],
    candidate_state_hash: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("AMBIENT_CORE_VERIFICATION_INVALID")
    if value.get("session_id") != preparation.get("session_id"):
        raise RuntimeError("AMBIENT_CORE_SESSION_MISMATCH")
    if value.get("binding_hash") != preparation.get("binding_hash"):
        raise RuntimeError("AMBIENT_CORE_BINDING_MISMATCH")
    if value.get("candidate_state_hash") != candidate_state_hash:
        raise RuntimeError("AMBIENT_CORE_CANDIDATE_STATE_MISMATCH")
    response = value.get("core_response")
    if not isinstance(response, Mapping) or response.get("schema") != CORE_RESPONSE_SCHEMA:
        raise RuntimeError("AMBIENT_CORE_RESPONSE_SCHEMA_MISMATCH")
    verification = response.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "VERIFIED":
        raise RuntimeError("AMBIENT_CORE_FAILED_VERIFICATION")
    hashes = response.get("hashes")
    if not isinstance(hashes, Mapping):
        raise RuntimeError("AMBIENT_CORE_HASHES_MISSING")
    required_hashes = (
        "acceptance_contract_hash",
        "change_set_hash",
        "verification_plan_hash",
        "evidence_bundle_hash",
        "change_manifest_hash",
    )
    normalized_hashes: dict[str, str] = {}
    for field in required_hashes:
        item = _required_text(hashes.get(field), field)
        if not _HASH_RE.fullmatch(item):
            raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
        normalized_hashes[field] = item
    if normalized_hashes["acceptance_contract_hash"] != preparation.get("acceptance_contract_hash"):
        raise RuntimeError("AMBIENT_CORE_CONTRACT_HASH_MISMATCH")
    projection = {
        "schema": VERIFICATION_PROJECTION_SCHEMA,
        "session_id": preparation["session_id"],
        "binding_hash": preparation["binding_hash"],
        "candidate_state_hash": candidate_state_hash,
        "core_response": {
            "protocol_version": response.get("protocol_version"),
            "schema": response["schema"],
            "verification": dict(verification),
            "hashes": normalized_hashes,
            "certification": response.get("certification"),
        },
    }
    return projection


def projection_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# --- Evidence Coverage verdict (#2181) -------------------------------------
#
# The host records Core's verdict durably for both outcomes. It never decides
# coverage itself: entries, categories and status come from Core. The host
# only checks that the verdict is bound to the declared universe and to a
# pinned Core revision, and refuses commit otherwise. A verdict carries no
# approval, merge or release field.

CORE_VERDICT_SCHEMA = "nexus.ambient-core-verdict.v1"
CORE_REVISION_PINNED = "CORE_REVISION_PINNED"
_COVERAGE_SATISFIED = frozenset({"COVERED", "CONDITIONALLY_NOT_APPLICABLE"})


class AmbientCoreVerdictBlocked(RuntimeError):
    """Core-required verification blocked; ``receipt`` is the durable blocked receipt."""

    def __init__(self, message: str, *, receipt: Any = None, verdict: Mapping[str, Any]):
        super().__init__(message)
        self.receipt = receipt
        self.verdict = dict(verdict)


def _declared_universe(contract: Any) -> dict[str, Any] | None:
    universe = getattr(contract, "expected_evidence", None)
    if universe is None:
        return None
    dump = getattr(universe, "model_dump", None)
    value = dump(mode="json") if callable(dump) else universe
    if not isinstance(value, Mapping):
        raise RuntimeError("AMBIENT_CORE_UNIVERSE_INVALID")
    return dict(value)


_SUBJECT_FIELDS = ("logical_subject_id", "evidence_kind", "requirement_mode", "applicability")


def _subject_tuple(value: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(getattr(value.get(field), "value", value.get(field))) for field in _SUBJECT_FIELDS
    )


def _core_expected_universe_identity() -> Callable[[Mapping[str, Any]], Any]:
    """Core's public ``expected_universe_identity`` from the pinned Core (#2246).

    Resolved through the Core transport, which owns the import of the
    configured Core and its shadowing guard. Raises when Core is unavailable;
    the host never falls back to its own copy of the formula.
    """
    from nexus.orchestrator import canonical_core_transport as transport

    if not transport.CORE_AVAILABLE:
        raise RuntimeError("CORE_UNIVERSE_IDENTITY_UNAVAILABLE")
    return transport.expected_universe_identity


def core_universe_identity(universe: Mapping[str, Any]) -> str:
    """The identity Core assigns to this declared universe.

    Computed on the host from the card declaration with Core's public
    ``product.protocol.generic_verification.expected_universe_identity``, over
    the same wire projection the transport sends, so a Core response cannot
    redefine it and the host keeps no copy of the formula. Raises
    ``RuntimeError`` when Core cannot compute it.
    """
    from types import SimpleNamespace

    from nexus.orchestrator.canonical_core_transport import project_expected_evidence_universe

    # Exactly the universe part of the wire contract the transport sends Core
    # (same projection, order and generation), so both identities agree.
    wire_contract = project_expected_evidence_universe(SimpleNamespace(expected_evidence=universe))
    if wire_contract is None:
        raise RuntimeError("CORE_UNIVERSE_IDENTITY_INVALID")
    try:
        identity = _core_expected_universe_identity()(wire_contract)
    except RuntimeError:
        raise
    except Exception as exc:  # Core rejected the declaration's shape
        raise RuntimeError(f"CORE_UNIVERSE_IDENTITY_INVALID:{type(exc).__name__}") from exc
    if not isinstance(identity, str) or not _HASH_RE.fullmatch(identity):
        raise RuntimeError("CORE_UNIVERSE_IDENTITY_INVALID")
    return identity


def _coverage_binding_errors(
    coverage: Mapping[str, Any], universe: Mapping[str, Any], identity: str | None
) -> list[str]:
    """Every way Core coverage can fail to be exactly the declared universe.

    ``identity`` is the card-derived Core identity (None when unavailable,
    which the caller already reports as blocking).
    """
    errors: list[str] = []
    if coverage.get("universe_generation") != universe.get("universe_generation"):
        errors.append("CORE_COVERAGE_GENERATION_MISMATCH")
    if identity is None or coverage.get("universe_identity") != identity:
        errors.append("CORE_COVERAGE_IDENTITY_MISMATCH")
    if coverage.get("unexpected_subjects"):
        errors.append("CORE_COVERAGE_UNEXPECTED_SUBJECTS")
    raw_entries = coverage.get("entries")
    entries = raw_entries if isinstance(raw_entries, list) else []
    if not all(isinstance(entry, Mapping) for entry in entries):
        errors.append("CORE_COVERAGE_MALFORMED")
        entries = [entry for entry in entries if isinstance(entry, Mapping)]
    declared = sorted(_subject_tuple(subject) for subject in universe.get("subjects") or ())
    observed = sorted(_subject_tuple(entry) for entry in entries)
    # Exact multiset equality: a missing, extra, duplicated or re-kinded
    # subject is never coverage of the declaration.
    if observed != declared or len(set(declared)) != len(declared):
        errors.append("CORE_COVERAGE_UNIVERSE_MISMATCH")
    if any(entry.get("category") not in _COVERAGE_SATISFIED for entry in entries):
        errors.append("CORE_COVERAGE_INCOMPLETE")
    return errors


def build_core_verdict(
    *,
    contract: Any,
    projection: Mapping[str, Any] | None,
    transport_error: str | None = None,
) -> dict[str, Any]:
    """Project one Core result (or its absence) into a durable host verdict.

    ``blocking`` is True unless Core VERIFIED the candidate and, for a task
    with a declared universe, the coverage is bound to that universe and to
    a pinned Core revision.
    """
    universe = _declared_universe(contract)
    declared = universe is not None
    host_reasons: list[str] = []
    core_status = None
    reason_codes: list[str] = []
    integrity = None
    coverage = None
    provenance = None
    response_hashes: Mapping[str, Any] | None = None
    card_identity: str | None = None
    if declared:
        try:
            card_identity = core_universe_identity(universe)
        except RuntimeError as exc:
            # A failed transport already blocks and names the root cause.
            if transport_error is None:
                host_reasons.append(str(exc) or "CORE_UNIVERSE_IDENTITY_UNAVAILABLE")
    if transport_error is not None:
        host_reasons.append(transport_error)
    elif not isinstance(projection, Mapping):
        host_reasons.append("AMBIENT_CORE_VERIFICATION_INVALID")
    else:
        response = projection.get("core_response")
        verification = response.get("verification") if isinstance(response, Mapping) else None
        raw_hashes = response.get("hashes") if isinstance(response, Mapping) else None
        response_hashes = raw_hashes if isinstance(raw_hashes, Mapping) else None
        if isinstance(verification, Mapping):
            core_status = verification.get("status")
            reason_codes = [str(item) for item in verification.get("reason_codes") or ()]
            integrity = verification.get("integrity")
            raw_coverage = verification.get("coverage")
            coverage = json.loads(json.dumps(raw_coverage)) if raw_coverage is not None else None
        raw_provenance = projection.get("core_provenance")
        if isinstance(raw_provenance, Mapping):
            provenance = json.loads(json.dumps(dict(raw_provenance), default=str))
        if core_status != "VERIFIED":
            host_reasons.append(f"AMBIENT_CORE_FAILED_VERIFICATION:{core_status or 'MISSING'}")
    if declared and transport_error is None and isinstance(projection, Mapping):
        if not isinstance(provenance, Mapping) or provenance.get("status") != CORE_REVISION_PINNED:
            status = provenance.get("status") if isinstance(provenance, Mapping) else None
            host_reasons.append(f"CORE_PROVENANCE_NOT_PINNED:{status or 'MISSING'}")
        if not isinstance(coverage, Mapping):
            host_reasons.append("CORE_COVERAGE_MISSING")
        else:
            host_reasons.extend(_coverage_binding_errors(coverage, universe, card_identity))
    # Core reports the identity it bound the contract to (#266). When present
    # it must be the card-derived one; a legacy (no-universe) task never has one.
    if (
        transport_error is None
        and response_hashes is not None
        and "universe_identity" in response_hashes
        and (card_identity is None or response_hashes.get("universe_identity") != card_identity)
    ):
        host_reasons.append("CORE_RESPONSE_UNIVERSE_IDENTITY_MISMATCH")
    blocking = bool(host_reasons)
    # The one comparison that must hold (#2451): the card universe under Core's
    # formula against the identity Core's coverage carries (and the identity
    # Core's response hashes report, when present). None for a legacy task,
    # which declares no universe; False whenever a side is missing or differs.
    coverage_identity = coverage.get("universe_identity") if isinstance(coverage, Mapping) else None
    response_identity_agrees = (
        response_hashes is None
        or "universe_identity" not in response_hashes
        or response_hashes.get("universe_identity") == card_identity
    )
    identity_matches = (
        (
            card_identity is not None
            and coverage_identity == card_identity
            and response_identity_agrees
        )
        if declared
        else None
    )
    return {
        "schema": CORE_VERDICT_SCHEMA,
        "core_status": core_status,
        "reason_codes": sorted(set(reason_codes)),
        "integrity": integrity,
        "host_reason_codes": host_reasons,
        "blocking": blocking,
        "universe_declared": declared,
        "universe_generation": universe.get("universe_generation") if declared else None,
        # Two identities, named for their formula: the Nexus contract hash of
        # the card universe, and the Core identity that coverage must carry.
        "contract_universe_identity": (
            getattr(contract, "universe_identity", None) if declared else None
        ),
        "core_universe_identity": card_identity,
        # contract_universe_identity uses the Nexus contract formula and never
        # equals either Core identity; read this flag, not that comparison.
        "core_universe_identity_matches": identity_matches,
        # Coverage is claimed only for a declared universe, never for legacy.
        "coverage": coverage if declared else None,
        "coverage_complete": bool(declared and not blocking),
        "core_provenance": provenance,
        "projection_hash": projection_hash(projection) if isinstance(projection, Mapping) else None,
    }


def live_core_db_path(state_dir: Any) -> str:
    """Core session DB for one self-hosted state root (never a shared /tmp path)."""
    from pathlib import Path

    return str(Path(state_dir).expanduser().resolve() / "canonical_core" / "core_provenance.sqlite")


class LazyCanonicalCoreControlPort:
    """Live-path port that loads the Core transport only when a task needs it.

    Legacy tasks never call this port, so they never import Core, never put a
    Core checkout on ``sys.path`` and never create the session DB.
    """

    def __init__(self, state_dir: Any):
        self.db_path = live_core_db_path(state_dir)
        self._port: Any = None

    def _delegate(self) -> Any:
        if self._port is None:
            from nexus.orchestrator.canonical_core_transport import (
                CanonicalNexusCoreTransportPort,
            )

            self._port = CanonicalNexusCoreTransportPort(db_path=self.db_path)
        return self._port

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._delegate().open_or_reuse_mutation_binding(**kwargs)

    def revalidate_mutation_binding(self, preparation: Mapping[str, Any], **kwargs: Any) -> None:
        return self._delegate().revalidate_mutation_binding(preparation, **kwargs)

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._delegate().verify_candidate(**kwargs)

    def record_terminal_not_covered(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._delegate().record_terminal_not_covered(**kwargs)
