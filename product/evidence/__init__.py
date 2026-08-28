import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

from product.protocol import EVIDENCE_BUNDLE_SCHEMA


def canonical_json(value):
    active = set()

    def clean(v):
        if v is None or type(v) in (str, int, bool):
            return v
        if type(v) in (tuple, list):
            marker = id(v)
            if marker in active:
                raise ValueError("cyclic canonical value")
            active.add(marker)
            result = [clean(x) for x in v]
            active.remove(marker)
            return result
        if type(v) is dict:
            marker = id(v)
            if marker in active:
                raise ValueError("cyclic canonical value")
            active.add(marker)
            if any(not isinstance(k, str) for k in v):
                raise TypeError("canonical object keys must be strings")
            result = {k: clean(v[k]) for k in sorted(v)}
            active.remove(marker)
            return result
        raise TypeError(f"unsupported canonical value: {type(v).__name__}")

    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


class IntegrityStatus(str, Enum):
    VALID = "VALID"
    SCOPE_ESCAPE = "SCOPE_ESCAPE"
    MISSING = "MISSING"
    STALE = "STALE"
    TAMPERED = "TAMPERED"
    MALFORMED = "MALFORMED"
    CROSS_BOUND = "CROSS_BOUND"
    DUPLICATE = "DUPLICATE"
    LEGACY_NON_CERTIFIABLE = "LEGACY_NON_CERTIFIABLE"
    CROSS_BINDING_INVALID = "CROSS_BOUND"


EvidenceCondition = IntegrityStatus


class ObservationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_text(value, field):
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be non-empty and normalized")


def _require_hash(value, field):
    _require_text(value, field)
    if not _HASH_RE.fullmatch(value):
        raise ValueError(f"{field} must be sha256:<64 lowercase hex>")


def _require_ids(values, field):
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    for value in values:
        _require_text(value, field)
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicates")
    if not values:
        raise ValueError(f"{field} must be non-empty")


