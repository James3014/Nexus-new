import pytest
from nexus.services.local_heal.local_qwen_evidence_gate import (
    verify_local_qwen_evidence,
    audit_evidence_bundle,
)


def _make_valid_row(**overrides):
    base = {
        "provider": "ollama",
        "model_name": "qwen2.5-coder:14b-instruct-q3_K_M",
        "model_calls": 3,
        "provider_token_count": 1200,
        "hidden_verifier": True,
        "deterministic_fallback": False,
        "public_gate_status": "PASS",
        "source_origin": "local",
    }
    base.update(overrides)
    return base


def test_valid_local_qwen_row_passes():
    row = _make_valid_row()
    result = verify_local_qwen_evidence(row)
    assert result.passed
    assert len(result.failures) == 0


def test_provider_not_ollama_fails():
    row = _make_valid_row(provider="gemini")
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("provider_is_ollama" in f for f in result.failures)


def test_model_calls_zero_fails():
    row = _make_valid_row(model_calls=0)
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("model_calls_positive" in f for f in result.failures)


def test_provider_token_zero_fails():
    row = _make_valid_row(provider_token_count=0)
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("provider_token_measured" in f for f in result.failures)


def test_hidden_verifier_false_fails():
    row = _make_valid_row(hidden_verifier=False)
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("hidden_verifier_enabled" in f for f in result.failures)


def test_deterministic_fallback_true_fails():
    row = _make_valid_row(deterministic_fallback=True)
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("no_deterministic_fallback" in f for f in result.failures)


def test_gemini_locked_fails():
    row = _make_valid_row(source_origin="gemini")
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("not_gemini_locked" in f for f in result.failures)


def test_public_gate_fail_marks_non_claim():
    row = _make_valid_row(public_gate_status="FAIL")
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("public_gate_status" in f for f in result.failures)


def test_model_name_empty_fails():
    row = _make_valid_row(model_name="")
    result = verify_local_qwen_evidence(row)
    assert not result.passed
    assert any("model_name_present" in f for f in result.failures)


def test_audit_bundle_all_pass():
    rows = [_make_valid_row() for _ in range(3)]
    report = audit_evidence_bundle(rows)
    assert report["all_passed"]
    assert report["passed"] == 3
    assert report["failed"] == 0


def test_audit_bundle_mixed():
    rows = [
        _make_valid_row(),
        _make_valid_row(model_calls=0),
        _make_valid_row(provider="gemini"),
    ]
    report = audit_evidence_bundle(rows)
    assert not report["all_passed"]
    assert report["passed"] == 1
    assert report["failed"] == 2


def test_audit_bundle_empty():
    report = audit_evidence_bundle([])
    assert report["all_passed"]
    assert report["total_rows"] == 0
