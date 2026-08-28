from dataclasses import dataclass
from math import isfinite

from product.evidence import _hash, _require_hash
_certification_types = __import__("product.certification", fromlist=("CertificationDisposition", "CertificationPolicy"))
CertificationDisposition = _certification_types.CertificationDisposition
CertificationPolicy = _certification_types.CertificationPolicy
from product.verification import is_reduced_result
from product.protocol import CERTIFICATION_RECEIPT_SCHEMA, IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import VerificationResult

CLAIM_CEILING = ("NO_MERGE_AUTHORIZATION", "NO_DEPLOYMENT_TRUTH", "NO_OUTCOME_TRUTH", "NO_PRODUCTION_READINESS", "NO_PUBLIC_PROTOCOL_STABILITY")

def _strict_json(value, active=None):
    if active is None: active = set()
    if value is None or type(value) in (str, bool, int): return
    if type(value) is float:
        if not isfinite(value): raise ValueError("non-finite value")
        return
    if isinstance(value, (list, tuple, dict)):
        marker = id(value)
        if marker in active: raise ValueError("cyclic value")
        active.add(marker)
        if isinstance(value, dict):
            for key, item in value.items():
                if type(key) is not str: raise TypeError("object keys must be strings")
                _strict_json(item, active)
        else:
            for item in value: _strict_json(item, active)
        active.remove(marker)
        return
    raise TypeError("unsupported value")

