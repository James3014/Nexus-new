import hashlib
import json
from dataclasses import dataclass
from enum import Enum


def canonical_json(value):
    def clean(v):
        if isinstance(v, (str, int, bool)) or v is None:
            return v
        if isinstance(v, (tuple, list)):
            return [clean(x) for x in v]
        if isinstance(v, dict):
            return {str(k): clean(v[k]) for k in sorted(v)}
        raise TypeError(f"unsupported canonical value: {type(v).__name__}")

    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


class IntegrityStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    CROSS_BINDING_INVALID = "CROSS_BINDING_INVALID"
    TAMPERED = "TAMPERED"
    SCOPE_ESCAPE = "SCOPE_ESCAPE"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class AcceptanceContract:
    contract_id: str
    requirements_hash: str
    required_verifier_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    deletion_policy: str

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
    status: str


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    observations: tuple[Observation, ...]
    claimed_bundle_hash: str | None = None

    @property
    def canonical_value(self):
        return (
            self.bundle_id,
            self.acceptance_contract_hash,
            self.change_set_hash,
            self.verification_plan_hash,
            tuple(
                (o.verifier_id, o.artifact_id, o.artifact_hash, o.status)
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
            or self.change_set_hash != change_set.hash
            or self.verification_plan_hash != plan.hash
            or plan.acceptance_contract_hash != contract.hash
            or plan.change_set_hash != change_set.hash
        ):
            return IntegrityStatus.CROSS_BINDING_INVALID
        keys = [(o.verifier_id, o.artifact_id) for o in self.observations]
        if len(keys) != len(set(keys)):
            return IntegrityStatus.DUPLICATE
        if set(change_set.paths) - set(contract.allowed_paths):
            return IntegrityStatus.SCOPE_ESCAPE
        return IntegrityStatus.VALID if self.observations else IntegrityStatus.MISSING