def _require_paths(values, field):
    _require_ids(values, field)
    for value in values:
        if (
            value.startswith("/")
            or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError(f"{field} must contain relative paths")


def validate_normalized_paths(values, field="paths"):
    """Validate a normalized tuple of repository-relative POSIX paths."""
    _require_paths(values, field)
    return values


@dataclass(frozen=True)
class AcceptanceContract:
    contract_id: str
    requirements_hash: str
    required_verifier_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    deletion_policy: str

    def __post_init__(self):
        _require_text(self.contract_id, "contract_id")
        _require_hash(self.requirements_hash, "requirements_hash")
        _require_ids(self.required_verifier_ids, "required_verifier_ids")
        _require_paths(self.allowed_paths, "allowed_paths")
        if type(self.deletion_policy) is not str or self.deletion_policy not in {"FORBID", "ALLOW"}:
            raise ValueError("deletion_policy must be FORBID or ALLOW")

    @property
    def hash(self):
        return _hash(
            (
                self.contract_id,
                self.requirements_hash,
                tuple(sorted(self.required_verifier_ids)),
                tuple(sorted(self.allowed_paths)),
                self.deletion_policy,
            )
        )


@dataclass(frozen=True)
class ChangeSet:
    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str
    paths: tuple[str, ...]

    def __post_init__(self):
        _require_text(self.change_set_id, "change_set_id")
        _require_text(self.source_revision, "source_revision")
        _require_text(self.target_revision, "target_revision")
        _require_hash(self.diff_hash, "diff_hash")
        _require_paths(self.paths, "paths")

    @property
    def hash(self):
        return _hash(
            (
                self.change_set_id,
                self.source_revision,
                self.target_revision,
                self.diff_hash,
                tuple(sorted(self.paths)),
            )
        )


@dataclass(frozen=True)
class VerificationPlan:
    plan_id: str
    acceptance_contract_hash: str
    change_set_hash: str
    required_verifier_ids: tuple[str, ...]

    def __post_init__(self):
        _require_text(self.plan_id, "plan_id")
        _require_hash(self.acceptance_contract_hash, "acceptance_contract_hash")
        _require_hash(self.change_set_hash, "change_set_hash")
        _require_ids(self.required_verifier_ids, "required_verifier_ids")

    @property
    def hash(self):
        return _hash(
            (
                self.plan_id,
                self.acceptance_contract_hash,
                self.change_set_hash,
                tuple(sorted(self.required_verifier_ids)),
            )
        )


@dataclass(frozen=True)
class Observation:
    verifier_id: str
    artifact_id: str
    artifact_hash: str
    status: ObservationStatus

    def __post_init__(self):
        _require_text(self.verifier_id, "verifier_id")
        _require_text(self.artifact_id, "artifact_id")
        _require_hash(self.artifact_hash, "artifact_hash")
        if type(self.status) is not ObservationStatus:
            raise TypeError("status must be ObservationStatus")


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    observations: tuple[Observation, ...]
    claimed_bundle_hash: str | None = None

    def __post_init__(self):
        _require_text(self.bundle_id, "bundle_id")
        _require_hash(self.acceptance_contract_hash, "acceptance_contract_hash")
        _require_hash(self.change_set_hash, "change_set_hash")
        _require_hash(self.verification_plan_hash, "verification_plan_hash")
        if type(self.observations) is not tuple or not self.observations:
            raise ValueError("observations must be non-empty tuple")
        if any(type(observation) is not Observation for observation in self.observations):
            raise TypeError("observations must contain Observation values")
        if self.claimed_bundle_hash is not None:
            _require_hash(self.claimed_bundle_hash, "claimed_bundle_hash")

    @property
    def canonical_value(self):
        return (
            self.bundle_id,
            self.acceptance_contract_hash,
            self.change_set_hash,
            self.verification_plan_hash,
            tuple(
                (o.verifier_id, o.artifact_id, o.artifact_hash, o.status.value)
                for o in sorted(self.observations, key=lambda x: (x.verifier_id, x.artifact_id))
            ),
        )

    @property
    def hash(self):
        return _hash(self.canonical_value)

    @property
    def envelope_hash(self):
        """Hash of the native serialized envelope (distinct from ``hash``)."""
        return self.to_dict()["bundle_hash"]

    def integrity(self, contract, change_set, plan):
        if self.claimed_bundle_hash is not None and self.claimed_bundle_hash != self.hash:
            return IntegrityStatus.TAMPERED
        if self.acceptance_contract_hash != contract.hash:
            return IntegrityStatus.CROSS_BOUND
        if self.change_set_hash != change_set.hash:
            return IntegrityStatus.STALE
        if (
            self.verification_plan_hash != plan.hash
            or plan.acceptance_contract_hash != contract.hash
            or plan.change_set_hash != change_set.hash
        ):
            return IntegrityStatus.CROSS_BINDING_INVALID
        verifier_ids = [o.verifier_id for o in self.observations]
        artifact_ids = [o.artifact_id for o in self.observations]
        if len(verifier_ids) != len(set(verifier_ids)) or len(artifact_ids) != len(
            set(artifact_ids)
        ):
            return IntegrityStatus.DUPLICATE
        return IntegrityStatus.VALID

    def to_dict(self):
        body = {
            "evidence_bundle_schema": EVIDENCE_BUNDLE_SCHEMA,
            "bundle_id": self.bundle_id,
            "acceptance_contract_hash": self.acceptance_contract_hash,
            "change_set_hash": self.change_set_hash,
            "verification_plan_hash": self.verification_plan_hash,
            "observations": [
                {
                    "verifier_id": o.verifier_id,
                    "artifact_id": o.artifact_id,
                    "artifact_hash": o.artifact_hash,
                    "status": o.status.value,
                }
                for o in sorted(self.observations, key=lambda x: (x.verifier_id, x.artifact_id))
            ],
        }
        body["bundle_hash"] = _hash(body)
        return body


def validate_evidence_bundle_envelope(
    payload, contract, change_set, plan, *, expected_bundle=None, expected_envelope_hash=None
):
    if (expected_bundle is None) == (expected_envelope_hash is None):
        raise TypeError(
            "exactly one independently supplied expected bundle or envelope hash is required"
        )
    if expected_bundle is not None and type(expected_bundle) is not EvidenceBundle:
        raise TypeError("expected_bundle must be EvidenceBundle")
    if expected_envelope_hash is not None:
        _require_hash(expected_envelope_hash, "expected_envelope_hash")
    if type(contract) is not AcceptanceContract:
        raise TypeError("contract must be AcceptanceContract")
    if type(change_set) is not ChangeSet:
        raise TypeError("change_set must be ChangeSet")
    if type(plan) is not VerificationPlan:
        raise TypeError("plan must be VerificationPlan")
    errors = []
    try:
        if type(payload) is not dict:
            return ("MALFORMED:payload",)
        expected_keys = {
            "evidence_bundle_schema",
            "bundle_id",
            "acceptance_contract_hash",
            "change_set_hash",
            "verification_plan_hash",
            "observations",
            "bundle_hash",
        }
        if set(payload) != expected_keys:
            errors.append("MALFORMED:keys")
        if payload.get("evidence_bundle_schema") != EVIDENCE_BUNDLE_SCHEMA:
            errors.append("STALE:evidence_bundle_schema")
        for field in (
            "bundle_id",
            "acceptance_contract_hash",
            "change_set_hash",
            "verification_plan_hash",
            "bundle_hash",
        ):
            if field not in payload or not isinstance(payload[field], str):
                errors.append(f"MALFORMED:{field}")
        if isinstance(payload.get("bundle_id"), str):
            _require_text(payload["bundle_id"], "bundle_id")
        for field in (
            "acceptance_contract_hash",
            "change_set_hash",
            "verification_plan_hash",
            "bundle_hash",
        ):
            if isinstance(payload.get(field), str):
                _require_hash(payload[field], field)
        observations = payload.get("observations")
        if not isinstance(observations, list) or not observations:
            errors.append("MALFORMED:observations")
        rows = []
        if type(observations) is list:
            for i, row in enumerate(observations):
                if type(row) is not dict or set(row) != {
                    "verifier_id",
                    "artifact_id",
                    "artifact_hash",
                    "status",
                }:
                    errors.append(f"MALFORMED:observations[{i}]")
                    continue
                if not all(
                    isinstance(row.get(k), str)
                    for k in ("verifier_id", "artifact_id", "artifact_hash", "status")
                ):
                    errors.append(f"MALFORMED:observations[{i}]")
                    continue
                if row["status"] not in {"PASS", "FAIL"}:
                    errors.append(f"MALFORMED:observations[{i}].status")
                try:
                    _require_text(row["verifier_id"], "verifier_id")
                    _require_text(row["artifact_id"], "artifact_id")
                    _require_hash(row["artifact_hash"], "artifact_hash")
                except (TypeError, ValueError):
                    errors.append(f"MALFORMED:observations[{i}]")
                rows.append(
                    (row["verifier_id"], row["artifact_id"], row["artifact_hash"], row["status"])
                )
        if len({r[0] for r in rows}) != len(rows) or len({r[1] for r in rows}) != len(rows):
            errors.append("DUPLICATE:observations")
        if rows != sorted(rows, key=lambda r: (r[0], r[1])):
            errors.append("MALFORMED:observation_order")
        body = {k: payload[k] for k in expected_keys - {"bundle_hash"} if k in payload}
        if not errors and payload.get("bundle_hash") != _hash(body):
            errors.append("TAMPERED:bundle_hash")
        if payload.get("acceptance_contract_hash") != contract.hash:
            errors.append("CROSS_BOUND:acceptance_contract_hash")
        if payload.get("change_set_hash") != change_set.hash:
            errors.append("STALE:change_set_hash")
        if (
            payload.get("verification_plan_hash") != plan.hash
            or plan.acceptance_contract_hash != contract.hash
            or plan.change_set_hash != change_set.hash
        ):
            errors.append("CROSS_BINDING_INVALID:verification_plan_hash")
        if not errors:
            if expected_bundle is not None:
                if payload != expected_bundle.to_dict():
                    errors.append("TAMPERED:fields")
            elif payload.get("bundle_hash") != expected_envelope_hash:
                errors.append("TAMPERED:fields")
    except (TypeError, ValueError, RecursionError, OverflowError):
        errors.append("MALFORMED:payload")
    return tuple(dict.fromkeys(errors))


def load_evidence_bundle_envelope(
    payload, contract, change_set, plan, *, expected_bundle=None, expected_envelope_hash=None
):
    errors = validate_evidence_bundle_envelope(
        payload,
        contract,
        change_set,
        plan,
        expected_bundle=expected_bundle,
        expected_envelope_hash=expected_envelope_hash,
    )
    if errors:
        return None
    return EvidenceBundle(
        payload["bundle_id"],
        payload["acceptance_contract_hash"],
        payload["change_set_hash"],
        payload["verification_plan_hash"],
        tuple(
            Observation(
                r["verifier_id"],
                r["artifact_id"],
                r["artifact_hash"],
                ObservationStatus(r["status"]),
            )
            for r in payload["observations"]
        ),
    )