@dataclass(frozen=True)
class Receipt:
    acceptance_contract_hash: str; change_set_hash: str; verification_plan_hash: str; evidence_hash: str
    verification: VerificationResult; disposition: CertificationDisposition; policy: CertificationPolicy
    claim_ceiling: tuple[str, ...] = CLAIM_CEILING
    protocol_version: str = PUBLIC_PROTOCOL_VERSION; implementation_schema: str = IMPLEMENTATION_SCHEMA
    claimed_receipt_hash: str | None = None
    def __post_init__(self):
        for f in ("acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "evidence_hash"):
            _require_hash(getattr(self, f), f)
        if not isinstance(self.verification, VerificationResult) or not is_reduced_result(self.verification):
            raise TypeError("verification must be reducer-produced VerificationResult")
        if not isinstance(self.disposition, CertificationDisposition):
            raise TypeError("disposition must be CertificationDisposition")
        if not isinstance(self.policy, CertificationPolicy) or any(
            value is not None and type(value) is not bool
            for value in (self.policy.accepted, self.policy.authority_present, self.policy.approval_present, self.policy.signing_present)
        ):
            raise TypeError("policy fields must be bool or None")
        if self.claimed_receipt_hash is not None:
            _require_hash(self.claimed_receipt_hash, "claimed_receipt_hash")
    @property
    def canonical_value(self):
        return {"receipt_schema":CERTIFICATION_RECEIPT_SCHEMA,"protocol_version":self.protocol_version,"implementation_schema":self.implementation_schema,"acceptance_contract_hash":self.acceptance_contract_hash,"change_set_hash":self.change_set_hash,"verification_plan_hash":self.verification_plan_hash,"evidence_hash":self.evidence_hash,"verification":{"status":self.verification.status.value,"condition":self.verification.integrity.value,"reason_codes":list(self.verification.reason_codes)},"certification":{"disposition":self.disposition.value,"policy":{"accepted":self.policy.accepted,"authority_present":self.policy.authority_present,"approval_present":self.policy.approval_present,"signing_present":self.policy.signing_present}},"claim_ceiling":list(self.claim_ceiling)}
    @property
    def hash(self): return _hash(self.canonical_value)
    def to_dict(self):
        return {"receipt_schema":CERTIFICATION_RECEIPT_SCHEMA,"protocol_version":self.protocol_version,"implementation_schema":self.implementation_schema,"acceptance_contract_hash":self.acceptance_contract_hash,"change_set_hash":self.change_set_hash,"verification_plan_hash":self.verification_plan_hash,"evidence_hash":self.evidence_hash,"verification":{"status":self.verification.status.value,"condition":self.verification.integrity.value,"reason_codes":list(self.verification.reason_codes)},"certification":{"disposition":self.disposition.value,"policy":{"accepted":self.policy.accepted,"authority_present":self.policy.authority_present,"approval_present":self.policy.approval_present,"signing_present":self.policy.signing_present}},"claim_ceiling":list(self.claim_ceiling),"receipt_hash":self.hash}
    def validate(self): return self.claimed_receipt_hash is None or self.claimed_receipt_hash == self.hash

@dataclass(frozen=True)
class CertificationResult:
    verification: VerificationResult
    disposition: CertificationDisposition
    receipt: Receipt

    def __post_init__(self):
        if not isinstance(self.verification, VerificationResult) or not is_reduced_result(self.verification):
            raise TypeError("verification must be reducer-produced VerificationResult")
        if not isinstance(self.disposition, CertificationDisposition) or not isinstance(self.receipt, Receipt):
            raise TypeError("invalid certification result types")

def validate_receipt_envelope(payload, expected_receipt):
    try:
        if not isinstance(payload, dict): return ("MALFORMED:payload",)
        _strict_json(payload)
        keys={"receipt_schema","protocol_version","implementation_schema","acceptance_contract_hash","change_set_hash","verification_plan_hash","evidence_hash","verification","certification","claim_ceiling","receipt_hash"}
        errors=[]
        if set(payload)!=keys: errors.append("MALFORMED:keys")
        # Check the envelope's own canonical hash first.  A changed semantic
        # field with a stale hash is a hash failure, while a rehashed envelope
        # is reported as a semantic mismatch below.
        if not errors and isinstance(payload.get("receipt_hash"), str):
            try:
                _require_hash(payload["receipt_hash"], "receipt_hash")
                canonical = {k: payload[k] for k in payload if k != "receipt_hash"}
                if payload["receipt_hash"] != _hash(canonical): errors.append("TAMPERED:receipt_hash")
            except (TypeError, ValueError, RecursionError, OverflowError):
                errors.append("TAMPERED:receipt_hash")
        if payload.get("receipt_schema")!=CERTIFICATION_RECEIPT_SCHEMA: errors.append("STALE:receipt_schema")
        for f in ("protocol_version","implementation_schema","acceptance_contract_hash","change_set_hash","verification_plan_hash","evidence_hash","receipt_hash"):
            if not isinstance(payload.get(f),str): errors.append(f"MALFORMED:{f}")
        for f in ("acceptance_contract_hash","change_set_hash","verification_plan_hash","evidence_hash","receipt_hash"):
            if isinstance(payload.get(f),str): _require_hash(payload[f],f)
        v=payload.get("verification"); c=payload.get("certification")
        if not isinstance(v,dict) or set(v)!={"status","condition","reason_codes"}: errors.append("MALFORMED:verification")
        elif (v.get("status") not in {"VERIFIED","FAILED_VERIFICATION","UNVERIFIABLE"} or v.get("condition") not in {"VALID","SCOPE_ESCAPE","MISSING","STALE","TAMPERED","MALFORMED","CROSS_BOUND","DUPLICATE","LEGACY_NON_CERTIFIABLE"} or not isinstance(v.get("reason_codes"),list) or any(not isinstance(x,str) for x in v["reason_codes"]) or v["reason_codes"] != sorted(set(v["reason_codes"]))): errors.append("MALFORMED:verification")
        if not isinstance(c,dict) or set(c)!={"disposition","policy"}: errors.append("MALFORMED:certification")
        if isinstance(c,dict) and (not isinstance(c.get("policy"),dict) or set(c.get("policy",{}))!={"accepted","authority_present","approval_present","signing_present"}): errors.append("MALFORMED:policy")
        if isinstance(c,dict) and c.get("disposition") not in {"CERTIFIED","REJECTED","BLOCKED"}: errors.append("MALFORMED:disposition")
        if isinstance(c,dict) and isinstance(c.get("policy"),dict) and any(x is not None and not isinstance(x,bool) for x in c["policy"].values()): errors.append("MALFORMED:policy")
        if not isinstance(payload.get("claim_ceiling"),list) or any(not isinstance(x,str) for x in payload.get("claim_ceiling",[])): errors.append("MALFORMED:claim_ceiling")
        if not errors and payload != expected_receipt.to_dict(): errors.append("TAMPERED:fields")
        return tuple(dict.fromkeys(errors))
    except (TypeError,ValueError,RecursionError,OverflowError): return ("MALFORMED:payload",)
