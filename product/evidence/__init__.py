from dataclasses import dataclass
import hashlib
import json
from enum import Enum


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical_json(value: object) -> str:
    """Return the one deterministic JSON representation used for hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class IntegrityStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    CROSS_BINDING_INVALID = "CROSS_BINDING_INVALID"
    TAMPERED = "TAMPERED"
    SCOPE_ESCAPE = "SCOPE_ESCAPE"


@dataclass(frozen=True)
class AcceptanceContract:
    contract_id: str
    required_observations: tuple[str, ...]
    allowed_paths: tuple[str, ...] = ()

    @property
    def hash(self) -> str:
        return _hash({"contract_id": self.contract_id, "required_observations": self.required_observations, "allowed_paths": self.allowed_paths})


@dataclass(frozen=True)
class ChangeSet:
    change_id: str
    paths: tuple[str, ...]
    content_hash: str

    @property
    def hash(self) -> str:
        return _hash({"change_id": self.change_id, "paths": self.paths, "content_hash": self.content_hash})


@dataclass(frozen=True)
class VerificationPlan:
    plan_id: str
    required_checks: tuple[str, ...]
    change_set_hash: str

    @property
    def hash(self) -> str:
        return _hash({"plan_id": self.plan_id, "required_checks": self.required_checks, "change_set_hash": self.change_set_hash})


@dataclass(frozen=True)
class Observation:
    check_id: str
    status: str
    scope_escaped: bool = False


@dataclass(frozen=True)
class EvidenceBundle:
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    observations: tuple[Observation, ...]
    evidence_hash: str | None = None
    bundle_id: str = "bundle-1"

    @property
    def hash(self) -> str:
        value = {"bundle_id": self.bundle_id, "acceptance_contract_hash": self.acceptance_contract_hash, "change_set_hash": self.change_set_hash, "verification_plan_hash": self.verification_plan_hash, "observations": tuple((o.check_id, o.status, o.scope_escaped) for o in self.observations)}
        return _hash(value)

    @property
    def canonical_json(self) -> str:
        return canonical_json({"bundle_id": self.bundle_id, "acceptance_contract_hash": self.acceptance_contract_hash, "change_set_hash": self.change_set_hash, "verification_plan_hash": self.verification_plan_hash, "observations": tuple((o.check_id, o.status, o.scope_escaped) for o in self.observations)})

    def integrity(self, contract: AcceptanceContract, change_set: ChangeSet, plan: VerificationPlan) -> IntegrityStatus:
        if self.evidence_hash is not None and self.evidence_hash != self.hash:
            return IntegrityStatus.TAMPERED
        if self.acceptance_contract_hash != contract.hash or self.change_set_hash != change_set.hash or self.verification_plan_hash != plan.hash or plan.change_set_hash != change_set.hash:
            return IntegrityStatus.CROSS_BINDING_INVALID
        if any(o.scope_escaped for o in self.observations):
            return IntegrityStatus.SCOPE_ESCAPE
        if not self.observations:
            return IntegrityStatus.MISSING
        return IntegrityStatus.VALID


__all__ = ["AcceptanceContract", "ChangeSet", "VerificationPlan", "Observation", "EvidenceBundle", "IntegrityStatus", "canonical_json"]
