from dataclasses import dataclass
from math import isfinite

from product.certification import CertificationDisposition, CertificationPolicy, certify_result
from product.evidence import _hash, _require_hash
from product.protocol import CERTIFICATION_RECEIPT_SCHEMA, IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import VerificationResult, is_reduced_result

CLAIM_CEILING = ("NO_MERGE_AUTHORIZATION", "NO_DEPLOYMENT_TRUTH", "NO_OUTCOME_TRUTH", "NO_PRODUCTION_READINESS", "NO_PUBLIC_PROTOCOL_STABILITY")
_VERIFICATION_STATUSES = {"VERIFIED", "FAILED_VERIFICATION", "UNVERIFIABLE"}
_INTEGRITY_STATUSES = {"VALID", "SCOPE_ESCAPE", "MISSING", "STALE", "TAMPERED", "MALFORMED", "CROSS_BOUND", "DUPLICATE", "LEGACY_NON_CERTIFIABLE"}


def _strict_json(value, active=None):
    if active is None: active = set()
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not isfinite(value): raise ValueError("non-finite value")
        return
    if type(value) in (list, tuple, dict):
        marker = id(value)
        if marker in active: raise ValueError("cyclic value")
        active.add(marker)
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str: raise TypeError("object keys must be strings")
                _strict_json(item, active)
        else:
            for item in value: _strict_json(item, active)
        active.remove(marker)
        return
    raise TypeError("unsupported value")


def _policy_valid(policy):
    return type(policy) is CertificationPolicy and all(
        value is None or type(value) is bool
        for value in (policy.accepted, policy.authority_present, policy.approval_present, policy.signing_present)
    )


