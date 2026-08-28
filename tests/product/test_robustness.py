import ast
from pathlib import Path

import pytest

from product.certification import CertificationDisposition, CertificationPolicy, certify_result
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    Observation,
    ObservationStatus,
    VerificationPlan,
    _hash,
)
from product.kernel import CertificationInput, certify
from product.verification import VerificationResult, VerificationStatus

H = _hash("fixture")


def valid_case(verifiers=("unit", "security"), observations=None):
    contract = AcceptanceContract("ac", H, verifiers, ("src/a.py",), "FORBID")
    change = ChangeSet("cs", "source", "target", H, ("src/a.py",))
    plan = VerificationPlan("plan", contract.hash, change.hash, verifiers)
    observations = observations or tuple(
        Observation(v, f"artifact-{v}", H, ObservationStatus.PASS) for v in verifiers
    )
    evidence = EvidenceBundle("bundle", contract.hash, change.hash, plan.hash, observations)
    return CertificationInput(contract, change, plan, evidence, True, True, True, True)


def test_duplicate_artifact_across_verifiers_is_order_independent_unverifiable():
    one = Observation("unit", "same", H, ObservationStatus.PASS)
    two = Observation("security", "same", H, ObservationStatus.PASS)
    for observations in ((one, two), (two, one)):
        result = certify(valid_case(observations=observations))
        assert result.verification.status is VerificationStatus.UNVERIFIABLE
        assert result.disposition is CertificationDisposition.BLOCKED


@pytest.mark.parametrize("field", ["requirements_hash", "diff_hash", "artifact_hash"])
def test_core_hash_fields_require_sha256_digest(field):
    kwargs = {field: "SHA256:BAD"}
    with pytest.raises(ValueError):
        if field == "requirements_hash":
            AcceptanceContract("ac", kwargs[field], ("unit",), ("src/a.py",), "FORBID")
        elif field == "diff_hash":
            ChangeSet("cs", "a", "b", kwargs[field], ("src/a.py",))
        else:
            Observation("unit", "artifact", kwargs[field], ObservationStatus.PASS)


def test_plan_contract_and_evidence_verifier_sets_must_match():
    valid = valid_case(verifiers=("unit",))
    contract = AcceptanceContract("ac", H, ("unit", "security"), ("src/a.py",), "FORBID")
    plan = VerificationPlan("plan", contract.hash, valid.change_set.hash, ("unit", "security"))
    evidence = EvidenceBundle(
        "bundle",
        contract.hash,
        valid.change_set.hash,
        plan.hash,
        (Observation("unit", "artifact", H, ObservationStatus.PASS),),
    )
    result = certify(
        CertificationInput(contract, valid.change_set, plan, evidence, True, True, True, True)
    )
    assert result.verification.status is VerificationStatus.UNVERIFIABLE


def test_invalid_enum_values_cannot_reach_certification():
    with pytest.raises(TypeError):
        Observation("unit", "artifact", H, "PASS")
    with pytest.raises(TypeError):
        VerificationResult("FAILED_VERIFICATION")
    forged = object.__new__(VerificationResult)
    object.__setattr__(forged, "status", "VERIFIED")
    object.__setattr__(forged, "integrity", object())
    assert (
        certify_result(forged, CertificationPolicy(True, True, True, True))
        is CertificationDisposition.BLOCKED
    )


def test_dag_gate_rejects_relative_imports():
    node = ast.parse("from ..execution import ExecutionRequest").body[0]
    assert isinstance(node, ast.ImportFrom)
    assert node.level > 0


def test_poetry_packages_include_product_without_version_change():
    text = (Path(__file__).parents[2] / "pyproject.toml").read_text()
    assert '{include = "product"}' in text
    assert 'version = "28.3.0"' in text
