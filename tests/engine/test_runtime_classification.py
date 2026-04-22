from nexus.engine.runtime_classification import classify_semantic


def test_classify_verified_returns_verified_pass():
    assert classify_semantic("VERIFIED", retryable=False, blocker_type="none") == "verified_pass"


def test_classify_blocked_returns_governance_state_block():
    assert classify_semantic("BLOCKED", retryable=False, blocker_type="none") == "governance_state_block"


def test_classify_governance_blocker_returns_governance_state_block():
    assert classify_semantic("unverified", retryable=True, blocker_type="governance") == "governance_state_block"


def test_classify_unverified_retryable_returns_runtime_defect():
    assert classify_semantic("UNVERIFIED", retryable=True, blocker_type="runtime_defect") == "runtime_defect"


def test_classify_rejected_returns_hallucination_rejected():
    assert classify_semantic("rejected", retryable=False, blocker_type="semantic_incomplete") == "hallucination_rejected"


def test_classify_unverified_non_retryable_falls_back_runtime_defect():
    assert classify_semantic("Unverified", retryable=False, blocker_type="semantic_incomplete") == "runtime_defect"
