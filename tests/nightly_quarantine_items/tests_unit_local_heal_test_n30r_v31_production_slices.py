"""Nightly quarantine entry: tests/unit/local_heal/test_n30r_v31_production_slices.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_n30r_v31_production_slices.py",
    "disposition": "quarantine",
    "issue": "#1924",
    # Slice A and C were mock drift (fixed #1924). Slice B is a real product gap: a LITE candidate that fails
    # verification inside the pipeline yields no canonical patch (World C receipt invalid), so the executor
    # escalates LITE->STANDARD but never gets isolated verifier evidence and cannot retry.
    "cause": "product gap: LITE->STANDARD escalation is recorded but the verifier-driven retry is unreachable (semantic_retry_evidence_not_ready) once the pipeline rejects the wrong patch",
    "tests": ("test_slice_b_lite_to_standard_recovery",),
}
