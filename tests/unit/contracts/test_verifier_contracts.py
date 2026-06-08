import pytest
from nexus.engine.contracts.verification import VerificationResult, VerifierType, Verdict

def test_verification_result_schema():
    """驗證契約層的資料結構是否獨立且具備 fail-closed 屬性。"""
    res = VerificationResult(
        verifier_type=VerifierType.SYNTAX,
        verdict=Verdict.HARD_REJECT,
        reason="IndentationError at line 4",
        constraint_for_next_round="Ensure Python indentation is 4 spaces."
    )
    
    assert res.is_passed() is False
    assert res.should_rollback() is True
    
    data = res.to_dict()
    assert data["verifier_type"] == "SYNTAX"
    assert data["verdict"] == "HARD_REJECT"

def test_verification_result_soft_advisory():
    """驗證 Soft Advisory 不會觸發回滾。"""
    res = VerificationResult(
        verifier_type=VerifierType.SEMANTIC,
        verdict=Verdict.SOFT_ADVISORY,
        reason="Variable name 'x' is uninformative.",
        constraint_for_next_round="None"
    )
    
    assert res.is_passed() is True  # Soft advisory allows progress
    assert res.should_rollback() is False
