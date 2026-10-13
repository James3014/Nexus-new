"""Nightly quarantine entry: tests/unit/test_pipeline.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_pipeline.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_pipeline_apology_patch_response_records_model_refusal",
        "test_pipeline_empty_patch_response_records_model_empty_response",
        "test_pipeline_hidden_verifier_required_fails_closed",
        "test_pipeline_localize_query_includes_plan_symbols_and_evidence",
        "test_pipeline_passes_phase_timeouts_to_model_calls",
        "test_pipeline_provider_exception_records_model_provider_error",
        "test_pipeline_records_tsp_model_decisions_for_astropy",
        "test_pipeline_retries_reproduction_after_env_denoise",
        "test_pipeline_retry_exhaustion_records_latest_patch_error",
        "test_pipeline_successful_flow",
        "test_pipeline_timeout_patch_response_records_model_timeout",
        "test_pipeline_uses_env_resolved_python_for_visible_verification",
    ),
}
