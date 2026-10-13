"""Nightly quarantine entry: tests/benchmark/test_capability_ab_runner.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/benchmark/test_capability_ab_runner.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": (
        "test_h6_0_audit_report_lock",
        "test_h6_1_audit_report_lock",
        "test_h6_2_audit_report_lock",
        "test_h6_3_audit_report_lock",
        "test_h6_4_audit_report_lock",
        "test_h6_5_audit_report_lock",
        "test_h6_6_audit_report_lock",
        "test_nexus_with_local_model_adapter_alone_no_call",
        "test_python_syntax_warning_detects_return_in_finally",
        "test_run_with_nexus_codex_provider_delivers_nexus_context",
    ),
}
