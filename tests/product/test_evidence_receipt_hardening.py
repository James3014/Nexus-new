from dataclasses import replace

import pytest

from product.certification import CertificationDisposition, CertificationPolicy
from product.certification.receipt import Receipt
from product.evidence import IntegrityStatus, _hash
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import reduce_verification
from product.kernel import CertificationInput, certify, validate_serialized_receipt


def _input(observations=None):
    contract = __import__("product.evidence", fromlist=["AcceptanceContract"]).AcceptanceContract(
        "ac", _hash("requirements"), ("unit",), ("src/a.py",), "FORBID"
    )
    change = __import__("product.evidence", fromlist=["ChangeSet"]).ChangeSet(
        "cs", "base", "head", _hash("diff"), ("src/a.py",)
    )
    plan = __import__("product.evidence", fromlist=["VerificationPlan"]).VerificationPlan(
        "plan", contract.hash, change.hash, ("unit",)
    )
    Observation = __import__("product.evidence", fromlist=["Observation"]).Observation
    ObservationStatus = __import__("product.evidence", fromlist=["ObservationStatus"]).ObservationStatus
    evidence = __import__("product.evidence", fromlist=["EvidenceBundle"]).EvidenceBundle(
        "bundle", contract.hash, change.hash, plan.hash,
        (Observation("unit", "artifact", _hash("artifact"), ObservationStatus.PASS),)
        if observations is None else observations,
    )
    return CertificationInput(contract, change, plan, evidence, True, True, True, True)


def test_canonical_json_is_stable_and_rejects_cycles():
    from product.evidence import canonical_json
    value = {"b": [2, 1], "a": True}
    assert canonical_json(value) == canonical_json({"a": True, "b": [2, 1]})
    value["cycle"] = value
    with pytest.raises(ValueError, match="cyclic"):
        canonical_json(value)


def test_evidence_semantic_and_envelope_hashes_are_distinct():
    evidence = _input().evidence
    assert evidence.hash != evidence.envelope_hash
    assert evidence.to_dict()["bundle_hash"] == evidence.envelope_hash


def test_evidence_expected_bundle_and_hash_round_trip():
    from product.evidence import validate_evidence_bundle_envelope, load_evidence_bundle_envelope
    data = _input()
    payload = data.evidence.to_dict()
    assert validate_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_bundle=data.evidence) == ()
    assert validate_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_envelope_hash=data.evidence.envelope_hash) == ()
    assert load_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_bundle=data.evidence) == data.evidence


@pytest.mark.parametrize("kwargs", [{}, {"expected_bundle": object()}, {"expected_envelope_hash": _hash("x"), "expected_bundle": _input().evidence}])
def test_evidence_requires_exactly_one_typed_trust_root(kwargs):
    from product.evidence import validate_evidence_bundle_envelope
    data = _input()
    if not kwargs:
        with pytest.raises(TypeError, match="exactly one"):
            validate_evidence_bundle_envelope(data.evidence.to_dict(), data.contract, data.change_set, data.plan)
    else:
        with pytest.raises(TypeError):
            validate_evidence_bundle_envelope(data.evidence.to_dict(), data.contract, data.change_set, data.plan, **kwargs)


@pytest.mark.parametrize("field", ["bundle_id", "acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "observations", "bundle_hash"])
def test_evidence_missing_fields_fail_closed(field):
    from product.evidence import validate_evidence_bundle_envelope, load_evidence_bundle_envelope
    data = _input(); payload = data.evidence.to_dict(); payload.pop(field)
    errors = validate_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_bundle=data.evidence)
    assert errors and load_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_bundle=data.evidence) is None


def test_evidence_rehashed_semantic_mutation_is_not_accepted():
    from product.evidence import validate_evidence_bundle_envelope
    data = _input(); payload = data.evidence.to_dict(); payload["bundle_id"] = "other"
    payload["bundle_hash"] = _hash({k: payload[k] for k in payload if k != "bundle_hash"})
    assert validate_evidence_bundle_envelope(payload, data.contract, data.change_set, data.plan, expected_bundle=data.evidence) == ("TAMPERED:fields",)


