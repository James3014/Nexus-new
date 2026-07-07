"""
C6AY: Diagnosis-guided candidate generation.
Verifies D-phase diagnosis root_cause is injected into candidate generation prompt,
and fail-closed when diagnosis is absent/empty/malformed.
"""
import hashlib
import inspect
import pytest


# ─── Phase 2.1: diagnosis_result exists → prompt contains diagnosis text ───

def test_diagnosis_guidance_injected_when_root_cause_present():
    from nexus.services.local_heal.local_model_executor import _inject_diagnosis_guidance
    base = "Fix the bug in table.py"
    diag = {"root_cause": "Missing None check in iter_rows", "confidence": 0.8, "model": "deepseek", "status": "success"}
    updated, injected, guid_hash = _inject_diagnosis_guidance(base, diag)
    assert injected is True
    assert "Committee Diagnosis: Missing None check in iter_rows" in updated
    assert "Use this diagnosis to prioritize the most likely faulty logic/location." in updated
    assert guid_hash == hashlib.sha256("Missing None check in iter_rows".encode()).hexdigest()[:16]
    # Original prompt preserved
    assert updated.startswith(base)


# ─── Phase 2.2: diagnosis_result absent → old behavior unchanged ───

def test_diagnosis_guidance_not_injected_when_result_none():
    from nexus.services.local_heal.local_model_executor import _inject_diagnosis_guidance
    base = "Fix the bug in table.py"
    updated, injected, guid_hash = _inject_diagnosis_guidance(base, None)
    assert injected is False
    assert guid_hash == ""
    assert updated == base  # unchanged


# ─── Phase 2.3: fail-closed — empty/malformed diagnosis does not pollute prompt ───

@pytest.mark.parametrize("diag", [
    {"root_cause": "", "confidence": 0.5, "status": "parsed_failed"},
    {"root_cause": "   ", "confidence": 0.3},
    {"confidence": 0.5},  # missing root_cause key
    {"root_cause": None},
    {},
    "not_a_dict",
    42,
])
def test_diagnosis_guidance_fail_closed_on_malformed(diag):
    from nexus.services.local_heal.local_model_executor import _inject_diagnosis_guidance
    base = "Fix the bug in table.py"
    updated, injected, guid_hash = _inject_diagnosis_guidance(base, diag)
    assert injected is False
    assert guid_hash == ""
    assert "Committee Diagnosis" not in updated
    assert updated == base  # no pollution


# ─── Phase 2.4: wiring — _run_impl calls helper + records telemetry ───

def test_run_impl_wires_diagnosis_guidance_and_telemetry():
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor
    source = inspect.getsource(LocalModelExecutor._run_impl)
    assert "_inject_diagnosis_guidance" in source, "C6AY helper not called in _run_impl"
    assert "diagnosis_guidance_injected" in source, "telemetry field missing"
    assert "diagnosis_guidance_hash" in source, "hash telemetry missing"
    # Verify injection happens BEFORE candidate generation
    inject_pos = source.index("_inject_diagnosis_guidance")
    gen_pos = source.index("generate_committee_candidates")
    assert inject_pos < gen_pos, "diagnosis guidance must be injected BEFORE candidate generation"