@dataclass(frozen=True)
class Receipt:
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    evidence_hash: str
    verification: VerificationResult
    disposition: CertificationDisposition
    policy: CertificationPolicy
    claim_ceiling: tuple[str, ...] = CLAIM_CEILING
    protocol_version: str = PUBLIC_PROTOCOL_VERSION
    implementation_schema: str = IMPLEMENTATION_SCHEMA
    claimed_receipt_hash: str | None = None

    def __post_init__(self):
        for field in ("acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "evidence_hash"):
            _require_hash(getattr(self, field), field)
        if type(self.verification) is not VerificationResult or not is_reduced_result(self.verification):
            raise TypeError("verification must be reducer-produced VerificationResult")
        if type(self.disposition) is not CertificationDisposition:
            raise TypeError("disposition must be CertificationDisposition")
        if not _policy_valid(self.policy): raise TypeError("policy fields must be bool or None")
        if self.claim_ceiling != CLAIM_CEILING: raise ValueError("claim_ceiling must equal CLAIM_CEILING")
        if self.protocol_version != PUBLIC_PROTOCOL_VERSION: raise ValueError("protocol_version must equal PUBLIC_PROTOCOL_VERSION")
        if self.implementation_schema != IMPLEMENTATION_SCHEMA: raise ValueError("implementation_schema must equal IMPLEMENTATION_SCHEMA")
        if certify_result(self.verification, self.policy) is not self.disposition:
            raise ValueError("disposition must match reducer")
        if self.claimed_receipt_hash is not None:
            _require_hash(self.claimed_receipt_hash, "claimed_receipt_hash")

    @property
    def canonical_value(self):
        return {"receipt_schema": CERTIFICATION_RECEIPT_SCHEMA, "protocol_version": self.protocol_version, "implementation_schema": self.implementation_schema, "acceptance_contract_hash": self.acceptance_contract_hash, "change_set_hash": self.change_set_hash, "verification_plan_hash": self.verification_plan_hash, "evidence_hash": self.evidence_hash, "verification": {"status": self.verification.status.value, "condition": self.verification.integrity.value, "reason_codes": list(self.verification.reason_codes)}, "certification": {"disposition": self.disposition.value, "policy": {"accepted": self.policy.accepted, "authority_present": self.policy.authority_present, "approval_present": self.policy.approval_present, "signing_present": self.policy.signing_present}}, "claim_ceiling": list(self.claim_ceiling)}

    @property
    def hash(self): return _hash(self.canonical_value)
    def to_dict(self): return {**self.canonical_value, "receipt_hash": self.hash}
    def validate(self): return self.claimed_receipt_hash is None or self.claimed_receipt_hash == self.hash


@dataclass(frozen=True)
class CertificationResult:
    verification: VerificationResult
    disposition: CertificationDisposition
    receipt: Receipt

    def __post_init__(self):
        if type(self.verification) is not VerificationResult or not is_reduced_result(self.verification):
            raise TypeError("verification must be reducer-produced VerificationResult")
        if type(self.disposition) is not CertificationDisposition or type(self.receipt) is not Receipt:
            raise TypeError("invalid certification result types")
        if self.receipt.verification != self.verification or self.receipt.disposition != self.disposition:
            raise ValueError("certification result must match receipt")
        if certify_result(self.verification, self.receipt.policy) is not self.disposition:
            raise ValueError("disposition must match reducer")


def validate_receipt_envelope(payload, expected_receipt):
    if type(expected_receipt) is not Receipt:
        raise TypeError("expected_receipt must be Receipt")
    if type(payload) is not dict:
        return ("MALFORMED:payload",)
    errors = []
    try:
        _strict_json(payload)
        keys = set(expected_receipt.to_dict())
        if set(payload) != keys: errors.append("MALFORMED:keys")
        if isinstance(payload.get("receipt_hash"), str):
            try:
                _require_hash(payload["receipt_hash"], "receipt_hash")
                body = {key: payload[key] for key in payload if key != "receipt_hash"}
                if payload["receipt_hash"] != _hash(body): errors.append("TAMPERED:receipt_hash")
            except (TypeError, ValueError): errors.append("TAMPERED:receipt_hash")
        if payload.get("receipt_schema") != CERTIFICATION_RECEIPT_SCHEMA: errors.append("STALE:receipt_schema")
        if payload.get("protocol_version") != PUBLIC_PROTOCOL_VERSION: errors.append("STALE:protocol_version")
        if payload.get("implementation_schema") != IMPLEMENTATION_SCHEMA: errors.append("STALE:implementation_schema")
        for field in ("acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "evidence_hash", "receipt_hash"):
            if not isinstance(payload.get(field), str): errors.append(f"MALFORMED:{field}")
            elif field != "receipt_hash":
                try: _require_hash(payload[field], field)
                except (TypeError, ValueError): errors.append(f"MALFORMED:{field}")
        verification = payload.get("verification")
        if not isinstance(verification, dict) or set(verification) != {"status", "condition", "reason_codes"}: errors.append("MALFORMED:verification")
        elif (verification.get("status") not in _VERIFICATION_STATUSES or verification.get("condition") not in _INTEGRITY_STATUSES or not isinstance(verification.get("reason_codes"), list) or any(type(code) is not str for code in verification["reason_codes"]) or verification["reason_codes"] != sorted(set(verification["reason_codes"]))): errors.append("MALFORMED:verification")
        certification = payload.get("certification")
        if not isinstance(certification, dict) or set(certification) != {"disposition", "policy"}: errors.append("MALFORMED:certification")
        else:
            if certification.get("disposition") not in {item.value for item in CertificationDisposition}: errors.append("MALFORMED:disposition")
            policy = certification.get("policy")
            if not isinstance(policy, dict) or set(policy) != {"accepted", "authority_present", "approval_present", "signing_present"} or any(value is not None and type(value) is not bool for value in (policy.values() if isinstance(policy, dict) else ())): errors.append("MALFORMED:policy")
        if payload.get("claim_ceiling") != list(CLAIM_CEILING): errors.append("MALFORMED:claim_ceiling")
        if not errors and payload != expected_receipt.to_dict(): errors.append("TAMPERED:fields")
        return tuple(dict.fromkeys(errors))
    except (TypeError, ValueError, RecursionError, OverflowError): return ("MALFORMED:payload",)