@pytest.mark.parametrize("bad", [b"bytes", {"set"}, float("nan"), float("inf"), {1: "nonstring"}])
def test_canonical_json_rejects_unsupported_values(bad):
    from product.evidence import canonical_json
    with pytest.raises((TypeError, ValueError)):
        canonical_json(bad)


def test_receipt_repeat_hash_and_serialized_validation():
    result = certify(_input()); receipt = result.receipt
    assert receipt.hash == certify(_input()).receipt.hash
    assert receipt.to_dict()["receipt_hash"] == receipt.hash
    assert validate_serialized_receipt(receipt.to_dict(), _input()) == ()


def test_receipt_self_claim_is_checked_against_semantic_hash():
    result = certify(_input()); receipt = replace(result.receipt, claimed_receipt_hash=result.receipt.hash)
    assert receipt.validate()
    assert not replace(receipt, claimed_receipt_hash=_hash("stale")).validate()


@pytest.mark.parametrize("field", ["acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "evidence_hash"])
def test_receipt_subject_mutations_are_rejected(field):
    data = _input(); result = certify(data); kwargs = {field: _hash("other")}
    candidate = replace(result.receipt, **kwargs)
    assert candidate.hash != result.receipt.hash
    from product.kernel import validate_receipt
    assert not validate_receipt(candidate, data)


@pytest.mark.parametrize("field", ["receipt_schema", "protocol_version", "implementation_schema", "claim_ceiling", "unknown"])
def test_receipt_envelope_schema_mutations_fail(field):
    data = _input(); payload = certify(data).receipt.to_dict()
    payload[field] = "bad" if field != "claim_ceiling" else ["bad"]
    errors = validate_serialized_receipt(payload, data)
    assert errors


def test_receipt_rejects_non_receipt_expected_root():
    from product.certification.receipt import validate_receipt_envelope
    with pytest.raises(TypeError, match="expected_receipt"):
        validate_receipt_envelope({}, object())


@pytest.mark.parametrize("bad", [b"bytes", {"set"}, float("nan"), float("inf"), {1: "bad"}])
def test_receipt_envelope_unsupported_values_fail_closed(bad):
    data = _input(); payload = certify(data).receipt.to_dict(); payload["bad"] = bad
    assert validate_serialized_receipt(payload, data)


def test_certification_result_cannot_forge_disposition():
    data = _input(); result = certify(data)
    from product.certification.receipt import CertificationResult
    with pytest.raises(ValueError):
        CertificationResult(result.verification, CertificationDisposition.BLOCKED, result.receipt)


def test_kernel_reexports_receipt_contract():
    import product.kernel as kernel
    assert kernel.Receipt is Receipt
    assert callable(kernel.validate_receipt_envelope)


def test_receipt_rejects_contradictory_certified_missing_result():
    result = reduce_verification(IntegrityStatus.MISSING)
    with pytest.raises(ValueError, match="disposition must match reducer"):
        Receipt(
            _hash("contract"),
            _hash("change"),
            _hash("plan"),
            _hash("evidence"),
            result,
            CertificationDisposition.CERTIFIED,
            CertificationPolicy(True, True, True, True),
        )

def test_receipt_binds_protocol_and_claim_ceiling():
    result = reduce_verification(IntegrityStatus.MISSING)
    with pytest.raises(ValueError):
        Receipt(
            _hash("contract"), _hash("change"), _hash("plan"), _hash("evidence"),
            result, CertificationDisposition.BLOCKED, CertificationPolicy(),
            claim_ceiling=("OTHER",),
        )
    with pytest.raises(ValueError):
        Receipt(
            _hash("contract"), _hash("change"), _hash("plan"), _hash("evidence"),
            result, CertificationDisposition.BLOCKED, CertificationPolicy(),
            protocol_version="old",
        )
    with pytest.raises(ValueError):
        Receipt(
            _hash("contract"), _hash("change"), _hash("plan"), _hash("evidence"),
            result, CertificationDisposition.BLOCKED, CertificationPolicy(),
            implementation_schema="old",
        )
