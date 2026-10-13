"""Online A/B gap A (hyper): escalate to Hyper when the first candidate fails verification.

A failed model candidate also fails its claim/delivery gates, which the receipt data
contract reports as ``receipt_data_contract_violation``.  That is the failed-verification
signal Hyper escalation exists for, not harness infra, so it must not block admission.
"""

from __future__ import annotations

from scripts.bench.capability_ab_runner import _hyper_admission_after_model_attempt


def test_hyper_admission_treats_receipt_contract_violation_as_candidate_failure() -> None:
    decision = _hyper_admission_after_model_attempt({
        "status": "FAILED",
        "model_calls": 1,
        "total_tokens": 10,
        "infra_invalid_reason": "receipt_data_contract_violation",
    })
    assert decision.run_hyper is True
    assert decision.reason == "strict_model_attempt_repairable"


def test_hyper_admission_still_refuses_real_infra_and_tokenless_calls() -> None:
    infra = _hyper_admission_after_model_attempt({
        "status": "FAILED",
        "model_calls": 1,
        "total_tokens": 10,
        "infra_invalid_reason": "quota_exhausted",
    })
    assert (infra.run_hyper, infra.reason) == (False, "infra_invalid")
    tokenless = _hyper_admission_after_model_attempt({
        "status": "FAILED",
        "model_calls": 1,
        "total_tokens": 0,
        "infra_invalid_reason": "receipt_data_contract_violation",
    })
    assert (tokenless.run_hyper, tokenless.reason) == (False, "model_call_without_tokens")
