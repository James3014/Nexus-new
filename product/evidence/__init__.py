import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum


def canonical_json(value):
    def clean(v):
        if isinstance(v, (str, int, bool)) or v is None:
            return v
        if isinstance(v, (tuple, list)):
            return [clean(x) for x in v]
        if isinstance(v, dict):
            if any(not isinstance(k, str) for k in v):
                raise TypeError("canonical object keys must be strings")
            return {str(k): clean(v[k]) for k in sorted(v)}
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
    if not isinstance(value, str):
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
        if self.deletion_policy not in {"FORBID", "ALLOW"}:
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
        if not isinstance(self.status, ObservationStatus):
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
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("observations must be non-empty tuple")
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

    def integrity(self, contract, change_set, plan):
        if self.claimed_bundle_hash is not None and self.claimed_bundle_hash != self.hash:
            return IntegrityStatus.TAMPERED
        if (
            self.acceptance_contract_hash != contract.hash
            or
            self.change_set_hash != change_set.hash
            or self.verification_plan_hash != plan.hash
            or plan.acceptance_contract_hash != contract.hash
            or plan.change_set_hash != change_set.hash
        ):
            return IntegrityStatus.CROSS_BINDING_INVALID
        verifier_ids = [o.verifier_id for o in self.observations]
        artifact_ids = [o.artifact_id for o in self.observations]
        if len(verifier_ids) != len(set(verifier_ids)) or len(artifact_ids) != len(set(artifact_ids)):
            return IntegrityStatus.DUPLICATE
        return IntegrityStatus.VALID
