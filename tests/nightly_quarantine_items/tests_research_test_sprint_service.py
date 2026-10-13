"""Nightly quarantine entry: tests/research/test_sprint_service.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/research/test_sprint_service.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "fixture Gateway is classified physical, so Workforce Admission blocks the online call and the fake gateway is never reached; needs governed admission fixtures or an owner decision",
    "tests": (
        "test_llm_failure_preserves_gateway_token_source",
        "test_llm_gateway_fail_payload_falls_back_to_local",
        "test_llm_generator_applies_edit_protocol",
        "test_llm_generator_can_route_local_assist_into_online_context",
        "test_llm_generator_uses_unified_runtime_on_revisioned_workspace",
        "test_llm_mode_estimates_tokens_when_gateway_stats_missing",
        "test_llm_model_name_can_be_overridden",
    ),
}
