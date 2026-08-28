import pytest

from product.certification import CertificationDisposition, CertificationPolicy
from product.certification.receipt import Receipt
from product.evidence import IntegrityStatus, _hash
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import reduce_verification


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
